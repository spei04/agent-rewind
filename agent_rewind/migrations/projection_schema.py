"""Additive C04 query projection DDL; no backfill or customer activation."""

from sqlalchemy.engine import Connection

from .schema import dialect


def create_projection_schema(connection: Connection) -> None:
    postgres = dialect(connection) == "postgresql"
    timestamp = "TIMESTAMP WITH TIME ZONE" if postgres else "DATETIME"

    def hexadecimal(field: str, size: int) -> str:
        if postgres:
            return f"{field} ~ '^[0-9a-f]{{{size}}}$'"
        return (
            f"typeof({field})='text' AND length({field})={size} "
            f"AND length(CAST({field} AS BLOB))={size} AND {field} NOT GLOB '*[^0-9a-f]*'"
        )

    counter = "run_sequence>=0"
    sequence = "published_seq>0"
    boolean = "branchable IN (false,true)"
    if not postgres:
        counter += " AND typeof(run_sequence)='integer'"
        sequence += " AND typeof(published_seq)='integer'"
        boolean += " AND typeof(branchable)='integer'"
    connection.exec_driver_sql(
        f"ALTER TABLE projects ADD COLUMN run_sequence BIGINT NOT NULL DEFAULT 0 CHECK({counter})"
    )
    statuses = " OR ".join(
        f"status='{value}'" for value in ("running", "complete", "failed", "incomplete")
    )
    connection.exec_driver_sql(f"""CREATE TABLE run_index (
        run_id VARCHAR(32) NOT NULL PRIMARY KEY CHECK({hexadecimal("run_id", 32)}),
        project_id VARCHAR(32) NOT NULL CHECK({hexadecimal("project_id", 32)}),
        resource_kind VARCHAR(20) NOT NULL DEFAULT 'run' CHECK(resource_kind='run'),
        created_at {timestamp} NOT NULL,
        status VARCHAR(16) NOT NULL CHECK({statuses}),
        branchable BOOLEAN NOT NULL CHECK({boolean}),
        parent_id VARCHAR(32) CHECK(parent_id IS NULL OR ({hexadecimal("parent_id", 32)})),
        event_head VARCHAR(64) CHECK(event_head IS NULL OR ({hexadecimal("event_head", 64)})),
        published_seq BIGINT NOT NULL CHECK({sequence}),
        projection_reason VARCHAR(32),
        UNIQUE(project_id,run_id),
        UNIQUE(project_id,published_seq),
        FOREIGN KEY(run_id) REFERENCES records(id),
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(project_id,resource_kind,run_id)
          REFERENCES resource_scopes(project_id,resource_kind,resource_id),
        FOREIGN KEY(project_id,parent_id) REFERENCES run_index(project_id,run_id),
        CHECK(branchable=false OR status='complete'),
        CHECK(projection_reason IS NULL OR projection_reason='unfenced_execution')
    )""")
    # Hold the project counter lock through insertion/commit in the caller. This
    # index provides tuple ordering, not commit-order publication by itself.
    connection.exec_driver_sql("""CREATE INDEX run_index_project_created_run
        ON run_index(project_id,created_at DESC,run_id DESC)""")
