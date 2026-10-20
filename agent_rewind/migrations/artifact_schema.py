"""Additive C04 object/reference schema; no publication or legacy data inference."""

from sqlalchemy.engine import Connection

from .schema import dialect


def create_artifact_schema(connection: Connection) -> None:
    postgres = dialect(connection) == "postgresql"
    timestamp = "TIMESTAMP WITH TIME ZONE" if postgres else "DATETIME"

    def hexadecimal(field: str, size: int) -> str:
        if postgres:
            return f"{field} ~ '^[0-9a-f]{{{size}}}$'"
        return f"length({field})={size} AND {field} NOT GLOB '*[^0-9a-f]*'"

    connection.exec_driver_sql(f"""CREATE TABLE artifact_objects (
        id VARCHAR(32) NOT NULL PRIMARY KEY CHECK({hexadecimal("id", 32)}),
        project_id VARCHAR(32) NOT NULL,
        digest VARCHAR(64) NOT NULL CHECK({hexadecimal("digest", 64)}),
        locator VARCHAR(1024) NOT NULL CHECK(length(locator) BETWEEN 1 AND 1024),
        format_version INTEGER NOT NULL CHECK(format_version=1),
        byte_count BIGINT NOT NULL CHECK(byte_count>=0),
        created_at {timestamp} NOT NULL,
        UNIQUE(project_id,digest,format_version), UNIQUE(project_id,id),
        FOREIGN KEY(project_id) REFERENCES projects(id),
        CHECK(locator='objects/' || digest
          OR locator='objects/' || project_id || '/v1/' || digest)
    )""")
    # Equality disjunctions avoid adding new PostgreSQL enum deparse variants.
    roles = (
        "payload",
        "admission_config",
        "task",
        "event",
        "checkpoint",
        "workspace",
        "file_blob",
        "evaluation",
        "result",
        "study_attachment",
        "budget_evidence",
    )
    role_check = " OR ".join(f"role='{role}'" for role in roles)
    kind_check = " OR ".join(
        f"owner_kind='{kind}'" for kind in ("run", "study", "job", "provider_call")
    )
    connection.exec_driver_sql(f"""CREATE TABLE artifact_refs (
        project_id VARCHAR(32) NOT NULL,
        owner_kind VARCHAR(20) NOT NULL CHECK({kind_check}),
        owner_id VARCHAR(32) NOT NULL,
        artifact_id VARCHAR(32) NOT NULL,
        role VARCHAR(32) NOT NULL CHECK({role_check}),
        PRIMARY KEY(project_id,owner_kind,owner_id,artifact_id,role),
        FOREIGN KEY(project_id,artifact_id) REFERENCES artifact_objects(project_id,id),
        FOREIGN KEY(project_id,owner_kind,owner_id)
          REFERENCES resource_scopes(project_id,resource_kind,resource_id),
        CHECK(role<>'budget_evidence' OR owner_kind='provider_call')
    )""")
