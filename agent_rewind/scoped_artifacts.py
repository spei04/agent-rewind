"""Structural handoff to the separately reviewed artifact metadata/storage slice."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.engine import Connection


class ArtifactObject(Protocol):
    """A resolved descriptor is metadata, never a permanent access capability."""

    @property
    def id(self) -> str: ...
    @property
    def project_id(self) -> str: ...
    @property
    def digest(self) -> str: ...
    @property
    def locator(self) -> str: ...
    @property
    def format_version(self) -> int: ...
    @property
    def byte_count(self) -> int: ...
    @property
    def created_at(self) -> datetime: ...


class ArtifactResolver(Protocol):
    def __call__(
        self,
        connection: Connection,
        *,
        project_id: str,
        owner_kind: str,
        owner_id: str,
        role: str,
        digest: str,
    ) -> ArtifactObject | None:
        """SQL only: require the published owner/role/object/project reference."""
        ...


class ArtifactLoader(Protocol):
    def __call__(self, value: ArtifactObject) -> bytes:
        """Validate format, locator, byte bound, encryption and plaintext digest."""
        ...
