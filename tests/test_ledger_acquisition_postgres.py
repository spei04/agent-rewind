"""C2: original pre-body LOCK expiry and cancellation of its exact owned waiter."""

import hashlib
import json
from pathlib import Path
from time import monotonic

import pytest
import test_ledger_recovery_postgres as recovery
import test_migrations_postgres as migration_tests
from ledger_acquisition_postgres_fixture import (
    CANCEL_SQL,
    MODES,
    UNRESOLVED_BLOCKERS,
    AcquisitionObserver,
    assert_absent,
    assert_cancel_receipt,
    assert_held,
    assert_identity,
    assert_origins,
    assert_result,
    assert_waiting,
)
from ledger_competing_process import CommandGroup
from ledger_provisioning_fixture import initial_manifest
from ledger_provisioning_postgres_fixture import (
    encrypted_files,
    native_snapshot,
    progress_diagnostic,
)
from test_ledger_service_postgres import controlled_database_name
from test_run_projection_postgres import drain, observed_reader

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest

__all__ = ["controlled_database_name", "observed_reader"]
pg, legacy = migration_tests.pg, recovery.legacy
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in original PostgreSQL acquisition failure"
)


def table_oids(fixture, pg):
    try:
        with fixture.case.engine.connect() as connection:
            return dict(
                connection.exec_driver_sql(
                    "SELECT c.relname,c.oid FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' "
                    "ORDER BY c.relname"
                ).all()
            )
    finally:
        drain(pg)


def coordinate(group, child, control, pg, tables, record):
    """The blocker cannot be released until the original backend has disappeared."""
    blocker_connection = None
    blocker_raw = None
    blocker = operator = None
    blocker_released = False
    errors = []
    try:
        held = child.receive()
        assert_held(held, sorted(tables))
        record["held"] = held
        witness = held["witness"]
        database = pg["owner"].url.database
        assert witness["database"] == database and witness["role"] == pg["owner_role"]
        setup = AcquisitionObserver(control, database, group.work_deadline, record["observations"])
        first = setup.observe(witness["backend_pid"], 0)
        assert len(first["activity"]) == 1 and first["target_pids"] == [witness["backend_pid"]]
        operator = first["activity"][0]
        assert operator["pid"] == witness["backend_pid"]
        assert operator["datname"] == database and operator["usename"] == pg["owner_role"]
        assert operator["state"] == "idle in transaction" and operator["blockers"] == []
        assert type(operator["backend_start"]) is str and operator["backend_start"]
        assert type(operator["datid"]) is int and operator["datid"] > 0
        record["operator_identity"] = operator
        # All original privilege/activity checks have returned before this
        # administrative connection joins the target database.
        blocker_connection = pg["admin"].connect()
        blocker_connection.begin()
        blocker_raw = blocker_connection.connection.driver_connection
        blocker_pid = blocker_raw.info.backend_pid
        assert blocker_pid != operator["pid"]
        blocker_connection.exec_driver_sql("SET LOCAL statement_timeout='1000ms'").close()
        blocker_connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'").close()
        blocker_connection.exec_driver_sql(
            "LOCK TABLE public.api_keys IN ACCESS SHARE MODE"
        ).close()
        setup = AcquisitionObserver(control, database, group.work_deadline, record["observations"])
        blocked = setup.observe(operator["pid"], blocker_pid)
        assert len(blocked["blocker_activity"]) == 1
        blocker = blocked["blocker_activity"][0]
        assert blocker["pid"] == blocker_pid and blocker["datid"] == operator["datid"]
        assert blocker["datname"] == database and blocker["usename"] == blocker_raw.info.user
        assert type(blocker["backend_start"]) is str and blocker["backend_start"]
        assert_identity(blocked["activity"][0], operator)
        assert blocked["target_pids"] == sorted([operator["pid"], blocker_pid])
        record["blocker_identity"] = blocker
        second = child.probe()
        assert_held(second, sorted(tables))
        assert second["witness"] == held["witness"]
        continued = monotonic()
        cap = min(group.work_deadline, continued + 9)
        record.update(continued=continued, disappearance_deadline=cap)
        child.resume()
        observer = AcquisitionObserver(control, database, cap, record["observations"])
        query = witness["sql"]

        def waiting(observation):
            assert child.process.poll() is None, "child exited before owned-wait observation"
            assert len(observation["activity"]) == 1
            assert_identity(observation["activity"][0], operator)
            assert len(observation["blocker_activity"]) == 1
            assert_identity(observation["blocker_activity"][0], blocker)
            assert observation["target_pids"] == sorted([operator["pid"], blocker_pid])
            row = observation["activity"][0]
            if row["state"] == "active" and row["wait_event_type"] == "Lock":
                assert_waiting(observation, operator, blocker, tables["api_keys"], query)
                return True
            assert row["state"] in {"idle in transaction", "active"}
            return False

        waiting_state = observer.poll(
            waiting, operator["pid"], blocker_pid, min(cap, continued + 2)
        )
        row = assert_waiting(waiting_state, operator, blocker, tables["api_keys"], query)
        record["wait_observation"] = waiting_state
        if child.identity["case"] == "cancel-waiter":
            assert row["age"] < 2 and monotonic() < min(cap, continued + 3)
            cancel = {
                "pid": operator["pid"],
                "backend_start": operator["backend_start"],
                "datid": operator["datid"],
                "database": database,
                "role": operator["usename"],
                "query_start": row["query_start"],
                "query": query,
                "blocker": blocker_pid,
                "blocker_start": blocker["backend_start"],
                "blocker_role": blocker["usename"],
                "relation": tables["api_keys"],
            }
            started = monotonic()
            result = observer.execute(CANCEL_SQL, cancel)
            finished = monotonic()
            record["cancel"] = {"row": list(result), "started": started, "finished": finished}
            assert_cancel_receipt(
                result, started=started, finished=finished, continued=continued, deadline=cap
            )
        else:
            assert child.identity["case"] == "lock-expiry"
            record["cancel"] = None

        def absent(observation):
            if observation["activity"]:
                assert len(observation["activity"]) == 1
                assert_identity(observation["activity"][0], operator)
                assert len(observation["blocker_activity"]) == 1
                assert_identity(observation["blocker_activity"][0], blocker)
                return False
            assert_absent(observation, operator, blocker)
            return True

        absent_state = observer.poll(absent, operator["pid"], blocker_pid, cap)
        absent_at = observer.last_completion
        release_deadline = min(cap, absent_at + 2)
        record.update(operator_absent=absent_state, absent_at=absent_at)
        # Native rollback and physical close precede the child's unchanged drain
        # and final result. A late release is a failed attempt, not a larger budget.
        blocker_connection.rollback()
        record["blocker_rollback_ack"] = {
            "at": monotonic(),
            "status": int(blocker_raw.info.transaction_status),
        }
        assert record["blocker_rollback_ack"]["status"] == 0
        blocker_connection.close()
        record["blocker_close_ack"] = {
            "at": monotonic(),
            "raw_closed": blocker_raw.closed,
            "connection_closed": blocker_connection.closed,
        }
        assert blocker_raw.closed and blocker_connection.closed
        blocker_released = True
        observer.account_release(absent_at, record["blocker_close_ack"]["at"])
        assert monotonic() <= release_deadline

        def released(observation):
            assert observation["activity"] == observation["locks"] == []
            if observation["blocker_activity"]:
                assert len(observation["blocker_activity"]) == 1
                assert_identity(observation["blocker_activity"][0], blocker)
                return False
            assert_absent(observation, operator, blocker, released=True)
            return True

        released_state = observer.poll(released, operator["pid"], blocker_pid, release_deadline)
        record.update(blocker_absent=released_state, blocker_absent_at=monotonic())
        assert record["blocker_absent_at"] <= release_deadline
        message = child.receive()
        record.update(result=message, result_received_at=monotonic())
        assert_result(message, held, child.identity["case"])
        assert child.record["reaped"] and child.record["returncode"] == 0
        assert len(group.children) == 1 and len(group.messages) == 6
        assert len([row for row in record["observations"] if row["sql"] == CANCEL_SQL]) == int(
            child.identity["case"] == "cancel-waiter"
        )
    except BaseException as error:
        record["first_error"] = {"type": type(error).__name__, "message": str(error)}
        errors.append(error)
    finally:
        # If disappearance was not proved, stop and reap the owned child while
        # still holding the blocker. Never unblock a live uncertain operator.
        try:
            group.close()
        except BaseException as error:
            errors.append(error)
        record["group"] = group.record
        if blocker_connection is not None and not blocker_released:
            if all(item.record.get("reaped") for item in group.children):
                try:
                    blocker_connection.rollback()
                    blocker_connection.close()
                    record["failure_blocker_close"] = {
                        "raw_closed": blocker_raw.closed,
                        "connection_closed": blocker_connection.closed,
                        "after_owned_reap": True,
                    }
                    assert blocker_raw.closed and blocker_connection.closed
                except BaseException as error:
                    errors.append(error)
            else:
                UNRESOLVED_BLOCKERS.append(blocker_connection)
                errors.append(AssertionError("blocker retained for outer owned-process cleanup"))
    if errors:
        raise BaseExceptionGroup("original acquisition attempt failed", errors)


@pytest.mark.parametrize("mode", list(MODES))
def test_original_acquisition_failure_preserves_s0(legacy, pg, mode, tmp_path, record_property):
    assert_origins()
    manifest = initial_manifest(legacy)
    validated = validate_ledger_manifest(manifest)
    before, files, tables = (
        native_snapshot(legacy.case, pg),
        encrypted_files(legacy),
        table_oids(legacy, pg),
    )
    assert len(files) == 18 and set(tables) == set(before["tables"])
    legacy.close()
    drain(pg)
    record = {"mode": mode, "observations": []}
    group = CommandGroup(tmp_path)
    errors = []
    try:
        with pg["control"].connect().execution_options(isolation_level="AUTOCOMMIT") as control:
            control.exec_driver_sql("SET statement_timeout='1000ms'").close()
            child = group.spawn(
                worker=Path(__file__).with_name("ledger_acquisition_postgres_worker.py"),
                case=mode,
                role="winner",
                intent_sha256=hashlib.sha256(validated.canonical_bytes).hexdigest(),
                configuration={
                    "url": legacy.case.engine.url.render_as_string(hide_password=False),
                    "control_url": pg["control"].url.render_as_string(hide_password=False),
                    "manifest": manifest,
                    "tables": sorted(tables),
                    "mode": mode,
                },
            )
            coordinate(group, child, control, pg, tables, record)
    except BaseException as error:
        errors.append(error)
    finally:
        try:
            group.close()
            assert group.closed and all(child.record.get("reaped") for child in group.children)
            assert not UNRESOLVED_BLOCKERS
            drain(pg)
            after, after_files, after_tables = (
                native_snapshot(legacy.case, pg),
                encrypted_files(legacy),
                table_oids(legacy, pg),
            )
            record.update(
                before=before,
                after=after,
                files_before=files,
                files_after=after_files,
                table_oids_before=tables,
                table_oids_after=after_tables,
            )
            assert before == after and files == after_files and tables == after_tables
        except BaseException as error:
            errors.append(error)
        finally:
            record["group"] = group.record
            record_property("acquisition", json.dumps(record, default=progress_diagnostic))
    if errors:
        raise BaseExceptionGroup("acquisition or preservation failed", errors)
