"""Explicit fresh ownership intent; never a replacement for legacy adoption intent."""

import json
import os
import stat
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError

from .inputs import Grant, Identifier, InstallationKey, StrictInput, _unique_object
from .schema import MigrationRefused, canonical

MAX_FRESH_FILE_BYTES = 65536
MAX_FRESH_INTENT_BYTES = 49152


class FreshOwnership(StrictInput):
    schema_version: Literal[1]
    installation_key: InstallationKey
    organization_id: Identifier
    project_id: Identifier
    project_name: Annotated[str, Field(min_length=1, max_length=120)]
    principal_grants: Annotated[list[Grant], Field(min_length=1, max_length=256)]


def validate_fresh(value: Any) -> FreshOwnership:
    try:
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
            raise ValueError("invalid version")
        parsed = FreshOwnership.model_validate(value)
        principals = [grant.principal_id for grant in parsed.principal_grants]
        if (
            len(set(principals)) != len(principals)
            or any(not p.startswith("oidc:") for p in principals)
            or not parsed.project_name.isprintable()
            or not parsed.project_name.strip()
            or len(canonical(parsed.model_dump())) > MAX_FRESH_INTENT_BYTES
        ):
            raise ValueError("invalid intent")
        return parsed
    except (ValueError, TypeError, ValidationError):
        raise MigrationRefused("invalid_fresh_ownership_intent") from None


def read_fresh(path: Path) -> FreshOwnership:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size > MAX_FRESH_FILE_BYTES
            ):
                raise ValueError("unsafe input")
            content = handle.read(MAX_FRESH_FILE_BYTES + 1)
        if len(content) > MAX_FRESH_FILE_BYTES:
            raise ValueError("oversize input")
        return validate_fresh(json.loads(content, object_pairs_hook=_unique_object))
    except (OSError, ValueError, RecursionError):
        raise MigrationRefused("invalid_fresh_ownership_file") from None
