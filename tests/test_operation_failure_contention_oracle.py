"""Actual terminal/reservation contention; no provider request is sent."""

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from threading import Event, get_ident

import pytest
import test_migrations_postgres as migration_tests
from failure_postgres_fixture import pg
from operation_failure_paid_oracle import assert_reservation_delta, reservation_intent
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from test_failure_persistence_native_oracle import (
    assert_only_completion_changed,
    genuine_failure_case,
    genuine_terminal_event,
    native_clock,
    native_digest_inputs,
    observe_controls,
    whole_state,
)

from agent_rewind import failure_persistence, failure_terminal, reservation_successor
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.reservation_service import ReservationCoordinator

__all__ = ["pg"]


@pytest.fixture(params=[
    "sqlite",
    pytest.param("postgresql", marks=(
        pytest.mark.f4_owned_postgres,
        pytest.mark.skipif(
            not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL F4 contention"
        ),
    )),
])
def case(request, tmp_path, monkeypatch, record_property):
    selected = request.getfixturevalue("pg") if request.param == "postgresql" else None
    template = request.getfixturevalue("fresh_sqlite_ar6_template") if selected is None else None
    with genuine_failure_case(
        tmp_path, monkeypatch, record_property, pg=selected, fresh_ar6_template=template
    ) as fixture:
        yield fixture.case


@pytest.mark.parametrize("winner", ["terminal", "reserve"])
def test_terminal_and_reservation_exclude_or_serialize_actual_native_writers(
    case, monkeypatch, record_property, winner
):
    """A native blocker/busy observation establishes overlap; time alone does not."""
    postgres = hasattr(case, "pg")
    controls = observe_controls(monkeypatch)
    with genuine_terminal_event(case, controls, record_property) as issued:
        before = issued.claimed
        native_inputs = native_digest_inputs(case)
        intent = reservation_intent(case, issued.fence)
        terminal = failure_terminal.TerminalCoordinator(case.engine, case.authority)
        reserve = ReservationCoordinator(case.engine, case.authority)
        coordinators = {"terminal": terminal, "reserve": reserve}
        loser = "reserve" if winner == "terminal" else "terminal"
        actors, pids, results, elapsed = {}, {}, {}, {}
        locked, contender_started, release = Event(), Event(), Event()
        cadence = Event()
        blockers, busy_codes = [], []
        compiled_binds = {"terminal": [], "reserve": []}
        persist = failure_terminal.persist_verified_failure
        insert = reservation_successor._insert_call
        terminal_lock = failure_terminal.lock_authority
        reserve_lock = reservation_successor.lock_authority
        original_sql = Connection.exec_driver_sql

        def locking(delegate, authority, connection, *args, **kwargs):
            actor = actors[get_ident()]
            if postgres:
                pids[actor] = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                if actor == loser:
                    contender_started.set()
            return delegate(authority, connection, *args, **kwargs)

        def terminal_locked(*args, **kwargs):
            return locking(terminal_lock, *args, **kwargs)

        def reserve_locked(*args, **kwargs):
            return locking(reserve_lock, *args, **kwargs)

        def hold():
            if actors[get_ident()] == winner:
                locked.set()
                assert release.wait(5), "owned F4 winner rendezvous expired"

        def held_persist(connection, token):
            hold()
            return persist(connection, token)

        def held_insert(connection, values):
            hold()
            return insert(connection, values)

        def native_sql(connection, statement, *args, **kwargs):
            actor = actors.get(get_ident())
            target = not postgres and actor == loser and statement == "BEGIN IMMEDIATE"
            if target:
                contender_started.set()
            try:
                return original_sql(connection, statement, *args, **kwargs)
            except Exception as error:
                if target:
                    busy_codes.append(
                        getattr(getattr(error, "orig", None), "sqlite_errorcode", None)
                    )
                raise

        def statement(_connection, _cursor, _sql, _parameters, context, _many):
            actor = actors.get(get_ident())
            if actor is not None and context.compiled is not None:
                compiled_binds[actor].append(len(context.compiled.params or {}))

        def attempt(actor):
            actors[get_ident()] = actor
            started = time.monotonic()
            try:
                try:
                    value = (
                        terminal.complete_failure(case.principal, case.context, issued.event)
                        if actor == "terminal" else reserve._reserve_successor(
                            case.principal, case.context, issued.fence, intent
                        )
                    )
                    results[actor] = {"value": value, "error": None}
                except AdmissionError as error:
                    results[actor] = {"value": None, "error": error}
            finally:
                elapsed[actor] = time.monotonic() - started
                actors.pop(get_ident())

        @contextmanager
        def observed_statements():
            event.listen(case.engine, "before_cursor_execute", statement)
            try:
                yield
            finally:
                event.remove(case.engine, "before_cursor_execute", statement)

        first_tick = native_clock(case)
        with observed_statements(), monkeypatch.context() as patch:
            patch.setattr(failure_terminal, "lock_authority", terminal_locked)
            patch.setattr(reservation_successor, "lock_authority", reserve_locked)
            patch.setattr(failure_terminal, "persist_verified_failure", held_persist)
            patch.setattr(reservation_successor, "_insert_call", held_insert)
            patch.setattr(Connection, "exec_driver_sql", native_sql)
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(attempt, winner)
                second = None
                try:
                    assert locked.wait(3), "winner never reached its protected write"
                    second = executor.submit(attempt, loser)
                    assert contender_started.wait(2)
                    if postgres:
                        assert pids["terminal"] != pids["reserve"]
                        deadline = time.monotonic() + 2
                        with case.pg["owner"].connect() as observer:
                            while time.monotonic() < deadline and not second.done():
                                actual = observer.execute(
                                    text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[loser]}
                                ).scalar_one()
                                if pids[winner] in actual:
                                    blockers.append(list(actual))
                                    break
                                cadence.wait(0.01)
                        assert blockers and not second.done()
                    else:
                        second.result(timeout=5)
                        assert busy_codes == [sqlite3.SQLITE_BUSY]
                    release.set()
                    first.result(timeout=6)
                    second.result(timeout=6)
                finally:
                    release.set()
            assert first.done() and second is not None and second.done()
        last_tick = native_clock(case)
        assert set(results) == {"terminal", "reserve"}
        assert issued.event not in failure_persistence._EVENTS and issued.record.event is None
        assert not failure_terminal._TERMINALS
        assert results[winner]["error"] is None
        assert coordinators[winner].outcome.commit_acknowledged
        after = whole_state(case)
        if winner == "terminal":
            created = results["terminal"]["value"]
            assert created.kind == "created"
            assert results["reserve"]["value"] is None
            assert isinstance(results["reserve"]["error"], AdmissionError)
            assert not reserve.outcome.commit_attempted
            if postgres:
                assert results["reserve"]["error"].reason == "not_eligible"
                assert reserve.outcome.rollback_acknowledged
            else:
                assert not reserve.outcome.begun
            assert_only_completion_changed(
                case, before, after, created.original, native_inputs, (first_tick, last_tick)
            )
        elif postgres:
            assert results["reserve"]["value"].kind == "created"
            assert results["terminal"]["error"] is None
            created = results["terminal"]["value"]
            assert created.kind == "created" and terminal.outcome.commit_acknowledged
            # Expected intermediate image of the specified deltas, not a claimed
            # concurrent database observation.
            expected_reserved = deepcopy(after)
            expected_reserved["tables"]["job_failure_evidence"]["rows"] = []
            next(row for row in expected_reserved["tables"]["jobs"]["rows"]
                 if row["id"] == case.job_id)["status"] = "running"
            assert_reservation_delta(
                case, before, expected_reserved, intent, (first_tick, last_tick)
            )
            assert_only_completion_changed(
                case, expected_reserved, after, created.original, native_inputs,
                (first_tick, last_tick),
            )
        else:
            assert results["reserve"]["value"].kind == "created"
            assert results["terminal"]["value"] is None
            assert isinstance(results["terminal"]["error"], AdmissionError)
            assert not terminal.outcome.begun and not terminal.outcome.commit_attempted
            assert_reservation_delta(case, before, after, intent, (first_tick, last_tick))

        facts = {}
        for actor, coordinator in coordinators.items():
            work = coordinator._work
            assert work is not None
            cleanup = sum(after_ - before_ for target, kind, before_, after_ in controls
                          if target is work and kind not in {"begin", "commit"})
            assert work._invocation_started is not None
            assert 0 <= cleanup <= 8 and work.statements - cleanup <= 504
            assert work.statements <= 512 and work.instructions < 20_000_000
            assert elapsed[actor] < 10
            assert max(compiled_binds[actor], default=0) <= 64
            assert work._detached and not work._listeners and work._connection is None
            assert work._started is None and work._lease is None
            facts[actor] = {
                "outcome": asdict(coordinator.outcome), "total": work.statements,
                "cleanup": cleanup, "elapsed_seconds": elapsed[actor],
                "vm": work.instructions,
                "maximum_compiled_binds": max(compiled_binds[actor], default=0),
            }
        assert case.engine.pool.checkedout() == 0
        record_property("f4_terminal_reservation_contention", json.dumps({
            "winner": winner, "native_postgres_pids": pids,
            "native_postgres_blockers": blockers, "native_sqlite_busy": busy_codes,
            "observations": facts, "no_provider_request": True,
        }, sort_keys=True))
