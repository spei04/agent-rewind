"""Installed system sentinel; never a customer-object lookup interface."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import BinaryIO, Literal, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .bounded_bytes import decrypt_checked, read_ciphertext, regular_reader

CONFIG_NAME = "readiness.json"


def canonical_payload(installation_key: str) -> bytes:
    return json.dumps(
        {"schema": 1, "purpose": "readiness", "installation_key": installation_key},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


class SentinelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    installation_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    locator: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def fixed_identity(self) -> SentinelConfig:
        if self.locator != f"system/{self.installation_key}/readiness-v1":
            raise ValueError("sentinel_locator_invalid")
        if self.digest != hashlib.sha256(canonical_payload(self.installation_key)).hexdigest():
            raise ValueError("sentinel_digest_invalid")
        return self


class SentinelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REWIND_", env_file=".env", extra="ignore")
    data_dir: Path = Path(".rewind")
    storage: Literal["local", "s3"] = "local"
    encryption_key: SecretStr
    installation_key: SecretStr | None = None
    s3_bucket: str = ""
    s3_endpoint: str | None = None
    s3_region: str = "us-east-1"


@contextmanager
def directory(root: Path, parts: tuple[str, ...] = (), *, create: bool = False) -> Iterator[int]:
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def load_config(root: Path) -> SentinelConfig:
    with directory(root) as parent:
        descriptor = os.open(
            CONFIG_NAME, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_size > 4096
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                raise ValueError("sentinel_config_invalid")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                content = stream.read(4097)
            if len(content) > 4096:
                raise ValueError("sentinel_config_invalid")
        finally:
            os.close(descriptor)
    return SentinelConfig.model_validate_json(content)


class _Store:
    def __init__(self, settings: SentinelSettings):
        self.settings = settings
        self.cipher = Fernet(settings.encryption_key.get_secret_value().encode())
        self.client = None
        if settings.storage == "s3":
            if not settings.s3_bucket:
                raise ValueError("sentinel_bucket_required")
            self.client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                region_name=settings.s3_region,
                config=Config(
                    connect_timeout=0.5, read_timeout=0.5, retries={"total_max_attempts": 1}
                ),
            )

    def read(self, config: SentinelConfig) -> bytes:
        if self.client is None:
            with (
                directory(self.settings.data_dir, ("system", config.installation_key)) as parent,
                regular_reader("readiness-v1", dir_fd=parent) as stream,
            ):
                ciphertext = read_ciphertext(stream)
        else:
            response = self.client.get_object(
                Bucket=self.settings.s3_bucket, Key=config.locator, Range="bytes=0-5560"
            )
            body = response["Body"]
            try:
                ciphertext = read_ciphertext(cast(BinaryIO, body))
                length = response.get("ContentLength")
                content_range = response.get("ContentRange")
                if length != len(ciphertext):
                    raise ValueError("sentinel_length_invalid")
                if content_range is not None and content_range != (
                    f"bytes 0-{len(ciphertext) - 1}/{len(ciphertext)}"
                ):
                    raise ValueError("sentinel_range_invalid")
            finally:
                body.close()
        plaintext = decrypt_checked(ciphertext, self.cipher, config.digest)
        if plaintext != canonical_payload(config.installation_key):
            raise ValueError("sentinel_payload_invalid")
        return plaintext

    def write_once(self, config: SentinelConfig) -> None:
        ciphertext = self.cipher.encrypt(canonical_payload(config.installation_key))
        if self.client is None:
            with directory(
                self.settings.data_dir, ("system", config.installation_key), create=True
            ) as parent:
                temporary = ".sentinel-" + secrets.token_hex(16)
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent,
                )
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(ciphertext)
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        # Publish the complete inode without replacing an existing
                        # sentinel. A crash before publication leaves only private
                        # temporary bytes, never a partial authoritative object.
                        os.link(
                            temporary,
                            "readiness-v1",
                            src_dir_fd=parent,
                            dst_dir_fd=parent,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        self.read(config)
                    os.fsync(parent)
                finally:
                    os.unlink(temporary, dir_fd=parent)
        else:
            try:
                self.client.put_object(
                    Bucket=self.settings.s3_bucket,
                    Key=config.locator,
                    Body=ciphertext,
                    ContentType="application/octet-stream",
                    IfNoneMatch="*",
                )
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") not in {"PreconditionFailed", "412"}:
                    raise
        self.read(config)


def read_system_sentinel(
    settings: SentinelSettings, deadline: float, *, installation_key: str
) -> bytes:
    """Invoke only inside the supervised transport's interruptible deadline."""
    if time.monotonic() >= deadline:
        raise TimeoutError("sentinel_deadline")
    config = load_config(settings.data_dir)
    if not installation_key or config.installation_key != installation_key:
        raise ValueError("sentinel_installation_mismatch")
    result = _Store(settings).read(config)
    if time.monotonic() >= deadline:
        raise TimeoutError("sentinel_deadline")
    return result


def provision(settings: SentinelSettings) -> None:
    if settings.installation_key is None:
        raise ValueError("installation_key_required")
    key = settings.installation_key.get_secret_value()
    config = SentinelConfig(
        installation_key=key,
        locator=f"system/{key}/readiness-v1",
        digest=hashlib.sha256(canonical_payload(key)).hexdigest(),
    )
    _Store(settings).write_once(config)
    # Only this explicit command replaces config, after verified object publication.
    with directory(settings.data_dir, create=True) as parent:
        temporary = ".readiness-" + secrets.token_hex(16)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(config.model_dump_json().encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, CONFIG_NAME, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent)
