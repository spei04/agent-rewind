"""Dormant failure-evidence DDL; no revision, profile or producer activation.

The caller owns exclusion, predecessor verification and the transaction. These
guards constrain stored associations; they do not authenticate a failure event.
"""

from sqlalchemy.engine import Connection

from .schema import dialect


def _association(prefix: str) -> str:
    # Count operations by job before checking the requested association. A
    # foreign or malformed candidate must never become apparent absence.
    return f"""
    SELECT 1 FROM {prefix}jobs AS j
    JOIN {prefix}resource_scopes AS s
      ON s.resource_kind='job' AND s.resource_id=j.id
    WHERE j.id=NEW.job_id AND s.project_id=NEW.project_id
      AND j.lease_generation=NEW.lease_generation AND j.status=NEW.job_status
      AND (
        (NEW.kind='verified_failure'
          AND j.payload_version=2 AND j.kind='run'
          AND j.error IS NULL AND j.result IS NULL
          AND (NEW.job_status='failed' OR
               (NEW.job_status='cancelled' AND j.cancel=true))
          AND NOT EXISTS(
            SELECT 1 FROM {prefix}artifact_refs AS a
            WHERE a.owner_kind='job' AND a.owner_id=j.id AND a.role='result')
          AND (NEW.phase<>'pre_dispatch' OR NOT EXISTS(
            SELECT 1 FROM {prefix}provider_calls AS c WHERE c.job_id=j.id))
          AND (SELECT count(*) FROM {prefix}operations AS o WHERE o.job_id=j.id)=1
          AND EXISTS(
            SELECT 1 FROM {prefix}operations AS o
            WHERE o.job_id=j.id AND o.id=NEW.operation_id
              AND o.project_id=NEW.project_id AND o.kind='run'
              AND o.payload_version=2 AND o.job_resource_kind='job'
              AND o.failure_correlation_id IS NOT NULL
              AND o.failure_correlation_id=NEW.correlation_id))
        OR
        (NEW.kind='historical_marker' AND (
          (j.payload_version=1 AND NEW.operation_id IS NULL AND NOT EXISTS(
            SELECT 1 FROM {prefix}operations AS o WHERE o.job_id=j.id))
          OR
          (j.payload_version=2 AND j.kind='run'
            AND (SELECT count(*) FROM {prefix}operations AS o WHERE o.job_id=j.id)=1
            AND EXISTS(
              SELECT 1 FROM {prefix}operations AS o
              WHERE o.job_id=j.id AND o.id=NEW.operation_id
                AND o.project_id=NEW.project_id AND o.kind='run'
                AND o.payload_version=2 AND o.job_resource_kind='job'
                AND o.failure_correlation_id IS NULL))))
      )
    """  # noqa: S608 -- Sole caller supplies only "" or "public." as the prefix.


def create_failure_schema(connection: Connection) -> None:
    """Create the unregistered relation and guards inside the caller's transaction."""
    postgres = dialect(connection) == "postgresql"
    prefix = "public." if postgres else ""

    def hexadecimal(field: str, size: int = 32) -> str:
        if postgres:
            return f"octet_length({field})={size} AND {field} ~ '^[0-9a-f]{{{size}}}$'"
        return (
            f"typeof({field})='text' AND length({field})={size} "
            f"AND length(CAST({field} AS BLOB))={size} AND {field} NOT GLOB '*[^0-9a-f]*'"
        )

    def integer(field: str, maximum: int, minimum: int = 0) -> str:
        rule = f"{field} BETWEEN {minimum} AND {maximum}"
        return rule if postgres else f"typeof({field})='integer' AND {rule}"

    def choice(field: str, values: tuple[str, ...]) -> str:
        literals = ",".join("'" + value + "'" for value in values)
        lengths = ",".join(str(size) for size in sorted({len(value) for value in values}))
        byte_length = f"octet_length({field})" if postgres else f"length(CAST({field} AS BLOB))"
        rule = f"{field} IN ({literals}) AND {byte_length} IN ({lengths})"
        return rule if postgres else f"typeof({field})='text' AND {rule}"

    connection.exec_driver_sql(
        f"CREATE UNIQUE INDEX job_failure_operation_binding_uq "
        f"ON {prefix}operations(id,job_id,project_id)"
    )
    connection.exec_driver_sql(f"""CREATE TABLE {prefix}job_failure_evidence (
      schema_version INTEGER NOT NULL
        CONSTRAINT failure_schema_version CHECK({integer("schema_version", 1, 1)}),
      kind VARCHAR(17) NOT NULL
        CONSTRAINT failure_kind CHECK({choice("kind", ("verified_failure", "historical_marker"))}),
      project_id VARCHAR(32) NOT NULL
        CONSTRAINT failure_project CHECK({hexadecimal("project_id")}),
      job_resource_kind VARCHAR(3) NOT NULL
        CONSTRAINT failure_job_kind CHECK({choice("job_resource_kind", ("job",))}),
      job_id VARCHAR(32) NOT NULL
        CONSTRAINT failure_job CHECK({hexadecimal("job_id")}),
      operation_id VARCHAR(32)
        CONSTRAINT failure_operation CHECK(operation_id IS NULL OR ({hexadecimal("operation_id")})),
      lease_generation BIGINT NOT NULL
        CONSTRAINT failure_generation CHECK({integer("lease_generation", 9223372036854775807)}),
      job_status VARCHAR(9) NOT NULL
        CONSTRAINT failure_status CHECK(
          {choice("job_status", ("queued", "running", "succeeded", "failed", "cancelled"))}),
      cause VARCHAR(18)
        CONSTRAINT failure_cause CHECK(cause IS NULL OR (
          {
        choice(
            "cause",
            (
                "budget_refused",
                "dependency_failed",
                "internal_fault",
                "dispatch_uncertain",
                "lease_expired",
            ),
        )
    })),
      phase VARCHAR(15)
        CONSTRAINT failure_phase CHECK(phase IS NULL OR (
          {choice("phase", ("pre_dispatch", "outcome_unknown"))})),
      origin_kind VARCHAR(16) NOT NULL
        CONSTRAINT failure_origin CHECK({choice("origin_kind", ("admission", "migration_marker"))}),
      correlation_id VARCHAR(32) NOT NULL
        CONSTRAINT failure_correlation CHECK({hexadecimal("correlation_id")}),
      association_sha256 VARCHAR(64) NOT NULL
        CONSTRAINT failure_association CHECK({hexadecimal("association_sha256", 64)}),
      source_sha256 VARCHAR(64) NOT NULL
        CONSTRAINT failure_source CHECK({hexadecimal("source_sha256", 64)}),
      created_at_micros BIGINT NOT NULL
        CONSTRAINT failure_created CHECK({integer("created_at_micros", 253402300799999999)}),
      CONSTRAINT failure_pk PRIMARY KEY(job_id),
      CONSTRAINT failure_job_fk FOREIGN KEY(job_id)
        REFERENCES {prefix}jobs(id) ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE,
      CONSTRAINT failure_scope_fk FOREIGN KEY(project_id,job_resource_kind,job_id)
        REFERENCES {prefix}resource_scopes(project_id,resource_kind,resource_id)
        ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE,
      CONSTRAINT failure_operation_fk FOREIGN KEY(operation_id,job_id,project_id)
        REFERENCES {prefix}operations(id,job_id,project_id)
        ON UPDATE NO ACTION ON DELETE NO ACTION NOT DEFERRABLE,
      CONSTRAINT failure_variant CHECK(
        (kind='verified_failure' AND origin_kind='admission'
          AND operation_id IS NOT NULL AND lease_generation>=1
          AND job_status IN ('failed','cancelled') AND cause IS NOT NULL AND phase IS NOT NULL
          AND (phase='outcome_unknown' OR
               (phase='pre_dispatch' AND cause IN
                 ('budget_refused','dependency_failed','internal_fault','lease_expired'))))
        OR (kind='historical_marker' AND origin_kind='migration_marker'
          AND cause IS NULL AND phase IS NULL))
    )""")

    association = _association(prefix)
    if postgres:
        connection.exec_driver_sql(f"""
CREATE FUNCTION public.job_failure_evidence_guard() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER PARALLEL UNSAFE
SET search_path = pg_catalog, pg_temp
AS $failure$
BEGIN
    IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'job_failure_evidence'
       OR TG_WHEN<>'BEFORE' OR TG_NARGS<>0 OR NOT (
         (TG_NAME='job_failure_evidence_row_guard' AND TG_LEVEL='ROW'
           AND TG_OP IN ('INSERT','UPDATE','DELETE'))
         OR (TG_NAME='job_failure_evidence_truncate_guard'
           AND TG_LEVEL='STATEMENT' AND TG_OP='TRUNCATE')) THEN
        RAISE EXCEPTION 'invalid failure guard' USING ERRCODE='23514';
    END IF;
    IF TG_OP<>'INSERT' THEN
        RAISE EXCEPTION 'immutable failure evidence' USING ERRCODE='23514';
    END IF;
    IF NEW.kind='historical_marker' AND EXISTS(
        SELECT 1 FROM pg_catalog.pg_class AS c
        WHERE c.relnamespace='public'::regnamespace AND c.relkind='r'
          AND c.relowner<>current_user::regrole) THEN
        RAISE EXCEPTION 'failure marker owner required' USING ERRCODE='23514';
    END IF;
    -- Serialize same-job inserts before checking evidence; callers still own
    -- project-first exclusion and the existing jobs UPDATE privilege.
    PERFORM 1 FROM public.jobs WHERE id=NEW.job_id FOR NO KEY UPDATE;
    IF EXISTS(SELECT 1 FROM public.job_failure_evidence WHERE job_id=NEW.job_id) THEN
        RAISE EXCEPTION 'existing failure evidence' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS({association}) THEN
        RAISE EXCEPTION 'invalid failure association' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$failure$""")  # noqa: S608 -- Association expands only the fixed dialect template.
        connection.exec_driver_sql(
            "REVOKE ALL ON FUNCTION public.job_failure_evidence_guard() FROM PUBLIC"
        )
        connection.exec_driver_sql("""
CREATE TRIGGER job_failure_evidence_row_guard BEFORE INSERT OR UPDATE OR DELETE
ON public.job_failure_evidence FOR EACH ROW
EXECUTE FUNCTION public.job_failure_evidence_guard()""")
        connection.exec_driver_sql("""
CREATE TRIGGER job_failure_evidence_truncate_guard BEFORE TRUNCATE
ON public.job_failure_evidence FOR EACH STATEMENT
EXECUTE FUNCTION public.job_failure_evidence_guard()""")
    else:
        connection.exec_driver_sql(f"""
CREATE TRIGGER job_failure_evidence_insert_guard BEFORE INSERT ON job_failure_evidence
BEGIN
  SELECT CASE WHEN EXISTS(SELECT 1 FROM job_failure_evidence WHERE job_id=NEW.job_id)
    THEN RAISE(ABORT,'existing failure evidence') END;
  SELECT CASE WHEN NOT EXISTS({association})
    THEN RAISE(ABORT,'invalid failure association') END;
END""")  # noqa: S608 -- Association expands only the fixed dialect template.
        for action in ("UPDATE", "DELETE"):
            connection.exec_driver_sql(f"""
CREATE TRIGGER job_failure_evidence_{action.lower()}_guard
BEFORE {action} ON job_failure_evidence
BEGIN SELECT RAISE(ABORT,'immutable failure evidence'); END""")
