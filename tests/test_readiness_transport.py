import asyncio
import json
import os
import signal
import sys
import time

import pytest
from pydantic import SecretStr

from agent_rewind.readiness import Readiness, _environment
from agent_rewind.sentinel import SentinelSettings, provision

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux process containment")


async def wait_until(condition):
    async with asyncio.timeout(5):
        while not condition():
            await asyncio.sleep(0.005)


def child_script(monkeypatch, script):
    original = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        return await original(sys.executable, "-c", script, args[-1], **kwargs)

    monkeypatch.setattr("agent_rewind.readiness.asyncio.create_subprocess_exec", spawn)


def fixture_child(action):
    return (
        "import os,sys,signal\n"
        "from agent_rewind.readiness_worker import _parent_guard\n"
        "_parent_guard(int(sys.argv[1]))\n"
        "sys.stdin.buffer.readline(32769)\n"
        "sys.stdout.buffer.write(b'warm\\n');sys.stdout.buffer.flush()\n"
        "while sys.stdin.buffer.readline(16)==b'probe\\n':\n"
        + "\n".join(" " + line for line in action.splitlines())
        + "\n"
    )


@pytest.mark.parametrize("partial", [b"", b"rea"])
def test_real_stall_deadline_kill_and_reap(settings, monkeypatch, tmp_path, partial):
    marker = tmp_path / "entered"
    child_script(
        monkeypatch,
        fixture_child(
            f"open({str(marker)!r},'w').close()\n"
            f"sys.stdout.buffer.write({partial!r});sys.stdout.buffer.flush()\nsignal.pause()"
        ),
    )

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        await wait_until(lambda: manager._warm)
        process = manager._process
        started = time.monotonic()
        task = asyncio.create_task(manager.check())
        await wait_until(marker.exists)
        assert await manager.check() == "dependency_unavailable"
        assert await task == "dependency_unavailable"
        assert time.monotonic() - started < 1.5
        await process.wait()
        assert process.returncode == -signal.SIGKILL
        await manager.close()
        assert manager._process is None

    asyncio.run(exercise())


def test_cancel_holds_physical_slot_until_reap(settings, monkeypatch, tmp_path):
    marker = tmp_path / "entered"
    child_script(monkeypatch, fixture_child(f"open({str(marker)!r},'w').close()\nsignal.pause()"))

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        await wait_until(lambda: manager._warm)
        process = manager._process
        original_reap = manager._reap
        hold = asyncio.Event()

        async def delayed_reap(process):
            await hold.wait()
            await original_reap(process)

        monkeypatch.setattr(manager, "_reap", delayed_reap)
        task = asyncio.create_task(manager.check())
        await wait_until(marker.exists)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert manager._process is process and manager._cleanup is not None
        manager.start()
        assert await manager.check() == "dependency_unavailable"
        assert manager._process is process
        hold.set()
        await process.wait()
        await manager.close()
        assert process.returncode == -signal.SIGKILL
        assert manager._process is None

    asyncio.run(exercise())


def test_ready_cache_expiry_process_exit_and_drain(settings, monkeypatch, tmp_path):
    count = tmp_path / "count"
    child_script(
        monkeypatch,
        fixture_child(
            f"with open({str(count)!r},'a') as f:f.write('x')\n"
            "sys.stdout.buffer.write(b'ready\\n');sys.stdout.buffer.flush()"
        ),
    )
    current = [100.0]
    monkeypatch.setattr("agent_rewind.readiness._now", lambda: current[0])

    async def exercise():
        manager = Readiness(settings)
        assert await manager.check() == "dependency_unavailable"
        manager.start()
        await wait_until(lambda: manager._warm)
        assert await manager.check() == "ready"
        current[0] = 104.99
        assert await manager.check() == "ready" and count.read_text() == "x"
        current[0] = 105.01
        assert await manager.check() == "ready" and count.read_text() == "xx"
        process = manager._process
        process.kill()
        await process.wait()
        assert await manager.check() == "dependency_unavailable"
        await manager.close()
        assert await manager.check() == "dependency_unavailable"

    asyncio.run(exercise())


@pytest.mark.parametrize("frame", [b"ready-but-not-ready\n", b"x" * 1000 + b"\n", b""])
def test_malformed_or_excessive_frame_fails_closed(settings, monkeypatch, frame):
    child_script(
        monkeypatch,
        fixture_child(
            f"sys.stdout.buffer.write({frame!r});sys.stdout.buffer.flush()\nraise SystemExit"
        ),
    )

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        await wait_until(lambda: manager._warm)
        assert await manager.check() == "dependency_unavailable"
        await manager.close()

    asyncio.run(exercise())


def test_real_worker_migration_only_and_secret_output(settings, capfd):
    from agent_rewind.database import Database

    database = Database(settings)
    database.migrate(installation_key="synthetic-test")

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        await wait_until(lambda: manager._warm)
        assert await manager.check() == "schema_incompatible"
        await manager.close()

    asyncio.run(exercise())
    captured = capfd.readouterr()
    assert settings.encryption_key.get_secret_value() not in captured.out + captured.err
    database.engine.dispose()


@pytest.mark.parametrize("stage", ["database", "dns", "store", "body", "decrypt"])
def test_physical_stalls_at_dependency_stages(settings, monkeypatch, tmp_path, stage):
    marker = tmp_path / "blocked"
    sentinel = SentinelSettings(
        _env_file=None,
        data_dir=settings.data_dir,
        encryption_key=settings.encryption_key,
        installation_key=SecretStr("synthetic-install"),
    )
    provision(sentinel)
    script = (
        "import signal,sys,socket\n"
        "from types import SimpleNamespace\n"
        "import agent_rewind.migrations.compatibility as compat\n"
        "import agent_rewind.sentinel as sentinel\n"
        "from agent_rewind.readiness_worker import main\n"
        "def stall(*a,**kw):\n"
        f" open({str(marker)!r},'w').close()\n signal.pause()\n"
        "compat.runtime_schema_compatibility=lambda engine:SimpleNamespace("
        "status='ready',installation_key='synthetic-install')\n"
    )
    if stage == "database":
        script += "compat.runtime_schema_compatibility=stall\n"
    elif stage == "decrypt":
        script += "sentinel.Fernet.decrypt=stall\n"
    else:
        settings.storage = "s3"
        settings.s3_bucket = "synthetic"
        settings.s3_endpoint = "http://synthetic.invalid:9000"
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic")
        monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
        if stage == "dns":
            script += "socket.getaddrinfo=stall\n"
        elif stage == "store":
            script += "sentinel.boto3.client=lambda *a,**kw:SimpleNamespace(get_object=stall)\n"
        else:
            script += (
                "body=SimpleNamespace(read=stall,close=lambda:None)\n"
                "sentinel.boto3.client=lambda *a,**kw:SimpleNamespace("
                "get_object=lambda **kw:{'Body':body,'ContentLength':1})\n"
            )
    script += "main()\n"
    child_script(monkeypatch, script)

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        await wait_until(lambda: manager._warm)
        process = manager._process
        task = asyncio.create_task(manager.check())
        await wait_until(marker.exists)
        assert await task == "dependency_unavailable"
        await process.wait()
        assert process.returncode == -signal.SIGKILL
        await manager.close()

    asyncio.run(exercise())


def test_worker_environment_excludes_unrelated_credentials(monkeypatch):
    for key in ("REWIND_MODEL_API_KEY", "REWIND_OIDC_CLIENT_SECRET", "OPENAI_API_KEY"):
        monkeypatch.setenv(key, "private-canary")
    monkeypatch.setenv("AWS_PROFILE", "must-not-load-credential-process")
    environment = _environment()
    assert "private-canary" not in json.dumps(environment)
    assert "AWS_PROFILE" not in environment
    assert environment["AWS_CONFIG_FILE"] == os.devnull


@pytest.mark.parametrize("identity", [None, "", "different-installation"])
def test_mismatched_database_identity_refuses_before_storage(
    settings, monkeypatch, tmp_path, identity
):
    provision(
        SentinelSettings(
            _env_file=None,
            data_dir=settings.data_dir,
            encryption_key=settings.encryption_key,
            installation_key=SecretStr("synthetic-install"),
        )
    )
    marker = tmp_path / "storage-touched"
    script = (
        "import sys\nfrom types import SimpleNamespace\n"
        "import agent_rewind.migrations.compatibility as compat\n"
        "import agent_rewind.sentinel as sentinel\n"
        "from agent_rewind.readiness_worker import main\n"
        "compat.runtime_schema_compatibility=lambda engine:SimpleNamespace("
        f"status='ready',installation_key={identity!r})\n"
        "def forbidden(*a,**kw):\n"
        f" open({str(marker)!r},'w').close()\n raise RuntimeError('storage touched')\n"
        "sentinel._Store.read=forbidden\nmain()\n"
    )
    child_script(monkeypatch, script)

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        try:
            await wait_until(lambda: manager._warm)
            assert await manager.check() == "dependency_unavailable"
            assert not marker.exists()
        finally:
            await manager.close()

    asyncio.run(exercise())


def test_raw_child_stderr_traceback_and_stdout_canary_are_discarded(settings, monkeypatch, capfd):
    canary = "secret-child-provider-body-and-key"
    child_script(
        monkeypatch,
        fixture_child(
            f"sys.stderr.write({canary!r});sys.stderr.flush()\n"
            f"sys.stdout.buffer.write({canary.encode()!r}+b'\\n');sys.stdout.buffer.flush()\n"
            f"raise RuntimeError({canary!r})"
        ),
    )

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        try:
            await wait_until(lambda: manager._warm)
            assert await manager.check() == "dependency_unavailable"
        finally:
            await manager.close()

    asyncio.run(exercise())
    captured = capfd.readouterr()
    assert canary not in captured.out + captured.err


def process_exited(pid):
    try:
        with open(f"/proc/{pid}/stat") as source:
            status = source.read().split()[2]
    except (FileNotFoundError, ProcessLookupError):
        return True
    # PID1 owns orphan reaping after parent death; a zombie cannot run/I/O.
    return status == "Z"


@pytest.mark.parametrize("error", [FileNotFoundError, ProcessLookupError, PermissionError])
def test_process_exit_observer_handles_only_disappearance_during_read(monkeypatch, error):
    class Disappearing:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            raise error("synthetic proc observation")

    monkeypatch.setattr("builtins.open", lambda *args: Disappearing())
    if error is PermissionError:
        with pytest.raises(PermissionError):
            process_exited(123)
    else:
        assert process_exited(123)


def test_parent_death_kills_guarded_worker(tmp_path):
    import subprocess

    marker = tmp_path / "guard-installed"
    child = (
        "import os,sys,signal\n"
        "from agent_rewind.readiness_worker import _parent_guard\n"
        "_parent_guard(int(sys.argv[1]))\n"
        f"open({str(marker)!r},'w').close()\n"
        "signal.pause()\n"
    )
    parent = (
        "import os,subprocess,sys\n"
        f"p=subprocess.Popen([sys.executable,'-c',{child!r},str(os.getpid())],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "print(p.pid,flush=True)\nsys.stdin.read()\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", parent],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    child_pid = int(process.stdout.readline())

    async def exercise():
        await wait_until(marker.exists)
        process.kill()
        process.wait(timeout=2)

        await wait_until(lambda: process_exited(child_pid))

    try:
        asyncio.run(exercise())
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()


def test_unsupported_platform_is_closed(settings, monkeypatch):
    monkeypatch.setattr("agent_rewind.readiness.sys.platform", "unsupported")

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        assert manager._process is None
        assert await manager.check() == "dependency_unavailable"
        await manager.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("partial", ["header", "body"])
def test_real_s3_partial_http_response_closes_connection(settings, monkeypatch, tmp_path, partial):
    from cryptography.fernet import Fernet

    from agent_rewind.sentinel import canonical_payload

    provision(
        SentinelSettings(
            _env_file=None,
            data_dir=settings.data_dir,
            encryption_key=settings.encryption_key,
            installation_key=SecretStr("synthetic-install"),
        )
    )
    token = Fernet(settings.encryption_key.get_secret_value().encode()).encrypt(
        canonical_payload("synthetic-install")
    )
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    script = (
        "from types import SimpleNamespace\n"
        "import agent_rewind.migrations.compatibility as compat\n"
        "from agent_rewind.readiness_worker import main\n"
        "compat.runtime_schema_compatibility=lambda engine:SimpleNamespace("
        "status='ready',installation_key='synthetic-install')\nmain()\n"
    )
    child_script(monkeypatch, script)

    async def exercise():
        entered, closed = asyncio.Event(), asyncio.Event()

        async def response(reader, writer):
            try:
                await reader.readuntil(b"\r\n\r\n")
                if partial == "header":
                    writer.write(b"HTTP/1.1 206 Partial Content\r\nContent-Len")
                else:
                    writer.write(
                        f"HTTP/1.1 206 Partial Content\r\nContent-Length: {len(token)}\r\n"
                        f"Content-Range: bytes 0-{len(token) - 1}/{len(token)}\r\n"
                        "Connection: close\r\n\r\n".encode()
                        + token[:1]
                    )
                await writer.drain()
                entered.set()
                assert await reader.read() == b""
            finally:
                writer.close()
                await writer.wait_closed()
                closed.set()

        server = await asyncio.start_server(response, "127.0.0.1", 0)
        settings.storage = "s3"
        settings.s3_bucket = "synthetic"
        settings.s3_endpoint = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        manager = Readiness(settings)
        manager.start()
        try:
            await wait_until(lambda: manager._warm)
            started = time.monotonic()
            task = asyncio.create_task(manager.check())
            await asyncio.wait_for(entered.wait(), 2)
            assert await task == "dependency_unavailable"
            assert time.monotonic() - started < 1.5
            await asyncio.wait_for(closed.wait(), 2)
        finally:
            await manager.close()
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_real_postgresql_connection_stall_is_killed(settings):
    async def exercise():
        entered, closed = asyncio.Event(), asyncio.Event()

        async def blackhole(reader, writer):
            try:
                assert await reader.read(8)
                entered.set()
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
                closed.set()

        server = await asyncio.start_server(blackhole, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        settings.database_url = (
            f"postgresql+psycopg://synthetic:synthetic@127.0.0.1:{port}/synthetic"
        )
        manager = Readiness(settings)
        manager.start()
        try:
            await wait_until(lambda: manager._warm)
            process = manager._process
            task = asyncio.create_task(manager.check())
            await asyncio.wait_for(entered.wait(), 2)
            assert await task == "dependency_unavailable"
            await asyncio.wait_for(closed.wait(), 2)
            await process.wait()
            assert process.returncode == -signal.SIGKILL
        finally:
            await manager.close()
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_restart_waits_for_reap_and_rewarms_with_no_stale_cache(settings, monkeypatch):
    original = asyncio.create_subprocess_exec
    processes = []
    good = fixture_child("sys.stdout.buffer.write(b'ready\\n');sys.stdout.buffer.flush()")

    async def spawn(*args, **kwargs):
        if processes:
            assert processes[-1].returncode is not None
        script = (
            "import sys,signal\nsys.stdin.buffer.readline(32769)\n"
            "sys.stdout.buffer.write(b'invalid\\n');sys.stdout.buffer.flush()\nsignal.pause()\n"
            if not processes
            else good
        )
        process = await original(sys.executable, "-c", script, args[-1], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr("agent_rewind.readiness.asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("agent_rewind.readiness.RESTART_SECONDS", 0.01)

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        try:
            assert await manager.check() == "dependency_unavailable"
            await wait_until(lambda: manager._warm)
            assert len(processes) == 2
            assert processes[0].returncode == -signal.SIGKILL
            assert manager._positive_at is None
            assert await manager.check() == "ready"
        finally:
            await manager.close()

    asyncio.run(exercise())


def test_shutdown_during_incomplete_handshake_reaps(settings, monkeypatch):
    child_script(
        monkeypatch,
        "import signal,sys\nfrom agent_rewind.readiness_worker import _parent_guard\n"
        "_parent_guard(int(sys.argv[1]))\nsys.stdin.buffer.readline(32769)\nsignal.pause()\n",
    )

    async def exercise():
        manager = Readiness(settings)
        manager.start()
        await wait_until(lambda: manager._process is not None)
        process = manager._process
        assert await manager.check() == "dependency_unavailable"
        await manager.close()
        assert process.returncode == -signal.SIGKILL
        assert manager._process is None

    asyncio.run(exercise())


def test_cancelled_spawn_is_owned_until_pid_return_and_reap(settings, monkeypatch):
    original = asyncio.create_subprocess_exec

    async def exercise():
        spawned, release = asyncio.Event(), asyncio.Event()
        processes = []

        async def delayed_spawn(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            spawned.set()
            await release.wait()
            return process

        monkeypatch.setattr("agent_rewind.readiness.asyncio.create_subprocess_exec", delayed_spawn)
        manager = Readiness(settings)
        manager.start()
        await asyncio.wait_for(spawned.wait(), 2)
        closing = asyncio.create_task(manager.close())
        await asyncio.sleep(0)
        manager.start()
        assert len(processes) == 1
        assert not closing.done()
        assert await manager.check() == "dependency_unavailable"
        release.set()
        await asyncio.wait_for(closing, 2)
        assert processes[0].returncode == -signal.SIGKILL
        assert manager._process is None

    asyncio.run(exercise())


def test_startup_timeout_then_repeated_shutdown_cancellation_retains_spawn(settings, monkeypatch):
    original = asyncio.create_subprocess_exec
    monkeypatch.setattr("agent_rewind.readiness.STARTUP_SECONDS", 0.03)

    async def exercise():
        spawned, release = asyncio.Event(), asyncio.Event()
        processes = []

        async def delayed_spawn(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            spawned.set()
            await release.wait()
            return process

        monkeypatch.setattr("agent_rewind.readiness.asyncio.create_subprocess_exec", delayed_spawn)
        manager = Readiness(settings)
        manager.start()
        try:
            await asyncio.wait_for(spawned.wait(), 2)
            await wait_until(lambda: manager._starting is None and manager._cleanup is not None)
            owner = manager._cleanup
            assert processes[0].returncode is None
            for _ in range(2):
                closing = asyncio.create_task(manager.close())
                await wait_until(lambda: manager._closing is not None)
                closing.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await closing
                assert not manager._closing.done()
                assert manager._cleanup is owner and not owner.done()
                manager.start()
                assert len(processes) == 1
                assert await manager.check() == "dependency_unavailable"
            release.set()
            await asyncio.wait_for(manager.close(), 2)
            assert processes[0].returncode == -signal.SIGKILL
            assert manager._process is None and manager._cleanup is None
            await manager.close()
        finally:
            release.set()
            for process in processes:
                if process.returncode is None:
                    process.kill()
                await process.wait()
            await manager.close()

    asyncio.run(exercise())


def test_legacy_boto_provider_cannot_load_host_credentials(monkeypatch):
    from botocore.credentials import BotoProvider

    monkeypatch.setenv("BOTO_CONFIG", "/synthetic/host-credentials")
    inspected = []

    def synthetic_parser(path):
        inspected.append(path)
        if path == os.devnull:
            return {}
        return {
            "Credentials": {"aws_access_key_id": "private-key", "aws_secret_access_key": "secret"}
        }

    assert BotoProvider(environ=_environment(), ini_parser=synthetic_parser).load() is None
    assert inspected == [os.devnull]
