from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

JSON = dict[str, Any]
SCHEMA_VERSION = 1


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def valid_path(path: str) -> str:
    parts = PurePosixPath(path)
    if (
        not path
        or len(path) > 512
        or parts.is_absolute()
        or ".." in parts.parts
        or "\\" in path
        or "\x00" in path
        or str(parts) != path
        or path == "."
    ):
        raise ValueError("Workspace paths must be normalized relative paths.")
    return path


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Action(StrictModel):
    tool: Literal["shell", "read_file", "write_file", "finish"]
    command: str = Field(default="", max_length=16000)
    path: str = Field(default="", max_length=512)
    content: str = Field(default="", max_length=100000)

    @model_validator(mode="after")
    def check(self) -> Action:
        if self.tool == "shell" and (not self.command.strip() or self.path or self.content):
            raise ValueError("shell requires only a command.")
        if self.tool in {"read_file", "write_file"}:
            valid_path(self.path)
            if self.command or (self.tool == "read_file" and self.content):
                raise ValueError("Unexpected arguments for file tool.")
        if self.tool == "finish" and (self.command or self.path or self.content):
            raise ValueError("finish takes no arguments.")
        return self


class TaskSpec(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=20000)
    image: str = Field(min_length=1, max_length=300)
    files: dict[str, str]
    evaluator_files: dict[str, str]
    evaluator_command: str = Field(min_length=1, max_length=4000)
    max_steps: int = Field(default=30, ge=1, le=100)
    command_timeout: int = Field(default=30, ge=1, le=120)
    redact_patterns: list[str] = Field(default_factory=list, max_length=16)
    budget_usd: float = Field(default=10.0, gt=0, le=200)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def check_files(self) -> TaskSpec:
        if len(self.files) + len(self.evaluator_files) > 2000:
            raise ValueError("Too many initial files.")
        for files in (self.files, self.evaluator_files):
            for path in files:
                valid_path(path)
        if set(self.files) & set(self.evaluator_files):
            raise ValueError("Evaluator files cannot overlap source files.")
        if len(canonical(self.model_dump())) > 8 * 1024 * 1024:
            raise ValueError("Task manifest exceeds 8 MiB.")
        if any(len(p) > 120 for p in self.redact_patterns):
            raise ValueError("Redaction patterns must be at most 120 characters.")
        return self


class Intervention(StrictModel):
    step: int = Field(ge=1, le=100)
    kind: Literal["action", "tool_result"]
    action: Action | None = None
    result: JSON | None = None
    label: str = Field(default="Manual intervention", max_length=160)

    @model_validator(mode="after")
    def check_kind(self) -> Intervention:
        if self.kind == "action" and (self.action is None or self.result is not None):
            raise ValueError("Action interventions require only an action.")
        if self.kind == "tool_result" and (self.result is None or self.action is not None):
            raise ValueError("Observation interventions require only a result.")
        if self.result is not None and len(canonical(self.result)) > 100000:
            raise ValueError("Observation is too large.")
        return self


class BranchRequest(StrictModel):
    parent_id: str
    intervention: Intervention
    seed: int = Field(default=1, ge=0, le=2**31 - 1)
    budget_usd: float = Field(default=10.0, gt=0, le=200)


class StudyRequest(StrictModel):
    run_id: str
    candidates: list[Intervention] = Field(min_length=1, max_length=8)
    screening_trials: int = Field(default=8, ge=2, le=50)
    confirmation_trials: int = Field(default=30, ge=5, le=200)
    seed: int = Field(default=42, ge=0, le=2**31 - 100201)
    budget_usd: float = Field(default=200.0, gt=0, le=200)

    @model_validator(mode="after")
    def unique_candidates(self) -> StudyRequest:
        values = [digest(c.model_dump(exclude={"label"})) for c in self.candidates]
        if len(set(values)) != len(values):
            raise ValueError("Duplicate candidates.")
        return self
