"""Stateful policy adapter and a server-side chat-completions implementation."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any, Literal, Protocol

import httpx

from .config import Settings
from .models import Action, TaskSpec, canonical, digest

SYSTEM = """You are a coding agent in a controlled Linux workspace. Solve the user's task.
Return one JSON object matching the action schema. Tools: shell (command), read_file
(path), write_file (path, content), finish (no arguments). Unused fields must be empty
strings or omitted. Work only under /workspace. There is no network. Dependencies are
preinstalled in the image. Every shell call starts fresh: only workspace files persist;
processes, /tmp, shell variables, and current directory do not. Use relative paths.
Inspect the repository, make changes, run its tests, then finish. Do not modify tests
to hide a failure. Do not include commentary outside the JSON object.
"""


class Policy(Protocol):
    def identity(self) -> dict[str, Any]: ...
    def initial(self, task: TaskSpec) -> dict[str, Any]: ...
    def propose(
        self, state: dict[str, Any], step: int, seed: int
    ) -> tuple[Action, dict[str, Any]]: ...
    def observe(
        self, state: dict[str, Any], action: Action, result: dict[str, Any]
    ) -> dict[str, Any]: ...


ModelCallCode = Literal[
    "response_unavailable",
    "invalid_response",
    "invalid_usage",
    "invalid_usage_cost",
    "usage_exceeds_reservation",
    "invalid_action",
]
PublicationStage = Literal["run", "study"]


class ModelCallFailure(RuntimeError):
    """A terminal paid-call failure; safe evidence never implies a refunded hold."""

    def __init__(
        self,
        code: ModelCallCode,
        reserved_micro_usd: int,
        *,
        usage: dict[str, int] | None = None,
        reported_micro_usd: int | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.reserved_micro_usd = reserved_micro_usd
        self.usage = dict(usage) if usage is not None else None
        self.reported_micro_usd = reported_micro_usd
        self.publication_failures: list[PublicationStage] = []

    def publication_failed(self, stage: PublicationStage) -> None:
        if stage not in self.publication_failures:
            self.publication_failures.append(stage)

    def evidence(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reserved_micro_usd": self.reserved_micro_usd,
            "usage": dict(self.usage) if self.usage is not None else None,
            "reported_micro_usd": self.reported_micro_usd,
            "publication_failures": list(self.publication_failures),
        }


def _prices(settings: Settings) -> tuple[float, float]:
    prices = settings.model_input_price, settings.model_output_price
    if any(not math.isfinite(price) or price <= 0 for price in prices):
        raise ValueError("Configure positive finite model prices in dollars per million tokens.")
    return prices


class ChatPolicy:
    def __init__(self, settings: Settings, reserve: Callable[[int], None]):
        if not settings.model_url or not settings.model_name or not settings.model_api_key:
            raise ValueError("Configure the model URL, name, and worker API key.")
        _prices(settings)
        self.settings = settings
        self.reserve = reserve

    def identity(self) -> dict[str, Any]:
        return {
            "adapter": "chat-completions-v1",
            "model": self.settings.model_name,
            "endpoint": self.settings.model_url,
            "prompt_digest": digest(SYSTEM),
            "seed_supported": self.settings.model_seed_supported,
            "max_output_tokens": self.settings.model_max_output_tokens,
            "max_input_tokens": self.settings.model_max_input_tokens,
            "reasoning_effort": self.settings.model_reasoning_effort,
            "input_price": self.settings.model_input_price,
            "output_price": self.settings.model_output_price,
        }

    def initial(self, task: TaskSpec) -> dict[str, Any]:
        return {
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM + "\nSchema: " + json.dumps(Action.model_json_schema()),
                },
                {
                    "role": "user",
                    "content": task.instruction
                    + "\nWorkspace files:\n"
                    + "\n".join(sorted(task.files)),
                },
            ]
        }

    def propose(self, state: dict[str, Any], step: int, seed: int) -> tuple[Action, dict[str, Any]]:
        # Snapshot mutable configuration before either reservation or dispatch.
        input_price, output_price = _prices(self.settings)
        body: dict[str, Any] = {
            "model": self.settings.model_name,
            "messages": state["messages"],
            "max_completion_tokens": self.settings.model_max_output_tokens,
            "response_format": {"type": "json_object"},
            "store": False,
        }
        if self.settings.model_seed_supported:
            body["seed"] = (seed + step) % (2**31 - 1)
        if self.settings.model_reasoning_effort:
            body["reasoning_effort"] = self.settings.model_reasoning_effort
        # Conservative allowance: one input token per serialized UTF-8 byte plus
        # protocol overhead. Reservations remain consumed on ambiguous failures.
        upper_input = len(canonical(body)) + 4096
        if upper_input > self.settings.model_max_input_tokens:
            raise ValueError("Model input exceeds the configured conservative token bound.")
        reserve = math.ceil(
            upper_input * input_price + self.settings.model_max_output_tokens * output_price
        )
        self.reserve(reserve)
        key = self.settings.model_api_key
        if key is None:
            raise ValueError("Model API key is not configured.")
        try:
            with httpx.Client(
                timeout=self.settings.model_timeout_seconds, follow_redirects=False
            ) as client:
                response = client.post(
                    self.settings.model_url,
                    json=body,
                    headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError, RecursionError):
            # Provider exception bodies may contain private request/response data.
            raise ModelCallFailure("response_unavailable", reserve) from None
        if type(data) is not dict:
            raise ModelCallFailure("invalid_response", reserve)
        usage = data.get("usage")
        if type(usage) is not dict or any(
            type(usage.get(name)) is not int or usage[name] < 0
            for name in ("prompt_tokens", "completion_tokens")
        ):
            raise ModelCallFailure("invalid_usage", reserve)
        counts = {name: usage[name] for name in ("prompt_tokens", "completion_tokens")}
        if "total_tokens" in usage and (
            type(usage["total_tokens"]) is not int or usage["total_tokens"] != sum(counts.values())
        ):
            raise ModelCallFailure("invalid_usage", reserve)
        # These documented counters are overlapping views, not extra billable tokens:
        # https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
        for detail_name, aggregate, counters in (
            (
                "prompt_tokens_details",
                "prompt_tokens",
                (
                    "audio_tokens",
                    "cache_write_tokens",
                    "cached_tokens",
                    "image_tokens",
                    "text_tokens",
                ),
            ),
            (
                "completion_tokens_details",
                "completion_tokens",
                (
                    "accepted_prediction_tokens",
                    "audio_tokens",
                    "reasoning_tokens",
                    "rejected_prediction_tokens",
                    "text_tokens",
                ),
            ),
        ):
            if detail_name not in usage:
                continue
            details = usage[detail_name]
            if type(details) is not dict or any(
                name in details
                and (type(details[name]) is not int or not 0 <= details[name] <= counts[aggregate])
                for name in counters
            ):
                raise ModelCallFailure("invalid_usage", reserve)
        try:
            cost = (
                counts["prompt_tokens"] * input_price + counts["completion_tokens"] * output_price
            )
            if not math.isfinite(cost):
                raise ValueError("Nonfinite cost")
            actual = math.ceil(cost)
        except (OverflowError, ValueError):
            raise ModelCallFailure("invalid_usage_cost", reserve, usage=counts) from None
        if actual > reserve:
            raise ModelCallFailure(
                "usage_exceeds_reservation", reserve, usage=counts, reported_micro_usd=actual
            )
        try:
            content = data["choices"][0]["message"]["content"]
            action = Action.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError):
            # Valid billing does not make an unusable response safe to continue.
            raise ModelCallFailure(
                "invalid_action", reserve, usage=counts, reported_micro_usd=actual
            ) from None
        return action, {
            "response": data,
            "reserved_micro_usd": reserve,
            "reported_micro_usd": actual,
            "step": step,
            "trial_seed": seed,
        }

    def observe(
        self, state: dict[str, Any], action: Action, result: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "messages": state["messages"]
            + [
                {"role": "assistant", "content": canonical(action.model_dump()).decode()},
                {"role": "user", "content": "Tool observation:\n" + canonical(result).decode()},
            ]
        }
