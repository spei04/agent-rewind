"""Database-free native protocol, scoped cleanup, and real driver-guard controls."""

import json
from types import SimpleNamespace

import pytest
from ledger_competing_native import NativeCommandGroup, NativeConversation, close_owned
from ledger_competing_postgres_observer import CLEAR, install_cleanup_guard
from ledger_competing_process import CommandGroup, Conversation, validate_control
from ledger_postgres_competing_fixture import TRY_LOCK_SQL
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

IDENTITY = {
    "nonce": "bound-native-nonce",
    "pid": 123,
    "case": "initialize",
    "role": "loser",
    "intent_sha256": "a" * 64,
}


def response(sequence=1, phase="held"):
    return {
        **IDENTITY,
        "raw_id": 456,
        "engine_id": 789,
        "sequence": sequence,
        "phase": phase,
        "witness": {},
    }


def test_native_loser_requires_attestation_before_continuation_and_result():
    protocol = NativeConversation(IDENTITY)
    with pytest.raises(AssertionError):
        protocol.control("continue")
    with pytest.raises(AssertionError):
        protocol.accept(response(1, "result"))
    protocol.accept(response())
    with pytest.raises(AssertionError):
        protocol.accept(response())
    with pytest.raises(AssertionError):
        protocol.control("probe")
    control = protocol.control("continue")
    validate_control(control, IDENTITY, raw_id=456, engine_id=789, sequence=2, action="continue")
    with pytest.raises(AssertionError):
        protocol.accept(response())
    protocol.accept(response(3, "result"))
    with pytest.raises(AssertionError):
        protocol.accept(response(3, "result"))
    assert protocol.state == "done"


@pytest.mark.parametrize(
    "field,value",
    [
        ("nonce", "wrong"),
        ("pid", True),
        ("case", "provision"),
        ("role", "winner"),
        ("intent_sha256", "b" * 64),
        ("sequence", True),
        ("sequence", 3),
        ("phase", "result"),
        ("raw_id", False),
        ("engine_id", 0),
        ("witness", []),
    ],
)
def test_native_attestation_rejects_wrong_binding(field, value):
    protocol = NativeConversation(IDENTITY)
    message = response()
    message[field] = value
    with pytest.raises(AssertionError):
        protocol.accept(message)
    assert protocol.state == "held" and protocol.sequence == 1


@pytest.mark.parametrize("field", ["raw_id", "engine_id", "nonce", "pid"])
def test_native_result_cannot_change_attested_identity(field):
    protocol = NativeConversation(IDENTITY)
    protocol.accept(response())
    protocol.control("continue")
    message = response(3, "result")
    message[field] = 987 if field != "nonce" else "other"
    with pytest.raises(AssertionError):
        protocol.accept(message)
    assert protocol.state == "result"


@pytest.mark.parametrize("kind,limit", [(CommandGroup, 10), (NativeCommandGroup, 12)])
def test_native_profile_keeps_explicit_message_and_time_limits(tmp_path, monkeypatch, kind, limit):
    # Cross a float precision boundary without subtracting rounded clock values.
    monkeypatch.setattr("ledger_competing_process.monotonic", lambda: 1023.9999999999999)
    group = kind(tmp_path)
    assert group.started == 1023.9999999999999
    assert group.work_deadline == 1084.0
    assert group.deadline == 1099.0
    child = SimpleNamespace(process=SimpleNamespace(pid=123))
    for index in range(limit):
        group.count(child, "parent-to-child" if index % 2 else "child-to-parent", 1)
    with pytest.raises(AssertionError, match="budget exhausted"):
        group.count(child, "child-to-parent", 1)
    assert len(group.messages) == limit
    group.close()
    assert CommandGroup.conversation_type is Conversation
    assert NativeCommandGroup.conversation_type is NativeConversation


def test_native_try_lock_matches_pinned_driver_compilation():
    assert (
        str(text("SELECT pg_try_advisory_xact_lock(:key)").compile(dialect=PGDialect_psycopg()))
        == TRY_LOCK_SQL
    )


class Raw:
    def __init__(self, *, closed=False, error=None):
        self.closed, self.error, self.calls = closed, error, 0

    def close(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        self.closed = True


class Engine:
    def __init__(self, error=None):
        self.calls, self.error = 0, error

    def dispose(self):
        self.calls += 1
        if self.error is not None:
            raise self.error


def test_native_scoped_cleanup_never_touches_foreign_raw():
    owned, foreign, engine, evidence = Raw(closed=True), Raw(), Engine(), {}
    close_owned(engine, [owned], evidence.__setitem__)
    assert owned.calls == foreign.calls == 0 and not foreign.closed
    assert engine.calls == 1 and evidence["scoped_cleanup"]["rescued_raw_ids"] == []


def test_native_cleanup_rescue_is_failure_even_after_physical_close():
    raw, engine, evidence = Raw(), Engine(), {}
    with pytest.raises(AssertionError, match="harness rescue"):
        close_owned(engine, [raw], evidence.__setitem__)
    assert raw.closed and raw.calls == engine.calls == 1
    assert evidence["scoped_cleanup"]["rescued_raw_ids"] == [id(raw)]


def test_native_cleanup_preserves_faults_and_disposes_all_owned_resources():
    class Stop(BaseException):
        pass

    first, second = Stop("raw"), RuntimeError("engine")
    failed, other, foreign = Raw(error=first), Raw(), Raw()
    engine, evidence = Engine(error=second), {}
    with pytest.raises(BaseExceptionGroup) as caught:
        close_owned(engine, [failed, other], evidence.__setitem__)
    assert caught.value.exceptions == (first, second)
    assert failed.calls == other.calls == engine.calls == 1 and other.closed
    assert foreign.calls == 0 and not foreign.closed
    assert evidence["scoped_cleanup"]["closed"] == [False, True]


@pytest.mark.parametrize("driver_sql", [False, True])
def test_live_child_guard_covers_actual_sqlalchemy_and_driver_execution(tmp_path, driver_sql):
    engine, evidence = create_engine("sqlite://"), {}
    group = NativeCommandGroup(tmp_path)
    child = SimpleNamespace(
        process=SimpleNamespace(pid=123, returncode=None),
        closed=False,
        record={"pid": 123},
    )

    def failed_close():
        raise TimeoutError("expired owned cleanup")

    child.close = failed_close
    group.children.append(child)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("CREATE TABLE protected(x)")
            connection.connection.driver_connection.create_function(
                "pg_stat_clear_snapshot", 0, lambda: 1
            )
            install_cleanup_guard(engine, group, evidence.__setitem__)
            # Allowed observations really reach the driver on both call paths.
            assert connection.exec_driver_sql(CLEAR).scalar_one() == 1
            assert connection.execute(text(CLEAR)).scalar_one() == 1
            with pytest.raises(BaseExceptionGroup):
                group.close()
            assert not child.closed and not group.closed
            with pytest.raises(AssertionError, match="forbidden"):
                if driver_sql:
                    connection.exec_driver_sql("DROP TABLE protected")
                else:
                    connection.execute(text("DROP TABLE protected"))
            assert evidence["blocked_finalizer"]["owned_pids"] == [123]
            # Only an actual reaped terminal handle opens teardown, not a
            # cleanup exception or the passage of the deadline.
            child.process.returncode = -9
            connection.exec_driver_sql("DROP TABLE protected")
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM sqlite_master WHERE name='protected'"
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_native_loser_socket_handshake_uses_original_shared_deadline(tmp_path):
    worker = tmp_path / "native_protocol_peer.py"
    worker.write_text(
        "import json,socket,struct,sys\n"
        "with socket.socket(fileno=int(sys.argv[1])) as channel:\n"
        " def read(n):\n"
        "  value=b''\n"
        "  while len(value)<n:\n"
        "   part=channel.recv(n-len(value))\n"
        "   if not part: raise EOFError('unexpected EOF')\n"
        "   value+=part\n"
        "  return value\n"
        " def receive(): return json.loads(read(struct.unpack('!I',read(4))[0]))\n"
        " def send(value):\n"
        "  payload=json.dumps(value).encode()\n"
        "  channel.sendall(struct.pack('!I',len(payload))+payload)\n"
        " request=receive()\n"
        " identity={k:request[k] for k in ('nonce','pid','case','role','intent_sha256')}\n"
        " assert identity['role']=='loser'\n"
        " reply=dict(identity,raw_id=1,engine_id=2,sequence=1,phase='held',witness={})\n"
        " send(reply)\n"
        " control=receive()\n"
        " assert control==dict(identity,raw_id=1,engine_id=2,sequence=2,action='continue')\n"
        " reply.update(sequence=3,phase='result',witness={'deadline':request['deadline']})\n"
        " send(reply)\n"
    )
    group = NativeCommandGroup(tmp_path)
    deadlines = group.work_deadline, group.deadline
    try:
        child = group.spawn(
            worker=worker,
            case="initialize",
            role="loser",
            intent_sha256="a" * 64,
            configuration={},
        )
        child.receive()
        assert child.process.poll() is None
        child.resume()
        result = child.receive()
        assert result["witness"]["deadline"] == deadlines[0]
        assert len(group.messages) == 4 and all(row["completed"] for row in group.messages)
        assert child.record["events"] == ["spawned", "held", "result", "reaped", "pipe_eof"]
    finally:
        group.close()
    assert (group.work_deadline, group.deadline) == deadlines
    assert group.record["cleanup_errors"] == []
    assert group.record["commands"][0]["reaped"]
    assert (
        json.loads((tmp_path / "command-group.json").read_text())["commands"][0]["returncode"] == 0
    )
