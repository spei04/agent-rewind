"""A concrete, finite control capability for the single api_keys COPY barrier."""

import json
import os
import re
import selectors
import time

from ledger_restore_interruption_contracts import (
    COPY,
    MAX_EVENTS,
    MAX_OBSERVATIONS,
    MAX_QUERIES,
    MAX_TRANSCRIPT,
    one,
    positive,
)
from ledger_restore_interruption_pq import Channel, check
from psycopg.conninfo import make_conninfo


class InterruptionControl:
    def __init__(
        self, owner, *, socket, token, database_oid, relation_oid, directory, parent_deadline
    ):
        assert type(token) is str and re.fullmatch(r"[0-9a-f]{32}", token)
        assert type(socket) is str and socket.startswith("/") and "\0" not in socket
        assert not any(key.startswith("PG") for key in os.environ), "ambient libpq configuration"
        check(parent_deadline)
        assert parent_deadline <= time.monotonic() + 360
        self.parent_deadline = parent_deadline
        self.owner, self.socket, self.token, self.directory = owner, socket, token, directory
        self.database = "ar_restore_" + token
        self.database_oid, self.relation_oid = (
            str(database_oid).encode(),
            str(relation_oid).encode(),
        )
        assert type(database_oid) is type(relation_oid) is int
        positive(self.database_oid)
        positive(self.relation_oid)
        self.events, self.channels, self.queries = [], [], 0
        self.event_bytes, self.observations, self.absences = 2, 0, 0
        self.constructions, self.pending_connections = 0, 0
        self.prepared = self.completed = self.uncertain = False
        self.cancel_attempted = self.cancel_ack = self.restore_absent = False
        self.control = self.blocker = self.child = self.candidate = None
        self.control_identity = self.blocker_identity = None
        self.first, self.marked, self.phase = None, None, "new"
        self.deadline = self.work_deadline = self.cleanup_deadline = None
        self.next_poll = 0.0
        owner.bind_control(self)

    def record(self, value):
        assert "index" not in value and "at" not in value
        event = {"index": len(self.events), "at": time.monotonic(), **value}
        # The transcript contract is this exact compact UTF-8 JSON list encoding.
        encoded = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)
        size = self.event_bytes + len(encoded.encode()) + bool(self.events)
        assert len(self.events) < MAX_EVENTS and size <= MAX_TRANSCRIPT
        self.events.append(event)
        self.event_bytes = size

    def remember(self, error):
        self.first = self.first or error
        self.uncertain = True
        self.owner.remember(error)

    def info(self, suffix, *, blocker=False):
        return make_conninfo(
            host=self.socket,
            port="55432",
            dbname=self.database if blocker else "postgres",
            user="postgres",
            application_name=self.database + "_" + suffix,
            connect_timeout="3",
            sslmode="disable",
            gssencmode="disable",
            passfile="/dev/null",
            client_encoding="UTF8",
            options="-c timezone=UTC -c datestyle=ISO,YMD "
            + (
                "-c statement_timeout=2000 -c lock_timeout=1000"
                if blocker
                else "-c statement_timeout=200 -c lock_timeout=100"
            ),
        ).encode()

    def connect(self, suffix, deadline, *, blocker=False):
        check(deadline)
        assert not self.uncertain and self.constructions < 3
        assert self.pending_connections + sum(not item.closed for item in self.channels) < 2
        # Charge before entering a constructor: an interrupted construction may
        # already own a backend even when no Python handle returned.
        self.constructions += 1
        self.pending_connections += 1
        try:
            self.record({"connect": suffix})
            channel = Channel(
                self.info(suffix, blocker=blocker),
                deadline=min(deadline, time.monotonic() + 3),
                record=self.record,
            )
            self.channels.append(channel)
            self.pending_connections -= 1
            self.pump(channel, deadline, connecting=True)
            return channel
        except BaseException as error:
            self.remember(error)
            raise

    def pump(self, channel, deadline, *, connecting=False):
        with selectors.DefaultSelector() as selector:
            while not (channel.ready if connecting else channel.complete):
                check(deadline)
                channel.step()
                if channel.ready if connecting else channel.complete:
                    break
                fd = channel.fd
                selector.register(fd, channel.interest)
                limit = min(deadline, channel.deadline)
                check(limit)
                for _key, mask in selector.select(min(0.02, limit - time.monotonic())):
                    channel.step(mask)
                selector.unregister(fd)
            check(deadline)

    def issue(self, channel, name, parameters, deadline, *, seconds=0.25):
        check(deadline)
        assert self.queries < MAX_QUERIES
        self.queries += 1
        channel.send(name, tuple(parameters), deadline=min(deadline, time.monotonic() + seconds))

    def query(self, channel, name, parameters, deadline, *, seconds=0.25):
        self.issue(channel, name, parameters, deadline, seconds=seconds)
        self.pump(channel, deadline)
        return channel.take()

    def identity(self, channel, suffix, deadline, *, blocker=False):
        result = one(self.query(channel, "identity", (), deadline))
        assert positive(result["pid"]) == channel.raw.backend_pid
        assert result["database"] == (self.database if blocker else "postgres").encode()
        assert result["username"] == b"postgres"
        assert result["application"] == (self.database + "_" + suffix).encode()
        assert result["server_version"] == b"160015" and result["local"] == b"true"
        assert result["statement_timeout"] == (b"2s" if blocker else b"200ms")
        assert result["lock_timeout"] == (b"1s" if blocker else b"100ms")
        assert result["started"] and len(result["started"]) < 64
        return result

    def prepare(self):
        assert self.phase == "new" and self.owner.prior_tools_terminal()
        self.deadline = min(self.parent_deadline, time.monotonic() + 10)
        try:
            self.control = self.connect("control", self.deadline)
            self.control_identity = self.identity(self.control, "control", self.deadline)
            self.blocker = self.connect("blocker", self.deadline, blocker=True)
            self.blocker_identity = self.identity(
                self.blocker, "blocker", self.deadline, blocker=True
            )
            assert self.control_identity["pid"] != self.blocker_identity["pid"]
            info = one(self.query(self.blocker, "blocker-info", (), self.deadline))
            assert info == {"database_oid": self.database_oid, "relation_oid": self.relation_oid}
            self.query(self.blocker, "begin", (), self.deadline, seconds=2)
            self.query(self.blocker, "lock", (), self.deadline, seconds=2)
            value = one(
                self.query(
                    self.control,
                    "prelaunch",
                    (
                        self.database_oid,
                        self.blocker_identity["pid"],
                        self.blocker_identity["started"],
                        self.relation_oid,
                        (self.database + "_restore").encode(),
                    ),
                    self.deadline,
                )
            )
            assert (
                value["clients"] == b"1" and value["restores"] == b"0" and value["held"] == b"true"
            )
            assert value["marked"] and len(value["marked"]) < 64
            self.marked, self.prepared, self.phase = value["marked"], True, "prepared"
            self.record({"prepared": True})
        except BaseException as error:
            self.remember(error)
            self.abort()
            raise

    def attach(self, child, started):
        assert self.prepared and self.phase == "prepared" and self.owner.children[-1] is child
        assert not self.owner.pending and not self.owner.uncertain
        self.child = child
        self.work_deadline = min(started + 30, self.parent_deadline)
        self.cleanup_deadline = min(started + 40, self.parent_deadline)
        self.deadline, self.phase = min(started + 5, self.parent_deadline), "candidate"
        self.record(
            {
                "attached_pid": child.pid,
                "intervention_deadline": self.deadline,
                "work_deadline": self.work_deadline,
                "cleanup_deadline": self.cleanup_deadline,
            }
        )

    def parameters(self):
        return (
            self.database_oid,
            self.blocker_identity["pid"],
            self.blocker_identity["started"],
            self.marked,
            self.relation_oid,
            (self.database + "_restore").encode(),
            COPY,
        )

    def check_child(self):
        assert self.child is not None and self.owner.children[-1] is self.child
        assert not self.owner.pending and not self.owner.uncertain and not self.uncertain
        try:
            code = self.child.poll()
        except BaseException as error:
            self.remember(error)
            raise
        if code is not None and not self.cancel_attempted:
            raise AssertionError("restore exited before acknowledged cancellation")
        return code

    def tick(self, mask=0):
        self.check_child()
        check(self.deadline)
        channel = self.control
        channel.step(mask)
        if channel.complete:
            rows = channel.take()
            # take clears query; phase is the independent expected operation.
            if self.phase == "candidate":
                self.observe_candidate(rows)
            elif self.phase == "cancel":
                assert one(rows) == {"candidates": b"1", "cancelled": b"true"}
                check(self.deadline)
                self.cancel_ack, self.phase = True, "absence"
                self.deadline = self.work_deadline
                self.record({"cancel_acknowledged": True})
            elif self.phase == "absence":
                row = one(rows)
                assert row["remaining"] in (b"0", b"1")
                self.restore_absent = row["remaining"] == b"0"
                self.next_poll = time.monotonic() + 0.02
            else:
                raise AssertionError("unexpected control phase")
        if channel.query is not None or self.restore_absent or time.monotonic() < self.next_poll:
            return
        if self.phase == "candidate":
            assert self.observations < MAX_OBSERVATIONS
            self.observations += 1
            self.issue(channel, "candidate", self.parameters(), self.deadline)
        elif self.phase == "absence":
            assert self.absences < MAX_OBSERVATIONS
            self.absences += 1
            assert self.candidate is not None
            self.issue(
                channel,
                "restore-absence",
                (
                    (self.database + "_restore").encode(),
                    self.candidate["pid"],
                    self.candidate["started"],
                ),
                self.deadline,
            )

    def observe_candidate(self, rows):
        assert len(rows) <= 1, "ambiguous target backend"
        self.next_poll = time.monotonic() + 0.02
        if not rows:
            return
        value = rows[0]
        positive(value["pid"])
        assert value["pid"] not in (self.control_identity["pid"], self.blocker_identity["pid"])
        assert value["database_oid"] == self.database_oid and value["username"] == b"postgres"
        assert value["application"] == (self.database + "_restore").encode()
        assert (
            value["backend_type"] == b"client backend"
            and value["local"] == value["recent"] == b"true"
        )
        assert value["started"] and value["query_started"]
        if self.candidate is not None:
            assert (value["pid"], value["started"]) == (
                self.candidate["pid"],
                self.candidate["started"],
            )
        self.candidate = value
        if value["eligible"] != b"true":
            assert value["eligible"] == b"false"
            return
        assert (
            value["query"] == COPY and value["state"] == b"active" and value["wait_type"] == b"Lock"
        )
        check(self.deadline)
        assert not self.cancel_attempted
        self.record(
            {
                "blocked_copy": {
                    key: None if item is None else item.decode() for key, item in value.items()
                }
            }
        )
        self.cancel_attempted, self.phase = True, "cancel"
        self.issue(
            self.control,
            "cancel",
            self.parameters() + (value["pid"], value["started"], value["query_started"]),
            self.deadline,
        )

    def finish(self):
        assert self.cancel_ack and self.restore_absent and self.check_child() is not None
        check(self.cleanup_deadline)
        self.phase = "closing"
        self.query(self.blocker, "rollback", (), self.cleanup_deadline, seconds=2)
        self.blocker.close()
        while True:
            assert self.absences < MAX_OBSERVATIONS
            self.absences += 1
            value = one(
                self.query(
                    self.control,
                    "blocker-absence",
                    (
                        (self.database + "_blocker").encode(),
                        self.blocker_identity["pid"],
                        self.blocker_identity["started"],
                    ),
                    self.cleanup_deadline,
                )
            )
            if value["remaining"] == b"0":
                break
            assert value["remaining"] == b"1"
            with selectors.DefaultSelector() as selector:
                check(self.cleanup_deadline)
                selector.select(min(0.02, self.cleanup_deadline - time.monotonic()))
        self.control.close()
        # The fence is still unresolved. Only this exact final capability runs.
        deadline = min(self.cleanup_deadline, time.monotonic() + 3.5)
        final = self.connect("closure", deadline)
        value = one(
            self.query(
                final,
                "final-absence",
                (
                    self.control_identity["pid"],
                    self.control_identity["started"],
                    (self.database + "_control").encode(),
                    (self.database + "_restore").encode(),
                    self.database_oid,
                ),
                deadline,
            )
        )
        assert value["control"] == value["restores"] == value["targets"] == b"0"
        assert positive(value["observer"]) == final.raw.backend_pid
        assert final.raw.db == b"postgres" and final.raw.user == b"postgres"
        final.close()
        check(deadline)
        assert not self.uncertain
        self.record({"final_observer_complete": True, "own_server_disappearance_claimed": False})
        self.completed, self.phase = True, "complete"

    def abort(self):
        self.uncertain = True
        for channel in self.channels:
            try:
                channel.close()
            except BaseException as error:
                self.remember(error)

    def report(self):
        return {
            "phase": self.phase,
            "completed": self.completed,
            "uncertain": self.uncertain,
            "cancel_attempted": self.cancel_attempted,
            "cancel_acknowledged": self.cancel_ack,
            "restore_absent": self.restore_absent,
            "queries": self.queries,
            "observations": self.observations,
            "absence_queries": self.absences,
            "connections": len(self.channels),
            "constructions": self.constructions,
            "pending_connections": self.pending_connections,
            "transcript_bytes": self.event_bytes,
            "events": self.events,
        }
