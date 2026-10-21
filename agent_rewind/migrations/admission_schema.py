"""Additive C04 admission identities; no admission, recovery or worker activation.

The caller owns migration exclusion and the transaction. Config digests are
content identities, not artifact IDs: the bounded repository must separately
verify the same-project job/admission_config reference and full descriptor.
Historical v1 NULL configurations are retained; every new writer requires a
verified configuration, including a future v1 writer.
"""

from sqlalchemy.engine import Connection

from .schema import dialect


def create_admission_schema(connection: Connection) -> None:
    postgres = dialect(connection) == "postgresql"
    timestamp = "TIMESTAMP WITH TIME ZONE" if postgres else "DATETIME"

    def hexadecimal(field: str, size: int) -> str:
        if postgres:
            return f"{field} ~ '^[0-9a-f]{{{size}}}$'"
        return (
            f"typeof({field})='text' AND length({field})={size} "
            f"AND length(CAST({field} AS BLOB))={size} AND {field} NOT GLOB '*[^0-9a-f]*'"
        )

    principal = (
        "principal_id ~ '^(oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})$'"
        if postgres
        else "typeof(principal_id)='text' AND ("
        "(substr(principal_id,1,5)='oidc:' AND length(principal_id)=69 "
        "AND length(CAST(principal_id AS BLOB))=69 "
        "AND substr(principal_id,6) NOT GLOB '*[^0-9a-f]*') OR "
        "(substr(principal_id,1,8)='api-key:' AND length(principal_id)=40 "
        "AND length(CAST(principal_id AS BLOB))=40 "
        "AND substr(principal_id,9) NOT GLOB '*[^0-9a-f]*'))"
    )
    version = "payload_version IN (1,2)"
    operation_version = "payload_version=2"
    if not postgres:
        version += " AND typeof(payload_version)='integer'"
        operation_version += " AND typeof(payload_version)='integer'"
    connection.exec_driver_sql(
        f"ALTER TABLE jobs ADD COLUMN payload_version INTEGER NOT NULL DEFAULT 1 CHECK({version})"
    )
    connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN execution_config_ref VARCHAR(64)")
    connection.exec_driver_sql(f"""ALTER TABLE jobs
        ADD COLUMN execution_config_digest VARCHAR(64) CHECK(
          (payload_version=1 AND execution_config_ref IS NULL
            AND execution_config_digest IS NULL)
          OR (execution_config_ref IS NOT NULL AND execution_config_digest IS NOT NULL
            AND {hexadecimal("execution_config_ref", 64)}
            AND {hexadecimal("execution_config_digest", 64)}
            AND execution_config_ref=execution_config_digest))""")
    # Canonical TEXT encodes the exact frozen two-ID Accepted object. It is not a
    # new response shape, and its values cannot disagree with the owning row.
    accepted = """accepted_response='{"job_id":"' || job_id || '","operation_id":"' || id || '"}'"""
    connection.exec_driver_sql(f"""CREATE TABLE operations (
        id VARCHAR(32) NOT NULL PRIMARY KEY CHECK({hexadecimal("id", 32)}),
        project_id VARCHAR(32) NOT NULL CHECK({hexadecimal("project_id", 32)}),
        principal_id VARCHAR(256) NOT NULL CHECK({principal}),
        kind VARCHAR(20) NOT NULL CHECK(kind='run'),
        client_operation_id VARCHAR(32) NOT NULL
          CHECK({hexadecimal("client_operation_id", 32)}),
        request_digest VARCHAR(64) NOT NULL CHECK({hexadecimal("request_digest", 64)}),
        job_id VARCHAR(32) NOT NULL UNIQUE CHECK({hexadecimal("job_id", 32)}),
        accepted_response TEXT NOT NULL CHECK({accepted}),
        created_at {timestamp} NOT NULL,
        retain_until {timestamp} NOT NULL CHECK(retain_until>=created_at),
        job_resource_kind VARCHAR(20) NOT NULL CHECK(job_resource_kind='job'),
        execution_config_digest VARCHAR(64) NOT NULL
          CHECK({hexadecimal("execution_config_digest", 64)}),
        payload_version INTEGER NOT NULL CHECK({operation_version}),
        failure_correlation_id VARCHAR(32)
          CHECK(failure_correlation_id IS NULL OR ({hexadecimal("failure_correlation_id", 32)})),
        UNIQUE(project_id,principal_id,kind,client_operation_id),
        UNIQUE(project_id,principal_id,kind,id),
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        FOREIGN KEY(project_id,job_resource_kind,job_id)
          REFERENCES resource_scopes(project_id,resource_kind,resource_id)
    )""")
    # No membership FK: revocation must not destroy retained admission history.
    # Alias request_digest equality is an additional repository check, not a
    # property of the composite owner FK below.
    connection.exec_driver_sql(f"""CREATE TABLE operation_keys (
        project_id VARCHAR(32) NOT NULL CHECK({hexadecimal("project_id", 32)}),
        principal_id VARCHAR(256) NOT NULL CHECK({principal}),
        kind VARCHAR(20) NOT NULL CHECK(kind='run'),
        key_hash VARCHAR(64) NOT NULL CHECK({hexadecimal("key_hash", 64)}),
        operation_id VARCHAR(32) NOT NULL CHECK({hexadecimal("operation_id", 32)}),
        request_digest VARCHAR(64) NOT NULL CHECK({hexadecimal("request_digest", 64)}),
        PRIMARY KEY(project_id,principal_id,kind,key_hash),
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(project_id,principal_id,kind,operation_id)
          REFERENCES operations(project_id,principal_id,kind,id)
    )""")
