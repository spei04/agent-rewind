"""Additive provenance only; real ownership is a later revision."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from .schema import dialect


def create_adoption_metadata(connection: Connection) -> None:
    postgres = dialect(connection) == "postgresql"
    timestamp = "TIMESTAMP WITH TIME ZONE" if postgres else "DATETIME"
    mapping_size = "octet_length(mapping::text)" if postgres else "length(CAST(mapping AS BLOB))"

    def hexadecimal(column: str, size: int) -> str:
        if postgres:
            return f"{column} ~ '^[0-9a-f]{{{size}}}$'"
        return f"length({column}) = {size} AND {column} NOT GLOB '*[^0-9a-f]*'"

    checks = [
        "CHECK(singleton = 1)",
        "CHECK(length(installation_key) BETWEEN 1 AND 64)",
        "CHECK(source_kind IN ('fresh','legacy'))",
        "CHECK(state IN ('prepared','ownership_complete'))",
        f"CHECK({mapping_size} <= 1048576)",
        "CHECK((source_kind='fresh' AND state='prepared' AND organization_id IS NULL "
        "AND project_id IS NULL) OR (organization_id IS NOT NULL AND project_id IS NOT NULL))",
        "CHECK((source_kind='fresh' AND backup_evidence_digest IS NULL "
        "AND drain_evidence_digest IS NULL) OR (source_kind='legacy' "
        "AND backup_evidence_digest IS NOT NULL AND drain_evidence_digest IS NOT NULL))",
    ]
    for column, size in [
        ("source_baseline", 40),
        ("schema_fingerprint", 64),
        ("installed_schema_fingerprint", 64),
        ("mapping_digest", 64),
        ("organization_id", 32),
        ("project_id", 32),
        ("backup_evidence_digest", 64),
        ("drain_evidence_digest", 64),
    ]:
        checks.append("CHECK(" + hexadecimal(column, size) + ")")
    connection.exec_driver_sql(f"""CREATE TABLE installation_adoptions (
        installation_key VARCHAR(64) NOT NULL PRIMARY KEY,
        singleton INTEGER NOT NULL UNIQUE,
        source_kind VARCHAR(16) NOT NULL,
        source_baseline VARCHAR(40) NOT NULL,
        schema_fingerprint VARCHAR(64) NOT NULL,
        installed_schema_fingerprint VARCHAR(64) NOT NULL,
        organization_id VARCHAR(32), project_id VARCHAR(32),
        mapping_digest VARCHAR(64) NOT NULL, mapping JSON NOT NULL,
        backup_evidence_digest VARCHAR(64), drain_evidence_digest VARCHAR(64),
        created_at {timestamp} NOT NULL, state VARCHAR(32) NOT NULL,
        {",".join(checks)}
    )""")
    cursor_size = "octet_length(cursor::text)" if postgres else "length(CAST(cursor AS BLOB))"
    connection.exec_driver_sql(f"""CREATE TABLE migration_progress (
        revision VARCHAR(32) NOT NULL, phase VARCHAR(64) NOT NULL,
        source_digest VARCHAR(64) NOT NULL, cursor JSON NOT NULL,
        rows_verified BIGINT NOT NULL CHECK(rows_verified >= 0),
        status VARCHAR(16) NOT NULL CHECK(status IN ('pending','running','complete','blocked')),
        updated_at {timestamp} NOT NULL, PRIMARY KEY(revision,phase),
        CHECK({hexadecimal("source_digest", 64)}),
        CHECK({cursor_size} <= 65536)
    )""")
