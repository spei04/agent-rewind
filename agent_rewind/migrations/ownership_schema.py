"""Frozen additive C05 ownership DDL, independent from runtime ORM metadata."""

from sqlalchemy.engine import Connection

from .schema import dialect


def create_ownership_schema(connection: Connection) -> None:
    timestamp = "TIMESTAMP WITH TIME ZONE" if dialect(connection) == "postgresql" else "DATETIME"

    def identifier(field: str) -> str:
        if dialect(connection) == "postgresql":
            return f"{field} ~ '^[0-9a-f]{{32}}$'"
        return f"length({field}) = 32 AND {field} NOT GLOB '*[^0-9a-f]*'"

    principal = (
        "principal_id ~ '^(oidc:[0-9a-f]{64}|api-key:[0-9a-f]{32})$'"
        if dialect(connection) == "postgresql"
        else "(substr(principal_id,1,5)='oidc:' AND length(principal_id)=69 "
        "AND substr(principal_id,6) NOT GLOB '*[^0-9a-f]*') OR "
        "(substr(principal_id,1,8)='api-key:' AND length(principal_id)=40 "
        "AND substr(principal_id,9) NOT GLOB '*[^0-9a-f]*')"
    )
    connection.exec_driver_sql(f"""CREATE TABLE organizations (
        id VARCHAR(32) NOT NULL PRIMARY KEY CHECK({identifier("id")}),
        installation_key VARCHAR(64) NOT NULL UNIQUE,
        created_at {timestamp} NOT NULL,
        FOREIGN KEY(installation_key) REFERENCES installation_adoptions(installation_key)
    )""")
    connection.exec_driver_sql(f"""CREATE TABLE projects (
        id VARCHAR(32) NOT NULL PRIMARY KEY CHECK({identifier("id")}),
        organization_id VARCHAR(32) NOT NULL,
        name VARCHAR(120) NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
        created_at {timestamp} NOT NULL,
        UNIQUE(organization_id,id),
        FOREIGN KEY(organization_id) REFERENCES organizations(id)
    )""")
    connection.exec_driver_sql(f"""CREATE TABLE project_memberships (
        project_id VARCHAR(32) NOT NULL,
        principal_id VARCHAR(256) NOT NULL CHECK({principal}),
        role VARCHAR(16) NOT NULL CHECK(role IN ('viewer','operator','maintainer')),
        revoked_at {timestamp},
        legacy_default BOOLEAN NOT NULL DEFAULT false CHECK(legacy_default IN (false,true)),
        PRIMARY KEY(project_id,principal_id),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    )""")
    connection.exec_driver_sql("""CREATE UNIQUE INDEX membership_active_legacy_default
        ON project_memberships(principal_id) WHERE legacy_default = true AND revoked_at IS NULL""")
    connection.exec_driver_sql(f"""CREATE TABLE resource_scopes (
        resource_kind VARCHAR(20) NOT NULL
            CHECK(resource_kind IN ('run','study','job','key','provider_call')),
        resource_id VARCHAR(32) NOT NULL CHECK({identifier("resource_id")}),
        project_id VARCHAR(32) NOT NULL,
        PRIMARY KEY(resource_kind,resource_id),
        UNIQUE(project_id,resource_kind,resource_id),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    )""")
