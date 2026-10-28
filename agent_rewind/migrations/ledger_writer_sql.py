"""Fixed ledger writer statements; values are always separately typed binds."""

_PROJECTS_GATE_SQLITE = (
    "WITH requested(project_id) AS (\n"
    "  VALUES (CAST(:project_00 AS TEXT)),\n"
    "    (CAST(:project_01 AS TEXT)),\n"
    "    (CAST(:project_02 AS TEXT)),\n"
    "    (CAST(:project_03 AS TEXT)),\n"
    "    (CAST(:project_04 AS TEXT)),\n"
    "    (CAST(:project_05 AS TEXT)),\n"
    "    (CAST(:project_06 AS TEXT)),\n"
    "    (CAST(:project_07 AS TEXT)),\n"
    "    (CAST(:project_08 AS TEXT)),\n"
    "    (CAST(:project_09 AS TEXT)),\n"
    "    (CAST(:project_10 AS TEXT)),\n"
    "    (CAST(:project_11 AS TEXT)),\n"
    "    (CAST(:project_12 AS TEXT)),\n"
    "    (CAST(:project_13 AS TEXT)),\n"
    "    (CAST(:project_14 AS TEXT)),\n"
    "    (CAST(:project_15 AS TEXT))\n"
    "), candidates AS (\n"
    "  SELECT p.id, p.organization_id\n"
    "  FROM requested r\n"
    "  LEFT JOIN projects p ON p.id = r.project_id\n"
    "  WHERE r.project_id IS NOT NULL\n"
    ")\n"
    "SELECT count(*) AS candidate_rows,\n"
    "  COALESCE(sum(CASE WHEN (typeof(id) = 'text' AND length(id) = 32 AN"
    "D length(CAST(id AS BLOB)) = 32 AND id NOT GLOB '*[^0-9a-f]*') AND ("
    "typeof(organization_id) = 'text' AND length(organization_id) = 32 AN"
    "D length(CAST(organization_id AS BLOB)) = 32 AND organization_id NOT"
    " GLOB '*[^0-9a-f]*') THEN 0 ELSE 1 END), 0) AS invalid_rows,\n"
    "  COALESCE(sum((COALESCE(length(CAST(id AS BLOB)), 0) + COALESCE(len"
    "gth(CAST(organization_id AS BLOB)), 0))), 0) AS native_bytes,\n"
    "  COALESCE(max((COALESCE(length(CAST(id AS BLOB)), 0) + COALESCE(len"
    "gth(CAST(organization_id AS BLOB)), 0))), 0) AS max_row_bytes\n"
    "FROM candidates\n"
)

_PROJECTS_BODY_SQLITE = (
    "WITH requested(project_id) AS (\n"
    "  VALUES (CAST(:project_00 AS TEXT)),\n"
    "    (CAST(:project_01 AS TEXT)),\n"
    "    (CAST(:project_02 AS TEXT)),\n"
    "    (CAST(:project_03 AS TEXT)),\n"
    "    (CAST(:project_04 AS TEXT)),\n"
    "    (CAST(:project_05 AS TEXT)),\n"
    "    (CAST(:project_06 AS TEXT)),\n"
    "    (CAST(:project_07 AS TEXT)),\n"
    "    (CAST(:project_08 AS TEXT)),\n"
    "    (CAST(:project_09 AS TEXT)),\n"
    "    (CAST(:project_10 AS TEXT)),\n"
    "    (CAST(:project_11 AS TEXT)),\n"
    "    (CAST(:project_12 AS TEXT)),\n"
    "    (CAST(:project_13 AS TEXT)),\n"
    "    (CAST(:project_14 AS TEXT)),\n"
    "    (CAST(:project_15 AS TEXT))\n"
    "), candidates AS (\n"
    "  SELECT p.id, p.organization_id\n"
    "  FROM requested r\n"
    "  LEFT JOIN projects p ON p.id = r.project_id\n"
    "  WHERE r.project_id IS NOT NULL\n"
    ")\n"
    "SELECT id, organization_id FROM candidates ORDER BY id LIMIT 17\n"
)

_PROVENANCE_OBSERVE_SQLITE = (
    "SELECT strftime('%Y-%m-%dT%H:%M:%f000Z', 'now') AS initialized_at,\n  NULL AS database_role\n"
)

_JOBS_BACKFILL_SQLITE = (
    "UPDATE jobs SET legacy_reserved_microusd=:opening, lease_generation=0 WHERE id=:id\n"
)

_ACCOUNTS_INSERT_SQLITE = (
    "INSERT INTO budget_accounts (\n"
    "  id, organization_id, scope, scope_id, project_id, job_id, period_s"
    "tart, period_end, limit_microusd, opening_held_microusd, held_microu"
    "sd, accounted_microusd\n"
    ") VALUES (\n"
    "  :id, :organization_id, :scope, :scope_id, :project_id, :job_id, :p"
    "eriod_start, :period_end, :limit_microusd, :opening_held_microusd, :"
    "held_microusd, :accounted_microusd\n"
    ")\n"
)

_PROGRESS_INSERT_SQLITE = (
    "INSERT INTO migration_progress (revision, phase, source_digest, curs"
    "or, rows_verified, status, updated_at)\n"
    "VALUES (:revision, :phase, :source_digest, :cursor, :rows_verified, "
    ":status, :updated_at)\n"
)

_ADOPTION_PUBLISH_FINGERPRINT_SQLITE = (
    "UPDATE installation_adoptions\n"
    "SET installed_schema_fingerprint=:fingerprint\n"
    "WHERE singleton=1 AND installation_key=:installation_key\n"
    "  AND installed_schema_fingerprint=:previous_fingerprint\n"
)

_PROJECTS_GATE_POSTGRESQL = (
    "WITH requested(project_id) AS (\n"
    "  VALUES (CAST(:project_00 AS TEXT)),\n"
    "    (CAST(:project_01 AS TEXT)),\n"
    "    (CAST(:project_02 AS TEXT)),\n"
    "    (CAST(:project_03 AS TEXT)),\n"
    "    (CAST(:project_04 AS TEXT)),\n"
    "    (CAST(:project_05 AS TEXT)),\n"
    "    (CAST(:project_06 AS TEXT)),\n"
    "    (CAST(:project_07 AS TEXT)),\n"
    "    (CAST(:project_08 AS TEXT)),\n"
    "    (CAST(:project_09 AS TEXT)),\n"
    "    (CAST(:project_10 AS TEXT)),\n"
    "    (CAST(:project_11 AS TEXT)),\n"
    "    (CAST(:project_12 AS TEXT)),\n"
    "    (CAST(:project_13 AS TEXT)),\n"
    "    (CAST(:project_14 AS TEXT)),\n"
    "    (CAST(:project_15 AS TEXT))\n"
    "), candidates AS (\n"
    "  SELECT p.id, p.organization_id\n"
    "  FROM requested r\n"
    "  LEFT JOIN projects p ON p.id = r.project_id\n"
    "  WHERE r.project_id IS NOT NULL\n"
    ")\n"
    "SELECT count(*) AS candidate_rows,\n"
    "  COALESCE(sum(CASE WHEN (pg_typeof(id) = 'character varying'::regty"
    'pe AND id IS NOT NULL AND octet_length(id) = 32 AND id COLLATE "C" ~'
    " '^[0-9a-f]{32}$') AND (pg_typeof(organization_id) = 'character vary"
    "ing'::regtype AND organization_id IS NOT NULL AND octet_length(organ"
    "ization_id) = 32 AND organization_id COLLATE \"C\" ~ '^[0-9a-f]{32}$')"
    " THEN 0 ELSE 1 END), 0) AS invalid_rows,\n"
    "  COALESCE(sum((COALESCE(octet_length(CAST(id AS TEXT)), 0) + COALES"
    "CE(octet_length(CAST(organization_id AS TEXT)), 0))), 0) AS native_b"
    "ytes,\n"
    "  COALESCE(max((COALESCE(octet_length(CAST(id AS TEXT)), 0) + COALES"
    "CE(octet_length(CAST(organization_id AS TEXT)), 0))), 0) AS max_row_"
    "bytes\n"
    "FROM candidates\n"
)

_PROVENANCE_OBSERVE_POSTGRESQL = (
    "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"H"
    'H24:MI:SS.US"Z"\') AS initialized_at,\n'
    "  CAST(current_user AS TEXT) AS database_role\n"
)

_ACCOUNTS_INSERT_POSTGRESQL = (
    "INSERT INTO budget_accounts (\n"
    "  id, organization_id, scope, scope_id, project_id, job_id, period_s"
    "tart, period_end, limit_microusd, opening_held_microusd, held_microu"
    "sd, accounted_microusd\n"
    ") VALUES (\n"
    "  :id, :organization_id, :scope, :scope_id, :project_id, :job_id, CA"
    "ST(:period_start AS TIMESTAMP WITH TIME ZONE), CAST(:period_end AS T"
    "IMESTAMP WITH TIME ZONE), :limit_microusd, :opening_held_microusd, :"
    "held_microusd, :accounted_microusd\n"
    ")\n"
)

_PROGRESS_INSERT_POSTGRESQL = (
    "INSERT INTO migration_progress (revision, phase, source_digest, curs"
    "or, rows_verified, status, updated_at)\n"
    "VALUES (:revision, :phase, :source_digest, CAST(:cursor AS JSONB), :"
    "rows_verified, :status, CAST(:updated_at AS TIMESTAMP WITH TIME ZONE"
    "))\n"
)

_OWNER_COMPATIBILITY_POSTGRESQL = (
    "SELECT\n"
    "  a.relowner = r.oid\n"
    "  AND NOT EXISTS (\n"
    "    SELECT 1\n"
    "    FROM pg_class c\n"
    "    JOIN pg_namespace cn ON cn.oid = c.relnamespace\n"
    "    WHERE cn.nspname = 'public'\n"
    "      AND c.relkind = 'r'\n"
    "      AND c.relowner <> a.relowner\n"
    "  ) AS owner_compatible\n"
    "FROM pg_class a\n"
    "JOIN pg_namespace an ON an.oid = a.relnamespace\n"
    "JOIN pg_roles r ON r.rolname = current_user\n"
    "WHERE an.nspname = 'public'\n"
    "  AND a.relname = 'installation_adoptions'\n"
    "  AND a.relkind = 'r'\n"
    "LIMIT 2\n"
)

_CONSTRAINTS_IMMEDIATE_POSTGRESQL = "SET CONSTRAINTS ALL IMMEDIATE\n"

SQL = {
    ("sqlite", "projects.gate"): _PROJECTS_GATE_SQLITE,
    ("sqlite", "projects.body"): _PROJECTS_BODY_SQLITE,
    ("sqlite", "provenance.observe"): _PROVENANCE_OBSERVE_SQLITE,
    ("sqlite", "jobs.backfill"): _JOBS_BACKFILL_SQLITE,
    ("sqlite", "accounts.insert"): _ACCOUNTS_INSERT_SQLITE,
    ("sqlite", "progress.insert"): _PROGRESS_INSERT_SQLITE,
    ("sqlite", "adoption.publish_fingerprint"): _ADOPTION_PUBLISH_FINGERPRINT_SQLITE,
    ("postgresql", "projects.gate"): _PROJECTS_GATE_POSTGRESQL,
    ("postgresql", "projects.body"): _PROJECTS_BODY_SQLITE,
    ("postgresql", "provenance.observe"): _PROVENANCE_OBSERVE_POSTGRESQL,
    ("postgresql", "jobs.backfill"): _JOBS_BACKFILL_SQLITE,
    ("postgresql", "accounts.insert"): _ACCOUNTS_INSERT_POSTGRESQL,
    ("postgresql", "progress.insert"): _PROGRESS_INSERT_POSTGRESQL,
    ("postgresql", "adoption.publish_fingerprint"): _ADOPTION_PUBLISH_FINGERPRINT_SQLITE,
    ("postgresql", "owner.compatibility"): _OWNER_COMPATIBILITY_POSTGRESQL,
    ("postgresql", "constraints.immediate"): _CONSTRAINTS_IMMEDIATE_POSTGRESQL,
}

PARAMETER_TYPES = {
    ("sqlite", "projects.gate"): {
        "project_00": "String",
        "project_01": "String",
        "project_02": "String",
        "project_03": "String",
        "project_04": "String",
        "project_05": "String",
        "project_06": "String",
        "project_07": "String",
        "project_08": "String",
        "project_09": "String",
        "project_10": "String",
        "project_11": "String",
        "project_12": "String",
        "project_13": "String",
        "project_14": "String",
        "project_15": "String",
    },
    ("sqlite", "projects.body"): {
        "project_00": "String",
        "project_01": "String",
        "project_02": "String",
        "project_03": "String",
        "project_04": "String",
        "project_05": "String",
        "project_06": "String",
        "project_07": "String",
        "project_08": "String",
        "project_09": "String",
        "project_10": "String",
        "project_11": "String",
        "project_12": "String",
        "project_13": "String",
        "project_14": "String",
        "project_15": "String",
    },
    ("sqlite", "provenance.observe"): {},
    ("sqlite", "jobs.backfill"): {"id": "String", "opening": "BigInteger"},
    ("sqlite", "accounts.insert"): {
        "accounted_microusd": "BigInteger",
        "held_microusd": "BigInteger",
        "id": "String",
        "job_id": "String",
        "limit_microusd": "BigInteger",
        "opening_held_microusd": "BigInteger",
        "organization_id": "String",
        "period_end": "String",
        "period_start": "String",
        "project_id": "String",
        "scope": "String",
        "scope_id": "String",
    },
    ("sqlite", "progress.insert"): {
        "cursor": "String",
        "phase": "String",
        "revision": "String",
        "rows_verified": "Integer",
        "source_digest": "String",
        "status": "String",
        "updated_at": "String",
    },
    ("sqlite", "adoption.publish_fingerprint"): {
        "fingerprint": "String",
        "installation_key": "String",
        "previous_fingerprint": "String",
    },
    ("postgresql", "projects.gate"): {
        "project_00": "String",
        "project_01": "String",
        "project_02": "String",
        "project_03": "String",
        "project_04": "String",
        "project_05": "String",
        "project_06": "String",
        "project_07": "String",
        "project_08": "String",
        "project_09": "String",
        "project_10": "String",
        "project_11": "String",
        "project_12": "String",
        "project_13": "String",
        "project_14": "String",
        "project_15": "String",
    },
    ("postgresql", "projects.body"): {
        "project_00": "String",
        "project_01": "String",
        "project_02": "String",
        "project_03": "String",
        "project_04": "String",
        "project_05": "String",
        "project_06": "String",
        "project_07": "String",
        "project_08": "String",
        "project_09": "String",
        "project_10": "String",
        "project_11": "String",
        "project_12": "String",
        "project_13": "String",
        "project_14": "String",
        "project_15": "String",
    },
    ("postgresql", "provenance.observe"): {},
    ("postgresql", "jobs.backfill"): {"id": "String", "opening": "BigInteger"},
    ("postgresql", "accounts.insert"): {
        "accounted_microusd": "BigInteger",
        "held_microusd": "BigInteger",
        "id": "String",
        "job_id": "String",
        "limit_microusd": "BigInteger",
        "opening_held_microusd": "BigInteger",
        "organization_id": "String",
        "period_end": "String",
        "period_start": "String",
        "project_id": "String",
        "scope": "String",
        "scope_id": "String",
    },
    ("postgresql", "progress.insert"): {
        "cursor": "String",
        "phase": "String",
        "revision": "String",
        "rows_verified": "Integer",
        "source_digest": "String",
        "status": "String",
        "updated_at": "String",
    },
    ("postgresql", "adoption.publish_fingerprint"): {
        "fingerprint": "String",
        "installation_key": "String",
        "previous_fingerprint": "String",
    },
    ("postgresql", "owner.compatibility"): {},
    ("postgresql", "constraints.immediate"): {},
}
