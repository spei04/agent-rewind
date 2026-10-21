"""Pure native-run intent preparation; no authorization, storage or admission.

The HTTP/raw parsing ceiling is 9 MiB. The 8 MiB semantic ceiling applies to
the complete materialized TaskSpec, not its SubmitRun wrapper. Prepared values
are evidence for the later coordinator, never permission or committed state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, NoReturn

from .models import TaskSpec, canonical

MAX_BODY_BYTES = 9 * 1024 * 1024
MAX_TASK_BYTES = 8 * 1024 * 1024
MAX_CONFIG_BYTES = 64 * 1024
_ID = re.compile(r"[0-9a-f]{32}")
_ESCAPED = re.compile(r'["\\]|[^\x20-\x7e]')
_SHORT_ESCAPES = frozenset('"\\\b\f\n\r\t')
_REQUIRED_TASK = frozenset(
    {"name", "instruction", "image", "files", "evaluator_files", "evaluator_command"}
)
_DEFAULT_TASK = {"max_steps": 30, "command_timeout": 30, "redact_patterns": []}
_SUBMIT_FIELDS = frozenset(
    {"client_operation_id", "adapter_config_id", "task", "seed", "budget_microusd"}
)
PreparationCode = Literal[
    "admission_invalid_input",
    "admission_body_limit",
    "admission_task_limit",
    "admission_configuration_invalid",
    "admission_configuration_unavailable",
    "admission_configuration_limit",
    "admission_binding_invalid",
]


class AdmissionPreparationError(ValueError):
    """An allowlisted preparation code, with no input or exception text."""

    def __init__(self, code: PreparationCode):
        self.code = code
        super().__init__(code)


def _invalid() -> NoReturn:
    raise AdmissionPreparationError("admission_invalid_input") from None


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _integer(value: str) -> int:
    # No supported request/config integer needs more than a signed 64-bit value.
    if len(value.lstrip("-")) > 19:
        _invalid()
    return int(value)


def _number(value: str) -> Any:
    # The wire schemas have only integer numeric fields, including prices.
    _invalid()


def decode_object(raw: bytes, *, limit: int, limit_code: PreparationCode) -> dict[str, Any]:
    """Bound raw bytes before decoding; reject duplicate members and noninteger numbers."""
    if type(raw) is not bytes:
        _invalid()
    if len(raw) > limit:
        raise AdmissionPreparationError(limit_code)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_integer,
            parse_float=_number,
            parse_constant=_number,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _invalid()
    if not isinstance(value, dict):
        _invalid()
    return value


def bounded_canonical(value: Any, *, limit: int, limit_code: PreparationCode) -> bytes:
    """Measure the existing canonical encoding before allocating its output.

    String escaping matches models.canonical's ASCII JSON encoding. This avoids
    first allocating a potentially expanded Unicode string to discover overflow.
    """
    total = 0

    def add(size: int) -> None:
        nonlocal total
        total += size
        if total > limit:
            raise AdmissionPreparationError(limit_code)

    def measure(item: Any) -> None:
        if isinstance(item, str):
            add(len(item) + 2)
            for match in _ESCAPED.finditer(item):
                char = match[0]
                point = ord(char)
                if 0xD800 <= point <= 0xDFFF:
                    _invalid()
                add(1 if char in _SHORT_ESCAPES else 5 if point <= 0xFFFF else 11)
        elif isinstance(item, dict):
            add(2 + max(0, len(item) - 1))
            for key, child in item.items():
                if not isinstance(key, str):
                    _invalid()
                measure(key)
                add(1)
                measure(child)
        elif isinstance(item, list):
            add(2 + max(0, len(item) - 1))
            for child in item:
                measure(child)
        elif item is None or type(item) in (int, float, bool):
            add(len(canonical(item)))
        else:
            _invalid()

    try:
        measure(value)
        encoded = canonical(value)
    except AdmissionPreparationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _invalid()
    if len(encoded) != total:
        _invalid()
    return encoded


@dataclass(frozen=True, init=False)
class CanonicalIntent:
    """Detached client identity and legacy task bytes, validated at construction."""

    client_operation_id: str
    adapter_config_id: Literal["native-v1"]
    seed: int
    budget_microusd: int
    canonical_bytes: bytes
    task_bytes: bytes

    def __init__(self, raw: bytes):
        value = decode_object(raw, limit=MAX_BODY_BYTES, limit_code="admission_body_limit")
        if (
            set(value) != _SUBMIT_FIELDS
            or not isinstance(value["client_operation_id"], str)
            or _ID.fullmatch(value["client_operation_id"]) is None
            or value["adapter_config_id"] != "native-v1"
            or type(value["seed"]) is not int
            or not 0 <= value["seed"] <= 2**31 - 1
            or type(value["budget_microusd"]) is not int
            or not 1 <= value["budget_microusd"] <= 200_000_000
        ):
            _invalid()
        task = value["task"]
        if (
            not isinstance(task, dict)
            or not task.keys() >= _REQUIRED_TASK
            or not task.keys() <= _REQUIRED_TASK | _DEFAULT_TASK.keys()
        ):
            _invalid()
        budget = value["budget_microusd"] / 1_000_000
        if round(budget * 1_000_000) != value["budget_microusd"]:
            _invalid()
        materialized = {
            **_DEFAULT_TASK,
            **task,
            "seed": value["seed"],
            "budget_usd": budget,
        }
        task_bytes = bounded_canonical(
            materialized, limit=MAX_TASK_BYTES, limit_code="admission_task_limit"
        )
        try:
            validated = TaskSpec.model_validate(materialized)
        except (ValueError, TypeError, RecursionError):
            _invalid()
        if canonical(validated.model_dump()) != task_bytes:
            _invalid()
        definition = validated.model_dump(exclude={"seed", "budget_usd"})
        body = {**value, "task": definition}
        # Valid fixed SubmitRun fields add only a small wrapper to the <=8 MiB
        # TaskSpec. This is an allocation guard, not a new 8 MiB intent limit.
        encoded = bounded_canonical(body, limit=MAX_BODY_BYTES, limit_code="admission_body_limit")
        object.__setattr__(self, "client_operation_id", value["client_operation_id"])
        object.__setattr__(self, "adapter_config_id", "native-v1")
        object.__setattr__(self, "seed", value["seed"])
        object.__setattr__(self, "budget_microusd", value["budget_microusd"])
        object.__setattr__(self, "canonical_bytes", encoded)
        object.__setattr__(self, "task_bytes", task_bytes)

    @property
    def request_digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def task_digest(self) -> str:
        return hashlib.sha256(self.task_bytes).hexdigest()


def parse_submit(raw: bytes) -> CanonicalIntent:
    return CanonicalIntent(raw)
