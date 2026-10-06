"""Authenticated encryption and content-addressed local/S3 artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import boto3
from cryptography.fernet import Fernet

from .config import Settings
from .models import canonical, valid_path
from .workspace import File


class Artifacts:
    def __init__(self, settings: Settings):
        self.cipher = Fernet(settings.encryption_key.get_secret_value().encode())
        self.root = settings.data_dir / "objects"
        self.bucket = settings.s3_bucket
        self.s3 = None
        if settings.storage == "s3":
            self.s3 = boto3.client(
                "s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region
            )
        else:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        ciphertext = self.cipher.encrypt(data)
        if self.s3:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=f"objects/{key}",
                Body=ciphertext,
                ContentType="application/octet-stream",
            )
        else:
            path = self.root / key
            if not path.exists():
                fd, temporary = tempfile.mkstemp(dir=self.root)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(ciphertext)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
        return key

    def get(self, key: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("Invalid artifact identifier.")
        if self.s3:
            response = self.s3.get_object(Bucket=self.bucket, Key=f"objects/{key}")
            ciphertext = response["Body"].read()
        else:
            ciphertext = (self.root / key).read_bytes()
        data = self.cipher.decrypt(ciphertext)
        if hashlib.sha256(data).hexdigest() != key:
            raise ValueError("Artifact integrity check failed.")
        return data

    def put_json(self, value: Any) -> str:
        return self.put(canonical(value))

    def json(self, key: str) -> Any:
        return json.loads(self.get(key))

    def put_workspace(self, files: dict[str, File]) -> str:
        return self.put_json(
            {
                "schema": 1,
                "files": {
                    valid_path(path): {
                        "blob": self.put(file.data),
                        "mode": file.mode,
                        "kind": file.kind,
                        "mtime": file.mtime,
                    }
                    for path, file in sorted(files.items())
                },
            }
        )

    def workspace(self, key: str, limit: int) -> dict[str, File]:
        tree = self.json(key)
        if tree.get("schema") != 1 or len(tree["files"]) > 10000:
            raise ValueError("Unsupported workspace snapshot.")
        files = {}
        total = 0
        for path, entry in tree["files"].items():
            valid_path(path)
            data = self.get(entry["blob"])
            total += len(data)
            if total > limit:
                raise ValueError("Workspace exceeds its byte limit.")
            files[path] = File(data, entry["mode"] & 0o777, entry["kind"], entry["mtime"])
        return files
