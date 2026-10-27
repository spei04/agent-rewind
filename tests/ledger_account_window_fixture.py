"""Independent manifests and exact original refusal oracles for finite windows."""

import ast
import hashlib
import inspect
import re
from copy import deepcopy
from datetime import UTC, datetime

from ledger_eligibility_fixture import rows
from ledger_provisioning_fixture import (
    ROLLOVER,
    START,
    digest,
    identity,
    initial_manifest,
    source_fingerprint,
)
from ledger_restore_authority import typed

from agent_rewind.migrations import ledger_provisioning
from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest, validate_time
from agent_rewind.migrations.schema import MigrationRefused

CASES = ("overlap-current-period", "renew-expired-job-period", "first-job-period-already-expired")
EXPIRED = "2001-01-01T00:00:00.000000Z"
OVERLAP_START = "2050-01-01T00:00:00.000000Z"
OVERLAP_END = "2150-01-01T00:00:00.000000Z"
# Exact historical native INSERT, independently retained from the accepted B1 receipt.
# Compiler regression checks this literal without normalizing whitespace or casts.
INSERT_SQL = (
    "INSERT INTO budget_accounts (\n"
    "  id, organization_id, scope, scope_id, project_id, job_id, period_start, period_end, "
    "limit_microusd, opening_held_microusd, held_microusd, accounted_microusd\n"
    ") VALUES (\n"
    "  %(id)s::VARCHAR, %(organization_id)s::VARCHAR, %(scope)s::VARCHAR, "
    "%(scope_id)s::VARCHAR, %(project_id)s::VARCHAR, %(job_id)s::VARCHAR, "
    "CAST(%(period_start)s::VARCHAR AS TIMESTAMP WITH TIME ZONE), "
    "CAST(%(period_end)s::VARCHAR AS TIMESTAMP WITH TIME ZONE), "
    "%(limit_microusd)s::BIGINT, %(opening_held_microusd)s::BIGINT, "
    "%(held_microusd)s::BIGINT, %(accounted_microusd)s::BIGINT\n)\n"
)

PROVENANCE_SQL = (
    "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS initialized_at,\n'
    "  CAST(current_user AS TEXT) AS database_role\n"
)


def equal(actual, expected):
    assert typed(actual) == typed(expected)


def initial_window(fixture, case):
    assert case in CASES
    manifest = initial_manifest(fixture)
    legacy_job = sorted(job["id"] for job in fixture.jobs)[0]
    if case == CASES[1]:
        (account,) = [row for row in manifest["accounts"] if row["job_id"] == legacy_job]
        account["period_end"] = EXPIRED
    validate_ledger_manifest(manifest)
    return manifest, legacy_job


def window_intent(fixture, first, case, admitted_job, legacy_job):
    assert case in CASES
    if case == CASES[0]:
        (account,) = [row for row in first["accounts"] if row["scope"] == "organization"]
        account = {**account, "period_start": OVERLAP_START, "period_end": OVERLAP_END}
    else:
        job_id = legacy_job if case == CASES[1] else admitted_job
        (job,) = [row for row in fixture.jobs if row["id"] == job_id]
        account = {
            "organization_id": fixture.organization,
            "scope": "job",
            "scope_id": job_id,
            "project_id": fixture.project,
            "job_id": job_id,
            "period_start": EXPIRED if case == CASES[1] else START,
            "period_end": ROLLOVER if case == CASES[1] else EXPIRED,
            "limit_microusd": job["budget"],
        }
    requested = {
        **deepcopy(first),
        "manifest_id": identity(9201),
        "operation": "provision",
        "parent_manifest_digest": digest(first),
        "source_digest": fixture.source,
        "opening_accounts": None,
        "accounts": [{**account, "id": identity(9200)}],
    }
    validate_ledger_manifest(requested)
    return requested


def site(case):
    function = (
        ledger_provisioning._ledger_cursors
        if case == CASES[2]
        else ledger_provisioning._prepare_ledger
    )
    source, start = inspect.getsourcelines(function)
    conditions = {
        CASES[
            0
        ]: "row['period_start'] < account.period_end and account.period_start < row['period_end']",
        CASES[1]: "account.job_id is not None and row['job_id'] == account.job_id",
        CASES[2]: "account.scope == 'job' and account.period_end <= initialized_at",
    }
    (condition,) = [
        node
        for node in ast.walk(ast.parse("".join(source)))
        if isinstance(node, ast.If) and ast.unparse(node.test) == conditions[case]
    ]
    (refusal,) = condition.body
    assert isinstance(refusal, ast.Raise)
    code = "invalid_ledger_manifest" if case == CASES[2] else "ledger_manifest_conflict"
    assert ast.unparse(refusal.exc) == f"MigrationRefused('{code}')"
    return function.__code__, start + refusal.lineno - 1


def canonical_time(value):
    if type(value) is datetime:
        assert value.tzinfo is not None and value.utcoffset().total_seconds() == 0
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert type(value) is str
    validate_time(value)
    return value


def assert_intent(first, requested, before, case, target_job, observed):
    validate_ledger_manifest(first)
    validate_ledger_manifest(requested)
    validate_time(observed)
    assert first["operation"] == "initialize" and requested["operation"] == "provision"
    assert requested["manifest_id"] != first["manifest_id"]
    assert requested["parent_manifest_digest"] == digest(first)
    assert requested["opening_accounts"] is None
    assert requested["installation_key"] == first["installation_key"]
    assert requested["schema_version"] == first["schema_version"]
    (account,) = requested["accounts"]
    current = rows(before, "budget_accounts")
    assert len({row["id"] for row in current}) == len(current)
    assert account["id"] not in {row["id"] for row in current}
    assert not any(
        (row["scope"], row["scope_id"], canonical_time(row["period_start"]))
        == (account["scope"], account["scope_id"], account["period_start"])
        for row in current
    )
    (organization,) = {row["organization_id"] for row in current}
    assert account["organization_id"] == organization
    assert type(account["limit_microusd"]) is int and account["limit_microusd"] >= 0
    if case == CASES[0]:
        assert target_job is None
        (old,) = [row for row in current if row["scope"] == "organization"]
        equal(
            {
                key: account[key]
                for key in ("scope", "scope_id", "project_id", "job_id", "limit_microusd")
            },
            {
                key: old[key]
                for key in ("scope", "scope_id", "project_id", "job_id", "limit_microusd")
            },
        )
        assert canonical_time(old["period_start"]) == START
        assert canonical_time(old["period_end"]) == ROLLOVER
        assert account["period_start"] == OVERLAP_START and account["period_end"] == OVERLAP_END
    else:
        (job,) = [row for row in rows(before, "jobs") if row["id"] == target_job]
        (scope,) = [
            row
            for row in rows(before, "resource_scopes")
            if row["resource_kind"] == "job" and row["resource_id"] == target_job
        ]
        assert account["job_id"] == account["scope_id"] == target_job
        assert account["scope"] == "job" and account["project_id"] == scope["project_id"]
        assert type(job["budget"]) is int
        equal(account["limit_microusd"], job["budget"])
        old = [row for row in current if row["job_id"] == target_job]
        assert observed >= EXPIRED
        if case == CASES[1]:
            (old,) = old
            assert canonical_time(old["period_start"]) == START
            assert canonical_time(old["period_end"]) == EXPIRED
            assert account["period_start"] == EXPIRED and account["period_end"] == ROLLOVER
            (original,) = [row for row in first["accounts"] if row["job_id"] == target_job]
            equal(original["period_end"], EXPIRED)
        else:
            assert case == CASES[2] and not old
            assert account["period_start"] == START and account["period_end"] == EXPIRED
            equal(
                {
                    key: job[key]
                    for key in ("status", "payload_version", "reserved", "owner", "lease_until")
                },
                {
                    "status": "queued",
                    "payload_version": 2,
                    "reserved": 0,
                    "owner": None,
                    "lease_until": None,
                },
            )


def assert_guarded_body(execution, body, watch):
    """Join the exact body to original raw setter pairs without filtering the trace."""
    events = watch.trace.events
    start, end = execution["entered_at"], execution["returned_at"]
    assert type(start) is int and type(end) is int
    assert 0 <= start < end <= len(events) and end == start + 6
    equal(body["entered_at"], start + 4)
    equal(body["returned_at"], end)
    equal(execution["rowcount"], 1)
    equal(body["rowcount"], 1)
    equal(watch.work.timeout_seconds, 5)
    raw_id = id(watch.work._raw)
    all_calls = [(i, row) for i, row in enumerate(events) if row[1] == "sql-call"]
    selected = [
        (position, row, receipt)
        for (position, row), receipt in zip(all_calls, watch.parameters.receipts, strict=True)
        if start <= position < end
    ]
    assert len(selected) == 3
    for ordinal, (position, row, receipt) in enumerate(selected):
        equal(position, start + ordinal * 2)
        phase, kind, raw, sql = row
        equal((phase, kind, raw), ("ordinary", "sql-call", raw_id))
        equal(events[position + 1], ("ordinary", "sql-return", raw_id, sql))
        if ordinal < 2:
            setting, cap = (
                ("statement_timeout", 20_000) if ordinal == 0 else ("lock_timeout", 5_000)
            )
            match = re.fullmatch(r"SET LOCAL " + setting + r" = '([1-9][0-9]*)ms'", sql)
            assert match and int(match[1]) <= cap
            parameter_type, parameter_count = "NoneType", 0
        else:
            equal(sql, body["sql"])
            assert type(body["parameters"]) is dict
            parameter_type, parameter_count = "dict", len(body["parameters"])
        equal(
            receipt,
            {
                "phase": "ordinary",
                "raw_id": raw_id,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                "parameter_type": parameter_type,
                "parameter_count": parameter_count,
                "outcome": "return",
            },
        )


def assert_refusal(
    first, requested, prior, observations, projects, entries, stages, error, watch, case
):
    """Check serialized joins and also the unmodified live original exception frame."""
    from ledger_account_window_observer import identity

    assert case in CASES
    anchor = identity(watch)
    equal(watch.work.timeout_seconds, 5)
    for collection in observations.values():
        assert type(collection) is list
        for entry in collection:
            for key, value in anchor.items():
                equal(entry[key], value)
            for key in ("entered_at", "returned_at", "refused_at"):
                if key in entry:
                    assert type(entry[key]) is int and 0 <= entry[key] <= len(watch.trace.events)
    (classification,) = observations["classification"]
    (project,) = projects
    (preparation,) = entries
    for entry in (classification, project, preparation):
        for key in ("raw_id", "work_id", "engine_id"):
            equal(entry[key], anchor[key])
        equal(entry["manifest"], requested)
    equal(classification["connection_id"], anchor["connection_id"])
    equal(project["connection_id"], anchor["connection_id"])
    assert classification["receipt"] is None and "error" not in classification
    assert project["returned"] is True and "error" not in project
    for value in (
        classification["entered_at"],
        classification["returned_at"],
        project["trace_position"],
        project["return_trace_position"],
        preparation["trace_position"],
    ):
        assert type(value) is int and value >= 0
    assert (
        classification["entered_at"] <= classification["returned_at"] <= project["trace_position"]
    )
    assert (
        project["trace_position"]
        <= project["return_trace_position"]
        <= preparation["trace_position"]
    )
    equal(preparation["state"], prior)
    (account,) = requested["accounts"]
    assert preparation["organization"] == project["organization"] == account["organization_id"]
    expected_code = "invalid_ledger_manifest" if case == CASES[2] else "ledger_manifest_conflict"
    assert type(error) is MigrationRefused and error.code == expected_code
    expected_error = {"type": "MigrationRefused", "code": expected_code, "identity": id(error)}
    code, line = site(case)
    live = []
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code is code:
            live.append(trace)
        trace = trace.tb_next
    (frame,) = live
    assert frame.tb_lineno == line and frame.tb_frame.f_locals["work"] is watch.work
    if case != CASES[2]:
        equal(stages, ["prepare.enter", "prepare.refused"])
        assert "returned" not in preparation
        equal(preparation["error"], expected_error)
        (rejected,) = preparation["traceback"]["preparation_frames"]
        equal(rejected["line"], line)
        equal(rejected["account"], account)
        equal(rejected["current"], preparation["financial"]["account"])
        jobs = {row["id"]: row for row in preparation["financial"]["job"]}
        scopes = {
            row["resource_id"]: row["project_id"]
            for row in preparation["financial"]["scope"]
            if row["resource_kind"] == "job"
        }
        equal(rejected["jobs"], jobs)
        equal(rejected["scopes"], scopes)
        assert rejected["assignments"] is None
        if case == CASES[1]:
            equal(rejected["job"], jobs[account["job_id"]])
            assert scopes[account["job_id"]] == account["project_id"]
        assert not observations["writes"]
        assert not any(
            row["name"]
            in {
                "accounts.insert",
                "progress.insert",
                "adoption.publish_fingerprint",
                "jobs.backfill",
            }
            for row in observations["executions"]
        )
        assert not observations["provenance"] and not observations["cursors"]
        assert not observations["native_calls"] and not observations["source_hashes"]
        refused_at = preparation["refusal_trace_position"]
    else:
        equal(stages, ["prepare.enter", "prepare.return"])
        assert preparation["returned"] is True and "error" not in preparation
        (write,) = observations["writes"]
        (provenance,) = observations["provenance"]
        (cursor,) = observations["cursors"]
        for entry in (write, provenance, cursor, *observations["native_calls"]):
            for key, value in anchor.items():
                equal(entry[key], value)
        assert write["name"] == "accounts.insert" and "error" not in write
        expected_values = {
            **account,
            "opening_held_microusd": 0,
            "held_microusd": 0,
            "accounted_microusd": 0,
        }
        equal(write["values"], expected_values)
        assert write["returned_at"] <= provenance["entered_at"]
        assert provenance["returned_at"] <= cursor["entered_at"]
        validate_time(provenance["observed"])
        assert account["period_end"] <= provenance["observed"]
        assert type(provenance["database_role"]) is str and provenance["database_role"]
        assert type(provenance["os_uid"]) is int and provenance["os_uid"] >= 0
        for key in ("observed", "database_role", "os_uid"):
            equal(cursor[key], provenance[key])
        equal(cursor["manifest"], requested)
        equal(cursor["error"], expected_error)
        assert "returned_at" not in cursor
        (rejected,) = cursor["original_frames"]
        equal(
            rejected,
            {
                "line": line,
                "account": account,
                "initialized_at": provenance["observed"],
                "work_id": anchor["work_id"],
                "connection_id": anchor["connection_id"],
            },
        )
        assert frame.tb_frame.f_locals["connection"] is watch.work._connection
        (execution,) = [
            row for row in observations["executions"] if row["name"] == "accounts.insert"
        ]
        equal(execution["values"], expected_values)
        equal(execution["rowcount"], 1)
        calls = observations["native_calls"]
        assert [row["name"] for row in calls] == ["accounts.insert", "provenance.observe"]
        insert = calls[0]
        equal(insert["sql"], INSERT_SQL)
        equal(insert["parameters"], expected_values)
        equal(insert["rowcount"], 1)
        assert (
            execution["entered_at"]
            <= insert["entered_at"]
            < insert["returned_at"]
            <= execution["returned_at"]
        )
        assert execution["returned_at"] <= write["returned_at"]
        equal(calls[1]["sql"], PROVENANCE_SQL)
        equal(calls[1]["parameters"], {})
        for call in calls:
            (original_execution,) = [
                row for row in observations["executions"] if row["name"] == call["name"]
            ]
            assert_guarded_body(original_execution, call, watch)
            assert call["returned_at"] == call["entered_at"] + 2
            equal(
                watch.trace.events[call["entered_at"] : call["returned_at"]],
                [
                    ("ordinary", "sql-call", anchor["raw_id"], call["sql"]),
                    ("ordinary", "sql-return", anchor["raw_id"], call["sql"]),
                ],
            )
        assert not any(
            row["name"] in {"progress.insert", "adoption.publish_fingerprint", "jobs.backfill"}
            for row in observations["executions"]
        )
        refused_at = cursor["refused_at"]
    names = [
        "rollback.before_native",
        "rollback.native_ack",
        "connection.close.before",
        "connection.close.return",
        "command.exit",
    ]
    selected = [row for row in watch.markers if row[0] in names]
    equal([row[0] for row in selected], names)
    positions = []
    for _name, raw_id, position in selected:
        equal(raw_id, anchor["raw_id"])
        assert type(position) is int and 0 <= position <= len(watch.trace.events)
        positions.append(position)
    assert positions == sorted(positions)
    assert "commit.before_native" not in [row[0] for row in watch.markers]
    assert type(refused_at) is int and refused_at <= selected[0][2]
    assert watch.outcome.confirmed_precommit_rollback and watch.outcome.rollback_acknowledged
    assert not watch.outcome.commit_attempted and not watch.outcome.cleanup_failed


def assert_preservation(before, after, source_before, source_after, stores_before, stores_after):
    equal(after, before)
    equal(source_after, source_before)
    equal(stores_after, stores_before)


def assert_expiry_source(observations, original, manifest, events, parameters, expected_identity):
    """Allow fixed source CTEs only inside the proven original pre-INSERT hash."""
    from ledger_source_boundary import source_site
    from ledger_source_boundary_postgres import _SOURCE_CTE_HASHES, assert_hash_span
    from test_ledger_reader_native import _assert_reviewed_ctes

    (hashed,) = observations["source_hashes"]
    (prepared,) = hashed["preparation"]
    (insertion,) = [row for row in observations["executions"] if row["name"] == "accounts.insert"]
    (insert_call,) = [
        row for row in observations["native_calls"] if row["name"] == "accounts.insert"
    ]
    for entry in (prepared, hashed, insertion, insert_call):
        for key, value in expected_identity.items():
            assert type(value) is int and value > 0
            equal(entry[key], value)
    gate, _ = source_site()
    assert prepared["original_caller"] is True and prepared["completed"] is True
    assert hashed["original_caller"] is True
    equal(prepared["line"], gate - 1)
    equal(hashed["line"], gate)
    equal(prepared["manifest"], manifest)
    expected_source = source_fingerprint(original)
    equal(hashed["result"], expected_source)
    equal(manifest["source_digest"], expected_source)
    for position in (
        prepared["entered_at"],
        prepared["returned_at"],
        hashed["entered_at"],
        hashed["returned_at"],
        insertion["entered_at"],
        insert_call["entered_at"],
        insert_call["returned_at"],
    ):
        assert type(position) is int and 0 <= position <= len(events)
    for key in ("work_before", "work_after"):
        assert type(hashed[key]) is int and 0 <= hashed[key] <= 2028
    assert (
        prepared["entered_at"]
        <= prepared["returned_at"]
        <= hashed["entered_at"]
        < hashed["returned_at"]
        <= insertion["entered_at"]
        < insert_call["entered_at"]
        < insert_call["returned_at"]
    )
    assert_hash_span(
        hashed, original, expected_identity["raw_id"], events, parameters, hashed["native_calls"]
    )
    equal(insert_call["sql"], INSERT_SQL)
    equal(insert_call["rowcount"], 1)
    body_position = insert_call["entered_at"]
    equal(events[body_position], ("ordinary", "sql-call", expected_identity["raw_id"], INSERT_SQL))
    equal(
        events[body_position + 1],
        ("ordinary", "sql-return", expected_identity["raw_id"], INSERT_SQL),
    )
    equal(insert_call["returned_at"], body_position + 2)
    reader_commands = []
    writes = 0
    start, end = hashed["entered_at"], hashed["returned_at"]
    for position, (phase, kind, raw, sql) in enumerate(events):
        if phase != "ordinary" or kind != "sql-call":
            continue
        equal(raw, expected_identity["raw_id"])
        if position == body_position:
            equal(sql, INSERT_SQL)
            writes += 1
            continue
        reviewed_source = (
            start <= position < end
            and hashlib.sha256(sql.encode()).hexdigest() in _SOURCE_CTE_HASHES
        )
        if not reviewed_source:
            reader_commands.append(sql)
        assert sql.lstrip().upper().startswith(("SELECT", "WITH", "SET", "SHOW", "LOCK"))
    equal(writes, 1)
    _assert_reviewed_ctes(reader_commands)
