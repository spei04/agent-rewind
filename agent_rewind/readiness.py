"""One supervised Linux probe process, bounded IPC and fail-closed caching."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import time
from typing import Literal

from .config import Settings

ProbeResult = Literal["ready", "schema_incompatible", "dependency_unavailable"]
DEADLINE = 1.0
CACHE_SECONDS = 5.0
STARTUP_SECONDS = 5.0
RESTART_SECONDS = 5.0
MAX_CONFIG = 32768
_now = time.monotonic
RESULTS: dict[bytes, ProbeResult] = {
    b"ready\n": "ready",
    b"schema_incompatible\n": "schema_incompatible",
    b"dependency_unavailable\n": "dependency_unavailable",
}


def _environment() -> dict[str, str]:
    # Do not inherit provider/IdP secrets or credential_process configuration.
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "PYTHONPATH",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_ROLE_SESSION_NAME",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
        "AWS_EC2_METADATA_DISABLED",
        "AWS_CA_BUNDLE",
    }
    result = {key: value for key, value in os.environ.items() if key in allowed}
    result.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "AWS_CONFIG_FILE": os.devnull,
            "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "PYTHONUNBUFFERED": "1",
        }
    )
    return result


class Readiness:
    def __init__(self, settings: Settings):
        selected = {
            name: getattr(settings, name)
            for name in ("database_url", "mode", "storage", "s3_bucket", "s3_endpoint", "s3_region")
        }
        selected["data_dir"] = str(settings.data_dir.absolute())
        selected["encryption_key"] = settings.encryption_key.get_secret_value()
        self._config = json.dumps(selected, separators=(",", ":")).encode() + b"\n"
        self._process: asyncio.subprocess.Process | None = None
        self._starting: asyncio.Task[None] | None = None
        self._cleanup: asyncio.Task[None] | None = None
        self._probe: asyncio.Task[ProbeResult] | None = None
        self._restart: asyncio.Task[None] | None = None
        self._warm = False
        self._draining = False
        self._positive_at: float | None = None

    def start(self) -> None:
        if (
            self._draining
            or self._starting is not None
            or self._cleanup is not None
            or self._process is not None
            or sys.platform != "linux"
            or len(self._config) > MAX_CONFIG
        ):
            return
        self._starting = asyncio.create_task(self._boot())

    async def _boot(self) -> None:
        spawning: asyncio.Task[asyncio.subprocess.Process] | None = None
        try:
            # exec/spawn starts a fresh interpreter: no inherited DB pool sockets.
            async with asyncio.timeout(STARTUP_SECONDS):
                spawning = asyncio.create_task(
                    asyncio.create_subprocess_exec(
                        sys.executable,
                        "-m",
                        "agent_rewind.readiness_worker",
                        str(os.getpid()),
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        limit=64,
                        env=_environment(),
                        start_new_session=True,
                    )
                )
                self._process = await asyncio.shield(spawning)
                if self._process.stdin is None or self._process.stdout is None:
                    raise RuntimeError("probe_pipes_unavailable")
                self._process.stdin.write(self._config)
                await self._process.stdin.drain()
                if await self._process.stdout.readline() != b"warm\n":
                    raise ValueError("invalid_probe_handshake")
                self._warm = True
        except (Exception, asyncio.CancelledError):
            # A cancelled spawn must still be accounted for before another worker.
            if self._process is None and spawning is not None:
                with contextlib.suppress(Exception):
                    self._process = await asyncio.shield(spawning)
            self._retire()
        finally:
            self._starting = None

    def _retire(self) -> None:
        self._warm = False
        self._positive_at = None
        process = self._process
        if process is None or self._cleanup is not None:
            return
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        # Physical ownership ends only after wait/reap, never at response timeout.
        self._cleanup = asyncio.create_task(self._reap(process))

    async def _reap(self, process: asyncio.subprocess.Process) -> None:
        await process.wait()
        if process.stdin is not None:
            process.stdin.close()
        if self._process is process:
            self._process = None
        self._cleanup = None
        # Restart initialization is lifecycle work, never a request's I/O.
        if not self._draining and self._restart is None:
            self._restart = asyncio.create_task(self._restart_later())

    async def _restart_later(self) -> None:
        try:
            await asyncio.sleep(RESTART_SECONDS)
            self.start()
        finally:
            self._restart = None

    async def _run(self, process: asyncio.subprocess.Process, deadline: float) -> ProbeResult:
        try:
            async with asyncio.timeout_at(deadline):
                if process.stdin is None or process.stdout is None:
                    raise RuntimeError("probe_pipes_unavailable")
                process.stdin.write(b"probe\n")
                await process.stdin.drain()
                frame = await process.stdout.readline()
                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError("late_probe_result")
                result = RESULTS.get(frame)
                if result is None or process.returncode is not None:
                    raise ValueError("invalid_probe_frame")
                if result == "ready" and not self._draining:
                    self._positive_at = _now()
                return result
        except (Exception, asyncio.CancelledError):
            self._retire()
            return "dependency_unavailable"

    async def check(self) -> ProbeResult:
        if self._draining:
            return "dependency_unavailable"
        process = self._process
        if process is None or process.returncode is not None or not self._warm:
            self._positive_at = None
            if process is not None and process.returncode is not None:
                self._retire()
            return "dependency_unavailable"
        if self._cleanup is not None or self._probe is not None:
            return "dependency_unavailable"
        if self._positive_at is not None and _now() - self._positive_at <= CACHE_SECONDS:
            return "ready"
        self._positive_at = None
        deadline = asyncio.get_running_loop().time() + DEADLINE
        task = asyncio.create_task(self._run(process, deadline))
        self._probe = task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self._retire()
            task.cancel()
            raise
        finally:
            # The physical process remains owned by _cleanup after cancellation.
            self._probe = None

    async def close(self) -> None:
        self._draining = True
        self._positive_at = None
        if self._restart is not None:
            self._restart.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._restart
        if self._starting is not None:
            self._starting.cancel()
            await self._starting
        self._retire()
        if self._probe is not None:
            self._probe.cancel()
            await self._probe
        if self._cleanup is not None:
            await asyncio.shield(self._cleanup)
