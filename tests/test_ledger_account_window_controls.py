"""Pure original-gate and independent witness controls; no native database evidence."""

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import psycopg
import pytest
from ledger_account_window_fixture import (
    CASES,
    EXPIRED,
    INSERT_SQL,
    PROVENANCE_SQL,
    assert_expiry_source,
    assert_intent,
    assert_preservation,
    assert_refusal,
    canonical_time,
    initial_window,
    site,
    window_intent,
)
from ledger_account_window_observer import identity as window_identity
from ledger_account_window_observer import observe_window
from ledger_cohort_observer import observe_cohort
from ledger_project_binding import observe_projects
from ledger_provisioning_fixture import digest, identity, source_fingerprint
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from agent_rewind.migrations import ledger_service, ledger_source
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.ledger_writer_sql import PARAMETER_TYPES, SQL
from agent_rewind.migrations.schema import COLUMNS, LEDGER, MigrationRefused

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

    def __iter__(self):
        return iter(deepcopy(self.rows))


def delegated(case, monkeypatch, *, earlier=None):
    first, requested, before, jobs, scopes, accounts, target = independent_state(case)
    raw = SimpleNamespace()
    engine = SimpleNamespace(dialect=PGDialect_psycopg())
    engine.dialect.server_version_info = (16, 0)
    connection = SimpleNamespace(
        engine=engine, dialect=engine.dialect, invalidated=False, closed=False
    )
    work = LedgerWork()
    work._raw, work._connection = raw, connection
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
        parameters=SimpleNamespace(receipts=[]),
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
        watch.parameters.receipts.append(
            {
                "phase": "ordinary",
                "raw_id": id(raw),
                "sql_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "parameter_type": type(parameters).__name__,
                "parameter_count": 0 if parameters is None else len(parameters),
                "outcome": "return",
            }
        )
        return cursor

    class InertCursor:
        connection = raw

        def __init__(self, rowcount=-1):
            self.rowcount = rowcount

        def execute(self, query, parameters=None):
            return psycopg.Cursor.execute(self, query, parameters)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    raw.cursor = InertCursor

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
        cursor = InertCursor(count)
        query = str(statement.compile(dialect=engine.dialect))
        work._before(connection, cursor, query, parameters, None, False)
        engine.dialect.do_execute(cursor, query, parameters)
        work._after()
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
    engine, raw = SimpleNamespace(dialect=PGDialect_psycopg()), object()
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


def test_original_work_guard_precedes_installed_dialect_body_capture(monkeypatch):
    value = delegated(CASES[2], monkeypatch)
    accept(value, CASES[2])
    calls = value.observations["native_calls"]
    assert [row["name"] for row in calls] == ["accounts.insert", "provenance.observe"]
    executions = [
        row
        for row in value.observations["executions"]
        if row["name"] in {"accounts.insert", "provenance.observe"}
    ]
    start, end = executions[0]["entered_at"], executions[-1]["returned_at"]
    span = value.watch.trace.events[start:end]
    # Six original physical queries remain; the body observer records only two.
    assert len(span) == 12
    assert [row[3] for row in span[::2]] == [
        "SET LOCAL statement_timeout = '20000ms'",
        "SET LOCAL lock_timeout = '5000ms'",
        INSERT_SQL,
        "SET LOCAL statement_timeout = '20000ms'",
        "SET LOCAL lock_timeout = '5000ms'",
        PROVENANCE_SQL,
    ]
    assert value.watch.work.observed_ordinary == 12  # Two projects queries and two targets.
    assert value.watch.work._deadline > 0


@pytest.mark.parametrize("name", ["accounts.insert", "provenance.observe"])
@pytest.mark.parametrize(
    "change",
    [
        "missing-setter",
        "wrong-setting",
        "reversed-settings",
        "statement-over-cap",
        "lock-over-cap",
        "zero-timeout",
        "noncanonical-timeout",
        "setter-raw-float",
        "setter-return-missing",
        "setter-parameter",
        "setter-count-bool",
        "setter-raise",
        "body-includes-setters",
        "execution-end",
        "unreported-extra-query",
    ],
)
def test_guarded_body_rejects_missing_foreign_or_invalid_setters(name, change, monkeypatch):
    value = delegated(CASES[2], monkeypatch)
    execution = next(row for row in value.observations["executions"] if row["name"] == name)
    body = next(row for row in value.observations["native_calls"] if row["name"] == name)
    events = value.watch.trace.events
    start = execution["entered_at"]
    index = sum(row[1] == "sql-call" for row in events[:start])
    receipts = value.watch.parameters.receipts

    def replace_query(position, query):
        for offset in (0, 1):
            phase, kind, raw, _ = events[position + offset]
            events[position + offset] = (phase, kind, raw, query)
        ordinal = sum(row[1] == "sql-call" for row in events[:position])
        receipts[ordinal]["sql_sha256"] = hashlib.sha256(query.encode()).hexdigest()

    if change == "missing-setter":
        execution["entered_at"] += 2
    elif change == "wrong-setting":
        replace_query(start, "SET LOCAL application_name = '20000ms'")
    elif change == "reversed-settings":
        a, b = events[start][3], events[start + 2][3]
        replace_query(start, b)
        replace_query(start + 2, a)
    elif change == "statement-over-cap":
        replace_query(start, "SET LOCAL statement_timeout = '20001ms'")
    elif change == "lock-over-cap":
        replace_query(start + 2, "SET LOCAL lock_timeout = '5001ms'")
    elif change == "zero-timeout":
        replace_query(start, "SET LOCAL statement_timeout = '0ms'")
    elif change == "noncanonical-timeout":
        replace_query(start, "SET LOCAL statement_timeout = '020000ms'")
    elif change == "setter-raw-float":
        phase, kind, raw, query = events[start]
        events[start] = (phase, kind, float(raw), query)
    elif change == "setter-return-missing":
        phase, _, raw, query = events[start + 1]
        events[start + 1] = (phase, "sql-raise", raw, query)
    elif change == "setter-parameter":
        receipts[index]["parameter_type"] = "dict"
    elif change == "setter-count-bool":
        receipts[index]["parameter_count"] = False
    elif change == "setter-raise":
        receipts[index]["outcome"] = "raise"
    elif change == "body-includes-setters":
        body["entered_at"] = start
    elif change == "execution-end":
        execution["returned_at"] -= 2
    else:
        replace_query(start, "SELECT 1")
    with pytest.raises((AssertionError, ValueError)):
        accept(value, CASES[2])


@pytest.mark.parametrize("name", ["accounts.insert", "provenance.observe"])
def test_guarded_body_accepts_strictly_reduced_remaining_time_setters(name, monkeypatch):
    value = delegated(CASES[2], monkeypatch)
    execution = next(row for row in value.observations["executions"] if row["name"] == name)
    events = value.watch.trace.events
    for offset, query in [
        (0, "SET LOCAL statement_timeout = '4567ms'"),
        (2, "SET LOCAL lock_timeout = '4566ms'"),
    ]:
        position = execution["entered_at"] + offset
        ordinal = sum(row[1] == "sql-call" for row in events[:position])
        for i in (position, position + 1):
            phase, kind, raw, _ = events[i]
            events[i] = (phase, kind, raw, query)
        value.watch.parameters.receipts[ordinal]["sql_sha256"] = hashlib.sha256(
            query.encode()
        ).hexdigest()
    accept(value, CASES[2])


def test_exact_provenance_literal_matches_original_postgresql_compiler():
    key = ("postgresql", "provenance.observe")
    assert str(text(SQL[key]).compile(dialect=PGDialect_psycopg())) == PROVENANCE_SQL


def source_span(monkeypatch):
    """Original hasher/guard/dialect on inert data, with synthetic caller metadata.

    Observed SQL/binds come from the original hasher, never source_profile().
    The literal rows and caller fields establish only this pure serialization control.
    """
    from ledger_source_boundary import source_site
    from ledger_source_boundary_postgres import observe_native_source

    original = {
        "api_keys": [("a" * 32, "hash", "admin", "key", None, 0)],
        "audit": [(1, 1.0, "actor", "action", "target")],
        "events": [("run", 1, "artifact", "hash")],
        "jobs": [
            ("b" * 32, "run", 1.0, "{}", "failed", None, None, 0, 1, 0, None, "error", "actor")
        ],
        "records": [("c" * 32, "task", 1.0, {})],
    }
    dialect = PGDialect_psycopg()
    dialect.server_version_info = (16, 0)
    engine, raw = SimpleNamespace(dialect=dialect), SimpleNamespace()
    connection = SimpleNamespace(engine=engine, dialect=dialect, invalidated=False, closed=False)
    work = LedgerWork()
    work._connection, work._raw, work._attached = connection, raw, True
    events, receipts, executed = [], [], []
    watch = SimpleNamespace(
        engine=engine,
        work=work,
        trace=SimpleNamespace(events=events, handles=[raw], phase="ordinary"),
        parameters=SimpleNamespace(receipts=receipts),
        owns=lambda candidate: candidate is raw,
    )

    def physical(cursor, query, parameters=None):
        assert cursor.connection is raw
        events.extend(
            [
                ("ordinary", "sql-call", id(raw), query),
                ("ordinary", "sql-return", id(raw), query),
            ]
        )
        receipts.append(
            {
                "phase": "ordinary",
                "raw_id": id(raw),
                "sql_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "parameter_type": type(parameters).__name__,
                "parameter_count": 0 if parameters is None else len(parameters),
                "outcome": "return",
            }
        )
        return cursor

    class Cursor:
        connection = raw

        def __init__(self, rowcount=-1):
            self.rowcount = rowcount

        def execute(self, query, parameters=None):
            return psycopg.Cursor.execute(self, query, parameters)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    raw.cursor = Cursor
    statements = {
        sql: name
        for (kind, backend, name), sql in ledger_source.SOURCE_PREFLIGHT_SQL.items()
        if kind == "all" and backend == "postgresql"
    }
    statements.update(
        {sql: name for (backend, name), sql in ledger_source.SQL.items() if backend == "postgresql"}
    )
    statements[SQL[("postgresql", "accounts.insert")]] = "accounts.insert"

    def execute(statement, parameters):
        name = statements[statement.text]
        if name == "accounts.insert":
            result = []
        elif name.startswith("source_count_"):
            result = [{"candidate_rows": 1}]
        elif name.startswith("source_stats_"):
            result = [
                {
                    "observed_rows": 1,
                    "graph_invalid_rows": 0,
                    "original_native_bytes": 1,
                    "max_original_native_bytes": 1,
                }
            ]
        elif name.startswith("source_gate_"):
            result = [
                {
                    "candidate_count": 1,
                    "invalid_rows": 0,
                    "max_row_bytes": 1,
                    "selected_count": 1,
                    "selected_bytes": 1,
                }
            ]
        else:
            assert name.startswith("source_body_") and name.endswith("_first")
            table_name = name.removeprefix("source_body_").removesuffix("_first")
            fields = [column[0] for column in COLUMNS[table_name]]
            result = [
                {
                    **dict(zip(fields, original[table_name][0], strict=True)),
                    "source_ordinal": 1,
                    "native_row_bytes": 1,
                    "invalid_row": 0,
                }
            ]
        cursor = Cursor(1)
        query = str(statement.compile(dialect=dialect))
        value = {
            **window_identity(watch),
            "name": name,
            "entered_at": len(events),
            "values": deepcopy(parameters),
        }
        work._before(connection, cursor, query, parameters, None, False)
        body_start = len(events)
        dialect.do_execute(cursor, query, parameters)
        body_end = len(events)
        work._after()
        value.update(returned_at=len(events), rowcount=cursor.rowcount)
        executed.append(
            (
                value,
                {
                    **window_identity(watch),
                    "name": name,
                    "sql": query,
                    "parameters": deepcopy(parameters),
                    "rowcount": cursor.rowcount,
                    "entered_at": body_start,
                    "returned_at": body_end,
                },
            )
        )
        return Result(result, cursor.rowcount)

    connection.execute = execute
    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Cursor, "execute", physical)
        with observe_native_source(watch, patch, lambda *_: None) as (boundary, calls):
            result = ledger_service.source_digest(connection, work)
        (observed_hash,) = boundary["hashes"]
        # The actual call here is from this control, not initialize_ledger.
        assert observed_hash["original_caller"] is False
        first, manifest, *_ = independent_state(CASES[2])
        manifest["source_digest"] = source_fingerprint(original)
        assert result == manifest["source_digest"]
        values = {
            **manifest["accounts"][0],
            "opening_held_microusd": 0,
            "held_microusd": 0,
            "accounted_microusd": 0,
        }
        ledger_service._write(connection, "accounts.insert", values)
    gate, _ = source_site()
    anchor = window_identity(watch)
    prepared = {
        **anchor,
        "original_caller": True,
        "line": gate - 1,
        "entered_at": 0,
        "returned_at": 0,
        "completed": True,
        "manifest": deepcopy(manifest),
        "state": {"manifest_count": 1},
    }
    hashed = {
        **observed_hash,
        "original_caller": True,
        "line": gate,
        "preparation": [prepared],
        "native_calls": calls,
    }
    execution, body = executed[-1]
    observations = {"source_hashes": [hashed], "executions": [execution], "native_calls": [body]}
    return observations, original, manifest, events, receipts, anchor


def test_original_source_hash_with_one_exact_insert_uses_only_local_cte_allowance(monkeypatch):
    args = source_span(monkeypatch)
    before = deepcopy(args)
    assert_expiry_source(*args)
    assert args == before
    assert len(args[0]["source_hashes"][0]["native_calls"]) == 60


@pytest.mark.parametrize(
    "change",
    [
        "missing-hash",
        "duplicate-hash",
        "wrong-caller",
        "caller-int",
        "wrong-line",
        "wrong-prepare-caller",
        "incomplete-prepare",
        "wrong-prepare-manifest",
        "foreign-work",
        "raw-float",
        "source-result",
        "manifest-source",
        "source-row",
        "before-prepare",
        "after-insert",
        "work-float",
        "work-undercount",
        "native-param-float",
        "native-param-wrong",
        "changed-source-cte",
        "outside-source-cte",
        "extra-insert",
        "unknown-outside-cte",
        "wrong-insert-position",
        "wrong-insert-rowcount",
    ],
)
def test_source_allowance_rejects_wrong_provenance_span_bindings_and_extra_queries(
    change, monkeypatch
):
    args = source_span(monkeypatch)
    assert_expiry_source(*args)
    observations, original, manifest, events, parameters, _ = args
    hashed = observations["source_hashes"][0]
    prepared = hashed["preparation"][0]
    calls = hashed["native_calls"]
    if change == "missing-hash":
        observations["source_hashes"].clear()
    elif change == "duplicate-hash":
        observations["source_hashes"].append(deepcopy(hashed))
    elif change == "wrong-caller":
        hashed["original_caller"] = False
    elif change == "caller-int":
        hashed["original_caller"] = 1
    elif change == "wrong-line":
        hashed["line"] += 1
    elif change == "wrong-prepare-caller":
        prepared["original_caller"] = False
    elif change == "incomplete-prepare":
        prepared["completed"] = False
    elif change == "wrong-prepare-manifest":
        prepared["manifest"]["source_digest"] = "e" * 64
    elif change == "foreign-work":
        hashed["work_id"] += 1
    elif change == "raw-float":
        hashed["raw_id"] = float(hashed["raw_id"])
    elif change == "source-result":
        hashed["result"] = "e" * 64
    elif change == "manifest-source":
        manifest["source_digest"] = "e" * 64
    elif change == "source-row":
        original["records"][0][-1]["changed"] = True
    elif change == "before-prepare":
        prepared["returned_at"] = hashed["entered_at"] + 1
    elif change == "after-insert":
        observations["executions"][0]["entered_at"] = hashed["returned_at"] - 1
    elif change == "work-float":
        hashed["work_before"] = float(hashed["work_before"])
    elif change == "work-undercount":
        hashed["work_after"] -= 1
    elif change in {"native-param-float", "native-param-wrong"}:
        call = next(
            row for row in calls if row["parameters"] and "selected_count" in row["parameters"]
        )
        call["parameters"]["selected_count"] = 1.0 if change.endswith("float") else 2
    elif change == "changed-source-cte":
        call = next(row for row in calls if row["sql"].startswith("WITH"))
        sql = call["sql"] + " "
        position = call["entered_at"]
        call["sql"] = sql
        for offset in (0, 1):
            phase, kind, raw, _ = events[position + offset]
            events[position + offset] = (phase, kind, raw, sql)
        parameters[position // 2]["sql_sha256"] = hashlib.sha256(sql.encode()).hexdigest()
    elif change in {"outside-source-cte", "extra-insert", "unknown-outside-cte"}:
        sql = (
            next(row["sql"] for row in calls if row["sql"].startswith("WITH"))
            if change == "outside-source-cte"
            else INSERT_SQL
            if change == "extra-insert"
            else "WITH changed AS (DELETE FROM jobs RETURNING id) SELECT * FROM changed"
        )
        raw = args[-1]["raw_id"]
        events.extend([("ordinary", "sql-call", raw, sql), ("ordinary", "sql-return", raw, sql)])
        parameters.append(
            {
                "phase": "ordinary",
                "raw_id": raw,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                "parameter_type": "dict",
                "parameter_count": 0,
                "outcome": "return",
            }
        )
    elif change == "wrong-insert-position":
        observations["native_calls"][0]["entered_at"] += 2
    else:
        observations["native_calls"][0]["rowcount"] = True
    with pytest.raises((AssertionError, ValueError)):
        assert_expiry_source(*args)
