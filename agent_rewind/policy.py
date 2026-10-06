"""Stateful policy adapter and a server-side chat-completions implementation."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any, Protocol

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


class ChatPolicy:
    def __init__(self, settings: Settings, reserve: Callable[[int], None]):
        if not settings.model_url or not settings.model_name or not settings.model_api_key:
            raise ValueError("Configure the model URL, name, and worker API key.")
        if settings.model_input_price <= 0 or settings.model_output_price <= 0:
            raise ValueError("Configure positive model prices in dollars per million tokens.")
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
            upper_input * self.settings.model_input_price
            + self.settings.model_max_output_tokens * self.settings.model_output_price
        )
        self.reserve(reserve)
        key = self.settings.model_api_key
        assert key is not None
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
        except (httpx.HTTPError, ValueError) as exc:
            # Provider bodies and request headers can contain sensitive payloads.
            raise RuntimeError(
                "Model request failed; reservation retained. Check provider service status."
            ) from exc
        try:
            content = data["choices"][0]["message"]["content"]
            action = Action.model_validate_json(content)
            usage = data.get("usage", {})
            actual = math.ceil(
                usage.get("prompt_tokens", 0) * self.settings.model_input_price
                + usage.get("completion_tokens", 0) * self.settings.model_output_price
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Model returned an invalid action or usage record.") from exc
        if actual > reserve:
            raise RuntimeError(
                "Provider usage exceeded the reserved bound; review pricing before continuing."
            )
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
