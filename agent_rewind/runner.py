"""One disposable gVisor container per shell action, with a bounded tmpfs volume."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import docker
from docker.errors import DockerException

from .config import Settings
from .database import identifier
from .models import Action
from .workspace import File, pack, unpack


class Runner(Protocol):
    def resolve_image(self, image: str) -> str: ...
    def execute(
        self,
        image: str,
        files: dict[str, File],
        action: Action,
        timeout: int,
        guard: Callable[[], None],
    ) -> tuple[dict[str, File], dict[str, Any]]: ...

    def evaluate(
        self,
        image: str,
        files: dict[str, File],
        evaluator: dict[str, File],
        command: str,
        timeout: int,
        guard: Callable[[], None],
    ) -> dict[str, Any]: ...


class DockerRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = docker.from_env(timeout=15)
        self.limit = settings.workspace_mb * 1024 * 1024
        info = self.client.info()
        runtime = settings.sandbox_runtime
        if runtime not in info.get("Runtimes", {}):
            raise RuntimeError(f"Required sandbox runtime '{runtime}' is not installed.")
        if runtime != "runsc" and not (
            settings.mode == "development" and settings.allow_insecure_runtime
        ):
            raise RuntimeError("Standard containers require an explicit development opt-in.")

    def resolve_image(self, image: str) -> str:
        allowed = {s.strip() for s in self.settings.allowed_images.split(",") if s.strip()}
        if image not in allowed:
            raise ValueError("Image is not in the administrator's allowlist.")
        if (
            self.settings.mode == "production"
            and "@sha256:" not in image
            and not image.startswith("sha256:")
        ):
            raise ValueError("Production images must be pinned by digest.")
        # Never pull operator-supplied images automatically.
        return str(self.client.images.get(image).id)

    def execute(
        self,
        image: str,
        files: dict[str, File],
        action: Action,
        timeout: int,
        guard: Callable[[], None],
    ) -> tuple[dict[str, File], dict[str, Any]]:
        guard()
        if action.tool == "read_file":
            file = files.get(action.path)
            if file is not None and file.kind == "directory":
                return files, {"exit_code": 1, "output": "Path is a directory.", "truncated": False}
            return files, {
                "exit_code": 0 if file else 1,
                "output": file.data[:64000].decode("utf-8", errors="replace")
                if file
                else "File not found.",
                "truncated": bool(file and len(file.data) > 64000),
            }
        if action.tool == "write_file":
            if action.path in files and files[action.path].kind == "directory":
                return files, {"exit_code": 1, "output": "Path is a directory.", "truncated": False}
            result = dict(files)
            result[action.path] = File(
                action.content.encode(), files.get(action.path, File(b"")).mode
            )
            if sum(len(f.data) for f in result.values()) > self.limit:
                raise ValueError("Workspace exceeds its byte limit.")
            return result, {"exit_code": 0, "output": f"Wrote {action.path}.", "truncated": False}
        if action.tool == "finish":
            return files, {"exit_code": 0, "output": "Agent finished.", "truncated": False}
        return self._shell(image, files, action.command, timeout, guard)

    def evaluate(
        self,
        image: str,
        files: dict[str, File],
        evaluator: dict[str, File],
        command: str,
        timeout: int,
        guard: Callable[[], None],
    ) -> dict[str, Any]:
        _, result = self._shell(image, files, command, timeout, guard, evaluator)
        return result

    def _shell(
        self,
        image: str,
        files: dict[str, File],
        command: str,
        timeout: int,
        guard: Callable[[], None],
        evaluator: dict[str, File] | None = None,
    ) -> tuple[dict[str, File], dict[str, Any]]:
        label = identifier()
        volume = self.client.volumes.create(
            name=f"rewind-{label}",
            driver_opts={
                "type": "tmpfs",
                "device": "tmpfs",
                "o": f"size={self.settings.workspace_mb}m,mode=1777",
            },
            labels={"agent-rewind.managed": "true", "agent-rewind.created": str(time.time())},
        )
        container = None
        grader_volume = None
        uploader = None
        mounts = {volume.name: {"bind": "/workspace", "mode": "rw"}}
        try:
            if evaluator is not None:
                grader_volume = self.client.volumes.create(
                    name=f"rewind-grader-{label}",
                    driver_opts={"type": "tmpfs", "device": "tmpfs", "o": "size=16m,mode=1777"},
                    labels={
                        "agent-rewind.managed": "true",
                        "agent-rewind.created": str(time.time()),
                    },
                )
                uploader = self.client.containers.run(
                    image,
                    entrypoint=["/bin/sh", "-c", "exec sleep 600"],
                    detach=True,
                    network_mode="none",
                    read_only=True,
                    user="1000:1000",
                    init=True,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    runtime=self.settings.sandbox_runtime,
                    mem_limit="64m",
                    pids_limit=16,
                    volumes={grader_volume.name: {"bind": "/workspace", "mode": "rw"}},
                    labels={
                        "agent-rewind.managed": "true",
                        "agent-rewind.created": str(time.time()),
                    },
                )
                uploader.put_archive("/workspace", pack(evaluator))
                mounts[grader_volume.name] = {"bind": "/evaluator", "mode": "ro"}
            container = self.client.containers.create(
                image=image,
                entrypoint=["/bin/sh", "-c", "exec sleep 600"],
                user="1000:1000",
                init=True,
                working_dir="/workspace",
                network_mode="none",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                runtime=self.settings.sandbox_runtime,
                mem_limit=f"{self.settings.sandbox_memory_mb}m",
                memswap_limit=f"{self.settings.sandbox_memory_mb}m",
                nano_cpus=1_000_000_000,
                pids_limit=128,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m,mode=1777"},
                volumes=mounts,
                environment={"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
                labels={"agent-rewind.managed": "true", "agent-rewind.created": str(time.time())},
            )
            container.start()
            container.put_archive("/workspace", pack(files))
            execution = self.client.api.exec_create(
                container.id, ["/bin/sh", "-lc", command], workdir="/workspace", user="1000:1000"
            )
            output = bytearray()
            completed = threading.Event()
            errors: list[Exception] = []
            overflow = threading.Event()

            def read_output() -> None:
                try:
                    for chunk in self.client.api.exec_start(execution["Id"], stream=True):
                        if len(output) + len(chunk) > 64000:
                            output.extend(chunk[: max(0, 64000 - len(output))])
                            overflow.set()
                            break
                        output.extend(chunk)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    completed.set()

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            deadline = time.monotonic() + timeout
            while not completed.wait(0.2):
                guard()
                if time.monotonic() > deadline:
                    raise TimeoutError("Shell command exceeded its wall-clock limit.")
            if overflow.is_set():
                raise ValueError("Shell output exceeded 64 KiB; checkpoint refused.")
            if errors:
                raise RuntimeError("Sandbox output stream failed.") from errors[0]
            info = self.client.api.exec_inspect(execution["Id"])
            if info.get("Running") or info.get("ExitCode") is None:
                raise RuntimeError("Command did not terminate cleanly.")
            # Freeze all writers before the daemon reads the workspace volume.
            container.pause()
            chunks, _ = container.get_archive("/workspace")
            archive = bytearray()
            for chunk in chunks:
                archive.extend(chunk)
                if len(archive) > self.limit + 16 * 1024 * 1024:
                    raise ValueError("Workspace archive exceeds its byte limit.")
            restored = unpack(bytes(archive), self.limit, docker_prefix=True)
            return restored, {
                "exit_code": info["ExitCode"],
                "output": output.decode("utf-8", errors="replace"),
                "truncated": False,
            }
        finally:
            # All process state is intentionally discarded at a tool boundary.
            try:
                if container is not None:
                    self._remove_container(container)
            finally:
                try:
                    if uploader is not None:
                        self._remove_container(uploader)
                finally:
                    volume.remove(force=True)
                    if grader_volume is not None:
                        grader_volume.remove(force=True)

    @staticmethod
    def _remove_container(container: docker.models.containers.Container) -> None:
        container.reload()
        status = container.attrs.get("State", {})
        # gVisor must receive termination while runnable so its init can reap
        # processes and notify the container shim before Docker removes mounts.
        if status.get("Paused"):
            container.unpause()
        if status.get("Running"):
            container.stop(timeout=1)
        container.remove(force=True)

    def cleanup(self, older_than_seconds: int = 3600) -> int:
        """Reap abandoned resources only after their maximum lifetime has elapsed."""
        cutoff = time.time() - older_than_seconds
        removed = 0
        for container in self.client.containers.list(
            all=True, filters={"label": "agent-rewind.managed=true"}
        ):
            created = float(container.labels.get("agent-rewind.created", time.time()))
            if created < cutoff:
                self._remove_container(container)
                removed += 1
        for volume in self.client.volumes.list(filters={"label": "agent-rewind.managed=true"}):
            labels = volume.attrs.get("Labels") or {}
            if float(labels.get("agent-rewind.created", time.time())) < cutoff:
                try:
                    volume.remove()  # The daemon refuses removal while a container uses it.
                except DockerException:
                    continue
        return removed
