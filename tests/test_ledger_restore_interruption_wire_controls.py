"""Offline controls for actual wire parsing and the fixed cancellation capability."""

import json
from types import SimpleNamespace

import ledger_restore_interruption_control as capability
import ledger_restore_interruption_pq as wire
import pytest
from ledger_restore_interruption_contracts import COPY, FIELDS, SQL
from ledger_restore_interruption_ownership import InterruptedOwnership
from test_ledger_restore_tool_ownership_controls import Child

TOKEN = "a" * 32


def owner():
    value = InterruptedOwnership(lambda *a, **kw: None, lambda *a, **kw: None)
    value.children = [Child(code=0) for _ in range(4)]
    for index, child in enumerate(value.children):
        child.pid = 10 + index
    return value


def control(monkeypatch):
    monkeypatch.setattr(capability.time, "monotonic", lambda: 100.0)
    for key in tuple(capability.os.environ):
        if key.startswith("PG"):
            monkeypatch.delenv(key)
    return capability.InterruptionControl(
        owner(),
        socket="/fixed",
        token=TOKEN,
        database_oid=10,
        relation_oid=20,
        directory=None,
        parent_deadline=460,
    )


class Result:
    def __init__(self, name="cancel", rows=None, *, status=wire.pq.ExecStatus.TUPLES_OK):
        self.status = status
        self.names = list(FIELDS[name])
        self.values = [[b"1", b"true"]] if rows is None else rows
        self.ntuples, self.nfields = len(self.values), len(self.names)
        self.command_status, self.cleared, self.binary = b"", False, False
        self.error_message = b""

    def fname(self, index):
        return self.names[index].encode()

    def fformat(self, index):
        return int(self.binary)

    def get_value(self, row, field):
        return self.values[row][field]

    def clear(self):
        self.cleared = True


class Raw:
    socket, backend_pid, db, user = 33, 333, b"postgres", b"postgres"
    status, transaction_status = wire.pq.ConnStatus.OK, wire.pq.TransactionStatus.IDLE

    def __init__(self):
        self.results, self.sent, self.flushes = [], [], [0]
        self.polls = [wire.pq.PollingStatus.OK]
        self.busy, self.finished, self.consumed = False, False, 0

    def connect_poll(self):
        return self.polls.pop(0)

    def send_query_params(self, sql, params):
        self.sent.append((sql, params))

    def flush(self):
        return self.flushes.pop(0) if self.flushes else 0

    def consume_input(self):
        self.consumed += 1

    def is_busy(self):
        return self.busy

    def get_result(self):
        return self.results.pop(0) if self.results else None

    def finish(self):
        self.finished = True


def channel(monkeypatch):
    raw, events = Raw(), []
    monkeypatch.setattr(wire.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(wire.pq, "PGconn", SimpleNamespace(connect_start=lambda _: raw))
    value = wire.Channel(b"fixed", deadline=103, record=events.append)
    value.step()
    return value, raw, events


def send_cancel(value):
    value.send("cancel", (b"1",) * 10, deadline=101)


def test_wire_retains_exact_sql_parameters_and_full_drain(monkeypatch):
    value, raw, events = channel(monkeypatch)
    send_cancel(value)
    result = Result()
    raw.results = [result, None]
    value.step(wire.READ)
    assert result.cleared and not value.complete
    value.step()
    assert value.complete and value.take() == [{"candidates": b"1", "cancelled": b"true"}]
    assert raw.sent == [(SQL["cancel"].encode(), (b"1",) * 10)]
    assert events[-1]["returned"] == "cancel"
    value.close()
    assert raw.finished and value.closed


@pytest.mark.parametrize(
    "change",
    [
        "status",
        "fields",
        "extra_field",
        "rows",
        "cell",
        "total",
        "binary",
        "nonbytes",
        "extra_result",
        "missing_result",
        "not_idle",
    ],
)
def test_wire_rejects_incomplete_or_unbounded_results(monkeypatch, change):
    value, raw, _ = channel(monkeypatch)
    send_cancel(value)
    result = Result()
    if change == "status":
        result.status = wire.pq.ExecStatus.FATAL_ERROR
    elif change == "fields":
        result.names.reverse()
    elif change == "extra_field":
        result.nfields += 1
    elif change == "rows":
        result.ntuples = 3
    elif change == "cell":
        result.values[0][0] = b"x" * 4097
    elif change == "total":
        value.query = "identity"
        result = Result("identity", [[b"x" * 4096] * 9])
    elif change == "binary":
        result.binary = True
    elif change == "nonbytes":
        result.values[0][0] = "1"
    raw.results = [result, Result()] if change == "extra_result" else [result, None]
    if change == "missing_result":
        raw.results = [None]
    if change == "not_idle":
        raw.transaction_status = wire.pq.TransactionStatus.INTRANS
    with pytest.raises(AssertionError):
        value.step(wire.READ)
        value.step()
    if change != "missing_result":
        assert result.cleared


@pytest.mark.parametrize(
    "operation,tag",
    [
        ("begin", b"BEGIN"),
        ("lock", b"LOCK TABLE"),
        ("rollback", b"ROLLBACK"),
    ],
)
def test_transaction_command_requires_exact_tag_and_state(monkeypatch, operation, tag):
    value, raw, _ = channel(monkeypatch)
    value.send(operation, (), deadline=101)
    result = Result(operation, [], status=wire.pq.ExecStatus.COMMAND_OK)
    result.command_status = tag
    raw.transaction_status = (
        wire.pq.TransactionStatus.IDLE
        if operation == "rollback"
        else wire.pq.TransactionStatus.INTRANS
    )
    raw.results = [result, None]
    value.step()
    value.step()
    assert value.take() == []
    value.send(operation, (), deadline=101)
    result.command_status = b"WRONG"
    raw.results = [result]
    with pytest.raises(AssertionError):
        value.step()


def test_wire_flush_and_busy_do_not_read_results_early(monkeypatch):
    value, raw, _ = channel(monkeypatch)
    raw.flushes = [1, 0]
    send_cancel(value)
    raw.results = [Result(), None]
    raw.busy = True
    value.step(wire.READ)
    assert len(raw.results) == 2 and value.interest == wire.READ | wire.WRITE
    value.step(wire.WRITE)
    assert len(raw.results) == 2
    raw.busy = False
    value.step(wire.READ)
    assert len(raw.results) == 1


@pytest.mark.parametrize("bad", [b"x" * 4097, b"a\0b", "wrong"])
def test_wire_parameters_reject_before_send(monkeypatch, bad):
    value, raw, _ = channel(monkeypatch)
    with pytest.raises(AssertionError):
        value.send("cancel", (bad,) * 10, deadline=101)
    assert raw.sent == []


def test_wire_deadline_and_notice_failure_keep_exception_identity(monkeypatch):
    value, raw, _ = channel(monkeypatch)
    error = RuntimeError("bounded transcript failed")
    value.record = lambda _: (_ for _ in ()).throw(error)
    value.notice(SimpleNamespace(error_message=b"NOTICE"))
    with pytest.raises(RuntimeError) as caught:
        value.step()
    assert caught.value is error
    value.notice_error = None
    with pytest.raises(TimeoutError):
        value.send("identity", (), deadline=100)
    assert raw.sent == []


def test_transcript_charges_exact_encoding_and_rejects_before_append(monkeypatch):
    value = control(monkeypatch)
    value.record({"unicode": "\u2603", "notice": "hello"})

    def encode():
        return json.dumps(
            value.events, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()

    assert value.event_bytes == len(encode())
    event = {"index": 1, "at": 100.0, "second": True}
    size = (
        len(encode())
        + len(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        + 1
    )
    monkeypatch.setattr(capability, "MAX_TRANSCRIPT", size)
    value.record({"second": True})
    assert value.event_bytes == size
    with pytest.raises(AssertionError):
        value.record({"overflow": ""})
    assert len(value.events) == 2 and len(encode()) == size


@pytest.mark.parametrize("condition", ["construction", "simultaneous", "pending"])
def test_connection_limit_prevents_constructor(monkeypatch, condition):
    value = control(monkeypatch)
    calls = []
    monkeypatch.setattr(capability, "Channel", lambda *a, **kw: calls.append((a, kw)))
    if condition == "construction":
        value.constructions = 3
    elif condition == "simultaneous":
        value.channels = [SimpleNamespace(closed=False), SimpleNamespace(closed=False)]
    else:
        value.pending_connections = 2
    with pytest.raises(AssertionError):
        value.connect("closure", 103)
    assert calls == []


def test_constructor_interruption_is_charged_and_fence_never_reopens(monkeypatch):
    value = control(monkeypatch)
    error = KeyboardInterrupt("after native construction")
    calls = []

    def constructor(*args, **kwargs):
        calls.append(kwargs["deadline"])
        raise error

    monkeypatch.setattr(capability, "Channel", constructor)
    with pytest.raises(KeyboardInterrupt) as caught:
        value.connect("control", 110)
    assert caught.value is error and calls == [103]
    assert value.constructions == value.pending_connections == 1
    assert value.uncertain and not value.owner.resolved()
    with pytest.raises(AssertionError):
        value.connect("control", 110)
    assert len(calls) == 1


def candidate(value):
    return {
        "pid": b"30",
        "started": b"2026-10-23 00:00:01+00",
        "query_started": b"q",
        "database_oid": b"10",
        "username": b"postgres",
        "application": (value.database + "_restore").encode(),
        "backend_type": b"client backend",
        "local": b"true",
        "state": b"active",
        "wait_type": b"Lock",
        "query": COPY,
        "recent": b"true",
        "eligible": b"true",
    }


def prepared(monkeypatch):
    value = control(monkeypatch)
    value.control_identity = {"pid": b"11", "started": b"first"}
    value.blocker_identity = {"pid": b"12", "started": b"second"}
    value.marked, value.deadline, value.work_deadline = b"marked", 105, 130
    value.control = SimpleNamespace()
    value.phase = "candidate"
    return value


@pytest.mark.parametrize(
    "key,bad",
    [
        ("pid", b"11"),
        ("pid", b"0"),
        ("database_oid", b"20"),
        ("username", b"app"),
        ("application", b"other"),
        ("backend_type", b"worker"),
        ("local", b"false"),
        ("recent", b"false"),
        ("started", b""),
        ("query_started", b""),
        ("eligible", b"unknown"),
        ("query", COPY.replace(b"api_keys", b"jobs")),
        ("state", b"idle"),
        ("wait_type", b"IO"),
    ],
)
def test_candidate_must_match_actual_fixed_barrier(monkeypatch, key, bad):
    value, issued = prepared(monkeypatch), []
    monkeypatch.setattr(value, "issue", lambda *a, **kw: issued.append(a))
    row = candidate(value)
    row[key] = bad
    with pytest.raises(AssertionError):
        value.observe_candidate([row])
    assert issued == [] and not value.cancel_attempted


def test_candidate_waits_for_lock_then_cancels_once_with_exact_identity(monkeypatch):
    value, issued = prepared(monkeypatch), []
    monkeypatch.setattr(value, "issue", lambda *a, **kw: issued.append(a))
    row = candidate(value)
    row["eligible"], row["query"] = b"false", b"SET"
    value.observe_candidate([row])
    assert issued == []
    row = candidate(value)
    value.observe_candidate([row])
    assert len(issued) == 1 and issued[0][1] == "cancel"
    assert issued[0][2][-3:] == (row["pid"], row["started"], row["query_started"])
    assert value.phase == "cancel" and value.cancel_attempted
    with pytest.raises(AssertionError):
        value.observe_candidate([row])
    assert len(issued) == 1


def test_candidate_rejects_ambiguity_and_pid_reuse(monkeypatch):
    value = prepared(monkeypatch)
    row = candidate(value)
    with pytest.raises(AssertionError):
        value.observe_candidate([row, row])
    value.candidate = {**row, "started": b"older"}
    with pytest.raises(AssertionError):
        value.observe_candidate([row])
    assert not value.cancel_attempted


def test_child_can_exit_after_request_while_ack_is_draining(monkeypatch):
    value = prepared(monkeypatch)
    child = Child(code=1)
    child.pid = 30
    value.owner.children.append(child)
    value.child = child
    with pytest.raises(AssertionError):
        value.check_child()
    value.cancel_attempted = True
    assert value.check_child() == 1


@pytest.mark.parametrize(
    "row",
    [
        {"candidates": b"0", "cancelled": None},
        {"candidates": b"1", "cancelled": b"false"},
        {"candidates": b"2", "cancelled": b"true"},
    ],
)
def test_cancel_ack_requires_single_confirmed_native_cancellation(monkeypatch, row):
    value = prepared(monkeypatch)
    child = Child(code=1)
    child.pid = 30
    value.owner.children.append(child)
    value.child, value.cancel_attempted, value.phase = child, True, "cancel"
    value.control = SimpleNamespace(step=lambda mask: None, complete=True, take=lambda: [row])
    with pytest.raises(AssertionError):
        value.tick()
    assert not value.cancel_ack


@pytest.mark.parametrize("poll", [wire.pq.PollingStatus.FAILED, wire.pq.PollingStatus.ACTIVE])
def test_connect_rejects_unexpected_poll_state_without_declaring_ready(monkeypatch, poll):
    raw = Raw()
    raw.polls = [poll]
    monkeypatch.setattr(wire.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(wire.pq, "PGconn", SimpleNamespace(connect_start=lambda _: raw))
    value = wire.Channel(b"fixed", deadline=103, record=lambda _: None)
    with pytest.raises(AssertionError):
        value.step()
    assert not value.ready


def test_connect_poll_waits_for_readiness_and_respects_original_deadline(monkeypatch):
    raw = Raw()
    raw.polls = [wire.pq.PollingStatus.READING, wire.pq.PollingStatus.OK]
    clock = [100.0]
    monkeypatch.setattr(wire.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(wire.pq, "PGconn", SimpleNamespace(connect_start=lambda _: raw))
    value = wire.Channel(b"fixed", deadline=103, record=lambda _: None)
    value.step()
    assert value.interest == wire.READ and not value.ready
    value.step()
    assert len(raw.polls) == 1
    clock[0] = 103
    with pytest.raises(TimeoutError):
        value.step(wire.READ)
    assert len(raw.polls) == 1 and not value.ready


def test_expired_intervention_never_issues_cancel(monkeypatch):
    value = prepared(monkeypatch)
    value.deadline = 100
    issued = []
    monkeypatch.setattr(value, "issue", lambda *args: issued.append(args))
    with pytest.raises(TimeoutError):
        value.observe_candidate([candidate(value)])
    assert issued == [] and not value.cancel_attempted


def test_parent_deadline_caps_all_tool_phases_without_refresh(monkeypatch):
    value = control(monkeypatch)
    value.parent_deadline, value.prepared, value.phase = 102, True, "prepared"
    child = Child()
    value.owner.children.append(child)
    value.attach(child, 100)
    assert value.deadline == value.work_deadline == value.cleanup_deadline == 102
    value.parent_deadline = 460
    # Once attached, a later value cannot retroactively extend the saved limits.
    assert value.deadline == value.work_deadline == value.cleanup_deadline == 102


def test_query_limit_rejects_before_channel_send(monkeypatch):
    value = control(monkeypatch)
    calls = []
    channel = SimpleNamespace(send=lambda *args, **kwargs: calls.append((args, kwargs)))
    value.queries = capability.MAX_QUERIES
    with pytest.raises(AssertionError):
        value.issue(channel, "identity", (), 110)
    assert calls == []
    value.queries -= 1
    value.issue(channel, "identity", (), 100.1)
    assert calls == [(("identity", ()), {"deadline": 100.1})]
