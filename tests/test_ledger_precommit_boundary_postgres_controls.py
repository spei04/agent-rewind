"""Offline discrimination of native early-boundary receipts; no database proof."""

from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_precommit_boundary_fixture import INDEXES, STAGES, TABLES
from ledger_precommit_boundary_postgres_fixture import (
    ALL_PROBES,
    REFLECTION_PARAMETERS,
    assert_preservation_values,
)
from ledger_precommit_boundary_postgres_observer import assert_boundary, observe_boundary
from ledger_provisioning_fixture import SOURCE_FIELDS, source_fingerprint
from test_ledger_source_boundary_postgres_controls import physical_witness

from agent_rewind.migrations import ledger_service, ledger_work
from agent_rewind.migrations.schema import LEDGER, MigrationRefused

# Literal native SQL from the retained accepted PostgreSQL continuation,
# independent of the runtime builder and the hash policy checked below.
UPGRADE_SQL = (
    (
        "SELECT pg_catalog.pg_class.relname \nFROM pg_catalog.pg_class JOIN pg_c"
        "atalog.pg_namespace ON pg_catalog.pg_namespace.oid = pg_catalog.pg_cla"
        "ss.relnamespace \nWHERE pg_catalog.pg_class.relname IN (%(table_names_1"
        ")s::VARCHAR) AND pg_catalog.pg_class.relkind = ANY (ARRAY[%(param_1)s:"
        ":VARCHAR, %(param_2)s::VARCHAR, %(param_3)s::VARCHAR, %(param_4)s::VAR"
        "CHAR, %(param_5)s::VARCHAR]) AND pg_catalog.pg_table_is_visible(pg_cat"
        "alog.pg_class.oid) AND pg_catalog.pg_namespace.nspname != %(nspname_1)"
        "s::VARCHAR"
    ),
    ("SELECT alembic_version.version_num \nFROM alembic_version"),
    (
        "ALTER TABLE jobs ADD COLUMN lease_generation BIGINT NOT NULL DEFAULT 0"
        " CONSTRAINT ar7_jobs_generation CHECK(lease_generation BETWEEN 0 AND 9"
        "223372036854775807)"
    ),
    (
        "ALTER TABLE jobs ADD COLUMN legacy_reserved_microusd BIGINT NOT NULL D"
        "EFAULT 0 CONSTRAINT ar7_jobs_legacy_reserved CHECK(legacy_reserved_mic"
        "rousd BETWEEN 0 AND 9223372036854775807)"
    ),
    (
        "CREATE TABLE budget_accounts (\n        id VARCHAR(32) NOT NULL CONSTRA"
        "INT ar7_accounts_id CHECK(id ~ '^[0-9a-f]{32}$'),\n        organization"
        "_id VARCHAR(32) NOT NULL\n          CONSTRAINT ar7_accounts_organizatio"
        "n CHECK(organization_id ~ '^[0-9a-f]{32}$'),\n        scope VARCHAR(16)"
        " NOT NULL\n          CONSTRAINT ar7_accounts_scope CHECK(\n            s"
        "cope='organization' OR scope='project' OR scope='job'),\n        scope_"
        "id VARCHAR(32) NOT NULL\n          CONSTRAINT ar7_accounts_scope_id CHE"
        "CK(scope_id ~ '^[0-9a-f]{32}$'),\n        period_start TIMESTAMP WITH T"
        "IME ZONE NOT NULL\n          CONSTRAINT ar7_accounts_start CHECK(isfini"
        "te(period_start) AND EXTRACT(YEAR FROM period_start AT TIME ZONE 'UTC'"
        ") BETWEEN 1 AND 9999),\n        period_end TIMESTAMP WITH TIME ZONE NOT"
        " NULL CONSTRAINT ar7_accounts_end CHECK(isfinite(period_end) AND EXTRA"
        "CT(YEAR FROM period_end AT TIME ZONE 'UTC') BETWEEN 1 AND 9999),\n     "
        "   limit_microusd BIGINT NOT NULL\n          CONSTRAINT ar7_accounts_li"
        "mit CHECK(limit_microusd BETWEEN 0 AND 9223372036854775807),\n        h"
        "eld_microusd BIGINT NOT NULL CONSTRAINT ar7_accounts_held CHECK(held_m"
        "icrousd BETWEEN 0 AND 9223372036854775807),\n        accounted_microusd"
        " BIGINT NOT NULL\n          CONSTRAINT ar7_accounts_accounted CHECK(acc"
        "ounted_microusd BETWEEN 0 AND 9223372036854775807),\n        project_id"
        " VARCHAR(32)\n          CONSTRAINT ar7_accounts_project CHECK(\n        "
        "    project_id IS NULL OR (project_id ~ '^[0-9a-f]{32}$')),\n        jo"
        "b_id VARCHAR(32)\n          CONSTRAINT ar7_accounts_job CHECK(job_id IS"
        " NULL OR (job_id ~ '^[0-9a-f]{32}$')),\n        opening_held_microusd B"
        "IGINT NOT NULL DEFAULT 0\n          CONSTRAINT ar7_accounts_opening CHE"
        "CK(opening_held_microusd BETWEEN 0 AND 9223372036854775807),\n        C"
        "ONSTRAINT ar7_accounts_pk PRIMARY KEY(id),\n        CONSTRAINT ar7_acco"
        "unts_scope_period UNIQUE(organization_id,scope,scope_id,period_start),"
        "\n        CONSTRAINT ar7_accounts_job_window UNIQUE(job_id),\n        CO"
        "NSTRAINT ar7_accounts_organization_fk FOREIGN KEY(organization_id)\n   "
        "       REFERENCES organizations(id),\n        CONSTRAINT ar7_accounts_p"
        "roject_fk FOREIGN KEY(organization_id,project_id)\n          REFERENCES"
        " projects(organization_id,id),\n        CONSTRAINT ar7_accounts_period "
        "CHECK(period_start<period_end),\n        CONSTRAINT ar7_accounts_balanc"
        "e CHECK(\n          accounted_microusd<=limit_microusd AND held_microus"
        "d<=limit_microusd-accounted_microusd),\n        CONSTRAINT ar7_accounts"
        "_shape CHECK(\n          (scope='organization' AND scope_id=organizatio"
        "n_id\n            AND project_id IS NULL AND job_id IS NULL)\n          "
        "OR (scope='project' AND project_id IS NOT NULL AND scope_id=project_id"
        " AND job_id IS NULL)\n          OR (scope='job' AND project_id IS NOT N"
        "ULL AND job_id IS NOT NULL AND scope_id=job_id))\n    )"
    ),
    (
        "CREATE TABLE provider_calls (\n        id VARCHAR(32) NOT NULL CONSTRAI"
        "NT ar7_calls_id CHECK(id ~ '^[0-9a-f]{32}$'),\n        project_id VARCH"
        "AR(32) NOT NULL\n          CONSTRAINT ar7_calls_project CHECK(project_i"
        "d ~ '^[0-9a-f]{32}$'),\n        job_id VARCHAR(32) NOT NULL CONSTRAINT "
        "ar7_calls_job CHECK(job_id ~ '^[0-9a-f]{32}$'),\n        logical_call_i"
        "d VARCHAR(32) NOT NULL\n          CONSTRAINT ar7_calls_logical CHECK(lo"
        "gical_call_id ~ '^[0-9a-f]{32}$'),\n        purpose VARCHAR(20) NOT NUL"
        "L\n          CONSTRAINT ar7_calls_purpose CHECK(purpose='continuation' "
        "OR purpose='discovery'),\n        request_digest CHAR(64) NOT NULL\n    "
        "      CONSTRAINT ar7_calls_digest CHECK(request_digest ~ '^[0-9a-f]{64"
        "}$'),\n        price_version VARCHAR(128) NOT NULL\n          CONSTRAINT"
        " ar7_calls_price CHECK(length(price_version)<=128),\n        state VARC"
        "HAR(20) NOT NULL\n          CONSTRAINT ar7_calls_state CHECK(\n         "
        "   state='reserved' OR state='dispatching' OR state='observed'\n       "
        "     OR state='uncertain' OR state='reconciled'),\n        reserved_mic"
        "rousd BIGINT NOT NULL\n          CONSTRAINT ar7_calls_reserved CHECK(re"
        "served_microusd BETWEEN 0 AND 9223372036854775807),\n        usage_esti"
        "mate_microusd BIGINT\n          CONSTRAINT ar7_calls_estimate CHECK(\n  "
        "          usage_estimate_microusd IS NULL OR (usage_estimate_microusd "
        "BETWEEN 0 AND 9223372036854775807)),\n        provider_request_id VARCH"
        "AR(256)\n          CONSTRAINT ar7_calls_provider_request CHECK(\n       "
        "     provider_request_id IS NULL OR (length(provider_request_id)<=256)"
        "),\n        created_at TIMESTAMP WITH TIME ZONE NOT NULL CONSTRAINT ar7"
        "_calls_created CHECK(isfinite(created_at) AND EXTRACT(YEAR FROM create"
        "d_at AT TIME ZONE 'UTC') BETWEEN 1 AND 9999),\n        organization_id "
        "VARCHAR(32) NOT NULL\n          CONSTRAINT ar7_calls_organization CHECK"
        "(organization_id ~ '^[0-9a-f]{32}$'),\n        job_resource_kind VARCHA"
        "R(20) NOT NULL\n          CONSTRAINT ar7_calls_job_kind CHECK(job_resou"
        "rce_kind='job'),\n        lease_generation BIGINT NOT NULL\n          CO"
        "NSTRAINT ar7_calls_generation CHECK(lease_generation BETWEEN 1 AND 922"
        "3372036854775807),\n        organization_account_id VARCHAR(32) NOT NUL"
        "L\n          CONSTRAINT ar7_calls_org_account CHECK(organization_accoun"
        "t_id ~ '^[0-9a-f]{32}$'),\n        project_account_id VARCHAR(32) NOT N"
        "ULL\n          CONSTRAINT ar7_calls_project_account CHECK(project_accou"
        "nt_id ~ '^[0-9a-f]{32}$'),\n        job_account_id VARCHAR(32) NOT NULL"
        "\n          CONSTRAINT ar7_calls_job_account CHECK(job_account_id ~ '^["
        "0-9a-f]{32}$'),\n        CONSTRAINT ar7_calls_pk PRIMARY KEY(id),\n     "
        "   CONSTRAINT ar7_calls_logical_unique UNIQUE(project_id,logical_call_"
        "id),\n        CONSTRAINT ar7_calls_project_unique UNIQUE(project_id,id)"
        ",\n        CONSTRAINT ar7_calls_project_fk FOREIGN KEY(project_id) REFE"
        "RENCES projects(id),\n        CONSTRAINT ar7_calls_job_fk FOREIGN KEY(j"
        "ob_id) REFERENCES jobs(id),\n        CONSTRAINT ar7_calls_job_scope_fk "
        "FOREIGN KEY(project_id,job_resource_kind,job_id)\n          REFERENCES "
        "resource_scopes(project_id,resource_kind,resource_id),\n        CONSTRA"
        "INT ar7_calls_organization_fk FOREIGN KEY(organization_id)\n          R"
        "EFERENCES organizations(id),\n        CONSTRAINT ar7_calls_organization"
        "_project_fk FOREIGN KEY(organization_id,project_id)\n          REFERENC"
        "ES projects(organization_id,id),\n        CONSTRAINT ar7_calls_org_acco"
        "unt_fk FOREIGN KEY(organization_account_id)\n          REFERENCES budge"
        "t_accounts(id),\n        CONSTRAINT ar7_calls_project_account_fk FOREIG"
        "N KEY(project_account_id)\n          REFERENCES budget_accounts(id),\n  "
        "      CONSTRAINT ar7_calls_job_account_fk FOREIGN KEY(job_account_id)\n"
        "          REFERENCES budget_accounts(id)\n    )"
    ),
    (
        "CREATE TABLE budget_entries (\n        call_id VARCHAR(32) NOT NULL CON"
        "STRAINT ar7_entries_call CHECK(call_id ~ '^[0-9a-f]{32}$'),\n        ac"
        "count_id VARCHAR(32) NOT NULL\n          CONSTRAINT ar7_entries_account"
        " CHECK(account_id ~ '^[0-9a-f]{32}$'),\n        entry_kind VARCHAR(16) "
        "NOT NULL\n          CONSTRAINT ar7_entries_kind CHECK(\n            entr"
        "y_kind='reserve' OR entry_kind='settle' OR entry_kind='release'),\n    "
        "    amount_microusd BIGINT NOT NULL\n          CONSTRAINT ar7_entries_a"
        "mount CHECK(amount_microusd BETWEEN 0 AND 9223372036854775807),\n      "
        "  evidence_ref VARCHAR(32)\n          CONSTRAINT ar7_entries_evidence C"
        "HECK(\n            evidence_ref IS NULL OR (evidence_ref ~ '^[0-9a-f]{3"
        "2}$')),\n        created_at TIMESTAMP WITH TIME ZONE NOT NULL CONSTRAIN"
        "T ar7_entries_created CHECK(isfinite(created_at) AND EXTRACT(YEAR FROM"
        " created_at AT TIME ZONE 'UTC') BETWEEN 1 AND 9999),\n        project_i"
        "d VARCHAR(32) NOT NULL\n          CONSTRAINT ar7_entries_project CHECK("
        "project_id ~ '^[0-9a-f]{32}$'),\n        evidence_owner_kind VARCHAR(20"
        ") NOT NULL DEFAULT 'provider_call'\n          CONSTRAINT ar7_entries_ow"
        "ner CHECK(evidence_owner_kind='provider_call'),\n        evidence_role "
        "VARCHAR(32) NOT NULL DEFAULT 'budget_evidence'\n          CONSTRAINT ar"
        "7_entries_role CHECK(evidence_role='budget_evidence'),\n        CONSTRA"
        "INT ar7_entries_pk PRIMARY KEY(call_id,account_id,entry_kind),\n       "
        " CONSTRAINT ar7_entries_call_fk FOREIGN KEY(call_id) REFERENCES provid"
        "er_calls(id),\n        CONSTRAINT ar7_entries_account_fk FOREIGN KEY(ac"
        "count_id) REFERENCES budget_accounts(id),\n        CONSTRAINT ar7_entri"
        "es_project_fk FOREIGN KEY(project_id) REFERENCES projects(id),\n       "
        " CONSTRAINT ar7_entries_project_call_fk FOREIGN KEY(project_id,call_id"
        ")\n          REFERENCES provider_calls(project_id,id),\n        CONSTRAI"
        "NT ar7_entries_evidence_fk FOREIGN KEY(\n          project_id,evidence_"
        "owner_kind,call_id,evidence_ref,evidence_role)\n          REFERENCES ar"
        "tifact_refs(project_id,owner_kind,owner_id,artifact_id,role),\n        "
        "CONSTRAINT ar7_entries_evidence_shape CHECK(\n          (entry_kind='re"
        "serve' AND evidence_ref IS NULL)\n          OR ((entry_kind='settle' OR"
        " entry_kind='release') AND evidence_ref IS NOT NULL))\n    )"
    ),
    ("CREATE INDEX ar7_calls_job_id ON provider_calls(job_id)"),
    ("CREATE INDEX ar7_calls_organization_account_id ON provider_calls(organization_account_id)"),
    ("CREATE INDEX ar7_calls_project_account_id ON provider_calls(project_account_id)"),
    ("CREATE INDEX ar7_calls_job_account_id ON provider_calls(job_account_id)"),
    ("CREATE INDEX ar7_entries_account_id ON budget_entries(account_id)"),
    (
        "UPDATE alembic_version SET version_num='ar_0007_ledger' WHERE alembic_"
        "version.version_num = 'ar_0006_admission'"
    ),
)


def stage_rows(jobs, stage):
    return [
        [(LEDGER,)],
        [
            (job["id"], 0, job["reserved"] if stage == "first-backfill" and i == 0 else 0)
            for i, job in enumerate(jobs)
        ],
        [(0, 0, 0)],
        sorted([(table, "r") for table in TABLES] + [(name, "i") for name, _ in INDEXES]),
        [
            ("lease_generation", "bigint", True, "0"),
            ("legacy_reserved_microusd", "bigint", True, "0"),
        ],
        [(0, 0)],
    ]


def witness(stage):
    watch, _ = physical_witness("rollback")
    engine = object()
    raw = watch.work._raw
    watch.engine = engine
    watch.work._connection = SimpleNamespace(engine=engine)
    watch.work.timeout_seconds = 5
    watch.work.observed_ordinary = 0
    watch.trace = SimpleNamespace(events=[], handles=[raw], phase="ordinary")
    watch.owns = lambda value: value is raw
    identity = {
        "raw_id": id(raw),
        "work_id": id(watch.work),
        "engine_id": id(engine),
        "connection_id": id(watch.work._connection),
    }
    jobs = [
        {"id": token * 32, "reserved": amount}
        for token, amount in (("a", 35000), ("b", 85000), ("c", 125000))
    ]
    fixture = SimpleNamespace(jobs=jobs)
    manifest = {"manifest_id": "d" * 32, "operation": "initialize"}
    first = MigrationRefused("migration_busy")
    receipt = {
        "stage": stage,
        "identity": identity,
        "upgrades": [],
        "writes": [],
        "backfill_executions": [],
        "probes": [],
        "injections": [],
        "native_calls": [],
    }

    def entry():
        return {
            **identity,
            "entered_at": len(watch.trace.events),
            "work_before": watch.work.observed_ordinary,
        }

    def emit(query, bound):
        for sql, params in [
            ("SET LOCAL statement_timeout = '20000ms'", {}),
            ("SET LOCAL lock_timeout = '5000ms'", {}),
            (query, bound),
        ]:
            position = len(watch.trace.events)
            watch.trace.events.extend(
                [("ordinary", "sql-call", id(raw), sql), ("ordinary", "sql-return", id(raw), sql)]
            )
            receipt["native_calls"].append(
                {
                    "entered_at": position,
                    "returned_at": position + 2,
                    "phase": "ordinary",
                    "raw_id": id(raw),
                    "sql": sql,
                    "parameter_type": "dict",
                    "parameters": deepcopy(params),
                    "outcome": "return",
                }
            )
            watch.work.observed_ordinary += 1

    def returned(value):
        value.update(returned_at=len(watch.trace.events), work_after=watch.work.observed_ordinary)

    upgrade = {**entry(), "original_caller": True, "line": 251, "manifest": manifest}
    for i, sql in enumerate(UPGRADE_SQL):
        emit(sql, REFLECTION_PARAMETERS if i == 0 else {})
    returned(upgrade)
    receipt["upgrades"].append(upgrade)
    if stage == "first-backfill":
        values = {"id": jobs[0]["id"], "opening": jobs[0]["reserved"]}
        write = {
            **entry(),
            "original_caller": True,
            "line": 254,
            "name": "jobs.backfill",
            "values": values,
        }
        execution = {**entry(), "name": "jobs.backfill", "values": deepcopy(values)}
        emit(
            "UPDATE jobs SET legacy_reserved_microusd=%(opening)s::BIGINT, lease_generation=0 "
            "WHERE id=%(id)s::VARCHAR",
            values,
        )
        returned(write)
        returned(execution)
        execution["rowcount"] = 1
        receipt["writes"].append(write)
        receipt["backfill_executions"].append(execution)
    receipt["probe_start"] = len(watch.trace.events)
    before = watch.work.observed_ordinary
    for (name, sql), rows in zip(ALL_PROBES, stage_rows(jobs, stage), strict=True):
        probe = {**entry(), "name": name, "sql": sql, "rows": rows}
        emit(sql, {})
        returned(probe)
        receipt["probes"].append(probe)
    offset = len(watch.trace.events)
    receipt.update(probe_end=offset, probe_work=watch.work.observed_ordinary - before)
    receipt["injections"].append(
        {
            **identity,
            "position": offset,
            "type": "MigrationRefused",
            "code": "migration_busy",
            "exception_id": id(first),
        }
    )
    watch.trace.events.extend([("cleanup", "rollback-return", id(raw), None)] * 19)
    watch.markers = [(name, handle, position + offset) for name, handle, position in watch.markers]
    for row in watch.physical:
        row["trace_end"] += offset
    watch.command_boundary["trace_end"] += offset
    return receipt, fixture, manifest, first, watch


def check(items, raised=None):
    receipt, fixture, manifest, first, watch = items
    assert_boundary(receipt, fixture, manifest, first, first if raised is None else raised, watch)


def replace_call(items, index, *, sql=None, parameters=None):
    receipt, _, _, _, watch = items
    call = receipt["native_calls"][index]
    if parameters is not None:
        call["parameters"] = parameters
    if sql is not None:
        call["sql"] = sql
        for offset, kind in enumerate(("sql-call", "sql-return")):
            watch.trace.events[call["entered_at"] + offset] = (
                "ordinary",
                kind,
                call["raw_id"],
                sql,
            )


@pytest.mark.parametrize("stage", STAGES)
def test_complete_native_boundary_receipt(stage):
    check(witness(stage))


@pytest.mark.parametrize(
    "fault",
    [
        "stage",
        "missing-return",
        "wrong-caller",
        "wrong-line",
        "wrong-manifest",
        "wrong-work",
        "duplicate-upgrade",
        "native-error",
        "missing-native-return",
        "wrong-native-raw",
        "wrong-native-phase",
        "reflection-bind",
        "alter-changed",
        "extra-statement",
        "wrong-setter",
        "statement-cap",
        "lock-cap",
        "zero-timeout",
        "work-undercount",
        "invalid-empty-bind",
        "probe-work",
        "probe-position",
        "wrong-probe-revision",
        "float-generation",
        "catalog-missing-relation",
        "catalog-nullable-column",
        "catalog-trigger",
        "missing-injection",
        "late-injection",
        "wrong-exception-identity",
        "native-marker-pollution",
        "wrong-rollback-state",
        "first-close-not-physical",
        "late-close",
        "later-writer",
        "ordinary-sql-after-injection",
    ],
)
def test_incomplete_or_misattributed_stage_is_rejected(fault):
    items = witness("after-ddl")
    receipt, _, _, _, watch = items
    upgrade = receipt["upgrades"][0]
    if fault == "stage":
        receipt["stage"] = "after-accounts"
    elif fault == "missing-return":
        upgrade.pop("returned_at")
    elif fault == "wrong-caller":
        upgrade["original_caller"] = False
    elif fault == "wrong-line":
        upgrade["line"] += 1
    elif fault == "wrong-manifest":
        upgrade["manifest"] = {"operation": "provision"}
    elif fault == "wrong-work":
        upgrade["work_id"] += 1
    elif fault == "duplicate-upgrade":
        receipt["upgrades"].append(deepcopy(upgrade))
    elif fault == "native-error":
        receipt["native_calls"][2]["outcome"] = "raise"
    elif fault == "missing-native-return":
        receipt["native_calls"][2]["returned_at"] -= 1
    elif fault == "wrong-native-raw":
        receipt["native_calls"][2]["raw_id"] += 1
    elif fault == "wrong-native-phase":
        receipt["native_calls"][2]["phase"] = "bootstrap"
    elif fault == "reflection-bind":
        replace_call(items, 2, parameters={**REFLECTION_PARAMETERS, "table_names_1": "jobs"})
    elif fault == "alter-changed":
        replace_call(items, 8, sql=UPGRADE_SQL[2].replace("DEFAULT 0", "DEFAULT 1"))
    elif fault == "extra-statement":
        receipt["native_calls"].append(deepcopy(receipt["native_calls"][-1]))
    elif fault in {"wrong-setter", "statement-cap", "lock-cap", "zero-timeout"}:
        index, sql = {
            "wrong-setter": (0, "SET LOCAL lock_timeout = '5000ms'"),
            "statement-cap": (0, "SET LOCAL statement_timeout = '20001ms'"),
            "lock-cap": (1, "SET LOCAL lock_timeout = '5001ms'"),
            "zero-timeout": (0, "SET LOCAL statement_timeout = '0ms'"),
        }[fault]
        replace_call(items, index, sql=sql)
    elif fault == "work-undercount":
        upgrade["work_after"] -= 1
    elif fault == "invalid-empty-bind":
        replace_call(items, 8, parameters=[])
    elif fault == "probe-work":
        receipt["probe_work"] -= 1
    elif fault == "probe-position":
        receipt["probes"][0]["entered_at"] += 1
    elif fault == "wrong-probe-revision":
        receipt["probes"][0]["rows"] = [("ar_0006_admission",)]
    elif fault == "float-generation":
        row = receipt["probes"][1]["rows"][0]
        receipt["probes"][1]["rows"][0] = (row[0], 0.0, row[2])
    elif fault == "catalog-missing-relation":
        receipt["probes"][3]["rows"].pop()
    elif fault == "catalog-nullable-column":
        receipt["probes"][4]["rows"][0] = ("lease_generation", "bigint", False, "0")
    elif fault == "catalog-trigger":
        receipt["probes"][5]["rows"] = [(0, 1)]
    elif fault == "missing-injection":
        receipt["injections"].clear()
    elif fault == "late-injection":
        receipt["injections"][0]["position"] += 1
    elif fault == "wrong-exception-identity":
        receipt["injections"][0]["exception_id"] += 1
    elif fault == "native-marker-pollution":
        watch.markers.insert(0, ("boundary.inject", id(watch.work._raw), receipt["probe_end"]))
    elif fault == "wrong-rollback-state":
        watch.physical[0]["status_before"] = 3
    elif fault == "first-close-not-physical":
        watch.physical[1]["closed_before"] = True
    elif fault == "late-close":
        watch.physical[2]["trace_end"] = watch.command_boundary["trace_end"] + 1
    elif fault == "later-writer":
        receipt["writes"].append({"name": "accounts.insert"})
    elif fault == "ordinary-sql-after-injection":
        watch.trace.events[receipt["probe_end"]] = (
            "ordinary",
            "sql-call",
            id(watch.work._raw),
            "SELECT 1",
        )
    with pytest.raises((AssertionError, KeyError, ValueError)):
        check(items)


@pytest.mark.parametrize(
    "fault",
    [
        "second-backfill",
        "wrong-job",
        "wrong-opening",
        "float-opening",
        "float-rowcount",
        "zero-rowcount",
        "pre-delegate-return",
        "wrong-caller",
        "wrong-line",
        "native-bind",
        "missing-real-update",
        "second-job-changed",
        "same-code-new-error",
    ],
)
def test_first_backfill_requires_only_the_original_first_real_write(fault):
    items = witness("first-backfill")
    receipt, _, _, _, _ = items
    write = receipt["writes"][0]
    execution = receipt["backfill_executions"][0]
    raised = None
    if fault == "second-backfill":
        receipt["writes"].append(deepcopy(write))
    elif fault in {"wrong-job", "wrong-opening", "float-opening"}:
        key, value = {
            "wrong-job": ("id", "b" * 32),
            "wrong-opening": ("opening", 125000),
            "float-opening": ("opening", 35000.0),
        }[fault]
        write["values"][key] = value
        execution["values"][key] = value
    elif fault == "float-rowcount":
        execution["rowcount"] = 1.0
    elif fault == "zero-rowcount":
        execution["rowcount"] = 0
    elif fault == "pre-delegate-return":
        execution["returned_at"] = execution["entered_at"]
    elif fault == "wrong-caller":
        write["original_caller"] = False
    elif fault == "wrong-line":
        write["line"] += 1
    elif fault == "native-bind":
        replace_call(items, 41, parameters={"id": "b" * 32, "opening": 35000})
    elif fault == "missing-real-update":
        replace_call(items, 41, sql="SELECT 1")
    elif fault == "second-job-changed":
        row = receipt["probes"][1]["rows"][1]
        receipt["probes"][1]["rows"][1] = (row[0], 0, 85000)
    elif fault == "same-code-new-error":
        raised = MigrationRefused("migration_busy")
    with pytest.raises((AssertionError, KeyError, ValueError)):
        check(items, raised)


@pytest.mark.parametrize(
    "field",
    [
        "identity",
        "upgrade-identity",
        "line",
        "work-before",
        "work-after",
        "trace-return",
        "native-enter",
        "native-return",
        "native-raw",
        "probe-start",
        "probe-end",
        "injection-position",
        "physical-position",
        "marker-position",
    ],
)
def test_equal_valued_numeric_substitutions_do_not_establish_native_identity(field):
    items = witness("after-ddl")
    receipt, _, _, _, watch = items
    upgrade = receipt["upgrades"][0]
    target, key = {
        "identity": (receipt["identity"], "raw_id"),
        "upgrade-identity": (upgrade, "work_id"),
        "line": (upgrade, "line"),
        "work-before": (upgrade, "work_before"),
        "work-after": (upgrade, "work_after"),
        "trace-return": (upgrade, "returned_at"),
        "native-enter": (receipt["native_calls"][0], "entered_at"),
        "native-return": (receipt["native_calls"][0], "returned_at"),
        "native-raw": (receipt["native_calls"][0], "raw_id"),
        "probe-start": (receipt, "probe_start"),
        "probe-end": (receipt, "probe_end"),
        "injection-position": (receipt["injections"][0], "position"),
        "physical-position": (watch.physical[0], "trace_end"),
        "marker-position": ({}, None),
    }[field]
    if field == "marker-position":
        name, raw, position = watch.markers[0]
        watch.markers[0] = (name, raw, float(position))
    else:
        target[key] = float(target[key])
    with pytest.raises(AssertionError):
        check(items)


def test_statement_ceiling_preserves_original_policy_and_tighter_remaining_time(monkeypatch):
    monkeypatch.setattr(ledger_work, "monotonic", lambda: 100.0)
    work = ledger_work.LedgerWork()
    assert work.remaining_timeouts_ms() == (20_000, 5_000)
    items = witness("after-ddl")
    assert items[0]["native_calls"][0]["sql"] == "SET LOCAL statement_timeout = '20000ms'"
    # A valid tighter statement limit can still exceed the lock ceiling.
    replace_call(items, 0, sql="SET LOCAL statement_timeout = '5001ms'")
    check(items)


@pytest.mark.parametrize("event_kind", ["sql-call", "sql-return"])
def test_trace_event_raw_identity_rejects_equal_valued_float(event_kind):
    items = witness("after-ddl")
    watch = items[-1]
    position = next(i for i, row in enumerate(watch.trace.events) if row[1] == event_kind)
    phase, kind, raw_id, sql = watch.trace.events[position]
    watch.trace.events[position] = (phase, kind, float(raw_id), sql)
    with pytest.raises(AssertionError):
        check(items)


def preservation_witness():
    original = {table: [] for table in SOURCE_FIELDS}
    before = {
        "tables": {"unrelated": {"columns": ("id", "enabled"), "rows": ((1, True),)}},
        "catalog": {"index": ["unchanged"]},
        "authority": {"owner": "original"},
    }
    encrypted = {str(i): str(i) * 64 for i in range(18)}
    fixture = SimpleNamespace(
        before=before, original=original, source=source_fingerprint(original), encrypted=encrypted
    )
    return fixture, deepcopy(before), deepcopy(original), deepcopy(encrypted)


def test_complete_typed_predecessor_and_ciphertext_inventory():
    assert_preservation_values(*preservation_witness())


@pytest.mark.parametrize(
    "fault",
    [
        "row",
        "native-type",
        "column",
        "catalog",
        "owner",
        "source",
        "missing-ciphertext",
        "changed-ciphertext",
    ],
)
def test_preservation_rejects_unrelated_state_and_ciphertext_changes(fault):
    fixture, after, original, encrypted = preservation_witness()
    if fault == "row":
        after["tables"]["unrelated"]["rows"] = ()
    elif fault == "native-type":
        after["tables"]["unrelated"]["rows"] = ((1, 1),)
    elif fault == "column":
        after["tables"]["unrelated"]["columns"] = ("id",)
    elif fault == "catalog":
        after["catalog"]["index"] = []
    elif fault == "owner":
        after["authority"]["owner"] = "other"
    elif fault == "source":
        original["jobs"] = [("changed",)]
    elif fault == "missing-ciphertext":
        encrypted.pop("0")
    else:
        encrypted["0"] = "changed"
    with pytest.raises(AssertionError):
        assert_preservation_values(fixture, after, original, encrypted)


@pytest.mark.parametrize("stage", STAGES)
def test_observer_delegates_before_raising_and_keeps_native_markers(monkeypatch, stage):
    _, fixture, manifest, _, watch = witness(stage)
    watch.trace.events.clear()
    before_markers = deepcopy(watch.markers)
    calls = []
    rows = dict(zip((sql for _, sql in ALL_PROBES), stage_rows(fixture.jobs, stage), strict=True))

    @contextmanager
    def query(sql):
        calls.append(("probe", sql))
        yield rows[sql]

    watch.work._connection.exec_driver_sql = query

    def upgrade(connection, actual_manifest):
        calls.append(("upgrade", actual_manifest))

    def execute(connection, name, values):
        calls.append(("execute", name, deepcopy(values)))
        return SimpleNamespace(rowcount=1)

    def write(connection, name, values):
        ledger_service._execute(connection, name, values)
        calls.append(("write-return", name))

    monkeypatch.setattr(ledger_service, "_upgrade", upgrade)
    monkeypatch.setattr(ledger_service, "_write", write)
    monkeypatch.setattr(ledger_service, "_execute", execute)
    records = []
    with (
        observe_boundary(
            watch, fixture, stage, monkeypatch, lambda *args: records.append(args)
        ) as (receipt, error),
        pytest.raises(MigrationRefused) as caught,
    ):
        ledger_service._upgrade(
            watch.work._connection, SimpleNamespace(model_dump=lambda **_: manifest)
        )
        ledger_service._write(
            watch.work._connection,
            "jobs.backfill",
            {"id": fixture.jobs[0]["id"], "opening": 35000},
        )
    assert caught.value is error
    assert calls[0][0] == "upgrade"
    offset = 1 if stage == "after-ddl" else 3
    assert [row[0] for row in calls[:offset]] == (
        ["upgrade"] if stage == "after-ddl" else ["upgrade", "execute", "write-return"]
    )
    assert [row[0] for row in calls[offset:]] == ["probe"] * len(ALL_PROBES)
    assert watch.markers == before_markers
    assert records == [("boundary_receipt", receipt)]
