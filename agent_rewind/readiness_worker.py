"""Private probe subprocess. Stdout is a finite protocol, never a diagnostic sink."""

from __future__ import annotations

import ctypes
import logging
import os
import resource
import signal
import sys
import time


def _parent_guard(expected_parent: int) -> None:
    if sys.platform != "linux":
        raise RuntimeError("unsupported_probe_platform")
    # Install before reading configuration/importing clients. The parent-PID check
    # closes the race where the parent exited before PR_SET_PDEATHSIG was set.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != expected_parent:
        raise RuntimeError("probe_parent_unavailable")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main() -> None:
    logging.disable(logging.CRITICAL)
    try:
        _parent_guard(int(sys.argv[1]))
        # Heavy imports and all client creation occur after the death guard.
        from pydantic import SecretStr
        from pydantic_settings import SettingsConfigDict
        from sqlalchemy import create_engine

        from .migrations.compatibility import (
            configure_runtime_engine,
            runtime_schema_compatibility,
        )
        from .sentinel import SentinelSettings, read_system_sentinel

        class ProbeSettings(SentinelSettings):
            model_config = SettingsConfigDict(env_file=None, extra="forbid")
            database_url: SecretStr
            mode: str

        raw = sys.stdin.buffer.readline(32769)
        if len(raw) > 32768 or not raw.endswith(b"\n"):
            return
        settings = ProbeSettings.model_validate_json(raw)
        engine = create_engine(
            settings.database_url.get_secret_value(),
            pool_size=1,
            max_overflow=0,
            pool_timeout=0.25,
            pool_pre_ping=True,
        )
        configure_runtime_engine(engine, production=settings.mode == "production")
        sys.stdout.buffer.write(b"warm\n")
        sys.stdout.buffer.flush()
        try:
            while sys.stdin.buffer.readline(16) == b"probe\n":
                result = b"dependency_unavailable\n"
                try:
                    deadline = time.monotonic() + 1
                    compatibility = runtime_schema_compatibility(engine)
                    if compatibility.status == "incompatible":
                        result = b"schema_incompatible\n"
                    elif compatibility.status == "ready":
                        if not compatibility.installation_key:
                            raise ValueError("installation_identity_unavailable")
                        read_system_sentinel(
                            settings, deadline, installation_key=compatibility.installation_key
                        )
                        result = b"ready\n"
                except Exception:
                    # Neither exception __str__ nor traceback/locals are emitted.
                    result = b"dependency_unavailable\n"
                sys.stdout.buffer.write(result)
                sys.stdout.buffer.flush()
        finally:
            engine.dispose()
    except BaseException:
        # Includes malformed bootstrap, invalid keys, SDK import or native setup.
        # The parent interprets EOF as unavailable; stderr is independently closed.
        return


if __name__ == "__main__":
    main()
