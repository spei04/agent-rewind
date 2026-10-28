"""Independent native compatibility snapshots and immutable-projection controls.

Seeded corrupt snapshots are fixture constructions, never service-write evidence.
Only the last three cases invoke the actual reviewed ledger writer.
"""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import psycopg
import pytest
import test_migrations_postgres as migration_tests
from ledger_reader_fixture import (
    RowTransferWatch,
    append_provision,
    complete_postgres_ar6,
    identifier,
    later_admitted_call,
    postgres_snapshot,
    seed_ar7,
)
from sqlalchemy import create_engine, text
from test_ledger_operator_postgres import PostgresTrace
from test_ledger_reader_native import (
    NativeParameterWatch,
    _assert_reviewed_ctes,
    _transaction_write_counters,
    _tuple_write_delta,
)
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations import compatibility as guard
from agent_rewind.migrations import ledger_reader_history as history_reader
from agent_rewind.migrations import service
from agent_rewind.migrations.ledger_compatibility_sql import SQL
from agent_rewind.migrations.schema import LEDGER, catalog, installed_profile

__all__ = ["observed_reader"]
pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in native ledger compatibility"
)
MODE = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"

# PostgreSQL renderings of the independently reviewed v3 projection packet.
_PG_COMPATIBILITY_CTES = frozenset(
    {
        "798861aad8f91c6f7dd4288db8765d1c2f717afe4dc5052ac9aa27623799f2b8",
        "0321e1797efdccde15c348231e5d5b77cdd7797d9167572040f263e2107759eb",
        "942a9e9bc4c5860f087440d23707584edc6e7c37904860a26db8e52004d989eb",
        "d2da7c36ac8a94e98a66cb7b22b9f3c4cfe06e3757637d4983d682a4f3e2f03d",
    }
)


def _statements(engine):
    return {
        str(text(query).compile(dialect=engine.dialect)): name
        for name, query in SQL.items()
        if name.startswith("pg_")
    }


def _grant_runtime(pg):
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {pg['app_role']}")
        connection.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {pg['app_role']}"
        )
    drain(pg)


def _observe(
    pg, monkeypatch, record_property, *, code, configure=None, unchanged=True, wait_drain=True
):
    """Observe the real wrapper; all oracle SQL also consumes its original deadline."""
    if wait_drain:
        _grant_runtime(pg)
    before = postgres_snapshot(pg["owner"])
    engine = create_engine(
        pg["app"].url, pool_size=1, max_overflow=0, pool_timeout=guard.POOL_TIMEOUT_SECONDS
    )
    guard.configure_runtime_engine(engine, production=True)
    # Dialect initialization is separate setup evidence, not an adapter target.
    with engine.connect():
        pass
    probe = SimpleNamespace(raw=None, modes=None, counters=None, invalidated=None, result=None)
    with monkeypatch.context() as local:
        trace = PostgresTrace(local)
        parameters = NativeParameterWatch(local, trace)
        statements = _statements(engine)
        transfer = RowTransferWatch(local, {}, statements=statements)
        original = guard._inspection

        @contextmanager
        def inspection(connection, **kwargs):
            probe.raw = connection.connection.driver_connection
            trace.phase = "compatibility-setup"
            try:
                with original(connection, **kwargs) as checks:
                    trace.phase = "oracle"
                    probe.modes = (
                        connection.exec_driver_sql("SHOW transaction_read_only").scalar_one(),
                        connection.exec_driver_sql("SHOW transaction_isolation").scalar_one(),
                    )
                    assert probe.modes == ("on", "repeatable read")
                    assert connection.exec_driver_sql("SHOW track_counts").scalar_one() == "on"
                    first = _transaction_write_counters(connection)
                    trace.phase = "compatibility"
                    try:
                        yield checks
                        assert connection.connection.driver_connection is probe.raw
                        trace.phase = "oracle"
                        probe.counters = _tuple_write_delta(
                            first, _transaction_write_counters(connection)
                        )
                        assert probe.counters == {}
                    finally:
                        trace.phase = "cleanup"
            finally:
                probe.invalidated = connection.invalidated
                assert not list(connection.dispatch.before_cursor_execute)

        local.setattr(guard, "_inspection", inspection)
        probe.trace, probe.parameters, probe.transfer = trace, parameters, transfer
        if configure is not None:
            configure(local, probe)
        try:
            probe.result = guard.runtime_schema_compatibility(engine)
            expected_status = "unavailable" if code == "schema_unavailable" else "incompatible"
            assert probe.result == guard.CompatibilityResult(expected_status, code)
            assert engine.pool.checkedout() == 0
            assert probe.raw is not None
            assert probe.raw.closed or probe.raw.info.transaction_status == 0
            calls = [
                (phase, raw_id, hashlib.sha256(sql.encode()).hexdigest())
                for phase, kind, raw_id, sql in trace.events
                if kind == "sql-call" and phase.startswith("compatibility")
            ]
            receipts = [
                value for value in parameters.receipts if value["phase"].startswith("compatibility")
            ]
            assert [
                (value["phase"], value["raw_id"], value["sql_sha256"]) for value in receipts
            ] == calls
            assert receipts and all(value["raw_id"] == id(probe.raw) for value in receipts)
            assert all(type(value["parameter_count"]) is int for value in receipts)
            hashes = {hashlib.sha256(sql.encode()).hexdigest() for sql in statements}
            assert hashes == _PG_COMPATIBILITY_CTES
            projection = [value for value in receipts if value["sql_sha256"] in hashes]
            assert all(0 <= value["parameter_count"] <= 16 for value in projection)
            commands = trace.sql("compatibility")
            assert all(
                sql.lstrip().upper().startswith(("SELECT", "WITH", "SHOW", "SET LOCAL"))
                for sql in commands
            )
            # The four compatibility CTEs were byte-reviewed separately. Other ar7
            # CTEs retain the frozen reader allowlist; no WITH-prefix write oracle.
            if any(sql in statements for sql in commands):
                _assert_reviewed_ctes([sql for sql in commands if sql not in statements])
            assert not any(
                phase.startswith("compatibility")
                and kind == "command"
                and sql
                and sql.lstrip().upper().startswith(("DECLARE", "FETCH"))
                for phase, kind, _, sql in trace.events
            )
        finally:
            try:
                engine.dispose()
            finally:
                trace.stop()
            record_property("compatibility_native_trace", json.dumps(trace.events))
            record_property("compatibility_parameters", json.dumps(parameters.receipts))
            record_property("compatibility_transfers", json.dumps(transfer.statement_hits))
            record_property(
                "compatibility_outcome",
                json.dumps(
                    {
                        "code": probe.result.code if probe.result else None,
                        "modes": probe.modes,
                        "tuple_delta": probe.counters,
                        "invalidated": probe.invalidated,
                        "raw_closed_after_dispose": probe.raw.closed if probe.raw else None,
                    }
                ),
            )
    if wait_drain:
        drain(pg)
    if unchanged:
        assert postgres_snapshot(pg["owner"]) == before
        if wait_drain:
            drain(pg)
    return probe


@pytest.fixture
def seeded(request, pg, observed_reader):
    kind = request.param
    case = complete_postgres_ar6(pg, legacy=kind == "legacy")
    seed_ar7(case, empty_accounts=kind == "empty")
    if kind == "provision":
        account = deepcopy(case.manifest["accounts"][0])
        account.update(
            id=identifier(7_000_000),
            period_start="2030-01-01T00:00:00.000000Z",
            period_end="2031-01-01T00:00:00.000000Z",
        )
        append_provision(case, [account])
    if kind == "evolved":
        later_admitted_call(case, effect="reserved", future_zero_period=True)
    drain(pg)
    yield case
    case.dispose()
    drain(pg)


@pytest.mark.parametrize(
    "seeded", ["empty", "fresh", "legacy", "provision", "evolved"], indirect=True
)
def test_postgres_complete_history_is_nonready_readonly(seeded, pg, monkeypatch, record_property):
    probe = _observe(pg, monkeypatch, record_property, code="migration_only")
    assert probe.modes == ("on", "repeatable read") and probe.counters == {}
    if seeded.legacy:
        assert seeded.opening["organization_opening_microusd"] == 245000
    assert any(hit["name"] == "pg_immutable_accounts_gate" for hit in probe.transfer.statement_hits)


@pytest.mark.parametrize("drift", ["account-limit", "original-opening"])
def test_postgres_corrupt_pretrigger_snapshot_reaches_native_equality(
    pg, observed_reader, monkeypatch, record_property, drift
):
    import ledger_reader_fixture as fixture

    case = complete_postgres_ar6(pg, legacy=True)
    installer = fixture.create_ledger_constraints
    setup = []

    def corrupt_then_install(connection):
        assert connection.dialect.name == "postgresql"
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND NOT t.tgisinternal"
            ).scalar_one()
            == 0
        )
        if drift == "account-limit":
            row = connection.exec_driver_sql(
                "SELECT id,limit_microusd FROM budget_accounts WHERE scope='organization'"
            ).one()
            assert 0 <= row[1] < 9223372036854775807
            changed = connection.execute(
                text(
                    "UPDATE budget_accounts SET limit_microusd=:new "
                    "WHERE id=:id AND limit_microusd=:old"
                ),
                {"id": row[0], "old": row[1], "new": row[1] + 1},
            )
        else:
            row = connection.exec_driver_sql(
                "SELECT id,legacy_reserved_microusd FROM jobs ORDER BY id LIMIT 1"
            ).one()
            assert 0 <= row[1] < 9223372036854775807
            changed = connection.execute(
                text(
                    "UPDATE jobs SET legacy_reserved_microusd=:new "
                    "WHERE id=:id AND legacy_reserved_microusd=:old"
                ),
                {"id": row[0], "old": row[1], "new": row[1] + 1},
            )
        assert changed.rowcount == 1
        setup.append((row[0], row[1], row[1] + 1))
        installer(connection)

    try:
        # Only test setup is wrapped. The real installer is never disabled or changed.
        with monkeypatch.context() as local:
            local.setattr(fixture, "create_ledger_constraints", corrupt_then_install)
            seed_ar7(case)
        assert len(setup) == 1 and case.opening["organization_opening_microusd"] == 245000
        with case.engine.connect() as connection:
            assert catalog(connection) == installed_profile("postgresql", LEDGER)
            field, table = (
                ("limit_microusd", "budget_accounts")
                if drift == "account-limit"
                else ("legacy_reserved_microusd", "jobs")
            )
            actual = connection.execute(
                text(f"SELECT {field} FROM {table} WHERE id=:id"), {"id": setup[0][0]}
            ).scalar_one()
            assert actual == setup[0][2]
        record_property("corrupt_fixture", json.dumps({"kind": drift, "cell": setup[0]}))
        probe = _observe(pg, monkeypatch, record_property, code="schema_incompatible")
        names = {hit["name"] for hit in probe.transfer.statement_hits if hit["rows"] > 0}
        assert "pg_immutable_accounts_body" in names
        if drift == "original-opening":
            assert "pg_original_jobs_body" in names
        else:
            assert "pg_original_jobs_body" not in names
    finally:
        case.dispose()
        drain(pg)


@pytest.mark.parametrize("revision", ["ar2", "ar7"])
def test_postgres_concurrent_metadata_commit_cannot_mix_snapshots(
    pg, observed_reader, monkeypatch, record_property, revision
):
    case = None
    if revision == "ar2":
        service.install(pg["owner"], "synthetic-guard-postgres")
    else:
        case = seed_ar7(complete_postgres_ar6(pg, legacy=True))
    _grant_runtime(pg)
    before = postgres_snapshot(pg["owner"])
    table = "installation_adoptions" if revision == "ar2" else "migration_progress"
    field = "mapping_digest" if revision == "ar2" else "source_digest"
    predicate = (
        "singleton=1"
        if revision == "ar2"
        else ("revision='ar_0007_ledger' AND phase='ledger_opening'")
    )
    with pg["owner"].connect() as mutation:
        found = mutation.exec_driver_sql(f"SELECT * FROM {table} WHERE {predicate}")
        keys = list(found.keys())
        old_row = tuple(found.one())
        position = keys.index(field)
        old = old_row[position]
        new = ("1" if old[0] != "1" else "2") + old[1:]
        assert old != new and len(old) == len(new) == 64
        mutation.rollback()
        commits = []

        def configure(local, probe):
            def commit_fixture():
                previous = probe.trace.phase
                probe.trace.phase = "concurrent-fixture"
                try:
                    mutation.exec_driver_sql("SET LOCAL statement_timeout='250ms'")
                    mutation.exec_driver_sql("SET LOCAL lock_timeout='250ms'")
                    changed = mutation.execute(
                        text(f"UPDATE {table} SET {field}=:new WHERE {predicate} AND {field}=:old"),
                        {"new": new, "old": old},
                    )
                    assert changed.rowcount == 1
                    mutation.commit()
                    commits.append(True)
                finally:
                    probe.trace.phase = previous

            if revision == "ar2":
                original = guard._installed

                def installed(*args, **kwargs):
                    assert not commits
                    commit_fixture()
                    return original(*args, **kwargs)

                local.setattr(guard, "_installed", installed)
            else:
                original = history_reader._query
                gate_rows = []

                def query(connection, name, parameters):
                    if name == "H60_ledger_progress_body":
                        assert gate_rows and not commits
                        commit_fixture()
                    rows = original(connection, name, parameters)
                    if name == "H60_ledger_progress_gate":
                        gate_rows.extend(rows)
                    if name == "H60_ledger_progress_body":
                        opening = next(row for row in rows if row["phase"] == "ledger_opening")
                        assert opening["source_digest"] == old
                    return rows

                local.setattr(history_reader, "_query", query)

        _observe(
            pg,
            monkeypatch,
            record_property,
            code="migration_only",
            configure=configure,
            unchanged=False,
            wait_drain=False,
        )
        assert commits == [True]
    expected = deepcopy(before)
    rows = expected["rows"][table]
    assert old_row in rows
    changed_row = list(old_row)
    changed_row[position] = new
    rows[rows.index(old_row)] = tuple(changed_row)
    expected["rows"][table] = sorted(rows, key=repr)
    assert postgres_snapshot(pg["owner"]) == expected
    _observe(pg, monkeypatch, record_property, code="schema_incompatible")
    record_property(
        "snapshot_interleave",
        json.dumps(
            {
                "revision": revision,
                "field": field,
                "old": old,
                "new": new,
                "raw_fixture_commits": len(commits),
            }
        ),
    )
    if case is not None:
        case.dispose()
    drain(pg)


@pytest.mark.parametrize("boundary", ["statement-setter", "lock-setter", "setup", "target"])
@pytest.mark.parametrize("expired", [False, True])
def test_postgres_native_return_deadline_never_publishes(
    pg, monkeypatch, record_property, boundary, expired
):
    service.install(pg["owner"], "synthetic-guard-postgres")
    calls = []
    now = [0.0]

    def configure(local, probe):
        local.setattr(guard, "time", SimpleNamespace(monotonic=lambda: now[0]))
        original = psycopg.Cursor.execute

        def execute(cursor, query, *args, **kwargs):
            sql = query.decode() if isinstance(query, bytes) else str(query)
            result = original(cursor, query, *args, **kwargs)
            matches = {
                "statement-setter": sql.startswith("SET LOCAL statement_timeout"),
                "lock-setter": sql.startswith("SET LOCAL lock_timeout"),
                "setup": sql == MODE,
                "target": probe.trace.phase == "compatibility" and sql.startswith("SELECT"),
            }[boundary]
            if not calls and matches and cursor.connection is probe.raw:
                calls.append(sql)
                now[0] = 2.0 if expired else 1.9
            return result

        local.setattr(psycopg.Cursor, "execute", execute)

    probe = _observe(
        pg,
        monkeypatch,
        record_property,
        code="schema_unavailable" if expired else "migration_only",
        configure=configure,
    )
    assert len(calls) == 1
    statements = [
        sql
        for phase, kind, _, sql in probe.trace.events
        if phase.startswith("compatibility") and kind == "sql-call"
    ]
    index = statements.index(calls[0])
    following = statements[index + 1 :]
    if expired:
        assert following == []
    elif boundary == "statement-setter":
        assert following[0].startswith("SET LOCAL lock_timeout")
        cap = int(following[0].split("'")[1].removesuffix("ms"))
        assert 0 < cap <= 100
    record_property(
        "controlled_clock",
        json.dumps(
            {
                "boundary": boundary,
                "expired": expired,
                "advanced_to": now[0],
                "interpretation": "Native delegation then module-local clock advancement",
            }
        ),
    )


@pytest.mark.parametrize("after_native", [False, True])
def test_postgres_rollback_fault_never_returns_migration_only(
    pg, monkeypatch, record_property, after_native
):
    service.install(pg["owner"], "synthetic-guard-postgres")
    faults = []

    def configure(local, probe):
        original = psycopg.Connection.rollback

        def rollback(raw):
            if probe.trace.phase == "cleanup" and raw is probe.raw and not faults:
                faults.append(id(raw))
                if after_native:
                    original(raw)
                raise OSError("synthetic-owned-inspection-rollback")
            return original(raw)

        local.setattr(psycopg.Connection, "rollback", rollback)

    probe = _observe(
        pg, monkeypatch, record_property, code="schema_unavailable", configure=configure
    )
    assert faults == [id(probe.raw)]
    assert probe.invalidated and probe.raw.closed
    record_property("rollback_injection", json.dumps({"after_native": after_native}))


@pytest.mark.parametrize("history", ["empty", "legacy", "later"])
def test_postgres_actual_service_state_is_still_migration_only(
    pg, observed_reader, monkeypatch, record_property, history
):
    from ledger_service_fixture import service_postgres_state
    from test_ledger_compatibility import assert_actual_service_history

    state = service_postgres_state(pg, history=history)
    try:
        assert state.initial_receipt.outcome == "complete"
        assert state.initial_receipt.imported_opening_microusd == (
            0 if history == "empty" else 245000
        )
        if history == "later":
            assert state.later_receipt.sequence == 1
        assert_actual_service_history(
            state.case, state.initial_manifest, state.initial_receipt, state.later_manifest
        )
        probe = _observe(pg, monkeypatch, record_property, code="migration_only")
        assert probe.counters == {}
        record_property("actual_service_receipt", state.initial_receipt.model_dump_json())
    finally:
        state.case.dispose()
        drain(pg)
