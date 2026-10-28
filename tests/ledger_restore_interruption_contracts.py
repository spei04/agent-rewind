"""Fixed SQL and wire contracts for one observed COPY cancellation."""

COPY = b"COPY public.api_keys (id, hash, role, name, expires, revoked) FROM stdin;\n"
PROFILE = ("pg-dump-version", "pg-restore-version", "dump", "schema-restore", "data-restore")
COLUMNS = ("id", "hash", "role", "name", "expires", "revoked")
MAX_QUERIES, MAX_OBSERVATIONS, MAX_EVENTS = 270, 128, 1024
MAX_TRANSCRIPT, MAX_RESULT, MAX_CELL = 1048576, 16384, 4096

IDENTITY = """
SELECT pg_backend_pid()::text AS pid,a.backend_start::text AS started,
       current_database() AS database,current_user AS username,
       current_setting('application_name') AS application,
       current_setting('statement_timeout') AS statement_timeout,
       current_setting('lock_timeout') AS lock_timeout,
       current_setting('server_version_num') AS server_version,
       (a.client_addr IS NULL)::text AS local
FROM pg_stat_activity a WHERE a.pid=pg_backend_pid()
"""
CANDIDATES = """
SELECT a.pid::text AS pid,a.backend_start::text AS started,
 a.query_start::text AS query_started,a.datid::text AS database_oid,
 a.usename AS username,a.application_name AS application,
 a.backend_type AS backend_type,(a.client_addr IS NULL)::text AS local,
 a.state,a.wait_event_type AS wait_type,a.query,
 (a.backend_start >= $4::timestamptz)::text AS recent,
 (a.state='active' AND a.wait_event_type='Lock' AND a.query=$7
  AND a.application_name=$6 AND a.usename='postgres'
  AND a.backend_type='client backend' AND a.client_addr IS NULL
  AND a.backend_start >= $4::timestamptz
  AND pg_blocking_pids(a.pid)=ARRAY[$2::int]
  AND EXISTS(SELECT 1 FROM pg_locks l WHERE l.pid=a.pid
    AND l.database=$1::oid AND l.relation=$5::oid AND l.locktype='relation'
    AND l.mode='RowExclusiveLock' AND NOT l.granted)
  AND EXISTS(SELECT 1 FROM pg_stat_activity b JOIN pg_locks l ON l.pid=b.pid
    WHERE b.pid=$2::int AND b.backend_start=$3::timestamptz
      AND b.datid=$1::oid AND l.database=$1::oid AND l.relation=$5::oid
      AND l.locktype='relation' AND l.mode='AccessExclusiveLock' AND l.granted)
 )::text AS eligible
FROM pg_stat_activity a WHERE a.datid=$1::oid AND a.pid<>$2::int
"""
SQL = {
    "identity": IDENTITY,
    "blocker-info": """
SELECT (SELECT oid::text FROM pg_database WHERE datname=current_database()) AS database_oid,
 'public.api_keys'::regclass::oid::text AS relation_oid
""",
    "begin": "BEGIN",
    "lock": "LOCK TABLE public.api_keys IN ACCESS EXCLUSIVE MODE",
    "rollback": "ROLLBACK",
    "prelaunch": """
SELECT clock_timestamp()::text AS marked,
 (SELECT count(*)::text FROM pg_stat_activity WHERE datid=$1::oid) AS clients,
 EXISTS(SELECT 1 FROM pg_stat_activity b JOIN pg_locks l ON l.pid=b.pid
 WHERE b.pid=$2::int AND b.backend_start=$3::timestamptz
 AND b.datid=$1::oid AND b.state='idle in transaction'
 AND l.database=$1::oid AND l.relation=$4::oid AND l.locktype='relation'
 AND l.mode='AccessExclusiveLock' AND l.granted)::text AS held,
 (SELECT count(*)::text FROM pg_stat_activity WHERE application_name=$5) AS restores
""",
    "candidate": CANDIDATES + " ORDER BY a.pid LIMIT 2",
    "cancel": """
WITH candidates AS MATERIALIZED (
"""
    + CANDIDATES
    + " ORDER BY a.pid LIMIT 2"
    + """
)
SELECT count(*)::text AS candidates,
 CASE WHEN count(*)=1 AND bool_and(eligible='true')
 AND min(pid)=$8 AND min(started)=$9 AND min(query_started)=$10
 AND clock_timestamp() < $4::timestamptz + interval '5 seconds'
 THEN pg_cancel_backend(min(pid)::int)::text ELSE NULL END AS cancelled
FROM candidates
""",
    "restore-absence": """
SELECT count(*)::text AS remaining FROM pg_stat_activity
WHERE application_name=$1 OR (pid=$2::int AND backend_start=$3::timestamptz)
""",
    "blocker-absence": """
SELECT count(*)::text AS remaining FROM pg_stat_activity
WHERE application_name=$1 OR (pid=$2::int AND backend_start=$3::timestamptz)
""",
    "final-absence": """
SELECT
 (SELECT count(*)::text FROM pg_stat_activity WHERE
  pid<>pg_backend_pid() AND
  ((pid=$1::int AND backend_start=$2::timestamptz) OR application_name=$3)) AS control,
 (SELECT count(*)::text FROM pg_stat_activity WHERE
  application_name=$4) AS restores,
 (SELECT count(*)::text FROM pg_stat_activity WHERE datid=$5::oid) AS targets,
 pg_backend_pid()::text AS observer
""",
}
FIELDS = {
    "identity": (
        "pid",
        "started",
        "database",
        "username",
        "application",
        "statement_timeout",
        "lock_timeout",
        "server_version",
        "local",
    ),
    "blocker-info": ("database_oid", "relation_oid"),
    "prelaunch": ("marked", "clients", "held", "restores"),
    "candidate": (
        "pid",
        "started",
        "query_started",
        "database_oid",
        "username",
        "application",
        "backend_type",
        "local",
        "state",
        "wait_type",
        "query",
        "recent",
        "eligible",
    ),
    "cancel": ("candidates", "cancelled"),
    "restore-absence": ("remaining",),
    "blocker-absence": ("remaining",),
    "final-absence": ("control", "restores", "targets", "observer"),
    "begin": (),
    "lock": (),
    "rollback": (),
}
PARAMETERS = {name: 0 for name in SQL}
PARAMETERS.update(prelaunch=5, candidate=7, cancel=10)
PARAMETERS.update({"restore-absence": 3, "blocker-absence": 3, "final-absence": 5})
COMMANDS = {"begin": b"BEGIN", "lock": b"LOCK TABLE", "rollback": b"ROLLBACK"}


def positive(value):
    assert type(value) is bytes and value.isdigit() and not value.startswith(b"0")
    parsed = int(value)
    assert 0 < parsed < 2**31
    return parsed


def one(rows):
    assert type(rows) is list and len(rows) == 1, "expected one exact control row"
    return rows[0]
