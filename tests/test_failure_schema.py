"""Native relation/guard proof only, before a successor installer or producer exists.

Fixtures create synthetic ar7 state; no readiness override or live failure
authority is introduced. Native affinity can coerce bound values, so caller
type validation remains a separate future producer responsibility.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event

import pytest
import test_ledger_constraints_postgres as ledger_pg_tests
import test_ledger_schema as ledger_tests
import test_migrations_postgres as migration_tests
from ledger_reader_fixture import complete_ar6
from ledger_service_fixture import service_postgres_state
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from test_admission_schema import DIGEST, JOB, OPERATION, OTHER, PROJECT, operation
from test_artifact_metadata import object_value
from test_ledger_schema import call, triple
from test_ledger_service import intent, invoke

from agent_rewind.artifact_metadata import record_verified, register_ref
from agent_rewind.migrations.failure_schema import create_failure_schema
from agent_rewind.migrations.schema import LEDGER, MigrationRefused, catalog, installed_profile

ledger_db = ledger_tests.ledger_db
ledger_pg = ledger_pg_tests.ledger_pg
pg = migration_tests.pg

TABLE = "job_failure_evidence"
COLUMNS = [
    ("schema_version", "INTEGER", False),
    ("kind", "VARCHAR(17)", False),
    ("project_id", "VARCHAR(32)", False),
    ("job_resource_kind", "VARCHAR(3)", False),
    ("job_id", "VARCHAR(32)", False),
    ("operation_id", "VARCHAR(32)", True),
    ("lease_generation", "BIGINT", False),
    ("job_status", "VARCHAR(9)", False),
    ("cause", "VARCHAR(18)", True),
    ("phase", "VARCHAR(15)", True),
    ("origin_kind", "VARCHAR(16)", False),
    ("correlation_id", "VARCHAR(32)", False),
    ("association_sha256", "VARCHAR(64)", False),
    ("source_sha256", "VARCHAR(64)", False),
    ("created_at_micros", "BIGINT", False),
]


def rows(connection):
    return {
        name: sorted(
            [tuple(row) for row in connection.exec_driver_sql(f'SELECT * FROM "{name}"')],
            key=repr,
        )
        for name in inspect(connection).get_table_names()
    }


def marker(**changes):
    value = {
        "schema_version": 1,
        "kind": "historical_marker",
        "project_id": PROJECT,
        "job_resource_kind": "job",
        "job_id": JOB,
        "operation_id": None,
        "lease_generation": 0,
        "job_status": "succeeded",
        "cause": None,
        "phase": None,
        "origin_kind": "migration_marker",
        "correlation_id": "e" * 32,
        "association_sha256": "a" * 64,
        "source_sha256": "b" * 64,
        "created_at_micros": 0,
    }
    return value | changes


def insert(connection, value, *, prefix="INSERT", suffix=""):
    connection.execute(
        text(
            f"{prefix} INTO {TABLE} ("
            + ",".join(value)
            + ") VALUES ("
            + ",".join(":" + field for field in value)
            + ") "
            + suffix
        ),
        value,
    )


def v2(connection, *, status="failed", cancel=False, correlation="f" * 32):
    connection.execute(
        text(
            "UPDATE jobs SET payload_version=2,execution_config_ref=:digest,"
            "execution_config_digest=:digest,lease_generation=1,status=:status,cancel=:cancel,"
            "error=NULL,result=NULL WHERE id=:job"
        ),
        {"digest": DIGEST, "status": status, "cancel": cancel, "job": JOB},
    )
    operation(connection, failure_correlation_id=correlation)
    return marker(
        kind="verified_failure",
        operation_id=OPERATION,
        lease_generation=1,
        job_status=status,
        cause="internal_fault",
        phase="outcome_unknown",
        origin_kind="admission",
        correlation_id="f" * 32,
    )


@pytest.fixture
def failure_db(ledger_db):
    engine, _ = ledger_db
    with engine.begin() as connection:
        assert catalog(connection) == installed_profile(engine.dialect.name, LEDGER)
        before = rows(connection)
        create_failure_schema(connection)
        after = rows(connection)
        assert after.pop(TABLE) == []
        assert after == before
    return engine


def test_native_shape_and_dormant_predecessor_refusal(failure_db):
    with failure_db.connect() as connection:
        observer = inspect(connection)
        assert len(observer.get_table_names()) == 21
        columns = observer.get_columns(TABLE)
        assert [(c["name"], str(c["type"]), c["nullable"]) for c in columns] == COLUMNS
        assert all(c["default"] is None and not c.get("computed") for c in columns)
        assert observer.get_pk_constraint(TABLE)["constrained_columns"] == ["job_id"]
        assert len(observer.get_check_constraints(TABLE)) == 16
        fks = observer.get_foreign_keys(TABLE)
        assert sorted(
            (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]))
            for f in fks
        ) == sorted(
            [
                (("job_id",), "jobs", ("id",)),
                (
                    ("project_id", "job_resource_kind", "job_id"),
                    "resource_scopes",
                    ("project_id", "resource_kind", "resource_id"),
                ),
                (
                    ("operation_id", "job_id", "project_id"),
                    "operations",
                    ("id", "job_id", "project_id"),
                ),
            ]
        )
        support = [
            i
            for i in observer.get_indexes("operations")
            if i["name"] == "job_failure_operation_binding_uq"
        ]
        assert len(support) == 1 and support[0]["unique"]
        assert support[0]["column_names"] == ["id", "job_id", "project_id"]
        assert not support[0].get("include_columns")
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
            == LEDGER
        )
        with pytest.raises(MigrationRefused, match="schema_incompatible"):
            catalog(connection)
        if connection.dialect.name == "sqlite":
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            triggers = (
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
                )
                .scalars()
                .all()
            )
            assert triggers == [
                "job_failure_evidence_delete_guard",
                "job_failure_evidence_insert_guard",
                "job_failure_evidence_update_guard",
            ]
            ddl = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name='job_failure_evidence'"
            ).scalar_one()
            assert ddl.count("NOT DEFERRABLE") == 3
            sizes = connection.exec_driver_sql(
                "SELECT max(length(CAST(sql AS BLOB))),sum(length(CAST(sql AS BLOB))) "
                "FROM sqlite_master WHERE type='table'"
            ).one()
            assert sizes[0] <= 65536 and sizes[1] <= 1310720
        else:
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM pg_constraint WHERE conrelid="
                    "'public.job_failure_evidence'::regclass AND contype='f' "
                    "AND NOT condeferrable AND confupdtype='a' AND confdeltype='a'"
                ).scalar_one()
                == 3
            )
            function = connection.exec_driver_sql(
                "SELECT prosecdef,provolatile,proparallel,pronargs,proconfig "
                "FROM pg_proc WHERE oid='public.job_failure_evidence_guard()'::regprocedure"
            ).one()
            assert tuple(function) == (False, "v", "u", 0, ["search_path=pg_catalog, pg_temp"])
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM pg_proc p,LATERAL aclexplode(p.proacl) a "
                    "WHERE p.oid='public.job_failure_evidence_guard()'::regprocedure "
                    "AND a.grantee=0"
                ).scalar_one()
                == 0
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"
                ).scalar_one()
                == 7
            )


def test_native_valid_variants_and_integer_boundaries(failure_db):
    with failure_db.begin() as connection:
        original = rows(connection)
        cases = [
            ("v1", "succeeded", False, 0),
            ("v1", "succeeded", False, 253402300799999999),
            ("v2-marker", "failed", False, 1),
            ("verified", "failed", False, 1),
            ("verified", "failed", True, 1),
            ("verified", "cancelled", True, 1),
        ]
        for kind, status, cancel, timestamp in cases:
            savepoint = connection.begin_nested()
            if kind == "v1":
                value = marker(created_at_micros=timestamp)
            else:
                value = v2(
                    connection,
                    status=status,
                    cancel=cancel,
                    correlation=None if kind == "v2-marker" else "f" * 32,
                )
                if kind == "v2-marker":
                    value.update(
                        kind="historical_marker",
                        cause=None,
                        phase=None,
                        origin_kind="migration_marker",
                    )
                value["created_at_micros"] = timestamp
            insert(connection, value)
            assert (
                dict(connection.execute(text(f"SELECT * FROM {TABLE}")).mappings().one()) == value
            )
            savepoint.rollback()
            assert rows(connection) == original
        for phase, causes in (
            (
                "pre_dispatch",
                ("budget_refused", "dependency_failed", "internal_fault", "lease_expired"),
            ),
            (
                "outcome_unknown",
                (
                    "budget_refused",
                    "dependency_failed",
                    "internal_fault",
                    "dispatch_uncertain",
                    "lease_expired",
                ),
            ),
        ):
            for cause in causes:
                savepoint = connection.begin_nested()
                value = v2(connection) | {"phase": phase, "cause": cause}
                insert(connection, value)
                assert connection.exec_driver_sql(f"SELECT cause,phase FROM {TABLE}").one() == (
                    cause,
                    phase,
                )
                savepoint.rollback()
                assert rows(connection) == original
        savepoint = connection.begin_nested()
        connection.execute(
            text("UPDATE jobs SET lease_generation=:n WHERE id=:id"),
            {"n": 9223372036854775807, "id": JOB},
        )
        insert(connection, marker(lease_generation=9223372036854775807))
        assert (
            connection.exec_driver_sql(f"SELECT lease_generation FROM {TABLE}").scalar_one()
            == 9223372036854775807
        )
        savepoint.rollback()
        assert rows(connection) == original


def test_native_scalar_variant_and_association_refusals(failure_db, record_property):
    with failure_db.begin() as connection:
        value = v2(connection)
        before = rows(connection)
        invalid = [
            {"schema_version": 2},
            {"schema_version": None},
            {"kind": "unknown"},
            {"project_id": OTHER},
            {"project_id": "A" * 32},
            {"project_id": "é" * 32},
            {"job_resource_kind": "run"},
            {"job_id": "1" * 32},
            {"operation_id": None},
            {"operation_id": "0" * 32},
            {"lease_generation": -1},
            {"lease_generation": 0},
            {"lease_generation": 2},
            {"job_status": "succeeded"},
            {"job_status": "cancelled"},
            {"cause": None},
            {"cause": "completed_calls"},
            {"phase": None},
            {"phase": "pre_dispatch", "cause": "dispatch_uncertain"},
            {"origin_kind": "migration_marker"},
            {"correlation_id": "0" * 32},
            {"association_sha256": "g" * 64},
            {"association_sha256": b"a" * 64},
            {"source_sha256": "b" * 63},
            {"source_sha256": "b" * 64 + "\0"},
            {"created_at_micros": -1},
            {"created_at_micros": 253402300800000000},
        ]
        if connection.dialect.name == "sqlite":
            invalid += [{"schema_version": 1.5}, {"created_at_micros": 0.5}]
        for changes in invalid:
            with pytest.raises(DBAPIError), connection.begin_nested():
                insert(connection, value | changes)
            assert rows(connection) == before, changes

        # Native literals avoid Python/DBAPI integer overflow before SQLite.
        # Observe BIGINT affinity separately, since a refused row is never stored.
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("CREATE TEMP TABLE failure_generation_probe(value BIGINT)")
            try:
                connection.exec_driver_sql(
                    "INSERT INTO failure_generation_probe VALUES"
                    "(9223372036854775808),('not-an-integer')"
                )
                observed = connection.exec_driver_sql(
                    "SELECT typeof(value),value FROM failure_generation_probe ORDER BY rowid"
                ).all()
                assert [row[0] for row in observed] == ["real", "text"]
                assert observed[0][1] == float(2**63)
                assert observed[1][1] == "not-an-integer"
                record_property(
                    "sqlite_generation_affinity", json.dumps([list(r) for r in observed])
                )
            finally:
                connection.exec_driver_sql("DROP TABLE failure_generation_probe")
        codes = []
        for literal in ("9223372036854775808", "'not-an-integer'"):
            statement = text(
                f"INSERT INTO {TABLE} ("
                + ",".join(value)
                + ") VALUES ("
                + ",".join(literal if key == "lease_generation" else ":" + key for key in value)
                + ")"
            )
            with pytest.raises(DBAPIError) as refused, connection.begin_nested():
                connection.execute(statement, value)
            if connection.dialect.name == "postgresql":
                codes.append(refused.value.orig.sqlstate)
            assert rows(connection) == before
        if connection.dialect.name == "postgresql":
            assert codes == ["22003", "22P02"]
            record_property("postgres_generation_native_sqlstates", json.dumps(codes))


def test_unfiltered_operation_presence_and_origin_refusal(failure_db):
    with failure_db.begin() as connection:
        before = rows(connection)
        for scenario in (
            "v1-with-operation",
            "v2-without-operation",
            "v2-marker-with-origin",
            "verified-without-origin",
        ):
            savepoint = connection.begin_nested()
            if scenario == "v1-with-operation":
                operation(connection)
                value = marker()
            else:
                value = v2(
                    connection,
                    correlation=None if scenario == "verified-without-origin" else "f" * 32,
                )
                if scenario == "v2-without-operation":
                    connection.exec_driver_sql("DELETE FROM operations")
                if scenario != "verified-without-origin":
                    value.update(
                        kind="historical_marker",
                        cause=None,
                        phase=None,
                        origin_kind="migration_marker",
                    )
            attempted = rows(connection)
            with pytest.raises(DBAPIError), connection.begin_nested():
                insert(connection, value)
            assert rows(connection) == attempted
            savepoint.rollback()
            assert rows(connection) == before


def test_result_and_unfiltered_call_preclude_selected_failure(failure_db):
    with failure_db.begin() as connection:
        value = v2(connection)
        for field in ("error", "result"):
            savepoint = connection.begin_nested()
            connection.execute(
                text(f"UPDATE jobs SET {field}=:value WHERE id=:job"),
                {"value": "private-original-canary", "job": JOB},
            )
            before = rows(connection)
            with pytest.raises(DBAPIError), connection.begin_nested():
                insert(connection, value)
            assert rows(connection) == before
            savepoint.rollback()
        savepoint = connection.begin_nested()
        artifact = object_value()
        record_verified(connection, artifact)
        register_ref(
            connection,
            project_id=PROJECT,
            owner_kind="job",
            owner_id=JOB,
            role="result",
            artifact_id=artifact.id,
        )
        before = rows(connection)
        with pytest.raises(DBAPIError), connection.begin_nested():
            insert(connection, value)
        assert rows(connection) == before
        savepoint.rollback()

        triple(connection)
        call(connection)
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
        before = rows(connection)
        with pytest.raises(DBAPIError), connection.begin_nested():
            insert(connection, value | {"phase": "pre_dispatch"})
        assert rows(connection) == before
        insert(connection, value)
        assert (
            connection.exec_driver_sql(f"SELECT phase FROM {TABLE}").scalar_one()
            == "outcome_unknown"
        )


def test_immutable_exact_duplicates_and_parent_foreign_keys(failure_db):
    with failure_db.begin() as connection:
        value = v2(connection)
        insert(connection, value)
        before = rows(connection)
        suffix = "ON CONFLICT DO NOTHING"
        mutations = [
            lambda: insert(connection, value),
            lambda: insert(connection, value, suffix=suffix),
            lambda: insert(
                connection,
                value | {"source_sha256": "c" * 64},
                suffix="ON CONFLICT(job_id) DO UPDATE SET source_sha256=excluded.source_sha256",
            ),
            lambda: connection.exec_driver_sql(f"UPDATE {TABLE} SET job_id=job_id"),
            lambda: connection.exec_driver_sql(f"DELETE FROM {TABLE}"),
            lambda: connection.execute(text("DELETE FROM jobs WHERE id=:id"), {"id": JOB}),
            lambda: connection.execute(
                text("DELETE FROM operations WHERE id=:id"), {"id": OPERATION}
            ),
            lambda: connection.execute(
                text("DELETE FROM resource_scopes WHERE resource_kind='job' AND resource_id=:id"),
                {"id": JOB},
            ),
        ]
        if connection.dialect.name == "sqlite":
            assert connection.exec_driver_sql("PRAGMA recursive_triggers").scalar_one() == 0
            mutations.append(
                lambda: insert(
                    connection, value | {"source_sha256": "c" * 64}, prefix="INSERT OR REPLACE"
                )
            )
        else:
            mutations.append(lambda: connection.exec_driver_sql(f"TRUNCATE {TABLE}"))
        for mutate in mutations:
            with pytest.raises(DBAPIError), connection.begin_nested():
                mutate()
            assert rows(connection) == before


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure DDL")
def test_postgres_owner_and_select_only_reader_boundary(ledger_pg):
    owner, app = ledger_pg["owner"], ledger_pg["app"]
    role = ledger_pg["app_role"]
    with owner.begin() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM pg_default_acl WHERE defaclrole=current_user::regrole"
            ).scalar_one()
            == 0
        )
        create_failure_schema(connection)
        assert (
            connection.exec_driver_sql(
                "SELECT has_function_privilege(current_user, "
                "'public.job_failure_evidence_guard()', 'EXECUTE')"
            ).scalar_one()
            is True
        )
        assert (
            connection.execute(
                text(
                    "SELECT has_function_privilege(:role, "
                    "'public.job_failure_evidence_guard()', 'EXECUTE')"
                ),
                {"role": role},
            ).scalar_one()
            is False
        )
        for privilege in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "REFERENCES",
            "TRIGGER",
        ):
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege(:role, "
                        "'public.job_failure_evidence', :privilege)"
                    ),
                    {"role": role, "privilege": privilege},
                ).scalar_one()
                is False
            )
        before = rows(connection)
        # Test-only grants exercise the trigger under a genuine nonowner;
        # the schema creator grants no application authority.
        for table in (
            "job_failure_evidence",
            "jobs",
            "resource_scopes",
            "operations",
            "artifact_refs",
            "provider_calls",
        ):
            connection.exec_driver_sql(f'GRANT SELECT ON "{table}" TO "{role}"')
    with app.connect() as connection:
        assert connection.exec_driver_sql(f"SELECT count(*) FROM {TABLE}").scalar_one() == 0
    with pytest.raises(DBAPIError) as denied, app.begin() as connection:
        insert(connection, marker())
    assert denied.value.orig.sqlstate == "42501"
    with owner.begin() as connection:
        connection.exec_driver_sql(f'GRANT INSERT ON "{TABLE}" TO "{role}"')
    with (
        pytest.raises(DBAPIError, match="failure marker owner required"),
        app.begin() as connection,
    ):
        insert(connection, marker())
    for sql in (f"UPDATE {TABLE} SET job_id=job_id", f"DELETE FROM {TABLE}", f"TRUNCATE {TABLE}"):
        with pytest.raises(DBAPIError) as denied, app.begin() as connection:
            connection.exec_driver_sql(sql)
        assert denied.value.orig.sqlstate == "42501"
    with owner.connect() as connection:
        assert rows(connection) == before


def test_caller_rollback_preserves_entire_predecessor(ledger_db):
    engine, _ = ledger_db
    with engine.connect() as connection:
        before, shape = rows(connection), catalog(connection)
        connection.rollback()
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()
        try:
            create_failure_schema(connection)
            with pytest.raises(DBAPIError):
                connection.exec_driver_sql("SELECT * FROM missing_after_failure_ddl")
        finally:
            connection.rollback()
        assert rows(connection) == before
        assert catalog(connection) == shape == installed_profile(engine.dialect.name, LEDGER)


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_real_sqlite_history_preserved(tmp_path, legacy):
    case = complete_ar6(tmp_path / "source.sqlite", legacy=legacy)
    try:
        invoke(case, intent(case, empty=not legacy))
        with case.engine.begin() as connection:
            before = rows(connection)
            native = connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
            ).all()
            create_failure_schema(connection)
            after = rows(connection)
            assert after.pop(TABLE) == []
            assert after == before
            retained = connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE tbl_name<>'job_failure_evidence' "
                "AND name<>'job_failure_operation_binding_uq' ORDER BY type,name"
            ).all()
            assert retained == native
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == LEDGER
            )
    finally:
        case.dispose()


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure DDL")
@pytest.mark.parametrize("history", ["empty", "legacy"])
def test_real_postgres_history_preserved(pg, history):
    state = service_postgres_state(pg, history=history)
    try:
        with state.case.engine.begin() as connection:
            before = rows(connection)
            old_function = connection.exec_driver_sql(
                "SELECT prosrc,proacl FROM pg_proc "
                "WHERE oid='public.ar7_ledger_constraint()'::regprocedure"
            ).one()
            old_triggers = connection.exec_driver_sql(
                "SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger "
                "WHERE NOT tgisinternal ORDER BY tgname"
            ).all()
            create_failure_schema(connection)
            after = rows(connection)
            assert after.pop(TABLE) == []
            assert after == before
            assert (
                connection.exec_driver_sql(
                    "SELECT prosrc,proacl FROM pg_proc "
                    "WHERE oid='public.ar7_ledger_constraint()'::regprocedure"
                ).one()
                == old_function
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger "
                    "WHERE NOT tgisinternal AND tgrelid<>'public.job_failure_evidence'::regclass "
                    "ORDER BY tgname"
                ).all()
                == old_triggers
            )
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == LEDGER
            )
    finally:
        state.case.dispose()


@pytest.mark.skipif(not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL failure DDL")
@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ"])
def test_postgres_concurrent_duplicate_is_refused(ledger_pg, isolation, record_property):
    engine = ledger_pg["owner"]
    with engine.begin() as connection:
        create_failure_schema(connection)
    value = marker()
    ready = Queue()
    finished = Event()

    def contender():
        with engine.connect().execution_options(isolation_level=isolation) as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET LOCAL statement_timeout='5s'")
                connection.exec_driver_sql("SET LOCAL lock_timeout='4s'")
                assert connection.exec_driver_sql("SHOW transaction_isolation").scalar_one() == (
                    isolation.lower()
                )
                # Establish the contender snapshot before the winner is committed.
                ready.put(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one())
                result = connection.execute(
                    text(
                        f"INSERT INTO {TABLE} ("
                        + ",".join(value)
                        + ") VALUES ("
                        + ",".join(":" + field for field in value)
                        + ") ON CONFLICT DO NOTHING RETURNING job_id"
                    ),
                    value,
                ).all()
                transaction.commit()
                return {"outcome": "succeeded", "returned": [tuple(row) for row in result]}
            except DBAPIError as error:
                transaction.rollback()
                return {"outcome": "refused", "sqlstate": error.orig.sqlstate}
            finally:
                finished.set()

    with engine.connect() as winner, ThreadPoolExecutor(max_workers=1) as executor:
        transaction = winner.begin()
        try:
            winner.exec_driver_sql("SET LOCAL statement_timeout='5s'")
            insert(winner, value)
            expected = rows(winner)
            winner_pid = winner.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            future = executor.submit(contender)
            loser_pid = ready.get(timeout=5)
            deadline = time.monotonic() + 2
            observed_blocking = False
            while time.monotonic() < deadline and not finished.is_set():
                blockers = winner.execute(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": loser_pid}
                ).scalar_one()
                if winner_pid in blockers:
                    observed_blocking = True
                    break
                # Poll native blocking with a bounded event wait, not a delay injection.
                finished.wait(0.01)
            assert observed_blocking, "contender never observably blocked on the winner"
            transaction.commit()
            outcome = future.result(timeout=6)
        finally:
            if transaction.is_active:
                transaction.rollback()
    with engine.connect() as connection:
        assert rows(connection) == expected
    record_property(
        "concurrent_duplicate",
        json.dumps(
            {
                "isolation": isolation,
                "winner_pid": winner_pid,
                "loser_pid": loser_pid,
                "blocked_on_winner": observed_blocking,
                "winner_state_preserved": True,
                **outcome,
            },
            sort_keys=True,
        ),
    )
    assert outcome["outcome"] == "refused"
    assert outcome["sqlstate"] == ("23514" if isolation == "READ COMMITTED" else "40001")
