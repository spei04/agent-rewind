"""Strict immutable operator ledger intent; no database authority or activation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .schema import MigrationRefused, canonical

MAX_MANIFEST_BYTES = 32768
MAX_MONEY = 2**63 - 1
MAX_DEPTH = 8
Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
InstallationKey = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]
Money = Annotated[int, Field(ge=0, le=MAX_MONEY)]
Time = Annotated[
    str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$")
]


class LedgerValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def validate_time(value: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value):
        raise ValueError("noncanonical time")
    datetime.fromisoformat(value[:-1] + "+00:00")
    return value


def validate_json_value(value: object, *, depth: int = 0) -> None:
    """Retain exact native JSON types and reject controls before model validation."""
    if value is None or type(value) is bool or type(value) is int:
        return
    if type(value) is str:
        if any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
            raise ValueError("control or surrogate")
        return
    if type(value) is list:
        if depth >= MAX_DEPTH:
            raise ValueError("nested value exceeds limit")
        for child in value:
            validate_json_value(child, depth=depth + 1)
        return
    if type(value) is dict:
        if depth >= MAX_DEPTH:
            raise ValueError("nested value exceeds limit")
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError("nonstring member")
            validate_json_value(key, depth=depth)
            validate_json_value(child, depth=depth + 1)
        return
    raise ValueError("non-JSON value")


def immutable_array(value: object) -> tuple[object, ...]:
    if type(value) is not list:
        raise ValueError("expected JSON array")
    return tuple(value)


class LedgerAccount(LedgerValue):
    id: Identifier
    organization_id: Identifier
    scope: Literal["organization", "project", "job"]
    scope_id: Identifier
    project_id: Identifier | None
    job_id: Identifier | None
    period_start: Time
    period_end: Time
    limit_microusd: Money

    _times = field_validator("period_start", "period_end")(validate_time)

    @model_validator(mode="after")
    def identity_and_period(self) -> LedgerAccount:
        if self.period_start >= self.period_end:
            raise ValueError("empty period")
        if self.scope == "organization":
            valid = (
                self.scope_id == self.organization_id
                and self.project_id is None
                and self.job_id is None
            )
        elif self.scope == "project":
            valid = (
                self.project_id is not None
                and self.scope_id == self.project_id
                and self.job_id is None
            )
        else:
            valid = (
                self.project_id is not None
                and self.job_id is not None
                and self.scope_id == self.job_id
            )
        if not valid:
            raise ValueError("scope shape")
        return self


class OpeningProject(LedgerValue):
    project_id: Identifier
    account_id: Identifier


class OpeningAccounts(LedgerValue):
    organization_account_id: Identifier | None
    projects: Annotated[tuple[OpeningProject, ...], Field(max_length=16)]

    _projects = field_validator("projects", mode="before")(immutable_array)

    @model_validator(mode="after")
    def ordered(self) -> OpeningAccounts:
        ids = [project.project_id for project in self.projects]
        if ids != sorted(set(ids)):
            raise ValueError("project order")
        return self


class LedgerManifest(LedgerValue):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    installation_key: InstallationKey
    manifest_id: Identifier
    operation: Literal["initialize", "provision"]
    source_digest: Digest
    parent_manifest_digest: Digest | None
    backup_evidence_digest: Digest
    drain_evidence_digest: Digest
    accounts: Annotated[tuple[LedgerAccount, ...], Field(max_length=64)]
    opening_accounts: OpeningAccounts | None

    _accounts = field_validator("accounts", mode="before")(immutable_array)

    @model_validator(mode="after")
    def associations(self) -> LedgerManifest:
        ids = [account.id for account in self.accounts]
        if ids != sorted(set(ids)):
            raise ValueError("account order")
        organizations = {account.organization_id for account in self.accounts}
        projects = {
            account.project_id for account in self.accounts if account.project_id is not None
        }
        jobs = [account.job_id for account in self.accounts if account.job_id is not None]
        if (
            len(organizations) > 1
            or len(projects) > 16
            or len(jobs) > 48
            or len(jobs) != len(set(jobs))
        ):
            raise ValueError("scope capacity or identity")
        scopes: dict[tuple[str, str], list[LedgerAccount]] = {}
        for account in self.accounts:
            scopes.setdefault((account.scope, account.scope_id), []).append(account)
        for accounts in scopes.values():
            ordered = sorted(accounts, key=lambda account: account.period_start)
            if any(
                left.period_end > right.period_start
                for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError("overlapping period")
        if self.operation == "provision":
            if (
                not self.accounts
                or self.parent_manifest_digest is None
                or self.opening_accounts is not None
            ):
                raise ValueError("provision bindings")
        else:
            if self.parent_manifest_digest is not None or self.opening_accounts is None:
                raise ValueError("initialize bindings")
            opening = self.opening_accounts
            if not self.accounts:
                if opening.organization_account_id is not None or opening.projects:
                    raise ValueError("empty opening")
            else:
                by_id = {account.id: account for account in self.accounts}
                organization = by_id.get(opening.organization_account_id or "")
                if organization is None or organization.scope != "organization":
                    raise ValueError("opening organization")
                job_projects = {
                    account.project_id for account in self.accounts if account.scope == "job"
                }
                if {project.project_id for project in opening.projects} != job_projects:
                    raise ValueError("opening project coverage")
                for project in opening.projects:
                    selected = by_id.get(project.account_id)
                    if (
                        selected is None
                        or selected.scope != "project"
                        or selected.project_id != project.project_id
                        or selected.period_start != organization.period_start
                        or selected.period_end != organization.period_end
                    ):
                        raise ValueError("opening project binding")
        if len(self.canonical_bytes) > MAX_MANIFEST_BYTES:
            raise ValueError("manifest size")
        return self

    @property
    def canonical_bytes(self) -> bytes:
        return canonical(self.model_dump(mode="json"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def validate_ledger_manifest(value: object) -> LedgerManifest:
    try:
        validate_json_value(value)
        return LedgerManifest.model_validate(value)
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise MigrationRefused("invalid_ledger_manifest") from None


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate member")
        result[key] = value
    return result


def _integer(numeric_lexeme: str) -> int:
    if numeric_lexeme == "-0":
        raise ValueError("negative zero")
    return int(numeric_lexeme)


def _not_integer(token: str) -> int:
    raise ValueError("noninteger token")


def decode_ledger_json(raw: bytes, *, maximum: int) -> object:
    """Lexical proof shared by manifest files and bounded durable cursor bytes."""
    if len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("size or BOM")
    # Keep raw limits above; only JSON's four legal outer whitespace bytes
    # are irrelevant to lexical validation. Quoted/internal content is untouched.
    source = raw.decode("utf-8").strip(" \t\r\n")
    depth = 0
    quoted = escaped = False
    for character in source:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError("nested token limit")
        elif character in "]}":
            depth -= 1
    value: object = json.loads(
        source,
        object_pairs_hook=_unique_members,
        parse_int=_integer,
        parse_float=_not_integer,
        parse_constant=_not_integer,
    )
    validate_json_value(value)
    return value


def read_ledger_manifest(path: Path) -> LedgerManifest:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or not stat.S_IMODE(info.st_mode) & 0o400
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size > MAX_MANIFEST_BYTES
            ):
                raise ValueError("unsafe input")
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
        value = decode_ledger_json(raw, maximum=MAX_MANIFEST_BYTES)
    except (OSError, ValueError, TypeError, RecursionError):
        raise MigrationRefused("invalid_ledger_manifest_file") from None
    return validate_ledger_manifest(value)
