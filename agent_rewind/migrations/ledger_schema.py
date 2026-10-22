"""Explicit ar7 DDL. The operator owns exclusion, backfill and atomic publication."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .schema import dialect

TRIGGERS = {
    "ar7_accounts_constraint": ("budget_accounts", "INSERT OR UPDATE OR DELETE"),
    "ar7_calls_constraint": ("provider_calls", "INSERT OR UPDATE OR DELETE"),
    "ar7_entries_constraint": ("budget_entries", "INSERT OR UPDATE OR DELETE"),
    "ar7_jobs_constraint": ("jobs", "UPDATE OR DELETE"),
    "ar7_scopes_constraint": ("resource_scopes", "UPDATE OR DELETE"),
}


def create_ledger_schema(connection: Connection) -> None:
    """Create tables/columns only; install immutable triggers after opening backfill."""
    postgres = dialect(connection) == "postgresql"
    timestamp = "TIMESTAMP WITH TIME ZONE" if postgres else "DATETIME"

    def hexadecimal(field: str, size: int = 32) -> str:
        if postgres:
            return f"{field} ~ '^[0-9a-f]{{{size}}}$'"
        return (
            f"typeof({field})='text' AND length({field})={size} "
            f"AND length(CAST({field} AS BLOB))={size} AND {field} NOT GLOB '*[^0-9a-f]*'"
        )

    def money(field: str, minimum: int = 0) -> str:
        check = f"{field} BETWEEN {minimum} AND 9223372036854775807"
        return check if postgres else f"typeof({field})='integer' AND {check}"

    def time(field: str) -> str:
        if postgres:
            return (
                f"isfinite({field}) AND "
                f"EXTRACT(YEAR FROM {field} AT TIME ZONE 'UTC') BETWEEN 1 AND 9999"
            )
        pattern = "[0-9]" * 4 + "-" + "[0-9]" * 2 + "-" + "[0-9]" * 2
        pattern += "T" + "[0-9]" * 2 + ":" + "[0-9]" * 2 + ":" + "[0-9]" * 2
        pattern += "." + "[0-9]" * 6 + "Z"
        return (
            f"typeof({field})='text' AND length(CAST({field} AS BLOB))=27 "
            f"AND {field} GLOB '{pattern}' AND substr({field},1,4) BETWEEN '0001' AND '9999' "
            f"AND date(substr({field},1,10),'+0 days') IS substr({field},1,10) "
            f"AND substr({field},12,2) BETWEEN '00' AND '23' "
            f"AND substr({field},15,2) BETWEEN '00' AND '59' "
            f"AND substr({field},18,2) BETWEEN '00' AND '59'"
        )

    def bounded_text(field: str, size: int) -> str:
        check = f"length({field})<={size}"
        if not postgres:
            check = (
                f"typeof({field})='text' AND {check} "
                f"AND length(CAST({field} AS BLOB))<={4 * size} AND instr({field},char(0))=0"
            )
        return check

    connection.exec_driver_sql(
        "ALTER TABLE jobs ADD COLUMN lease_generation BIGINT NOT NULL DEFAULT 0 "
        f"CONSTRAINT ar7_jobs_generation CHECK({money('lease_generation')})"
    )
    connection.exec_driver_sql(
        "ALTER TABLE jobs ADD COLUMN legacy_reserved_microusd BIGINT NOT NULL DEFAULT 0 "
        f"CONSTRAINT ar7_jobs_legacy_reserved CHECK({money('legacy_reserved_microusd')})"
    )
    connection.exec_driver_sql(f"""CREATE TABLE budget_accounts (
        id VARCHAR(32) NOT NULL CONSTRAINT ar7_accounts_id CHECK({hexadecimal("id")}),
        organization_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_accounts_organization CHECK({hexadecimal("organization_id")}),
        scope VARCHAR(16) NOT NULL
          CONSTRAINT ar7_accounts_scope CHECK(
            scope='organization' OR scope='project' OR scope='job'),
        scope_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_accounts_scope_id CHECK({hexadecimal("scope_id")}),
        period_start {timestamp} NOT NULL
          CONSTRAINT ar7_accounts_start CHECK({time("period_start")}),
        period_end {timestamp} NOT NULL CONSTRAINT ar7_accounts_end CHECK({time("period_end")}),
        limit_microusd BIGINT NOT NULL
          CONSTRAINT ar7_accounts_limit CHECK({money("limit_microusd")}),
        held_microusd BIGINT NOT NULL CONSTRAINT ar7_accounts_held CHECK({money("held_microusd")}),
        accounted_microusd BIGINT NOT NULL
          CONSTRAINT ar7_accounts_accounted CHECK({money("accounted_microusd")}),
        project_id VARCHAR(32)
          CONSTRAINT ar7_accounts_project CHECK(
            project_id IS NULL OR ({hexadecimal("project_id")})),
        job_id VARCHAR(32)
          CONSTRAINT ar7_accounts_job CHECK(job_id IS NULL OR ({hexadecimal("job_id")})),
        opening_held_microusd BIGINT NOT NULL DEFAULT 0
          CONSTRAINT ar7_accounts_opening CHECK({money("opening_held_microusd")}),
        CONSTRAINT ar7_accounts_pk PRIMARY KEY(id),
        CONSTRAINT ar7_accounts_scope_period UNIQUE(organization_id,scope,scope_id,period_start),
        CONSTRAINT ar7_accounts_job_window UNIQUE(job_id),
        CONSTRAINT ar7_accounts_organization_fk FOREIGN KEY(organization_id)
          REFERENCES organizations(id),
        CONSTRAINT ar7_accounts_project_fk FOREIGN KEY(organization_id,project_id)
          REFERENCES projects(organization_id,id),
        CONSTRAINT ar7_accounts_period CHECK(period_start<period_end),
        CONSTRAINT ar7_accounts_balance CHECK(
          accounted_microusd<=limit_microusd AND held_microusd<=limit_microusd-accounted_microusd),
        CONSTRAINT ar7_accounts_shape CHECK(
          (scope='organization' AND scope_id=organization_id
            AND project_id IS NULL AND job_id IS NULL)
          OR (scope='project' AND project_id IS NOT NULL AND scope_id=project_id AND job_id IS NULL)
          OR (scope='job' AND project_id IS NOT NULL AND job_id IS NOT NULL AND scope_id=job_id))
    )""")
    connection.exec_driver_sql(f"""CREATE TABLE provider_calls (
        id VARCHAR(32) NOT NULL CONSTRAINT ar7_calls_id CHECK({hexadecimal("id")}),
        project_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_calls_project CHECK({hexadecimal("project_id")}),
        job_id VARCHAR(32) NOT NULL CONSTRAINT ar7_calls_job CHECK({hexadecimal("job_id")}),
        logical_call_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_calls_logical CHECK({hexadecimal("logical_call_id")}),
        purpose VARCHAR(20) NOT NULL
          CONSTRAINT ar7_calls_purpose CHECK(purpose='continuation' OR purpose='discovery'),
        request_digest CHAR(64) NOT NULL
          CONSTRAINT ar7_calls_digest CHECK({hexadecimal("request_digest", 64)}),
        price_version VARCHAR(128) NOT NULL
          CONSTRAINT ar7_calls_price CHECK({bounded_text("price_version", 128)}),
        state VARCHAR(20) NOT NULL
          CONSTRAINT ar7_calls_state CHECK(
            state='reserved' OR state='dispatching' OR state='observed'
            OR state='uncertain' OR state='reconciled'),
        reserved_microusd BIGINT NOT NULL
          CONSTRAINT ar7_calls_reserved CHECK({money("reserved_microusd")}),
        usage_estimate_microusd BIGINT
          CONSTRAINT ar7_calls_estimate CHECK(
            usage_estimate_microusd IS NULL OR ({money("usage_estimate_microusd")})),
        provider_request_id VARCHAR(256)
          CONSTRAINT ar7_calls_provider_request CHECK(
            provider_request_id IS NULL OR ({bounded_text("provider_request_id", 256)})),
        created_at {timestamp} NOT NULL CONSTRAINT ar7_calls_created CHECK({time("created_at")}),
        organization_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_calls_organization CHECK({hexadecimal("organization_id")}),
        job_resource_kind VARCHAR(20) NOT NULL
          CONSTRAINT ar7_calls_job_kind CHECK(job_resource_kind='job'),
        lease_generation BIGINT NOT NULL
          CONSTRAINT ar7_calls_generation CHECK({money("lease_generation", 1)}),
        organization_account_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_calls_org_account CHECK({hexadecimal("organization_account_id")}),
        project_account_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_calls_project_account CHECK({hexadecimal("project_account_id")}),
        job_account_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_calls_job_account CHECK({hexadecimal("job_account_id")}),
        CONSTRAINT ar7_calls_pk PRIMARY KEY(id),
        CONSTRAINT ar7_calls_logical_unique UNIQUE(project_id,logical_call_id),
        CONSTRAINT ar7_calls_project_unique UNIQUE(project_id,id),
        CONSTRAINT ar7_calls_project_fk FOREIGN KEY(project_id) REFERENCES projects(id),
        CONSTRAINT ar7_calls_job_fk FOREIGN KEY(job_id) REFERENCES jobs(id),
        CONSTRAINT ar7_calls_job_scope_fk FOREIGN KEY(project_id,job_resource_kind,job_id)
          REFERENCES resource_scopes(project_id,resource_kind,resource_id),
        CONSTRAINT ar7_calls_organization_fk FOREIGN KEY(organization_id)
          REFERENCES organizations(id),
        CONSTRAINT ar7_calls_organization_project_fk FOREIGN KEY(organization_id,project_id)
          REFERENCES projects(organization_id,id),
        CONSTRAINT ar7_calls_org_account_fk FOREIGN KEY(organization_account_id)
          REFERENCES budget_accounts(id),
        CONSTRAINT ar7_calls_project_account_fk FOREIGN KEY(project_account_id)
          REFERENCES budget_accounts(id),
        CONSTRAINT ar7_calls_job_account_fk FOREIGN KEY(job_account_id)
          REFERENCES budget_accounts(id)
    )""")
    connection.exec_driver_sql(f"""CREATE TABLE budget_entries (
        call_id VARCHAR(32) NOT NULL CONSTRAINT ar7_entries_call CHECK({hexadecimal("call_id")}),
        account_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_entries_account CHECK({hexadecimal("account_id")}),
        entry_kind VARCHAR(16) NOT NULL
          CONSTRAINT ar7_entries_kind CHECK(
            entry_kind='reserve' OR entry_kind='settle' OR entry_kind='release'),
        amount_microusd BIGINT NOT NULL
          CONSTRAINT ar7_entries_amount CHECK({money("amount_microusd")}),
        evidence_ref VARCHAR(32)
          CONSTRAINT ar7_entries_evidence CHECK(
            evidence_ref IS NULL OR ({hexadecimal("evidence_ref")})),
        created_at {timestamp} NOT NULL CONSTRAINT ar7_entries_created CHECK({time("created_at")}),
        project_id VARCHAR(32) NOT NULL
          CONSTRAINT ar7_entries_project CHECK({hexadecimal("project_id")}),
        evidence_owner_kind VARCHAR(20) NOT NULL DEFAULT 'provider_call'
          CONSTRAINT ar7_entries_owner CHECK(evidence_owner_kind='provider_call'),
        evidence_role VARCHAR(32) NOT NULL DEFAULT 'budget_evidence'
          CONSTRAINT ar7_entries_role CHECK(evidence_role='budget_evidence'),
        CONSTRAINT ar7_entries_pk PRIMARY KEY(call_id,account_id,entry_kind),
        CONSTRAINT ar7_entries_call_fk FOREIGN KEY(call_id) REFERENCES provider_calls(id),
        CONSTRAINT ar7_entries_account_fk FOREIGN KEY(account_id) REFERENCES budget_accounts(id),
        CONSTRAINT ar7_entries_project_fk FOREIGN KEY(project_id) REFERENCES projects(id),
        CONSTRAINT ar7_entries_project_call_fk FOREIGN KEY(project_id,call_id)
          REFERENCES provider_calls(project_id,id),
        CONSTRAINT ar7_entries_evidence_fk FOREIGN KEY(
          project_id,evidence_owner_kind,call_id,evidence_ref,evidence_role)
          REFERENCES artifact_refs(project_id,owner_kind,owner_id,artifact_id,role),
        CONSTRAINT ar7_entries_evidence_shape CHECK(
          (entry_kind='reserve' AND evidence_ref IS NULL)
          OR ((entry_kind='settle' OR entry_kind='release') AND evidence_ref IS NOT NULL))
    )""")
    for field in ("job_id", "organization_account_id", "project_account_id", "job_account_id"):
        connection.exec_driver_sql(f"CREATE INDEX ar7_calls_{field} ON provider_calls({field})")
    connection.exec_driver_sql("CREATE INDEX ar7_entries_account_id ON budget_entries(account_id)")


# Kept literal so the catalog records the exact installed executable body.
LEDGER_CONSTRAINT_SQL = """
CREATE FUNCTION public.ar7_ledger_constraint() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER PARALLEL UNSAFE
SET search_path = pg_catalog, pg_temp
AS $ar7$
DECLARE
    account_row public.budget_accounts%ROWTYPE;
    call_row public.provider_calls%ROWTYPE;
    parent_job public.jobs%ROWTYPE;
    org_account public.budget_accounts%ROWTYPE;
    project_account public.budget_accounts%ROWTYPE;
    job_account public.budget_accounts%ROWTYPE;
    target_account text;
    target_call text;
    target_job text;
    scope_project text;
    account_candidates integer := 0;
    entries record;
BEGIN
    IF TG_TABLE_SCHEMA <> 'public' OR TG_WHEN <> 'AFTER'
       OR TG_LEVEL <> 'ROW' OR TG_NARGS <> 0
       OR NOT (
         (TG_NAME = 'ar7_accounts_constraint' AND TG_TABLE_NAME = 'budget_accounts'
          AND TG_OP IN ('INSERT','UPDATE','DELETE'))
         OR (TG_NAME = 'ar7_calls_constraint' AND TG_TABLE_NAME = 'provider_calls'
          AND TG_OP IN ('INSERT','UPDATE','DELETE'))
         OR (TG_NAME = 'ar7_entries_constraint' AND TG_TABLE_NAME = 'budget_entries'
          AND TG_OP IN ('INSERT','UPDATE','DELETE'))
         OR (TG_NAME = 'ar7_jobs_constraint' AND TG_TABLE_NAME = 'jobs'
          AND TG_OP IN ('UPDATE','DELETE'))
         OR (TG_NAME = 'ar7_scopes_constraint' AND TG_TABLE_NAME = 'resource_scopes'
          AND TG_OP IN ('UPDATE','DELETE'))
       ) THEN
        RAISE EXCEPTION 'ledger trigger identity' USING ERRCODE = '23514';
    END IF;

    IF TG_TABLE_NAME = 'budget_accounts' THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'immutable ledger account' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'UPDATE' AND
           ROW(OLD.id,OLD.organization_id,OLD.scope,OLD.scope_id,OLD.period_start,
               OLD.period_end,OLD.limit_microusd,OLD.project_id,OLD.job_id,
               OLD.opening_held_microusd)
           IS DISTINCT FROM
           ROW(NEW.id,NEW.organization_id,NEW.scope,NEW.scope_id,NEW.period_start,
               NEW.period_end,NEW.limit_microusd,NEW.project_id,NEW.job_id,
               NEW.opening_held_microusd) THEN
            RAISE EXCEPTION 'immutable ledger account' USING ERRCODE = '23514';
        END IF;
        target_account := NEW.id;
        SELECT * INTO STRICT account_row FROM public.budget_accounts
            WHERE id = target_account LIMIT 2;
        IF account_row.scope IN ('organization','project') AND EXISTS(
            SELECT 1 FROM public.budget_accounts AS candidate
            WHERE candidate.organization_id = account_row.organization_id
              AND candidate.scope = account_row.scope
              AND candidate.scope_id = account_row.scope_id
              AND candidate.id <> account_row.id
              AND candidate.period_start < account_row.period_end
              AND account_row.period_start < candidate.period_end
        ) THEN
            RAISE EXCEPTION 'overlapping ledger period' USING ERRCODE = '23514';
        END IF;
        target_job := account_row.job_id;
    ELSIF TG_TABLE_NAME = 'jobs' THEN
        IF TG_OP = 'UPDATE' THEN
            IF OLD.legacy_reserved_microusd IS DISTINCT FROM NEW.legacy_reserved_microusd
               OR NEW.lease_generation < OLD.lease_generation THEN
                RAISE EXCEPTION 'immutable opening or decreasing generation'
                    USING ERRCODE = '23514';
            END IF;
        END IF;
        target_job := OLD.id;
    ELSIF TG_TABLE_NAME = 'resource_scopes' THEN
        IF OLD.resource_kind = 'job' THEN
            target_job := OLD.resource_id;
        ELSIF OLD.resource_kind = 'provider_call' THEN
            target_call := OLD.resource_id;
        END IF;
    ELSIF TG_TABLE_NAME = 'provider_calls' THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'immutable ledger call' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'UPDATE' AND
           ROW(OLD.id,OLD.project_id,OLD.job_id,OLD.logical_call_id,OLD.purpose,
               OLD.request_digest,OLD.price_version,OLD.reserved_microusd,OLD.created_at,
               OLD.organization_id,OLD.job_resource_kind,OLD.lease_generation,
               OLD.organization_account_id,OLD.project_account_id,OLD.job_account_id)
           IS DISTINCT FROM
           ROW(NEW.id,NEW.project_id,NEW.job_id,NEW.logical_call_id,NEW.purpose,
               NEW.request_digest,NEW.price_version,NEW.reserved_microusd,NEW.created_at,
               NEW.organization_id,NEW.job_resource_kind,NEW.lease_generation,
               NEW.organization_account_id,NEW.project_account_id,NEW.job_account_id) THEN
            RAISE EXCEPTION 'immutable ledger call' USING ERRCODE = '23514';
        END IF;
        target_call := NEW.id;
    ELSIF TG_TABLE_NAME = 'budget_entries' THEN
        IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'append-only ledger entry' USING ERRCODE = '23514';
        END IF;
        target_call := NEW.call_id;
    END IF;

    IF target_job IS NOT NULL THEN
        FOR account_row IN
            SELECT * FROM public.budget_accounts WHERE job_id = target_job LIMIT 2
        LOOP
            account_candidates := account_candidates + 1;
            IF account_candidates > 1 THEN
                RAISE EXCEPTION 'duplicate job account' USING ERRCODE = '23514';
            END IF;
            SELECT * INTO parent_job FROM public.jobs WHERE id = target_job LIMIT 2;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'missing ledger job' USING ERRCODE = '23514';
            END IF;
            SELECT project_id INTO scope_project FROM public.resource_scopes
                WHERE resource_kind = 'job' AND resource_id = target_job LIMIT 2;
            IF NOT FOUND OR scope_project IS DISTINCT FROM account_row.project_id
               OR account_row.limit_microusd > parent_job.budget THEN
                RAISE EXCEPTION 'ledger job scope or cap' USING ERRCODE = '23514';
            END IF;
        END LOOP;
    END IF;

    IF target_call IS NOT NULL THEN
        SELECT * INTO call_row FROM public.provider_calls WHERE id = target_call LIMIT 2;
        IF NOT FOUND THEN
            IF TG_TABLE_NAME = 'resource_scopes' THEN
                RETURN NULL;
            END IF;
            RAISE EXCEPTION 'missing ledger call' USING ERRCODE = '23514';
        END IF;
        IF TG_TABLE_NAME = 'resource_scopes' THEN
            -- Deferred final-state checks must not erase an earlier identity change.
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'immutable ledger call scope' USING ERRCODE = '23514';
            END IF;
            IF ROW(OLD.resource_kind,OLD.resource_id,OLD.project_id) IS DISTINCT FROM
               ROW(NEW.resource_kind,NEW.resource_id,NEW.project_id) THEN
                RAISE EXCEPTION 'immutable ledger call scope' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF call_row.organization_account_id = call_row.project_account_id
           OR call_row.organization_account_id = call_row.job_account_id
           OR call_row.project_account_id = call_row.job_account_id THEN
            RAISE EXCEPTION 'ledger account triple' USING ERRCODE = '23514';
        END IF;
        SELECT * INTO STRICT org_account FROM public.budget_accounts
            WHERE id = call_row.organization_account_id LIMIT 2;
        SELECT * INTO STRICT project_account FROM public.budget_accounts
            WHERE id = call_row.project_account_id LIMIT 2;
        SELECT * INTO STRICT job_account FROM public.budget_accounts
            WHERE id = call_row.job_account_id LIMIT 2;
        IF org_account.scope <> 'organization'
           OR org_account.scope_id <> call_row.organization_id
           OR project_account.scope <> 'project'
           OR project_account.scope_id <> call_row.project_id
           OR job_account.scope <> 'job' OR job_account.scope_id <> call_row.job_id
           OR job_account.project_id <> call_row.project_id
           OR org_account.organization_id <> call_row.organization_id
           OR project_account.organization_id <> call_row.organization_id
           OR job_account.organization_id <> call_row.organization_id
           OR NOT (org_account.period_start <= call_row.created_at
                   AND call_row.created_at < org_account.period_end)
           OR NOT (project_account.period_start <= call_row.created_at
                   AND call_row.created_at < project_account.period_end)
           OR NOT (job_account.period_start <= call_row.created_at
                   AND call_row.created_at < job_account.period_end) THEN
            RAISE EXCEPTION 'ledger account scope or period' USING ERRCODE = '23514';
        END IF;
        SELECT project_id INTO scope_project FROM public.resource_scopes
            WHERE resource_kind = 'provider_call' AND resource_id = target_call LIMIT 2;
        IF NOT FOUND OR scope_project IS DISTINCT FROM call_row.project_id THEN
            RAISE EXCEPTION 'ledger call scope' USING ERRCODE = '23514';
        END IF;
        SELECT count(*) AS total,
               count(*) FILTER (WHERE entry_kind = 'reserve') AS reserves,
               count(*) FILTER (WHERE entry_kind = 'settle') AS settlements,
               count(*) FILTER (WHERE entry_kind = 'release') AS releases,
               min(amount_microusd) FILTER (WHERE entry_kind = 'reserve') AS reserve_min,
               max(amount_microusd) FILTER (WHERE entry_kind = 'reserve') AS reserve_max,
               min(amount_microusd) FILTER (WHERE entry_kind = 'settle') AS settle_min,
               max(amount_microusd) FILTER (WHERE entry_kind = 'settle') AS settle_max,
               min(amount_microusd) FILTER (WHERE entry_kind = 'release') AS release_min,
               max(amount_microusd) FILTER (WHERE entry_kind = 'release') AS release_max,
               bool_and(account_id IN (
                   call_row.organization_account_id,
                   call_row.project_account_id,call_row.job_account_id)) AS members
        INTO entries FROM (
            SELECT account_id,entry_kind,amount_microusd FROM public.budget_entries
            WHERE call_id = target_call LIMIT 10
        ) AS cohort;
        IF entries.total > 9 OR entries.reserves <> 3
           OR entries.reserve_min <> call_row.reserved_microusd
           OR entries.reserve_max <> call_row.reserved_microusd
           OR entries.members IS DISTINCT FROM true
           OR entries.settlements NOT IN (0,3) OR entries.releases NOT IN (0,3)
           OR entries.settle_min IS DISTINCT FROM entries.settle_max
           OR entries.release_min IS DISTINCT FROM entries.release_max
           OR coalesce(entries.release_max,0) > call_row.reserved_microusd
           OR coalesce(entries.settle_max,0) >
              call_row.reserved_microusd - coalesce(entries.release_max,0) THEN
            RAISE EXCEPTION 'ledger entry cohort' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NULL;
END
$ar7$
"""


def create_ledger_constraints(connection: Connection) -> None:
    """Install PostgreSQL checks after opening backfill, before the same COMMIT."""
    if dialect(connection) == "sqlite":
        return
    connection.execute(text(LEDGER_CONSTRAINT_SQL))
    connection.exec_driver_sql("REVOKE ALL ON FUNCTION public.ar7_ledger_constraint() FROM PUBLIC")
    for name, (table, events) in TRIGGERS.items():
        connection.exec_driver_sql(
            f"CREATE CONSTRAINT TRIGGER {name} AFTER {events} ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.ar7_ledger_constraint()"
        )
