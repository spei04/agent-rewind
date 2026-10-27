"""Pure original-gate and independent witness controls; no native database evidence."""

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import psycopg
import pytest
from ledger_account_window_fixture import (
    CASES,
    EXPIRED,
    INSERT_SQL,
    assert_intent,
    assert_preservation,
    assert_refusal,
    canonical_time,
    initial_window,
    site,
    window_intent,
)
from ledger_account_window_observer import observe_window
from ledger_cohort_observer import observe_cohort
from ledger_project_binding import observe_projects
from ledger_provisioning_fixture import digest, identity
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from agent_rewind.migrations import ledger_service
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_writer_sql import PARAMETER_TYPES, SQL
from agent_rewind.migrations.schema import LEDGER, MigrationRefused

ORG, PROJECT, OLD_JOB, NEW_JOB = (identity(i) for i in (11, 22, 33, 44))
OBSERVED = "2026-10-27T12:00:00.000000Z"


def table(records):
    columns = tuple(records[0]) if records else ()
    return {
        "columns": columns,
        "rows": tuple(tuple(row[key] for key in columns) for row in records),
    }


def independent_state(case):
    """Literal observations do not call the manifest/delta helpers under test."""
    accounts = [
        {
            "id": identity(100),
            "organization_id": ORG,
            "scope": "organization",
            "scope_id": ORG,
            "project_id": None,
            "job_id": None,
            "period_start": "2000-01-01T00:00:00.000000Z",
            "period_end": "2100-01-01T00:00:00.000000Z",
            "limit_microusd": 245000,
        },
        {
            "id": identity(200),
            "organization_id": ORG,
            "scope": "project",
            "scope_id": PROJECT,
            "project_id": PROJECT,
            "job_id": None,
            "period_start": "2000-01-01T00:00:00.000000Z",
            "period_end": "2100-01-01T00:00:00.000000Z",
            "limit_microusd": 245000,
        },
        {
            "id": identity(300),
            "organization_id": ORG,
            "scope": "job",
            "scope_id": OLD_JOB,
            "project_id": PROJECT,
            "job_id": OLD_JOB,
            "period_start": "2000-01-01T00:00:00.000000Z",
            "period_end": "2001-01-01T00:00:00.000000Z"
            if case == CASES[1]
            else "2100-01-01T00:00:00.000000Z",
            "limit_microusd": 10000000,
        },
    ]
    first = {
        "schema_version": 1,
        "installation_key": "independent-window-control",
        "manifest_id": identity(1000),
        "operation": "initialize",
        "source_digest": "a" * 64,
        "parent_manifest_digest": None,
        "backup_evidence_digest": "b" * 64,
        "drain_evidence_digest": "d" * 64,
        "accounts": deepcopy(accounts),
        "opening_accounts": {
            "organization_account_id": identity(100),
            "projects": [{"project_id": PROJECT, "account_id": identity(200)}],
        },
    }
    jobs = [
        {
            "id": OLD_JOB,
            "budget": 10000000,
            "project_id": PROJECT,
            "status": "failed",
            "payload_version": 1,
            "reserved": 0,
            "owner": None,
            "lease_until": None,
        },
        {
            "id": NEW_JOB,
            "budget": 1,
            "project_id": PROJECT,
            "status": "queued",
            "payload_version": 2,
            "reserved": 0,
            "owner": None,
            "lease_until": None,
        },
    ]
    scopes = [
        {"resource_kind": "job", "resource_id": row["id"], "project_id": PROJECT} for row in jobs
    ]
    financial_accounts = [
        {**row, "opening_held_microusd": 125000, "held_microusd": 125000, "accounted_microusd": 0}
        for row in accounts
    ]
    native_accounts = [
        {
            **row,
            **{
                key: datetime.fromisoformat(row[key].replace("Z", "+00:00"))
                for key in ("period_start", "period_end")
            },
        }
        for row in financial_accounts
    ]
    before = {
        "tables": {
            "budget_accounts": table(native_accounts),
            "jobs": table(jobs),
            "resource_scopes": table(scopes),
        }
    }
    # A standalone requested manifest: not produced by window_intent().
    target = None if case == CASES[0] else OLD_JOB if case == CASES[1] else NEW_JOB
    account = (
        {
            **accounts[0],
            "id": identity(9200),
            "period_start": "2050-01-01T00:00:00.000000Z",
            "period_end": "2150-01-01T00:00:00.000000Z",
        }
        if case == CASES[0]
        else {
            "id": identity(9200),
            "organization_id": ORG,
            "scope": "job",
            "scope_id": target,
            "project_id": PROJECT,
            "job_id": target,
            "period_start": "2001-01-01T00:00:00.000000Z"
            if case == CASES[1]
            else "2000-01-01T00:00:00.000000Z",
            "period_end": "2100-01-01T00:00:00.000000Z"
            if case == CASES[1]
            else "2001-01-01T00:00:00.000000Z",
            "limit_microusd": 10000000 if case == CASES[1] else 1,
        }
    )
    requested = {
        "schema_version": 1,
        "installation_key": "independent-window-control",
        "manifest_id": identity(9201),
        "operation": "provision",
        "source_digest": "a" * 64,
        "parent_manifest_digest": digest(first),
        "backup_evidence_digest": "b" * 64,
        "drain_evidence_digest": "d" * 64,
        "accounts": [account],
        "opening_accounts": None,
    }
    return first, requested, before, jobs, scopes, financial_accounts, target


class Result:
    def __init__(self, rows, rowcount):
        self.rows, self.rowcount = rows, rowcount

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def mappings(self):
        return self

    def all(self):
        return deepcopy(self.rows)


def delegated(case, monkeypatch, *, earlier=None):
    first, requested, before, jobs, scopes, accounts, target = independent_state(case)
    raw, engine = object(), object()
    connection = SimpleNamespace(
        engine=engine, dialect=SimpleNamespace(name="postgresql", server_version_info=(16, 0))
    )
    work = SimpleNamespace(_raw=raw, _connection=connection, timeout_seconds=5, check=lambda: None)
    prior = {"revision": LEDGER, "status": "ready", "manifest_count": 1, "account_count": 3}
    state = SimpleNamespace(
        **prior,
        installation_key=first["installation_key"],
        head=SimpleNamespace(manifest_digest=digest(first)),
        model_dump=lambda **kwargs: deepcopy(prior),
    )
    context = SimpleNamespace(
        state=state,
        history=SimpleNamespace(
            ownership=SimpleNamespace(organization_id=ORG),
            manifests=(SimpleNamespace(manifest=validate_ledger_manifest(first)),),
            opening=object(),
            adoption={"installed_schema_fingerprint": "c" * 64},
        ),
        financial={"job": deepcopy(jobs), "scope": deepcopy(scopes), "account": deepcopy(accounts)},
    )
    watch = SimpleNamespace(
        work=work,
        engine=engine,
        trace=SimpleNamespace(raws=[raw], events=[]),
        outcome=SimpleNamespace(
            confirmed_precommit_rollback=True,
            rollback_acknowledged=True,
            commit_attempted=False,
            cleanup_failed=False,
        ),
        markers=[],
    )
    if earlier == "organization":
        context.history.ownership.organization_id = identity(99)
    elif earlier == "capacity":
        state.account_count = 4096

    def inert_native(cursor, query, parameters=None):
        assert cursor.connection is raw
        watch.trace.events.extend(
            [
                ("ordinary", "sql-call", id(raw), query),
                ("ordinary", "sql-return", id(raw), query),
            ]
        )
        return cursor

    def inert_execute(statement, parameters):
        names = [
            name
            for (dialect, name), sql in SQL.items()
            if dialect == "postgresql" and sql == statement.text
        ]
        (name,) = names
        fixtures = {
            "projects.gate": (
                [{"candidate_rows": 1, "invalid_rows": 0, "native_bytes": 64, "max_row_bytes": 64}],
                1,
            ),
            "projects.body": ([{"id": PROJECT, "organization_id": ORG}], 1),
            "accounts.insert": ([], 1),
            "provenance.observe": (
                [{"initialized_at": OBSERVED, "database_role": "window_control_owner"}],
                1,
            ),
        }
        rows, count = fixtures[name]
        cursor = SimpleNamespace(connection=raw, rowcount=count)
        query = str(statement.compile(dialect=PGDialect_psycopg()))
        psycopg.Cursor.execute(cursor, query, parameters)
        return Result(rows, count)

    connection.execute = inert_execute
    saved = []
    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Cursor, "execute", inert_native)
        with (
            observe_projects(watch, patch, lambda *value: saved.append(value)) as projects,
            observe_cohort(watch, patch, lambda *value: saved.append(value)) as (entries, stages),
            observe_window(watch, patch, lambda *value: saved.append(value)) as observations,
            pytest.raises(MigrationRefused) as failure,
        ):
            model = validate_ledger_manifest(requested)
            assert ledger_service._classify_manifest(context, model, work) is None
            ledger_service._projects(connection, model, ORG, work)
            prepared = ledger_service._prepare_ledger(context, model, work)
            # Independently constructed service input follows the original write contract.
            values = {
                **requested["accounts"][0],
                "opening_held_microusd": 0,
                "held_microusd": 0,
                "accounted_microusd": 0,
            }
            ledger_service._write(connection, "accounts.insert", values)
            observed, role, uid = ledger_service._provenance(connection)
            ledger_service._ledger_cursors(connection, model, prepared, observed, role, uid, work)
    watch.markers = [
        (name, id(raw), len(watch.trace.events))
        for name in (
            "rollback.before_native",
            "rollback.native_ack",
            "connection.close.before",
            "connection.close.return",
            "command.exit",
        )
    ]
    return SimpleNamespace(
        first=first,
        requested=requested,
        before=before,
        target=target,
        prior=prior,
        observations=observations,
        projects=projects,
        entries=entries,
        stages=stages,
        error=failure.value,
        watch=watch,
        saved=saved,
    )


def accept(value, case):
    assert_refusal(
        value.first,
        value.requested,
        value.prior,
        value.observations,
        value.projects,
        value.entries,
        value.stages,
        value.error,
        value.watch,
        case,
    )


@pytest.mark.parametrize("case", CASES)
def test_original_gates_preserve_refusal_identity_and_distinct_write_roles(case, monkeypatch):
    value = delegated(case, monkeypatch)
    assert_intent(value.first, value.requested, value.before, case, value.target, OBSERVED)
    accept(value, case)
    assert [name for name, _ in value.saved] == [
        "window_observation",
        "cohort_preparation",
        "projects_gate",
    ]
    assert len(value.observations["writes"]) == int(case == CASES[2])
    assert value.error.__traceback__ is not None


@pytest.mark.parametrize("case", CASES)
def test_manifest_adapter_matches_independent_literal_without_changing_m0(case):
    first, requested, _, jobs, _, _, _ = independent_state(case)
    fixture = SimpleNamespace(
        organization=ORG,
        project=PROJECT,
        source="a" * 64,
        case=SimpleNamespace(adoption={"installation_key": "independent-window-control"}),
        jobs=jobs[:1],
    )
    original = deepcopy(first)
    initial, target = initial_window(fixture, case)
    assert initial == first and target == OLD_JOB
    fixture.jobs = jobs
    assert window_intent(fixture, initial, case, NEW_JOB, OLD_JOB) == requested
    assert first == original


@pytest.mark.parametrize("earlier", ["organization", "capacity"])
def test_earlier_real_refusal_cannot_satisfy_window_site(earlier, monkeypatch):
    value = delegated(CASES[0], monkeypatch, earlier=earlier)
    with pytest.raises((AssertionError, ValueError)):
        accept(value, CASES[0])


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    "change",
    [
        "replacement-exception",
        "line",
        "error-identity-float",
        "work-identity-float",
        "returned",
        "manifest",
        "prior-state",
        "project",
        "classification-replay",
        "classification-position-bool",
        "commit",
        "rollback",
        "cleanup",
        "marker-identity-float",
        "marker-order",
        "timeout-float",
        "timeout-override",
        "refusal-after-rollback",
    ],
)
def test_refusal_rejects_wrong_stage_identity_state_and_cleanup(case, change, monkeypatch):
    value = delegated(case, monkeypatch)
    observations = value.observations
    entry = observations["cursors"][0] if case == CASES[2] else value.entries[0]
    frame = (
        entry["original_frames"][0]
        if case == CASES[2]
        else entry["traceback"]["preparation_frames"][0]
    )
    if change == "replacement-exception":
        value.error = MigrationRefused(value.error.code)
    elif change == "line":
        frame["line"] += 1
    elif change == "error-identity-float":
        entry["error"]["identity"] = float(entry["error"]["identity"])
    elif change == "work-identity-float":
        observations["classification"][0]["work_id"] = float(id(value.watch.work))
    elif change == "returned":
        entry["returned_at" if case == CASES[2] else "returned"] = True
    elif change == "manifest":
        value.entries[0]["manifest"]["source_digest"] = "e" * 64
    elif change == "prior-state":
        value.entries[0]["state"]["account_count"] += 1
    elif change == "project":
        value.projects[0]["returned"] = False
    elif change == "classification-replay":
        observations["classification"][0]["receipt"] = {"sequence": 1}
    elif change == "classification-position-bool":
        observations["classification"][0]["entered_at"] = False
    elif change == "commit":
        value.watch.outcome.commit_attempted = True
    elif change == "rollback":
        value.watch.outcome.rollback_acknowledged = False
    elif change == "cleanup":
        value.watch.outcome.cleanup_failed = True
    elif change == "marker-identity-float":
        name, raw, position = value.watch.markers[0]
        value.watch.markers[0] = (name, float(raw), position)
    elif change == "timeout-float":
        value.watch.work.timeout_seconds = 5.0
    elif change == "timeout-override":
        value.watch.work.timeout_seconds = 30
    elif change == "marker-order":
        value.watch.markers[0], value.watch.markers[1] = (
            value.watch.markers[1],
            value.watch.markers[0],
        )
    else:
        entry["refused_at" if case == CASES[2] else "refusal_trace_position"] = (
            len(value.watch.trace.events) + 1
        )
    with pytest.raises((AssertionError, ValueError)):
        accept(value, case)


@pytest.mark.parametrize(
    "change",
    [
        "missing-write",
        "rowcount-bool",
        "rowcount-zero",
        "wrong-query",
        "wrong-bind",
        "bind-zero-float",
        "execution-identity-float",
        "native-identity-float",
        "call-trace-identity-float",
        "return-trace-identity-float",
        "native-call-order",
        "write-after-provenance",
        "position-float",
        "observed-before-expiry",
        "observed-mismatch",
        "role",
        "uid-bool",
        "progress-write",
        "missing-provenance",
    ],
)
def test_expiry_requires_exact_returned_insert_then_original_cursor_refusal(change, monkeypatch):
    value = delegated(CASES[2], monkeypatch)
    records = value.observations
    insert = records["native_calls"][0]
    execution = next(row for row in records["executions"] if row["name"] == "accounts.insert")
    if change == "missing-write":
        records["writes"].clear()
    elif change == "rowcount-bool":
        insert["rowcount"] = True
    elif change == "rowcount-zero":
        insert["rowcount"] = 0
    elif change == "wrong-query":
        insert["sql"] = insert["sql"].rstrip()
    elif change == "wrong-bind":
        insert["parameters"]["id"] = identity(999)
    elif change == "bind-zero-float":
        insert["parameters"]["held_microusd"] = 0.0
    elif change == "execution-identity-float":
        execution["raw_id"] = float(execution["raw_id"])
    elif change == "native-identity-float":
        insert["raw_id"] = float(insert["raw_id"])
    elif change in {"call-trace-identity-float", "return-trace-identity-float"}:
        position = insert["entered_at"] + int(change.startswith("return"))
        phase, kind, raw, sql = value.watch.trace.events[position]
        value.watch.trace.events[position] = (phase, kind, float(raw), sql)
    elif change == "native-call-order":
        records["native_calls"].reverse()
    elif change == "write-after-provenance":
        records["writes"][0]["returned_at"] = records["provenance"][0]["entered_at"] + 1
    elif change == "position-float":
        insert["entered_at"] = float(insert["entered_at"])
    elif change == "observed-before-expiry":
        records["provenance"][0]["observed"] = "2000-01-01T00:00:00.000000Z"
    elif change == "observed-mismatch":
        records["cursors"][0]["observed"] = "2027-01-01T00:00:00.000000Z"
    elif change == "role":
        records["provenance"][0]["database_role"] = ""
    elif change == "uid-bool":
        records["provenance"][0]["os_uid"] = False
    elif change == "progress-write":
        records["executions"].append({**deepcopy(execution), "name": "progress.insert"})
    else:
        records["provenance"].clear()
    with pytest.raises((AssertionError, ValueError)):
        accept(value, CASES[2])


@pytest.mark.parametrize("case", CASES[:2])
@pytest.mark.parametrize("field", ["writes", "executions", "provenance", "cursors", "native_calls"])
def test_preparation_refusal_has_no_insert_or_post_write_receipts(case, field, monkeypatch):
    value = delegated(case, monkeypatch)
    value.observations[field].append({"name": "accounts.insert"})
    with pytest.raises((AssertionError, ValueError, KeyError)):
        accept(value, case)


@pytest.mark.parametrize(
    "change",
    [
        "old-id",
        "old-start",
        "parent",
        "job-budget-float",
        "queued-reserved-bool",
        "queued-payload",
        "wrong-scope-project",
        "old-job-present",
        "not-expired",
    ],
)
def test_expired_first_account_intent_requires_distinct_genuine_admitted_job(change):
    first, requested, before, _, _, _, target = independent_state(CASES[2])
    if change == "old-id":
        requested["accounts"][0]["id"] = identity(300)
    elif change == "old-start":
        requested["accounts"][0].update(
            scope="organization", scope_id=ORG, job_id=None, project_id=None
        )
    elif change == "parent":
        requested["parent_manifest_digest"] = "f" * 64
    elif change in {"job-budget-float", "queued-reserved-bool", "queued-payload"}:
        key, replacement = {
            "job-budget-float": ("budget", 1.0),
            "queued-reserved-bool": ("reserved", False),
            "queued-payload": ("payload_version", 1),
        }[change]
        cells = [list(row) for row in before["tables"]["jobs"]["rows"]]
        cells[1][before["tables"]["jobs"]["columns"].index(key)] = replacement
        before["tables"]["jobs"]["rows"] = tuple(tuple(row) for row in cells)
    elif change == "wrong-scope-project":
        requested["accounts"][0]["project_id"] = identity(999)
    elif change == "old-job-present":
        target = OLD_JOB
        requested["accounts"][0].update(job_id=OLD_JOB, scope_id=OLD_JOB, limit_microusd=10000000)
    else:
        requested["accounts"][0]["period_end"] = "2100-01-01T00:00:00.000000Z"
    with pytest.raises((AssertionError, ValueError, MigrationRefused)):
        assert_intent(first, requested, before, CASES[2], target, OBSERVED)


@pytest.mark.parametrize(
    "change",
    [
        "table-cell",
        "table-type",
        "column",
        "table",
        "catalog",
        "authority",
        "role",
        "source",
        "legacy",
        "objects",
        "journal",
    ],
)
def test_full_state_and_all_storage_domains_are_preserved(change):
    # Independent explicit snapshot, intentionally including unrelated/native domains.
    before = {
        "tables": {
            "jobs": {"columns": ("id", "budget"), "rows": (("j", 1),)},
            "unrelated": {"columns": ("data",), "rows": (({"key": [1]},),)},
        },
        "catalog": {"tables": ["jobs", "unrelated"]},
        "authority": {"relations": [("jobs", "owner", None)]},
        "role": "owner",
    }
    source = {"jobs": [("j", 1)], "records": [("r", {"payload": True})]}
    stores = {
        "legacy": {"cipher": "a" * 64},
        "objects": {"admitted": "b" * 64},
        "journal": {"intent": "c" * 64},
    }
    after, source_after, stores_after = deepcopy(before), deepcopy(source), deepcopy(stores)
    assert_preservation(before, after, source, source_after, stores, stores_after)
    if change == "table-cell":
        after["tables"]["unrelated"]["rows"][0][0]["key"].append(2)
    elif change == "table-type":
        after["tables"]["jobs"]["rows"] = (("j", True),)
    elif change == "column":
        after["tables"]["jobs"]["columns"] = ("id", "limit")
    elif change == "table":
        del after["tables"]["unrelated"]
    elif change == "catalog":
        after["catalog"]["tables"].append("extra")
    elif change == "authority":
        after["authority"]["relations"][0] = ("jobs", "other", None)
    elif change == "role":
        after["role"] = "other"
    elif change == "source":
        source_after["records"][0][1]["payload"] = 1
    else:
        stores_after[change].clear()
    with pytest.raises(AssertionError):
        assert_preservation(before, after, source, source_after, stores, stores_after)


def test_exact_insert_literal_matches_original_typed_postgresql_compiler():
    key = ("postgresql", "accounts.insert")
    statement = text(SQL[key]).bindparams(
        *(
            bindparam(name, type_=ledger_service._TYPES[kind])
            for name, kind in PARAMETER_TYPES[key].items()
        )
    )
    assert str(statement.compile(dialect=PGDialect_psycopg())) == INSERT_SQL


@pytest.mark.parametrize("case,expected", [(CASES[0], 131), (CASES[1], 124), (CASES[2], 244)])
def test_original_source_sites_are_the_reviewed_three_branches(case, expected):
    assert site(case)[1] == expected


def test_timestamp_normalization_preserves_native_utc_without_accepting_numeric():
    assert canonical_time(datetime(2001, 1, 1, tzinfo=UTC)) == EXPIRED
    with pytest.raises(AssertionError):
        canonical_time(1)


@pytest.mark.parametrize("kind", [KeyboardInterrupt, SystemExit])
def test_cursor_observer_preserves_interrupt_object(kind, monkeypatch):
    first, requested, *_ = independent_state(CASES[2])
    engine, raw = object(), object()
    connection = SimpleNamespace(engine=engine)
    error = kind("window-control")

    def fail():
        raise error

    work = SimpleNamespace(_raw=raw, _connection=connection, check=fail)
    watch = SimpleNamespace(work=work, engine=engine, trace=SimpleNamespace(events=[]))
    recorded = []
    with (
        observe_window(watch, monkeypatch, lambda *value: recorded.append(value)) as observed,
        pytest.raises(kind) as caught,
    ):
        ledger_service._ledger_cursors(
            connection, validate_ledger_manifest(requested), None, OBSERVED, "owner", 1001, work
        )
    assert caught.value is error
    assert observed["cursors"][0]["error"]["identity"] == id(error)
    assert recorded[0][0] == "window_observation"
