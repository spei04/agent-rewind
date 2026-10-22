"""Bounded historical provenance and ledger progress statements."""

# Fixed fragments share identical predicates; no input becomes SQL syntax.

_POSTGRESQL_ALL_H10_ADOPTION_VALID = (
    " ((pg_typeof(installation_key) IN ('text'::regtype, 'character "
    "varying'::regtype) AND installation_key IS NOT NULL AND "
    "octet_length(CAST(installation_key AS TEXT)) BETWEEN 1 AND 64) AND "
    "installation_key COLLATE \"C\" ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')\n     "
    "   AND (pg_typeof(singleton) IN ('integer'::regtype, 'bigint'::regtype) "
    "AND singleton BETWEEN 1 AND 1)\n        AND ((pg_typeof(source_kind) IN "
    "('text'::regtype, 'character varying'::regtype) AND source_kind IS NOT "
    "NULL AND octet_length(CAST(source_kind AS TEXT)) BETWEEN 1 AND 6) AND "
    "source_kind COLLATE \"C\" IN ('fresh', 'legacy'))\n        AND "
    "((pg_typeof(source_baseline) IN ('text'::regtype, 'character "
    "varying'::regtype) AND source_baseline IS NOT NULL AND "
    "octet_length(CAST(source_baseline AS TEXT)) BETWEEN 1 AND 40) AND "
    'source_baseline COLLATE "C" IN (\'8f1ae757005c95c50a789e4fa0a10aae9b3c402'
    "4'))\n        AND ((pg_typeof(state) IN ('text'::regtype, 'character "
    "varying'::regtype) AND state IS NOT NULL AND octet_length(CAST(state AS "
    'TEXT)) BETWEEN 1 AND 18) AND state COLLATE "C" IN '
    "('ownership_complete'))\n        AND ((pg_typeof(\"schema_fingerprint\") "
    "IN ('text'::regtype, 'character varying'::regtype) AND "
    '"schema_fingerprint" IS NOT NULL AND octet_length(CAST("schema_fingerpri'
    'nt" AS TEXT)) BETWEEN 64 AND 64) AND "schema_fingerprint" COLLATE "C" ~ '
    "'^[0-9a-f]{64}$')\n        AND ((pg_typeof(\"installed_schema_fingerprint\""
    ") IN ('text'::regtype, 'character varying'::regtype) AND "
    '"installed_schema_fingerprint" IS NOT NULL AND '
    'octet_length(CAST("installed_schema_fingerprint" AS TEXT)) BETWEEN 64 '
    'AND 64) AND "installed_schema_fingerprint" COLLATE "C" ~ '
    "'^[0-9a-f]{64}$')\n        AND ((pg_typeof(\"mapping_digest\") IN "
    "('text'::regtype, 'character varying'::regtype) AND \"mapping_digest\" IS "
    'NOT NULL AND octet_length(CAST("mapping_digest" AS TEXT)) BETWEEN 64 '
    'AND 64) AND "mapping_digest" COLLATE "C" ~ \'^[0-9a-f]{64}$\')\n        '
    "AND ((pg_typeof(\"organization_id\") IN ('text'::regtype, 'character "
    'varying\'::regtype) AND "organization_id" IS NOT NULL AND '
    'octet_length(CAST("organization_id" AS TEXT)) BETWEEN 32 AND 32) AND '
    '"organization_id" COLLATE "C" ~ \'^[0-9a-f]{32}$\')\n        AND '
    "((pg_typeof(\"project_id\") IN ('text'::regtype, 'character "
    'varying\'::regtype) AND "project_id" IS NOT NULL AND '
    'octet_length(CAST("project_id" AS TEXT)) BETWEEN 32 AND 32) AND '
    '"project_id" COLLATE "C" ~ \'^[0-9a-f]{32}$\')\n        AND ((source_kind '
    "= 'fresh' AND backup_evidence_digest IS NULL AND drain_evidence_digest "
    "IS NULL) OR (source_kind = 'legacy' AND "
    "((pg_typeof(\"backup_evidence_digest\") IN ('text'::regtype, 'character "
    'varying\'::regtype) AND "backup_evidence_digest" IS NOT NULL AND '
    'octet_length(CAST("backup_evidence_digest" AS TEXT)) BETWEEN 64 AND 64) '
    'AND "backup_evidence_digest" COLLATE "C" ~ \'^[0-9a-f]{64}$\') AND '
    "((pg_typeof(\"drain_evidence_digest\") IN ('text'::regtype, 'character "
    'varying\'::regtype) AND "drain_evidence_digest" IS NOT NULL AND '
    'octet_length(CAST("drain_evidence_digest" AS TEXT)) BETWEEN 64 AND 64) '
    'AND "drain_evidence_digest" COLLATE "C" ~ \'^[0-9a-f]{64}$\')))\n        '
    "AND (pg_typeof(mapping) = 'json'::regtype AND mapping IS NOT NULL AND "
    "octet_length(CAST(mapping AS TEXT)) BETWEEN 1 AND 1048576)\n        AND "
    "(pg_typeof(created_at) = 'timestamp with time zone'::regtype AND "
    "isfinite(created_at) AND created_at >= TIMESTAMPTZ '0001-01-01 "
    "00:00:00+00' AND created_at < TIMESTAMPTZ '10000-01-01 00:00:00+00')\n   "
    "    "
)


_SQLITE_ALL_H10_ADOPTION_VALID = (
    " ((typeof(installation_key) = 'text' AND length(CAST(installation_key "
    "AS BLOB)) BETWEEN 1 AND 64) AND length(installation_key) = "
    "length(CAST(installation_key AS BLOB)) AND substr(installation_key, 1, "
    "1) GLOB '[A-Za-z0-9]' AND installation_key NOT GLOB '*[^A-Za-z0-9_-]*')\n"
    "        AND (typeof(singleton) = 'integer' AND singleton BETWEEN 1 AND "
    "1)\n        AND ((typeof(source_kind) = 'text' AND "
    "length(CAST(source_kind AS BLOB)) BETWEEN 1 AND 6) AND source_kind "
    "COLLATE BINARY IN ('fresh', 'legacy'))\n        AND "
    "((typeof(source_baseline) = 'text' AND length(CAST(source_baseline AS "
    "BLOB)) BETWEEN 1 AND 40) AND source_baseline COLLATE BINARY IN "
    "('8f1ae757005c95c50a789e4fa0a10aae9b3c4024'))\n        AND "
    "((typeof(state) = 'text' AND length(CAST(state AS BLOB)) BETWEEN 1 AND "
    "18) AND state COLLATE BINARY IN ('ownership_complete'))\n        AND "
    "((typeof(\"schema_fingerprint\") = 'text' AND "
    'length(CAST("schema_fingerprint" AS BLOB)) BETWEEN 64 AND 64) AND '
    'length("schema_fingerprint") = 64 AND "schema_fingerprint" NOT GLOB '
    "'*[^0-9a-f]*')\n        AND ((typeof(\"installed_schema_fingerprint\") = "
    "'text' AND length(CAST(\"installed_schema_fingerprint\" AS BLOB)) BETWEEN "
    '64 AND 64) AND length("installed_schema_fingerprint") = 64 AND '
    "\"installed_schema_fingerprint\" NOT GLOB '*[^0-9a-f]*')\n        AND "
    '((typeof("mapping_digest") = \'text\' AND length(CAST("mapping_digest" AS '
    'BLOB)) BETWEEN 64 AND 64) AND length("mapping_digest") = 64 AND '
    "\"mapping_digest\" NOT GLOB '*[^0-9a-f]*')\n        AND "
    '((typeof("organization_id") = \'text\' AND length(CAST("organization_id" '
    'AS BLOB)) BETWEEN 32 AND 32) AND length("organization_id") = 32 AND '
    "\"organization_id\" NOT GLOB '*[^0-9a-f]*')\n        AND "
    '((typeof("project_id") = \'text\' AND length(CAST("project_id" AS BLOB)) '
    'BETWEEN 32 AND 32) AND length("project_id") = 32 AND "project_id" NOT '
    "GLOB '*[^0-9a-f]*')\n        AND ((source_kind = 'fresh' AND "
    "backup_evidence_digest IS NULL AND drain_evidence_digest IS NULL) OR "
    "(source_kind = 'legacy' AND ((typeof(\"backup_evidence_digest\") = 'text' "
    'AND length(CAST("backup_evidence_digest" AS BLOB)) BETWEEN 64 AND 64) '
    'AND length("backup_evidence_digest") = 64 AND "backup_evidence_digest" '
    "NOT GLOB '*[^0-9a-f]*') AND ((typeof(\"drain_evidence_digest\") = 'text' "
    'AND length(CAST("drain_evidence_digest" AS BLOB)) BETWEEN 64 AND 64) '
    'AND length("drain_evidence_digest") = 64 AND "drain_evidence_digest" '
    "NOT GLOB '*[^0-9a-f]*')))\n        AND (typeof(mapping) = 'text' AND "
    "length(CAST(mapping AS BLOB)) BETWEEN 1 AND 1048576)\n        AND "
    "(typeof(created_at) = 'text' AND length(CAST(created_at AS BLOB)) "
    "BETWEEN 1 AND 65536)\n       "
)


_POSTGRESQL_ALL_H60_LEDGER_PROGRESS_VALID = (
    " ((pg_typeof(revision) IN ('text'::regtype, 'character "
    "varying'::regtype) AND revision IS NOT NULL AND "
    "octet_length(CAST(revision AS TEXT)) BETWEEN 1 AND 14) AND revision "
    "COLLATE \"C\" IN ('ar_0007_ledger'))\n        AND (((pg_typeof(phase) IN "
    "('text'::regtype, 'character varying'::regtype) AND phase IS NOT NULL "
    "AND octet_length(CAST(phase AS TEXT)) BETWEEN 1 AND 14) AND phase "
    "COLLATE \"C\" IN ('ledger_opening')) OR ((pg_typeof(phase) IN "
    "('text'::regtype, 'character varying'::regtype) AND phase IS NOT NULL "
    "AND octet_length(CAST(phase AS TEXT)) BETWEEN 48 AND 48) AND "
    "substr(phase, 1, 16) = 'ledger_manifest_' AND ((pg_typeof(substr(phase, "
    "17)) IN ('text'::regtype, 'character varying'::regtype) AND "
    "substr(phase, 17) IS NOT NULL AND octet_length(CAST(substr(phase, 17) "
    'AS TEXT)) BETWEEN 32 AND 32) AND substr(phase, 17) COLLATE "C" ~ '
    "'^[0-9a-f]{32}$')))\n        AND ((pg_typeof(source_digest) IN "
    "('text'::regtype, 'character varying'::regtype) AND source_digest IS "
    "NOT NULL AND octet_length(CAST(source_digest AS TEXT)) BETWEEN 64 AND "
    "64) AND source_digest COLLATE \"C\" ~ '^[0-9a-f]{64}$')\n        AND "
    "(pg_typeof(cursor) = 'json'::regtype AND cursor IS NOT NULL AND "
    "octet_length(CAST(cursor AS TEXT)) BETWEEN 1 AND 65536)\n        AND "
    "(pg_typeof(rows_verified) IN ('integer'::regtype, 'bigint'::regtype) "
    "AND rows_verified BETWEEN 0 AND 64)\n        AND ((pg_typeof(status) IN "
    "('text'::regtype, 'character varying'::regtype) AND status IS NOT NULL "
    "AND octet_length(CAST(status AS TEXT)) BETWEEN 1 AND 8) AND status "
    "COLLATE \"C\" IN ('complete'))\n        AND (pg_typeof(updated_at) = "
    "'timestamp with time zone'::regtype AND isfinite(updated_at) AND "
    "updated_at >= TIMESTAMPTZ '0001-01-01 00:00:00+00' AND updated_at < "
    "TIMESTAMPTZ '10000-01-01 00:00:00+00')\n       "
)


_SQLITE_ALL_H60_LEDGER_PROGRESS_VALID = (
    " ((typeof(revision) = 'text' AND length(CAST(revision AS BLOB)) BETWEEN "
    "1 AND 14) AND revision COLLATE BINARY IN ('ar_0007_ledger'))\n        "
    "AND (((typeof(phase) = 'text' AND length(CAST(phase AS BLOB)) BETWEEN 1 "
    "AND 14) AND phase COLLATE BINARY IN ('ledger_opening')) OR "
    "((typeof(phase) = 'text' AND length(CAST(phase AS BLOB)) BETWEEN 48 AND "
    "48) AND substr(phase, 1, 16) = 'ledger_manifest_' AND "
    "((typeof(substr(phase, 17)) = 'text' AND length(CAST(substr(phase, 17) "
    "AS BLOB)) BETWEEN 32 AND 32) AND length(substr(phase, 17)) = 32 AND "
    "substr(phase, 17) NOT GLOB '*[^0-9a-f]*')))\n        AND "
    "((typeof(source_digest) = 'text' AND length(CAST(source_digest AS "
    "BLOB)) BETWEEN 64 AND 64) AND length(source_digest) = 64 AND "
    "source_digest NOT GLOB '*[^0-9a-f]*')\n        AND (typeof(cursor) = "
    "'text' AND length(CAST(cursor AS BLOB)) BETWEEN 1 AND 65536)\n        "
    "AND (typeof(rows_verified) = 'integer' AND rows_verified BETWEEN 0 AND "
    "64)\n        AND ((typeof(status) = 'text' AND length(CAST(status AS "
    "BLOB)) BETWEEN 1 AND 8) AND status COLLATE BINARY IN ('complete'))\n     "
    "   AND ((typeof(updated_at) = 'text' AND length(CAST(updated_at AS "
    "BLOB)) BETWEEN 1 AND 27) AND length(CAST(updated_at AS BLOB)) = 27 AND "
    "updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:["
    "0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z')\n       "
)


_POSTGRESQL_ALL_H30_PROJECTION_VALID = (
    " ((pg_typeof(source_digest) IN ('text'::regtype, 'character "
    "varying'::regtype) AND source_digest IS NOT NULL AND "
    "octet_length(CAST(source_digest AS TEXT)) BETWEEN 64 AND 64) AND "
    "source_digest COLLATE \"C\" ~ '^[0-9a-f]{64}$')\n        AND "
    "(pg_typeof(cursor) = 'json'::regtype AND cursor IS NOT NULL AND "
    "octet_length(CAST(cursor AS TEXT)) BETWEEN 1 AND 65536)\n        AND "
    "(pg_typeof(rows_verified) IN ('integer'::regtype, 'bigint'::regtype) "
    "AND rows_verified BETWEEN 0 AND 10000)\n        AND ((pg_typeof(status) "
    "IN ('text'::regtype, 'character varying'::regtype) AND status IS NOT "
    "NULL AND octet_length(CAST(status AS TEXT)) BETWEEN 1 AND 8) AND status "
    "COLLATE \"C\" IN ('complete'))\n        AND (pg_typeof(updated_at) = "
    "'timestamp with time zone'::regtype AND isfinite(updated_at) AND "
    "updated_at >= TIMESTAMPTZ '0001-01-01 00:00:00+00' AND updated_at < "
    "TIMESTAMPTZ '10000-01-01 00:00:00+00')\n        AND "
    "(COALESCE(octet_length(CAST(source_digest AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(rows_verified AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(status AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(updated_at AS TEXT)), 0)) BETWEEN 1 AND 1024\n"
    "       "
)


_POSTGRESQL_ALL_H20_OWNERSHIP_VALID = (
    " ((pg_typeof(source_digest) IN ('text'::regtype, 'character "
    "varying'::regtype) AND source_digest IS NOT NULL AND "
    "octet_length(CAST(source_digest AS TEXT)) BETWEEN 64 AND 64) AND "
    "source_digest COLLATE \"C\" ~ '^[0-9a-f]{64}$')\n        AND "
    "(pg_typeof(cursor) = 'json'::regtype AND cursor IS NOT NULL AND "
    "octet_length(CAST(cursor AS TEXT)) BETWEEN 1 AND 65536)\n        AND "
    "(pg_typeof(rows_verified) IN ('integer'::regtype, 'bigint'::regtype) "
    "AND rows_verified BETWEEN 0 AND 100000)\n        AND ((pg_typeof(status) "
    "IN ('text'::regtype, 'character varying'::regtype) AND status IS NOT "
    "NULL AND octet_length(CAST(status AS TEXT)) BETWEEN 1 AND 8) AND status "
    "COLLATE \"C\" IN ('complete'))\n        AND (pg_typeof(updated_at) = "
    "'timestamp with time zone'::regtype AND isfinite(updated_at) AND "
    "updated_at >= TIMESTAMPTZ '0001-01-01 00:00:00+00' AND updated_at < "
    "TIMESTAMPTZ '10000-01-01 00:00:00+00')\n       "
)


_POSTGRESQL_ALL_H50_SEED_PROJECT_VALID = (
    " ((pg_typeof(id) IN ('text'::regtype, 'character varying'::regtype) AND "
    "id IS NOT NULL AND octet_length(CAST(id AS TEXT)) BETWEEN 32 AND 32) "
    "AND id COLLATE \"C\" ~ '^[0-9a-f]{32}$')\n        AND "
    "((pg_typeof(organization_id) IN ('text'::regtype, 'character "
    "varying'::regtype) AND organization_id IS NOT NULL AND "
    "octet_length(CAST(organization_id AS TEXT)) BETWEEN 32 AND 32) AND "
    "organization_id COLLATE \"C\" ~ '^[0-9a-f]{32}$')\n        AND id = "
    ":expected_project_id\n        AND organization_id = "
    ":expected_organization_id\n        AND (pg_typeof(name) IN "
    "('text'::regtype, 'character varying'::regtype) AND name IS NOT NULL "
    "AND octet_length(CAST(name AS TEXT)) BETWEEN 1 AND 480)\n        AND "
    "(pg_typeof(created_at) = 'timestamp with time zone'::regtype AND "
    "isfinite(created_at) AND created_at >= TIMESTAMPTZ '0001-01-01 "
    "00:00:00+00' AND created_at < TIMESTAMPTZ '10000-01-01 00:00:00+00')\n   "
    "    "
)


_SQLITE_ALL_H30_PROJECTION_VALID = (
    " ((typeof(source_digest) = 'text' AND length(CAST(source_digest AS "
    "BLOB)) BETWEEN 64 AND 64) AND length(source_digest) = 64 AND "
    "source_digest NOT GLOB '*[^0-9a-f]*')\n        AND (typeof(cursor) = "
    "'text' AND length(CAST(cursor AS BLOB)) BETWEEN 1 AND 65536)\n        "
    "AND (typeof(rows_verified) = 'integer' AND rows_verified BETWEEN 0 AND "
    "10000)\n        AND ((typeof(status) = 'text' AND length(CAST(status AS "
    "BLOB)) BETWEEN 1 AND 8) AND status COLLATE BINARY IN ('complete'))\n     "
    "   AND (typeof(updated_at) = 'text' AND length(CAST(updated_at AS "
    "BLOB)) BETWEEN 1 AND 1024)\n        AND "
    "(COALESCE(length(CAST(source_digest AS BLOB)), 0) + "
    "COALESCE(length(CAST(rows_verified AS BLOB)), 0) + "
    "COALESCE(length(CAST(status AS BLOB)), 0) + "
    "COALESCE(length(CAST(updated_at AS BLOB)), 0)) BETWEEN 1 AND 1024\n      "
    " "
)


_POSTGRESQL_ALL_H40_ORGANIZATION_VALID = (
    " ((pg_typeof(id) IN ('text'::regtype, 'character varying'::regtype) AND "
    "id IS NOT NULL AND octet_length(CAST(id AS TEXT)) BETWEEN 32 AND 32) "
    "AND id COLLATE \"C\" ~ '^[0-9a-f]{32}$')\n        AND "
    "((pg_typeof(installation_key) IN ('text'::regtype, 'character "
    "varying'::regtype) AND installation_key IS NOT NULL AND "
    "octet_length(CAST(installation_key AS TEXT)) BETWEEN 1 AND 64) AND "
    "installation_key COLLATE \"C\" ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')\n     "
    "   AND id = :expected_organization_id\n        AND installation_key = "
    ":expected_installation_key\n        AND (pg_typeof(created_at) = "
    "'timestamp with time zone'::regtype AND isfinite(created_at) AND "
    "created_at >= TIMESTAMPTZ '0001-01-01 00:00:00+00' AND created_at < "
    "TIMESTAMPTZ '10000-01-01 00:00:00+00')\n       "
)


_SQLITE_ALL_H40_ORGANIZATION_VALID = (
    " ((typeof(id) = 'text' AND length(CAST(id AS BLOB)) BETWEEN 32 AND 32) "
    "AND length(id) = 32 AND id NOT GLOB '*[^0-9a-f]*')\n        AND "
    "((typeof(installation_key) = 'text' AND length(CAST(installation_key AS "
    "BLOB)) BETWEEN 1 AND 64) AND length(installation_key) = "
    "length(CAST(installation_key AS BLOB)) AND substr(installation_key, 1, "
    "1) GLOB '[A-Za-z0-9]' AND installation_key NOT GLOB '*[^A-Za-z0-9_-]*')\n"
    "        AND id = :expected_organization_id\n        AND installation_key "
    "= :expected_installation_key\n        AND (typeof(created_at) = 'text' "
    "AND length(CAST(created_at AS BLOB)) BETWEEN 1 AND 65536)\n       "
)


_SQLITE_ALL_H50_SEED_PROJECT_VALID = (
    " ((typeof(id) = 'text' AND length(CAST(id AS BLOB)) BETWEEN 32 AND 32) "
    "AND length(id) = 32 AND id NOT GLOB '*[^0-9a-f]*')\n        AND "
    "((typeof(organization_id) = 'text' AND length(CAST(organization_id AS "
    "BLOB)) BETWEEN 32 AND 32) AND length(organization_id) = 32 AND "
    "organization_id NOT GLOB '*[^0-9a-f]*')\n        AND id = "
    ":expected_project_id\n        AND organization_id = "
    ":expected_organization_id\n        AND (typeof(name) = 'text' AND "
    "length(CAST(name AS BLOB)) BETWEEN 1 AND 480)\n        AND "
    "(typeof(created_at) = 'text' AND length(CAST(created_at AS BLOB)) "
    "BETWEEN 1 AND 65536)\n       "
)


_SQLITE_ALL_H20_OWNERSHIP_VALID = (
    " ((typeof(source_digest) = 'text' AND length(CAST(source_digest AS "
    "BLOB)) BETWEEN 64 AND 64) AND length(source_digest) = 64 AND "
    "source_digest NOT GLOB '*[^0-9a-f]*')\n        AND (typeof(cursor) = "
    "'text' AND length(CAST(cursor AS BLOB)) BETWEEN 1 AND 65536)\n        "
    "AND (typeof(rows_verified) = 'integer' AND rows_verified BETWEEN 0 AND "
    "100000)\n        AND ((typeof(status) = 'text' AND length(CAST(status AS "
    "BLOB)) BETWEEN 1 AND 8) AND status COLLATE BINARY IN ('complete'))\n     "
    "   AND (typeof(updated_at) = 'text' AND length(CAST(updated_at AS "
    "BLOB)) BETWEEN 1 AND 65536)\n       "
)


_POSTGRESQL_ALL_H00_REVISION_VALID = (
    " ((pg_typeof(version_num) IN ('text'::regtype, 'character "
    "varying'::regtype) AND version_num IS NOT NULL AND "
    "octet_length(CAST(version_num AS TEXT)) BETWEEN 1 AND 17) AND "
    "version_num COLLATE \"C\" IN ('ar_0006_admission', 'ar_0007_ledger')) "
)


_SQLITE_ALL_H00_REVISION_VALID = (
    " ((typeof(version_num) = 'text' AND length(CAST(version_num AS BLOB)) "
    "BETWEEN 1 AND 17) AND version_num COLLATE BINARY IN "
    "('ar_0006_admission', 'ar_0007_ledger')) "
)


_SQLITE_ALL_H00_REVISION_PROJECTION = (
    "SELECT COUNT(*) AS candidate_rows,\n       COALESCE(SUM(CASE WHEN row_ok "
    "= 1 THEN 0 ELSE 1 END), 0) AS invalid_rows,\n       CASE WHEN COUNT(*) = "
    "1 AND MIN(row_ok) = 1 THEN MIN(safe_revision) ELSE NULL END AS "
    "safe_revision\nFROM checked;\n"
)


_SQLITE_ALL_H10_ADOPTION_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "installation_key", '
    '"singleton", "source_kind", "source_baseline", "schema_fingerprint", '
    '"installed_schema_fingerprint", "organization_id", "project_id", '
    '"mapping_digest", "mapping", "backup_evidence_digest", '
    '"drain_evidence_digest", "created_at", "state"\n    FROM '
    '"installation_adoptions"\n    LIMIT 2\n)'
)


_SQLITE_ALL_H10_ADOPTION_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "installation_key", '
            '"singleton", "source_kind", "source_baseline", '
            '"schema_fingerprint", "installed_schema_fingerprint", '
            '"organization_id", "project_id", "mapping_digest", "mapping", '
            '"backup_evidence_digest", "drain_evidence_digest", "created_at", '
            '"state",\n       CASE WHEN'
        ),
        _SQLITE_ALL_H10_ADOPTION_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_SQLITE_ALL_H10_ADOPTION_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "installation_key", "singleton", '
    '"source_kind", "source_baseline", "schema_fingerprint", '
    '"installed_schema_fingerprint", "organization_id", "project_id", '
    '"mapping_digest", "mapping", "backup_evidence_digest", '
    '"drain_evidence_digest", "created_at", "state", row_ok,\n       CASE '
    'WHEN row_ok = 1 THEN COALESCE(length(CAST("installation_key" AS BLOB)), '
    '0) + COALESCE(length(CAST("singleton" AS BLOB)), 0) + '
    'COALESCE(length(CAST("source_kind" AS BLOB)), 0) + '
    'COALESCE(length(CAST("source_baseline" AS BLOB)), 0) + '
    'COALESCE(length(CAST("schema_fingerprint" AS BLOB)), 0) + '
    'COALESCE(length(CAST("installed_schema_fingerprint" AS BLOB)), 0) + '
    'COALESCE(length(CAST("organization_id" AS BLOB)), 0) + '
    'COALESCE(length(CAST("project_id" AS BLOB)), 0) + '
    'COALESCE(length(CAST("mapping_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(mapping AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("backup_evidence_digest" AS BLOB)), 0) + '
    'COALESCE(length(CAST("drain_evidence_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(created_at AS BLOB)), 0) + "
    'COALESCE(length(CAST("state" AS BLOB)), 0) ELSE 0 END AS native_bytes,\n '
    '      CASE WHEN row_ok = 1 THEN COALESCE(length(CAST("installation_key" '
    'AS BLOB)), 0) + COALESCE(length(CAST("singleton" AS BLOB)), 0) + '
    'COALESCE(length(CAST("source_kind" AS BLOB)), 0) + '
    'COALESCE(length(CAST("source_baseline" AS BLOB)), 0) + '
    'COALESCE(length(CAST("schema_fingerprint" AS BLOB)), 0) + '
    'COALESCE(length(CAST("installed_schema_fingerprint" AS BLOB)), 0) + '
    'COALESCE(length(CAST("organization_id" AS BLOB)), 0) + '
    'COALESCE(length(CAST("project_id" AS BLOB)), 0) + '
    'COALESCE(length(CAST("mapping_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(mapping AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("backup_evidence_digest" AS BLOB)), 0) + '
    'COALESCE(length(CAST("drain_evidence_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(created_at AS BLOB)), 0) + "
    'COALESCE(length(CAST("state" AS BLOB)), 0) ELSE 0 END AS utf8_bytes,\n   '
    "    CASE WHEN row_ok = 1 THEN length(CAST(created_at AS BLOB)) ELSE 0 "
    "END AS historical_timestamp_bytes\n    FROM row_checks\n)"
)


_SQLITE_ALL_H10_ADOPTION_SUMMARY = (
    ",\nsummary AS MATERIALIZED (\n    SELECT COUNT(*) AS candidate_rows,\n     "
    "  COALESCE(SUM(CASE WHEN row_ok = 1 THEN 0 ELSE 1 END), 0) AS "
    "invalid_rows,\n       COALESCE(SUM(native_bytes), 0) AS native_bytes,\n   "
    "    COALESCE(SUM(utf8_bytes), 0) AS utf8_bytes,\n       "
    "COALESCE(SUM(historical_timestamp_bytes), 0) AS "
    "historical_timestamp_bytes\n    FROM checked\n)\n"
)


_SQLITE_ALL_H10_ADOPTION_PROJECTION = (
    "SELECT candidate_rows, invalid_rows, native_bytes, utf8_bytes, "
    "historical_timestamp_bytes FROM summary;\n"
)


_SQLITE_ALL_H20_OWNERSHIP_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at"\n    FROM "migration_progress"\n  '
    "  WHERE revision COLLATE BINARY = 'ar_0003_ownership' AND phase COLLATE "
    "BINARY = 'ownership'\n    LIMIT 2\n)"
)


_SQLITE_ALL_H20_OWNERSHIP_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "source_digest", '
            '"cursor", "rows_verified", "status", "updated_at",\n       CASE WHEN'
        ),
        _SQLITE_ALL_H20_OWNERSHIP_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_SQLITE_ALL_H20_OWNERSHIP_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at", row_ok,\n       CASE WHEN '
    'row_ok = 1 THEN COALESCE(length(CAST("source_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(cursor AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("rows_verified" AS BLOB)), 0) + '
    'COALESCE(length(CAST("status" AS BLOB)), 0) + '
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS "
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(length(CAST("source_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(cursor AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("rows_verified" AS BLOB)), 0) + '
    'COALESCE(length(CAST("status" AS BLOB)), 0) + '
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS utf8_bytes,\n"
    "       CASE WHEN row_ok = 1 THEN length(CAST(updated_at AS BLOB)) ELSE "
    "0 END AS historical_timestamp_bytes\n    FROM row_checks\n)"
)


_SQLITE_ALL_H30_PROJECTION_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at"\n    FROM "migration_progress"\n  '
    "  WHERE revision COLLATE BINARY = 'ar_0005_run_index' AND phase COLLATE "
    "BINARY = 'run_index'\n    LIMIT 2\n)"
)


_SQLITE_ALL_H30_PROJECTION_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "source_digest", '
            '"cursor", "rows_verified", "status", "updated_at",\n       CASE WHEN'
        ),
        _SQLITE_ALL_H30_PROJECTION_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_SQLITE_ALL_H30_PROJECTION_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at", row_ok,\n       CASE WHEN '
    'row_ok = 1 THEN COALESCE(length(CAST("source_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(cursor AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("rows_verified" AS BLOB)), 0) + '
    'COALESCE(length(CAST("status" AS BLOB)), 0) + '
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS "
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(length(CAST("source_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(cursor AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("rows_verified" AS BLOB)), 0) + '
    'COALESCE(length(CAST("status" AS BLOB)), 0) + '
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS utf8_bytes,\n"
    "       CASE WHEN row_ok = 1 THEN 0 ELSE 0 END AS "
    "historical_timestamp_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "COALESCE(length(CAST(source_digest AS BLOB)), 0) + "
    "COALESCE(length(CAST(rows_verified AS BLOB)), 0) + "
    "COALESCE(length(CAST(status AS BLOB)), 0) + "
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS "
    "original_metadata_bytes\n    FROM row_checks\n)"
)


_SQLITE_ALL_H30_PROJECTION_SUMMARY = (
    ",\nsummary AS MATERIALIZED (\n    SELECT COUNT(*) AS candidate_rows,\n     "
    "  COALESCE(SUM(CASE WHEN row_ok = 1 THEN 0 ELSE 1 END), 0) AS "
    "invalid_rows,\n       COALESCE(SUM(native_bytes), 0) AS native_bytes,\n   "
    "    COALESCE(SUM(utf8_bytes), 0) AS utf8_bytes,\n       "
    "COALESCE(SUM(historical_timestamp_bytes), 0) AS "
    "historical_timestamp_bytes,\n       COALESCE(SUM(original_metadata_bytes)"
    ", 0) AS original_metadata_bytes\n    FROM checked\n)\n"
)


_SQLITE_ALL_H30_PROJECTION_PROJECTION = (
    "SELECT candidate_rows, invalid_rows, native_bytes, utf8_bytes, "
    "historical_timestamp_bytes, original_metadata_bytes FROM summary;\n"
)


_SQLITE_ALL_H40_ORGANIZATION_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "id", "installation_key", '
    '"created_at"\n    FROM "organizations"\n    LIMIT 2\n)'
)


_SQLITE_ALL_H40_ORGANIZATION_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "id", "installation_key", '
            '"created_at",\n       CASE WHEN'
        ),
        _SQLITE_ALL_H40_ORGANIZATION_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_SQLITE_ALL_H40_ORGANIZATION_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "id", "installation_key", '
    '"created_at", row_ok,\n       CASE WHEN row_ok = 1 THEN '
    "COALESCE(length(CAST(created_at AS BLOB)), 0) ELSE 0 END AS "
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "COALESCE(length(CAST(created_at AS BLOB)), 0) ELSE 0 END AS utf8_bytes,\n"
    "       CASE WHEN row_ok = 1 THEN length(CAST(created_at AS BLOB)) ELSE "
    "0 END AS historical_timestamp_bytes\n    FROM row_checks\n)"
)


_SQLITE_ALL_H50_SEED_PROJECT_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "id", "organization_id", '
    '"name", "created_at"\n    FROM "projects"\n    WHERE id = '
    ":expected_project_id\n    LIMIT 2\n)"
)


_SQLITE_ALL_H50_SEED_PROJECT_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "id", "organization_id", '
            '"name", "created_at",\n       CASE WHEN'
        ),
        _SQLITE_ALL_H50_SEED_PROJECT_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_SQLITE_ALL_H50_SEED_PROJECT_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "id", "organization_id", "name", '
    '"created_at", row_ok,\n       CASE WHEN row_ok = 1 THEN '
    'COALESCE(length(CAST("name" AS BLOB)), 0) + '
    "COALESCE(length(CAST(created_at AS BLOB)), 0) ELSE 0 END AS "
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(length(CAST("name" AS BLOB)), 0) + '
    "COALESCE(length(CAST(created_at AS BLOB)), 0) ELSE 0 END AS utf8_bytes,\n"
    "       CASE WHEN row_ok = 1 THEN length(CAST(created_at AS BLOB)) ELSE "
    "0 END AS historical_timestamp_bytes\n    FROM row_checks\n)"
)


_SQLITE_ALL_H60_LEDGER_PROGRESS_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "revision", "phase", '
    '"source_digest", "cursor", "rows_verified", "status", "updated_at"\n    '
    'FROM "migration_progress"\n    WHERE revision COLLATE BINARY = '
    "'ar_0007_ledger'\n    ORDER BY phase\n    LIMIT 258\n)"
)


_SQLITE_ALL_H60_LEDGER_PROGRESS_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "revision", "phase", '
            '"source_digest", "cursor", "rows_verified", "status", "updated_at",\n'
            "       CASE WHEN"
        ),
        _SQLITE_ALL_H60_LEDGER_PROGRESS_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_SQLITE_ALL_H60_LEDGER_PROGRESS_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "revision", "phase", '
    '"source_digest", "cursor", "rows_verified", "status", "updated_at", '
    "row_ok,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(length(CAST("revision" AS BLOB)), 0) + '
    'COALESCE(length(CAST("phase" AS BLOB)), 0) + '
    'COALESCE(length(CAST("source_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(cursor AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("rows_verified" AS BLOB)), 0) + '
    'COALESCE(length(CAST("status" AS BLOB)), 0) + '
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS "
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(length(CAST("revision" AS BLOB)), 0) + '
    'COALESCE(length(CAST("phase" AS BLOB)), 0) + '
    'COALESCE(length(CAST("source_digest" AS BLOB)), 0) + '
    "COALESCE(length(CAST(CAST(cursor AS TEXT) AS BLOB)), 0) + "
    'COALESCE(length(CAST("rows_verified" AS BLOB)), 0) + '
    'COALESCE(length(CAST("status" AS BLOB)), 0) + '
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS utf8_bytes,\n"
    "       CASE WHEN row_ok = 1 THEN 0 ELSE 0 END AS "
    "historical_timestamp_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "length(CAST(cursor AS BLOB)) ELSE 0 END AS cursor_bytes,\n       CASE "
    "WHEN row_ok = 1 THEN COALESCE(length(CAST(revision AS BLOB)), 0) + "
    "COALESCE(length(CAST(phase AS BLOB)), 0) + "
    "COALESCE(length(CAST(source_digest AS BLOB)), 0) + "
    "COALESCE(length(CAST(rows_verified AS BLOB)), 0) + "
    "COALESCE(length(CAST(status AS BLOB)), 0) + "
    "COALESCE(length(CAST(updated_at AS BLOB)), 0) ELSE 0 END AS "
    "metadata_bytes\n    FROM row_checks\n)"
)


_SQLITE_ALL_H60_LEDGER_PROGRESS_SUMMARY = (
    ",\nsummary AS MATERIALIZED (\n    SELECT COUNT(*) AS candidate_rows,\n     "
    "  COALESCE(SUM(CASE WHEN row_ok = 1 THEN 0 ELSE 1 END), 0) AS "
    "invalid_rows,\n       COALESCE(SUM(native_bytes), 0) AS native_bytes,\n   "
    "    COALESCE(SUM(utf8_bytes), 0) AS utf8_bytes,\n       "
    "COALESCE(SUM(historical_timestamp_bytes), 0) AS "
    "historical_timestamp_bytes,\n       COALESCE(SUM(cursor_bytes), 0) AS "
    "cursor_bytes,\n       COALESCE(SUM(metadata_bytes), 0) AS "
    "metadata_bytes,\n       COALESCE(SUM(CASE WHEN phase = 'ledger_opening' "
    "THEN 1 ELSE 0 END), 0) AS opening_rows,\n       COALESCE(SUM(CASE WHEN "
    "phase <> 'ledger_opening' THEN 1 ELSE 0 END), 0) AS manifest_rows\n    "
    "FROM checked\n)\n"
)


_SQLITE_ALL_H60_LEDGER_PROGRESS_PROJECTION = (
    "SELECT candidate_rows, invalid_rows, native_bytes, utf8_bytes, "
    "historical_timestamp_bytes, cursor_bytes, metadata_bytes, opening_rows, "
    "manifest_rows FROM summary;\n"
)


_POSTGRESQL_ALL_H10_ADOPTION_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "installation_key", '
            '"singleton", "source_kind", "source_baseline", '
            '"schema_fingerprint", "installed_schema_fingerprint", '
            '"organization_id", "project_id", "mapping_digest", "mapping", '
            '"backup_evidence_digest", "drain_evidence_digest", "created_at", '
            '"state",\n       CASE WHEN'
        ),
        _POSTGRESQL_ALL_H10_ADOPTION_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_POSTGRESQL_ALL_H10_ADOPTION_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "installation_key", "singleton", '
    '"source_kind", "source_baseline", "schema_fingerprint", '
    '"installed_schema_fingerprint", "organization_id", "project_id", '
    '"mapping_digest", "mapping", "backup_evidence_digest", '
    '"drain_evidence_digest", "created_at", "state", row_ok,\n       CASE '
    'WHEN row_ok = 1 THEN COALESCE(octet_length(CAST("installation_key" AS '
    'TEXT)), 0) + COALESCE(octet_length(CAST("singleton" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("source_kind" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("source_baseline" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("schema_fingerprint" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("installed_schema_fingerprint" AS TEXT)), 0) '
    '+ COALESCE(octet_length(CAST("organization_id" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("project_id" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("mapping_digest" AS TEXT)), 0) + '
    "COALESCE(octet_length(CAST(CAST(mapping AS TEXT) AS TEXT)), 0) + "
    'COALESCE(octet_length(CAST("backup_evidence_digest" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("drain_evidence_digest" AS TEXT)), 0) + '
    "COALESCE(octet_length(CAST(to_char(created_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("state" AS TEXT)), 0) ELSE 0 END AS '
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(octet_length(convert_to(CAST("installation_key" AS TEXT), '
    "'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"singleton\" AS "
    "TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"source_kind"
    "\" AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"source"
    "_baseline\" AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAS"
    "T(\"schema_fingerprint\" AS TEXT), 'UTF8')), 0) + "
    'COALESCE(octet_length(convert_to(CAST("installed_schema_fingerprint" AS '
    "TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"organizatio"
    "n_id\" AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"pr"
    "oject_id\" AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST"
    "(\"mapping_digest\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(CAST(mapping AS TEXT) AS TEXT), "
    "'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"backup_evidence_di"
    "gest\" AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"dr"
    "ain_evidence_digest\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(to_char(created_at AT TIME ZONE "
    "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(\"state\" AS TEXT), 'UTF8')), 0) "
    "ELSE 0 END AS utf8_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "octet_length(CAST(to_char(created_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)) ELSE 0 END AS '
    "historical_timestamp_bytes\n    FROM row_checks\n)"
)


_POSTGRESQL_ALL_H20_OWNERSHIP_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at"\n    FROM "migration_progress"\n  '
    "  WHERE revision COLLATE \"C\" = 'ar_0003_ownership' AND phase COLLATE "
    "\"C\" = 'ownership'\n    LIMIT 2\n)"
)


_POSTGRESQL_ALL_H20_OWNERSHIP_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "source_digest", '
            '"cursor", "rows_verified", "status", "updated_at",\n       CASE WHEN'
        ),
        _POSTGRESQL_ALL_H20_OWNERSHIP_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_POSTGRESQL_ALL_H20_OWNERSHIP_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at", row_ok,\n       CASE WHEN '
    'row_ok = 1 THEN COALESCE(octet_length(CAST("source_digest" AS TEXT)), '
    "0) + COALESCE(octet_length(CAST(CAST(cursor AS TEXT) AS TEXT)), 0) + "
    'COALESCE(octet_length(CAST("rows_verified" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("status" AS TEXT)), 0) + '
    "COALESCE(octet_length(CAST(to_char(updated_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)), 0) ELSE 0 END AS '
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(octet_length(convert_to(CAST("source_digest" AS TEXT), '
    "'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(CAST(cursor AS "
    "TEXT) AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"ro"
    "ws_verified\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(\"status\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(to_char(updated_at AT TIME ZONE "
    "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS TEXT), 'UTF8')), 0) ELSE 0 "
    "END AS utf8_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "octet_length(CAST(to_char(updated_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)) ELSE 0 END AS '
    "historical_timestamp_bytes\n    FROM row_checks\n)"
)


_POSTGRESQL_ALL_H30_PROJECTION_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at"\n    FROM "migration_progress"\n  '
    "  WHERE revision COLLATE \"C\" = 'ar_0005_run_index' AND phase COLLATE "
    "\"C\" = 'run_index'\n    LIMIT 2\n)"
)


_POSTGRESQL_ALL_H30_PROJECTION_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "source_digest", '
            '"cursor", "rows_verified", "status", "updated_at",\n       CASE WHEN'
        ),
        _POSTGRESQL_ALL_H30_PROJECTION_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_POSTGRESQL_ALL_H30_PROJECTION_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "source_digest", "cursor", '
    '"rows_verified", "status", "updated_at", row_ok,\n       CASE WHEN '
    'row_ok = 1 THEN COALESCE(octet_length(CAST("source_digest" AS TEXT)), '
    "0) + COALESCE(octet_length(CAST(CAST(cursor AS TEXT) AS TEXT)), 0) + "
    'COALESCE(octet_length(CAST("rows_verified" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("status" AS TEXT)), 0) + '
    "COALESCE(octet_length(CAST(to_char(updated_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)), 0) ELSE 0 END AS '
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(octet_length(convert_to(CAST("source_digest" AS TEXT), '
    "'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(CAST(cursor AS "
    "TEXT) AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"ro"
    "ws_verified\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(\"status\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(to_char(updated_at AT TIME ZONE "
    "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS TEXT), 'UTF8')), 0) ELSE 0 "
    "END AS utf8_bytes,\n       CASE WHEN row_ok = 1 THEN 0 ELSE 0 END AS "
    "historical_timestamp_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "COALESCE(octet_length(CAST(source_digest AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(rows_verified AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(status AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(updated_at AS TEXT)), 0) ELSE 0 END AS "
    "original_metadata_bytes\n    FROM row_checks\n)"
)


_POSTGRESQL_ALL_H40_ORGANIZATION_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "id", "installation_key", '
            '"created_at",\n       CASE WHEN'
        ),
        _POSTGRESQL_ALL_H40_ORGANIZATION_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_POSTGRESQL_ALL_H40_ORGANIZATION_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "id", "installation_key", '
    '"created_at", row_ok,\n       CASE WHEN row_ok = 1 THEN '
    "COALESCE(octet_length(CAST(to_char(created_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)), 0) ELSE 0 END AS '
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "COALESCE(octet_length(convert_to(CAST(to_char(created_at AT TIME ZONE "
    "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS TEXT), 'UTF8')), 0) ELSE 0 "
    "END AS utf8_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "octet_length(CAST(to_char(created_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)) ELSE 0 END AS '
    "historical_timestamp_bytes\n    FROM row_checks\n)"
)


_POSTGRESQL_ALL_H50_SEED_PROJECT_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "id", "organization_id", '
            '"name", "created_at",\n       CASE WHEN'
        ),
        _POSTGRESQL_ALL_H50_SEED_PROJECT_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_POSTGRESQL_ALL_H50_SEED_PROJECT_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "id", "organization_id", "name", '
    '"created_at", row_ok,\n       CASE WHEN row_ok = 1 THEN '
    'COALESCE(octet_length(CAST("name" AS TEXT)), 0) + '
    "COALESCE(octet_length(CAST(to_char(created_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)), 0) ELSE 0 END AS '
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "COALESCE(octet_length(convert_to(CAST(\"name\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(to_char(created_at AT TIME ZONE "
    "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS TEXT), 'UTF8')), 0) ELSE 0 "
    "END AS utf8_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "octet_length(CAST(to_char(created_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)) ELSE 0 END AS '
    "historical_timestamp_bytes\n    FROM row_checks\n)"
)


_POSTGRESQL_ALL_H60_LEDGER_PROGRESS_CANDIDATES = (
    'WITH candidates AS MATERIALIZED (\n    SELECT "revision", "phase", '
    '"source_digest", "cursor", "rows_verified", "status", "updated_at"\n    '
    'FROM "migration_progress"\n    WHERE revision COLLATE "C" = '
    "'ar_0007_ledger'\n    ORDER BY phase\n    LIMIT 258\n)"
)


_POSTGRESQL_ALL_H60_LEDGER_PROGRESS_ROW_CHECKS = "".join(
    (
        (
            ',\nrow_checks AS MATERIALIZED (\n    SELECT "revision", "phase", '
            '"source_digest", "cursor", "rows_verified", "status", "updated_at",\n'
            "       CASE WHEN"
        ),
        _POSTGRESQL_ALL_H60_LEDGER_PROGRESS_VALID,
        ("THEN 1 ELSE 0 END AS row_ok\n    FROM candidates\n)"),
    )
)


_POSTGRESQL_ALL_H60_LEDGER_PROGRESS_CHECKED = (
    ',\nchecked AS MATERIALIZED (\n    SELECT "revision", "phase", '
    '"source_digest", "cursor", "rows_verified", "status", "updated_at", '
    "row_ok,\n       CASE WHEN row_ok = 1 THEN "
    'COALESCE(octet_length(CAST("revision" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("phase" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("source_digest" AS TEXT)), 0) + '
    "COALESCE(octet_length(CAST(CAST(cursor AS TEXT) AS TEXT)), 0) + "
    'COALESCE(octet_length(CAST("rows_verified" AS TEXT)), 0) + '
    'COALESCE(octet_length(CAST("status" AS TEXT)), 0) + '
    "COALESCE(octet_length(CAST(to_char(updated_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)), 0) ELSE 0 END AS '
    "native_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "COALESCE(octet_length(convert_to(CAST(\"revision\" AS TEXT), 'UTF8')), 0) "
    "+ COALESCE(octet_length(convert_to(CAST(\"phase\" AS TEXT), 'UTF8')), 0) "
    '+ COALESCE(octet_length(convert_to(CAST("source_digest" AS TEXT), '
    "'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(CAST(cursor AS "
    "TEXT) AS TEXT), 'UTF8')), 0) + COALESCE(octet_length(convert_to(CAST(\"ro"
    "ws_verified\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(\"status\" AS TEXT), 'UTF8')), 0) + "
    "COALESCE(octet_length(convert_to(CAST(to_char(updated_at AT TIME ZONE "
    "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS TEXT), 'UTF8')), 0) ELSE 0 "
    "END AS utf8_bytes,\n       CASE WHEN row_ok = 1 THEN 0 ELSE 0 END AS "
    "historical_timestamp_bytes,\n       CASE WHEN row_ok = 1 THEN "
    "octet_length(CAST(cursor AS TEXT)) ELSE 0 END AS cursor_bytes,\n       "
    "CASE WHEN row_ok = 1 THEN COALESCE(octet_length(CAST(revision AS "
    "TEXT)), 0) + COALESCE(octet_length(CAST(phase AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(source_digest AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(rows_verified AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(status AS TEXT)), 0) + "
    "COALESCE(octet_length(CAST(to_char(updated_at AT TIME ZONE 'UTC', "
    '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') AS TEXT)), 0) ELSE 0 END AS '
    "metadata_bytes\n    FROM row_checks\n)"
)


SQL: dict[tuple[str, str, str], str] = {
    ("all", "sqlite", "H00_revision"): "".join(
        (
            (
                "WITH candidates AS MATERIALIZED (\n    SELECT version_num FROM "
                "alembic_version LIMIT 2\n),\nchecked AS MATERIALIZED (\n    SELECT "
                "CASE WHEN"
            ),
            _SQLITE_ALL_H00_REVISION_VALID,
            ("THEN 1 ELSE 0 END AS row_ok,\n           CASE WHEN"),
            _SQLITE_ALL_H00_REVISION_VALID,
            ("THEN version_num ELSE NULL END AS safe_revision\n    FROM candidates\n)\n"),
            _SQLITE_ALL_H00_REVISION_PROJECTION,
        )
    ),
    ("all", "sqlite", "H01_progress_addressability"): (
        "SELECT CASE WHEN EXISTS (\n    SELECT 1 FROM migration_progress\n    "
        "WHERE CASE WHEN (typeof(revision) = 'text' AND length(CAST(revision AS "
        "BLOB)) BETWEEN 0 AND 128) AND (typeof(phase) = 'text' AND "
        "length(CAST(phase AS BLOB)) BETWEEN 0 AND 256) THEN 0 ELSE 1 END = 1\n   "
        " LIMIT 1\n) THEN 1 ELSE 0 END AS invalid_key_exists;\n"
    ),
    ("all", "sqlite", "H02_misplaced_ledger_namespace"): (
        "SELECT CASE WHEN EXISTS (\n    SELECT 1 FROM migration_progress\n    "
        "WHERE revision COLLATE BINARY <> 'ar_0007_ledger'\n      AND (phase "
        "COLLATE BINARY = 'ledger_opening' OR substr(phase, 1, 16) COLLATE "
        "BINARY = 'ledger_manifest_')\n    LIMIT 1\n) THEN 1 ELSE 0 END AS "
        "misplaced_exists;\n"
    ),
    ("all", "sqlite", "H10_adoption_gate"): "".join(
        (
            _SQLITE_ALL_H10_ADOPTION_CANDIDATES,
            _SQLITE_ALL_H10_ADOPTION_ROW_CHECKS,
            _SQLITE_ALL_H10_ADOPTION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "sqlite", "H10_adoption_body"): "".join(
        (
            _SQLITE_ALL_H10_ADOPTION_CANDIDATES,
            _SQLITE_ALL_H10_ADOPTION_ROW_CHECKS,
            _SQLITE_ALL_H10_ADOPTION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "installation_key" ELSE NULL END '
                'AS "installation_key",\n       CASE WHEN c.row_ok = 1 THEN '
                '"singleton" ELSE NULL END AS "singleton",\n       CASE WHEN c.row_ok '
                '= 1 THEN "source_kind" ELSE NULL END AS "source_kind",\n       CASE '
                'WHEN c.row_ok = 1 THEN "source_baseline" ELSE NULL END AS '
                '"source_baseline",\n       CASE WHEN c.row_ok = 1 THEN '
                '"schema_fingerprint" ELSE NULL END AS "schema_fingerprint",\n       '
                'CASE WHEN c.row_ok = 1 THEN "installed_schema_fingerprint" ELSE '
                'NULL END AS "installed_schema_fingerprint",\n       CASE WHEN '
                'c.row_ok = 1 THEN "organization_id" ELSE NULL END AS '
                '"organization_id",\n       CASE WHEN c.row_ok = 1 THEN "project_id" '
                'ELSE NULL END AS "project_id",\n       CASE WHEN c.row_ok = 1 THEN '
                '"mapping_digest" ELSE NULL END AS "mapping_digest",\n       CASE '
                "WHEN c.row_ok = 1 THEN CAST(mapping AS TEXT) ELSE NULL END AS "
                '"mapping",\n       CASE WHEN c.row_ok = 1 THEN '
                '"backup_evidence_digest" ELSE NULL END AS "backup_evidence_digest",\n'
                '       CASE WHEN c.row_ok = 1 THEN "drain_evidence_digest" ELSE '
                'NULL END AS "drain_evidence_digest",\n       CASE WHEN c.row_ok = 1 '
                'THEN created_at ELSE NULL END AS "created_at",\n       CASE WHEN '
                'c.row_ok = 1 THEN "state" ELSE NULL END AS "state"\nFROM checked AS '
                "c CROSS JOIN summary AS s\nWHERE s.candidate_rows = 1\n  AND "
                "s.invalid_rows = 0\n  AND s.native_bytes BETWEEN 1 AND 1114625\n  AND "
                "s.utf8_bytes BETWEEN 1 AND 4458500\n  AND s.candidate_rows = "
                ":expected_rows\n  AND s.native_bytes = :expected_native_bytes\n  AND "
                "s.utf8_bytes = :expected_utf8_bytes\nLIMIT 2;\n"
            ),
        )
    ),
    ("all", "sqlite", "H20_ownership_gate"): "".join(
        (
            _SQLITE_ALL_H20_OWNERSHIP_CANDIDATES,
            _SQLITE_ALL_H20_OWNERSHIP_ROW_CHECKS,
            _SQLITE_ALL_H20_OWNERSHIP_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "sqlite", "H20_ownership_body"): "".join(
        (
            _SQLITE_ALL_H20_OWNERSHIP_CANDIDATES,
            _SQLITE_ALL_H20_OWNERSHIP_ROW_CHECKS,
            _SQLITE_ALL_H20_OWNERSHIP_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "source_digest" ELSE NULL END AS '
                '"source_digest",\n       CASE WHEN c.row_ok = 1 THEN CAST(cursor AS '
                'TEXT) ELSE NULL END AS "cursor",\n       CASE WHEN c.row_ok = 1 THEN '
                '"rows_verified" ELSE NULL END AS "rows_verified",\n       CASE WHEN '
                'c.row_ok = 1 THEN "status" ELSE NULL END AS "status",\n       CASE '
                'WHEN c.row_ok = 1 THEN updated_at ELSE NULL END AS "updated_at"\n'
                "FROM checked AS c CROSS JOIN summary AS s\nWHERE s.candidate_rows = "
                "1\n  AND s.invalid_rows = 0\n  AND s.native_bytes BETWEEN 1 AND "
                "131150\n  AND s.utf8_bytes BETWEEN 1 AND 524600\n  AND "
                "s.candidate_rows = :expected_rows\n  AND s.native_bytes = "
                ":expected_native_bytes\n  AND s.utf8_bytes = :expected_utf8_bytes\n"
                "LIMIT 2;\n"
            ),
        )
    ),
    ("all", "sqlite", "H30_projection_gate"): "".join(
        (
            _SQLITE_ALL_H30_PROJECTION_CANDIDATES,
            _SQLITE_ALL_H30_PROJECTION_ROW_CHECKS,
            _SQLITE_ALL_H30_PROJECTION_CHECKED,
            _SQLITE_ALL_H30_PROJECTION_SUMMARY,
            _SQLITE_ALL_H30_PROJECTION_PROJECTION,
        )
    ),
    ("all", "sqlite", "H30_projection_body"): "".join(
        (
            _SQLITE_ALL_H30_PROJECTION_CANDIDATES,
            _SQLITE_ALL_H30_PROJECTION_ROW_CHECKS,
            _SQLITE_ALL_H30_PROJECTION_CHECKED,
            _SQLITE_ALL_H30_PROJECTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "source_digest" ELSE NULL END AS '
                '"source_digest",\n       CASE WHEN c.row_ok = 1 THEN CAST(cursor AS '
                'TEXT) ELSE NULL END AS "cursor",\n       CASE WHEN c.row_ok = 1 THEN '
                '"rows_verified" ELSE NULL END AS "rows_verified",\n       CASE WHEN '
                'c.row_ok = 1 THEN "status" ELSE NULL END AS "status",\n       CASE '
                'WHEN c.row_ok = 1 THEN updated_at ELSE NULL END AS "updated_at"\n'
                "FROM checked AS c CROSS JOIN summary AS s\nWHERE s.candidate_rows = "
                "1\n  AND s.invalid_rows = 0\n  AND s.native_bytes BETWEEN 1 AND 66560\n"
                "  AND s.utf8_bytes BETWEEN 1 AND 266240\n  AND s.candidate_rows = "
                ":expected_rows\n  AND s.native_bytes = :expected_native_bytes\n  AND "
                "s.utf8_bytes = :expected_utf8_bytes\nLIMIT 2;\n"
            ),
        )
    ),
    ("all", "sqlite", "H40_organization_gate"): "".join(
        (
            _SQLITE_ALL_H40_ORGANIZATION_CANDIDATES,
            _SQLITE_ALL_H40_ORGANIZATION_ROW_CHECKS,
            _SQLITE_ALL_H40_ORGANIZATION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "sqlite", "H40_organization_body"): "".join(
        (
            _SQLITE_ALL_H40_ORGANIZATION_CANDIDATES,
            _SQLITE_ALL_H40_ORGANIZATION_ROW_CHECKS,
            _SQLITE_ALL_H40_ORGANIZATION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                "SELECT CASE WHEN c.row_ok = 1 THEN created_at ELSE NULL END AS "
                '"created_at"\nFROM checked AS c CROSS JOIN summary AS s\nWHERE '
                "s.candidate_rows = 1\n  AND s.invalid_rows = 0\n  AND s.native_bytes "
                "BETWEEN 1 AND 65536\n  AND s.utf8_bytes BETWEEN 1 AND 262144\n  AND "
                "s.candidate_rows = :expected_rows\n  AND s.native_bytes = "
                ":expected_native_bytes\n  AND s.utf8_bytes = :expected_utf8_bytes\n"
                "LIMIT 2;\n"
            ),
        )
    ),
    ("all", "sqlite", "H50_seed_project_gate"): "".join(
        (
            _SQLITE_ALL_H50_SEED_PROJECT_CANDIDATES,
            _SQLITE_ALL_H50_SEED_PROJECT_ROW_CHECKS,
            _SQLITE_ALL_H50_SEED_PROJECT_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "sqlite", "H50_seed_project_body"): "".join(
        (
            _SQLITE_ALL_H50_SEED_PROJECT_CANDIDATES,
            _SQLITE_ALL_H50_SEED_PROJECT_ROW_CHECKS,
            _SQLITE_ALL_H50_SEED_PROJECT_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "name" ELSE NULL END AS "name",\n '
                "      CASE WHEN c.row_ok = 1 THEN created_at ELSE NULL END AS "
                '"created_at"\nFROM checked AS c CROSS JOIN summary AS s\nWHERE '
                "s.candidate_rows = 1\n  AND s.invalid_rows = 0\n  AND s.native_bytes "
                "BETWEEN 1 AND 66016\n  AND s.utf8_bytes BETWEEN 1 AND 264064\n  AND "
                "s.candidate_rows = :expected_rows\n  AND s.native_bytes = "
                ":expected_native_bytes\n  AND s.utf8_bytes = :expected_utf8_bytes\n"
                "LIMIT 2;\n"
            ),
        )
    ),
    ("all", "sqlite", "H60_ledger_progress_gate"): "".join(
        (
            _SQLITE_ALL_H60_LEDGER_PROGRESS_CANDIDATES,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_ROW_CHECKS,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_CHECKED,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_SUMMARY,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_PROJECTION,
        )
    ),
    ("all", "sqlite", "H60_ledger_progress_body"): "".join(
        (
            _SQLITE_ALL_H60_LEDGER_PROGRESS_CANDIDATES,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_ROW_CHECKS,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_CHECKED,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "revision" ELSE NULL END AS '
                '"revision",\n       CASE WHEN c.row_ok = 1 THEN "phase" ELSE NULL '
                'END AS "phase",\n       CASE WHEN c.row_ok = 1 THEN "source_digest" '
                'ELSE NULL END AS "source_digest",\n       CASE WHEN c.row_ok = 1 '
                'THEN CAST(cursor AS TEXT) ELSE NULL END AS "cursor",\n       CASE '
                'WHEN c.row_ok = 1 THEN "rows_verified" ELSE NULL END AS '
                '"rows_verified",\n       CASE WHEN c.row_ok = 1 THEN "status" ELSE '
                'NULL END AS "status",\n       CASE WHEN c.row_ok = 1 THEN updated_at '
                'ELSE NULL END AS "updated_at"\nFROM checked AS c CROSS JOIN summary '
                "AS s\nWHERE s.candidate_rows BETWEEN 2 AND 257\n  AND s.invalid_rows "
                "= 0\n  AND s.opening_rows = 1\n  AND s.manifest_rows BETWEEN 1 AND "
                "256\n  AND s.cursor_bytes BETWEEN 1 AND 16777216\n  AND "
                "s.metadata_bytes BETWEEN 1 AND 41891\n  AND s.native_bytes BETWEEN 1 "
                "AND 16819107\n  AND s.utf8_bytes BETWEEN 1 AND 67276428\n  AND "
                "s.candidate_rows = :expected_rows\n  AND s.native_bytes = "
                ":expected_native_bytes\n  AND s.utf8_bytes = :expected_utf8_bytes\n  "
                "AND s.cursor_bytes = :expected_cursor_bytes\nORDER BY c.phase\nLIMIT "
                "258;\n"
            ),
        )
    ),
    ("all", "postgresql", "H00_revision"): "".join(
        (
            (
                "WITH candidates AS MATERIALIZED (\n    SELECT version_num FROM "
                "alembic_version LIMIT 2\n),\nchecked AS MATERIALIZED (\n    SELECT "
                "CASE WHEN"
            ),
            _POSTGRESQL_ALL_H00_REVISION_VALID,
            ("THEN 1 ELSE 0 END AS row_ok,\n           CASE WHEN"),
            _POSTGRESQL_ALL_H00_REVISION_VALID,
            ("THEN version_num ELSE NULL END AS safe_revision\n    FROM candidates\n)\n"),
            _SQLITE_ALL_H00_REVISION_PROJECTION,
        )
    ),
    ("all", "postgresql", "H01_progress_addressability"): (
        "SELECT CASE WHEN EXISTS (\n    SELECT 1 FROM migration_progress\n    "
        "WHERE CASE WHEN (pg_typeof(revision) IN ('text'::regtype, 'character "
        "varying'::regtype) AND revision IS NOT NULL AND "
        "octet_length(CAST(revision AS TEXT)) BETWEEN 0 AND 128) AND "
        "(pg_typeof(phase) IN ('text'::regtype, 'character varying'::regtype) "
        "AND phase IS NOT NULL AND octet_length(CAST(phase AS TEXT)) BETWEEN 0 "
        "AND 256) THEN 0 ELSE 1 END = 1\n    LIMIT 1\n) THEN 1 ELSE 0 END AS "
        "invalid_key_exists;\n"
    ),
    ("all", "postgresql", "H02_misplaced_ledger_namespace"): (
        "SELECT CASE WHEN EXISTS (\n    SELECT 1 FROM migration_progress\n    "
        "WHERE revision COLLATE \"C\" <> 'ar_0007_ledger'\n      AND (phase COLLATE "
        '"C" = \'ledger_opening\' OR substr(phase, 1, 16) COLLATE "C" = '
        "'ledger_manifest_')\n    LIMIT 1\n) THEN 1 ELSE 0 END AS "
        "misplaced_exists;\n"
    ),
    ("all", "postgresql", "H10_adoption_gate"): "".join(
        (
            _SQLITE_ALL_H10_ADOPTION_CANDIDATES,
            _POSTGRESQL_ALL_H10_ADOPTION_ROW_CHECKS,
            _POSTGRESQL_ALL_H10_ADOPTION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "postgresql", "H10_adoption_body"): "".join(
        (
            _SQLITE_ALL_H10_ADOPTION_CANDIDATES,
            _POSTGRESQL_ALL_H10_ADOPTION_ROW_CHECKS,
            _POSTGRESQL_ALL_H10_ADOPTION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "installation_key" ELSE NULL END '
                'AS "installation_key",\n       CASE WHEN c.row_ok = 1 THEN '
                '"singleton" ELSE NULL END AS "singleton",\n       CASE WHEN c.row_ok '
                '= 1 THEN "source_kind" ELSE NULL END AS "source_kind",\n       CASE '
                'WHEN c.row_ok = 1 THEN "source_baseline" ELSE NULL END AS '
                '"source_baseline",\n       CASE WHEN c.row_ok = 1 THEN '
                '"schema_fingerprint" ELSE NULL END AS "schema_fingerprint",\n       '
                'CASE WHEN c.row_ok = 1 THEN "installed_schema_fingerprint" ELSE '
                'NULL END AS "installed_schema_fingerprint",\n       CASE WHEN '
                'c.row_ok = 1 THEN "organization_id" ELSE NULL END AS '
                '"organization_id",\n       CASE WHEN c.row_ok = 1 THEN "project_id" '
                'ELSE NULL END AS "project_id",\n       CASE WHEN c.row_ok = 1 THEN '
                '"mapping_digest" ELSE NULL END AS "mapping_digest",\n       CASE '
                "WHEN c.row_ok = 1 THEN CAST(mapping AS TEXT) ELSE NULL END AS "
                '"mapping",\n       CASE WHEN c.row_ok = 1 THEN '
                '"backup_evidence_digest" ELSE NULL END AS "backup_evidence_digest",\n'
                '       CASE WHEN c.row_ok = 1 THEN "drain_evidence_digest" ELSE '
                'NULL END AS "drain_evidence_digest",\n       CASE WHEN c.row_ok = 1 '
                "THEN to_char(created_at AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') ELSE NULL END AS "created_at",\n    '
                '   CASE WHEN c.row_ok = 1 THEN "state" ELSE NULL END AS "state"\n'
                "FROM checked AS c CROSS JOIN summary AS s\nWHERE s.candidate_rows = "
                "1\n  AND s.invalid_rows = 0\n  AND s.native_bytes BETWEEN 1 AND "
                "1114625\n  AND s.utf8_bytes BETWEEN 1 AND 4458500\n  AND "
                "s.candidate_rows = :expected_rows\n  AND s.native_bytes = "
                ":expected_native_bytes\n  AND s.utf8_bytes = :expected_utf8_bytes\n"
                "LIMIT 2;\n"
            ),
        )
    ),
    ("all", "postgresql", "H20_ownership_gate"): "".join(
        (
            _POSTGRESQL_ALL_H20_OWNERSHIP_CANDIDATES,
            _POSTGRESQL_ALL_H20_OWNERSHIP_ROW_CHECKS,
            _POSTGRESQL_ALL_H20_OWNERSHIP_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "postgresql", "H20_ownership_body"): "".join(
        (
            _POSTGRESQL_ALL_H20_OWNERSHIP_CANDIDATES,
            _POSTGRESQL_ALL_H20_OWNERSHIP_ROW_CHECKS,
            _POSTGRESQL_ALL_H20_OWNERSHIP_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "source_digest" ELSE NULL END AS '
                '"source_digest",\n       CASE WHEN c.row_ok = 1 THEN CAST(cursor AS '
                'TEXT) ELSE NULL END AS "cursor",\n       CASE WHEN c.row_ok = 1 THEN '
                '"rows_verified" ELSE NULL END AS "rows_verified",\n       CASE WHEN '
                'c.row_ok = 1 THEN "status" ELSE NULL END AS "status",\n       CASE '
                "WHEN c.row_ok = 1 THEN to_char(updated_at AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') ELSE NULL END AS "updated_at"\nFROM '
                "checked AS c CROSS JOIN summary AS s\nWHERE s.candidate_rows = 1\n  "
                "AND s.invalid_rows = 0\n  AND s.native_bytes BETWEEN 1 AND 131150\n  "
                "AND s.utf8_bytes BETWEEN 1 AND 524600\n  AND s.candidate_rows = "
                ":expected_rows\n  AND s.native_bytes = :expected_native_bytes\n  AND "
                "s.utf8_bytes = :expected_utf8_bytes\nLIMIT 2;\n"
            ),
        )
    ),
    ("all", "postgresql", "H30_projection_gate"): "".join(
        (
            _POSTGRESQL_ALL_H30_PROJECTION_CANDIDATES,
            _POSTGRESQL_ALL_H30_PROJECTION_ROW_CHECKS,
            _POSTGRESQL_ALL_H30_PROJECTION_CHECKED,
            _SQLITE_ALL_H30_PROJECTION_SUMMARY,
            _SQLITE_ALL_H30_PROJECTION_PROJECTION,
        )
    ),
    ("all", "postgresql", "H30_projection_body"): "".join(
        (
            _POSTGRESQL_ALL_H30_PROJECTION_CANDIDATES,
            _POSTGRESQL_ALL_H30_PROJECTION_ROW_CHECKS,
            _POSTGRESQL_ALL_H30_PROJECTION_CHECKED,
            _SQLITE_ALL_H30_PROJECTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "source_digest" ELSE NULL END AS '
                '"source_digest",\n       CASE WHEN c.row_ok = 1 THEN CAST(cursor AS '
                'TEXT) ELSE NULL END AS "cursor",\n       CASE WHEN c.row_ok = 1 THEN '
                '"rows_verified" ELSE NULL END AS "rows_verified",\n       CASE WHEN '
                'c.row_ok = 1 THEN "status" ELSE NULL END AS "status",\n       CASE '
                "WHEN c.row_ok = 1 THEN to_char(updated_at AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') ELSE NULL END AS "updated_at"\nFROM '
                "checked AS c CROSS JOIN summary AS s\nWHERE s.candidate_rows = 1\n  "
                "AND s.invalid_rows = 0\n  AND s.native_bytes BETWEEN 1 AND 66560\n  "
                "AND s.utf8_bytes BETWEEN 1 AND 266240\n  AND s.candidate_rows = "
                ":expected_rows\n  AND s.native_bytes = :expected_native_bytes\n  AND "
                "s.utf8_bytes = :expected_utf8_bytes\nLIMIT 2;\n"
            ),
        )
    ),
    ("all", "postgresql", "H40_organization_gate"): "".join(
        (
            _SQLITE_ALL_H40_ORGANIZATION_CANDIDATES,
            _POSTGRESQL_ALL_H40_ORGANIZATION_ROW_CHECKS,
            _POSTGRESQL_ALL_H40_ORGANIZATION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "postgresql", "H40_organization_body"): "".join(
        (
            _SQLITE_ALL_H40_ORGANIZATION_CANDIDATES,
            _POSTGRESQL_ALL_H40_ORGANIZATION_ROW_CHECKS,
            _POSTGRESQL_ALL_H40_ORGANIZATION_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                "SELECT CASE WHEN c.row_ok = 1 THEN to_char(created_at AT TIME ZONE "
                "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') ELSE NULL END AS "
                '"created_at"\nFROM checked AS c CROSS JOIN summary AS s\nWHERE '
                "s.candidate_rows = 1\n  AND s.invalid_rows = 0\n  AND s.native_bytes "
                "BETWEEN 1 AND 65536\n  AND s.utf8_bytes BETWEEN 1 AND 262144\n  AND "
                "s.candidate_rows = :expected_rows\n  AND s.native_bytes = "
                ":expected_native_bytes\n  AND s.utf8_bytes = :expected_utf8_bytes\n"
                "LIMIT 2;\n"
            ),
        )
    ),
    ("all", "postgresql", "H50_seed_project_gate"): "".join(
        (
            _SQLITE_ALL_H50_SEED_PROJECT_CANDIDATES,
            _POSTGRESQL_ALL_H50_SEED_PROJECT_ROW_CHECKS,
            _POSTGRESQL_ALL_H50_SEED_PROJECT_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            _SQLITE_ALL_H10_ADOPTION_PROJECTION,
        )
    ),
    ("all", "postgresql", "H50_seed_project_body"): "".join(
        (
            _SQLITE_ALL_H50_SEED_PROJECT_CANDIDATES,
            _POSTGRESQL_ALL_H50_SEED_PROJECT_ROW_CHECKS,
            _POSTGRESQL_ALL_H50_SEED_PROJECT_CHECKED,
            _SQLITE_ALL_H10_ADOPTION_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "name" ELSE NULL END AS "name",\n '
                "      CASE WHEN c.row_ok = 1 THEN to_char(created_at AT TIME ZONE "
                "'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') ELSE NULL END AS "
                '"created_at"\nFROM checked AS c CROSS JOIN summary AS s\nWHERE '
                "s.candidate_rows = 1\n  AND s.invalid_rows = 0\n  AND s.native_bytes "
                "BETWEEN 1 AND 66016\n  AND s.utf8_bytes BETWEEN 1 AND 264064\n  AND "
                "s.candidate_rows = :expected_rows\n  AND s.native_bytes = "
                ":expected_native_bytes\n  AND s.utf8_bytes = :expected_utf8_bytes\n"
                "LIMIT 2;\n"
            ),
        )
    ),
    ("all", "postgresql", "H60_ledger_progress_gate"): "".join(
        (
            _POSTGRESQL_ALL_H60_LEDGER_PROGRESS_CANDIDATES,
            _POSTGRESQL_ALL_H60_LEDGER_PROGRESS_ROW_CHECKS,
            _POSTGRESQL_ALL_H60_LEDGER_PROGRESS_CHECKED,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_SUMMARY,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_PROJECTION,
        )
    ),
    ("all", "postgresql", "H60_ledger_progress_body"): "".join(
        (
            _POSTGRESQL_ALL_H60_LEDGER_PROGRESS_CANDIDATES,
            _POSTGRESQL_ALL_H60_LEDGER_PROGRESS_ROW_CHECKS,
            _POSTGRESQL_ALL_H60_LEDGER_PROGRESS_CHECKED,
            _SQLITE_ALL_H60_LEDGER_PROGRESS_SUMMARY,
            (
                'SELECT CASE WHEN c.row_ok = 1 THEN "revision" ELSE NULL END AS '
                '"revision",\n       CASE WHEN c.row_ok = 1 THEN "phase" ELSE NULL '
                'END AS "phase",\n       CASE WHEN c.row_ok = 1 THEN "source_digest" '
                'ELSE NULL END AS "source_digest",\n       CASE WHEN c.row_ok = 1 '
                'THEN CAST(cursor AS TEXT) ELSE NULL END AS "cursor",\n       CASE '
                'WHEN c.row_ok = 1 THEN "rows_verified" ELSE NULL END AS '
                '"rows_verified",\n       CASE WHEN c.row_ok = 1 THEN "status" ELSE '
                'NULL END AS "status",\n       CASE WHEN c.row_ok = 1 THEN '
                "to_char(updated_at AT TIME ZONE 'UTC', "
                '\'YYYY-MM-DD"T"HH24:MI:SS.US"Z"\') ELSE NULL END AS "updated_at"\nFROM '
                "checked AS c CROSS JOIN summary AS s\nWHERE s.candidate_rows BETWEEN "
                "2 AND 257\n  AND s.invalid_rows = 0\n  AND s.opening_rows = 1\n  AND "
                "s.manifest_rows BETWEEN 1 AND 256\n  AND s.cursor_bytes BETWEEN 1 "
                "AND 16777216\n  AND s.metadata_bytes BETWEEN 1 AND 41891\n  AND "
                "s.native_bytes BETWEEN 1 AND 16819107\n  AND s.utf8_bytes BETWEEN 1 "
                "AND 67276428\n  AND s.candidate_rows = :expected_rows\n  AND "
                "s.native_bytes = :expected_native_bytes\n  AND s.utf8_bytes = "
                ":expected_utf8_bytes\n  AND s.cursor_bytes = :expected_cursor_bytes\n"
                "ORDER BY c.phase\nLIMIT 258;\n"
            ),
        )
    ),
}
