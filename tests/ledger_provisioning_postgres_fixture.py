"""Native PostgreSQL observations for the independent provisioning oracle."""

import hashlib
import json
from datetime import datetime

from ledger_provisioning_fixture import (
    SOURCE_FIELDS,
    ProvisioningFixture,
    assert_preserved_jobs,
    canonical,
    digest,
    expected_stage,
    source_fingerprint,
)
from ledger_reader_fixture import complete_postgres_ar6
from legacy_fixture import FIXTURE_ROOT
from test_run_projection_postgres import drain

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
from agent_rewind.migrations.ledger_service import initialize_ledger
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import LEDGER, catalog, installed_profile


def source_rows(connection):
    return {
        table: [
            tuple(row)
            for row in connection.exec_driver_sql(
                f"SELECT {','.join(fields)} FROM {table} ORDER BY "
                + ("run_id,step" if table == "events" else "id")
            )
        ]
        for table, fields in SOURCE_FIELDS.items()
    }


def encrypted_files(fixture):
    if not fixture.case.legacy:
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((FIXTURE_ROOT / "objects").iterdir())
    }


def native_snapshot(case, pg):
    """Native typed cells, column order, executable catalog and owner/ACL witnesses."""
    try:
        with case.engine.connect() as connection:
            shape = catalog(connection)
            tables = {}
            for name in sorted(shape):
                if name.startswith("$"):
                    continue
                quoted = connection.dialect.identifier_preparer.quote(name)
                result = connection.exec_driver_sql(f"SELECT * FROM {quoted}")
                tables[name] = {
                    "columns": tuple(result.keys()),
                    "rows": tuple(sorted((tuple(row) for row in result), key=repr)),
                }
            authority = {
                "schema": tuple(
                    tuple(row)
                    for row in connection.exec_driver_sql(
                        "SELECT nspname,pg_get_userbyid(nspowner),nspacl::text "
                        "FROM pg_namespace WHERE nspname='public'"
                    )
                ),
                "relations": tuple(
                    tuple(row)
                    for row in connection.exec_driver_sql(
                        "SELECT c.relname,pg_get_userbyid(c.relowner),c.relacl::text "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='public' ORDER BY c.relname"
                    )
                ),
                "functions": tuple(
                    tuple(row)
                    for row in connection.exec_driver_sql(
                        "SELECT p.proname,pg_get_function_identity_arguments(p.oid),"
                        "pg_get_userbyid(p.proowner),p.proacl::text "
                        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                        "WHERE n.nspname='public' ORDER BY p.proname,"
                        "pg_get_function_identity_arguments(p.oid)"
                    )
                ),
            }
            role = connection.exec_driver_sql("SELECT current_user").scalar_one()
            assert role == pg["owner_role"]
            return {"catalog": shape, "tables": tables, "authority": authority, "role": role}
    finally:
        drain(pg)


def build_postgres_case(pg, *, legacy=True):
    case = complete_postgres_ar6(pg, legacy=legacy)
    try:
        before = native_snapshot(case, pg)
        with case.engine.connect() as connection:
            original = source_rows(connection)
            organization = connection.exec_driver_sql("SELECT id FROM organizations").scalar_one()
            project = connection.exec_driver_sql("SELECT id FROM projects").scalar_one()
            jobs = [
                dict(row)
                for row in connection.exec_driver_sql(
                    "SELECT j.id,j.budget,j.reserved,s.project_id FROM jobs j "
                    "JOIN resource_scopes s ON s.resource_kind='job' AND s.resource_id=j.id "
                    "ORDER BY j.id"
                ).mappings()
            ]
        drain(pg)
        fixture = ProvisioningFixture(
            case,
            before,
            original,
            source_fingerprint(original),
            {},
            jobs,
            organization,
            project,
        )
        fixture.encrypted = encrypted_files(fixture)
        assert fixture.source == case.original_digest
        if legacy:
            assert sorted(row["reserved"] for row in jobs) == [35000, 85000, 125000]
            assert len(jobs) == 3 and {row["project_id"] for row in jobs} == {project}
            assert fixture.encrypted
        else:
            assert jobs == [] and fixture.encrypted == {}
        return fixture
    except BaseException:
        case.dispose()
        raise


def database_time(fixture, pg):
    try:
        with fixture.case.engine.connect() as connection:
            return connection.exec_driver_sql("SELECT clock_timestamp()").scalar_one()
    finally:
        drain(pg)


def invoke(fixture, pg, manifest):
    checked = validate_ledger_manifest(manifest)
    assert checked.canonical_bytes == canonical(manifest) and checked.digest == digest(manifest)
    before = database_time(fixture, pg)
    engine = fixture.case.operator_engine()
    try:
        receipt = initialize_ledger(engine, checked)
    finally:
        engine.dispose()
        drain(pg)
    after = database_time(fixture, pg)
    observed = datetime.fromisoformat(receipt.initialized_at.replace("Z", "+00:00"))
    assert before <= observed <= after
    return receipt


def inspect(fixture, pg):
    engine = fixture.case.operator_engine()
    outcome = LedgerOutcome()
    try:
        with ledger_transaction(engine, outcome, work=LedgerWork()) as connection:
            result = inspect_ledger_state(connection)
        assert outcome.commit_acknowledged and not outcome.cleanup_failed
        return result
    finally:
        engine.dispose()
        drain(pg)


def canonical_cursor(raw):
    """Compare stored JSON values without accepting duplicate keys or nonfinite numbers."""

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate progress cursor member")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("nonfinite progress cursor number")

    value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if type(value) is not dict:
        raise ValueError("progress cursor must be an object")
    return canonical(value)


def progress_diagnostic(value):
    if isinstance(value, datetime):
        return {"native_type": "timestamptz", "iso8601": value.isoformat()}
    raise TypeError("unsupported progress diagnostic value")


def assert_stage(fixture, pg, manifests, receipts, *, record_property):
    """Independent expected values against PostgreSQL's real typed serialization."""
    accounts, progress, state = expected_stage(
        fixture, manifests, receipts, database_role=pg["owner_role"]
    )
    expected_accounts = [
        {
            **account,
            "period_start": datetime.fromisoformat(account["period_start"].replace("Z", "+00:00")),
            "period_end": datetime.fromisoformat(account["period_end"].replace("Z", "+00:00")),
        }
        for account in accounts
    ]
    try:
        with fixture.case.engine.connect() as connection:
            actual_accounts = [
                dict(row)
                for row in connection.exec_driver_sql(
                    "SELECT * FROM budget_accounts ORDER BY id"
                ).mappings()
            ]
            assert actual_accounts == sorted(expected_accounts, key=lambda row: row["id"])
            # The writer casts through JSONB, which normalizes stored JSON text.
            # Compare strict JSON values and retain raw native observations first.
            rows = [
                dict(row)
                for row in connection.exec_driver_sql(
                    "SELECT revision,phase,source_digest,cursor::text AS cursor,"
                    "rows_verified,status,updated_at FROM migration_progress "
                    "WHERE revision='ar_0007_ledger' ORDER BY phase"
                ).mappings()
            ]
            expected_rows = {}
            for phase, (cursor, count, source) in progress.items():
                expected_rows[phase] = {
                    "revision": LEDGER,
                    "phase": phase,
                    "source_digest": source,
                    "cursor": canonical(cursor).decode(),
                    "rows_verified": count,
                    "status": "complete",
                    "updated_at": datetime.fromisoformat(
                        cursor["initialized_at"].replace("Z", "+00:00")
                    ),
                }
            record_property(
                "provisioning_progress_rows",
                json.dumps(
                    {
                        "manifest_count": len(manifests),
                        "actual": rows,
                        "expected": list(expected_rows.values()),
                    },
                    default=progress_diagnostic,
                    allow_nan=False,
                ),
            )
            assert len(rows) == len(expected_rows)
            assert {row["phase"] for row in rows} == set(expected_rows)
            for row in rows:
                actual = {**row, "cursor": canonical_cursor(row["cursor"]).decode()}
                assert actual == expected_rows[row["phase"]]
            assert [
                tuple(row)
                for row in connection.exec_driver_sql(
                    "SELECT id,legacy_reserved_microusd,lease_generation FROM jobs ORDER BY id"
                )
            ] == [(job["id"], job["reserved"], 0) for job in fixture.jobs]
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM provider_calls").scalar_one() == 0
            )
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM budget_entries").scalar_one() == 0
            )
            adoption = dict(
                connection.exec_driver_sql("SELECT * FROM installation_adoptions").mappings().one()
            )
            previous = [
                tuple(row)
                for row in connection.exec_driver_sql(
                    "SELECT * FROM migration_progress WHERE revision<>'ar_0007_ledger' "
                    "ORDER BY revision,phase"
                )
            ]
            assert previous == fixture.case.previous_progress
            assert adoption == {
                **fixture.case.adoption,
                "installed_schema_fingerprint": digest(installed_profile("postgresql", LEDGER)),
            }
            assert source_rows(connection) == fixture.original
            assert source_fingerprint(source_rows(connection)) == fixture.source
    finally:
        drain(pg)
    after = native_snapshot(fixture.case, pg)
    assert after["catalog"] == installed_profile("postgresql", LEDGER)
    assert after["tables"]["alembic_version"] == {
        "columns": ("version_num",),
        "rows": ((LEDGER,),),
    }
    assert_preserved_jobs(fixture.before, after)
    for table, before in fixture.before["tables"].items():
        if table not in {"jobs", "alembic_version", "installation_adoptions", "migration_progress"}:
            assert after["tables"][table] == before, table
    assert after["authority"]["schema"] == fixture.before["authority"]["schema"]
    # Existing relation/function identities retain their exact owner and ACL.
    for kind in ("relations", "functions"):
        width = 1 if kind == "relations" else 2
        current = {row[:width]: row for row in after["authority"][kind]}
        assert all(current[row[:width]] == row for row in fixture.before["authority"][kind])
    assert encrypted_files(fixture) == fixture.encrypted
    assert inspect(fixture, pg).model_dump(mode="json") == state


def assert_append_only(before, after, keys):
    assert before["columns"] == after["columns"]

    def rows(table):
        indexes = [table["columns"].index(key) for key in keys]
        return {tuple(row[i] for i in indexes): row for row in table["rows"]}

    original, current = rows(before), rows(after)
    assert len(original) == len(before["rows"]) and len(current) == len(after["rows"])
    assert all(current[key] == row for key, row in original.items())
