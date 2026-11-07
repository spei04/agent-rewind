"""Owned PostgreSQL cases for the explicitly admitted F4 native sequence.

The parent supplies exact case identities and absolute deadlines. This fixture
does not create an allowance, retry CREATE, or spend the parent's cleanup reserve.
Its bounded journal lets that same parent reconcile a terminated child's case.
"""

import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from postgres_control import observe_exclusion_failure, wait_for_database_drain
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from agent_rewind.migrations import service
from scripts.ci_postgres import IMAGE

_MAX_MANIFEST = 128 * 1024
_MAX_RECORD = 16 * 1024
_MAX_CASES = 64
_MAX_EVENTS = 64
_ROLE_FIELDS = (
    "oid",
    "rolname",
    "rolsuper",
    "rolinherit",
    "rolcreaterole",
    "rolcreatedb",
    "rolcanlogin",
    "rolreplication",
    "rolbypassrls",
    "rolconnlimit",
    "rolvaliduntil",
)
_DATABASE_FIELDS = ("oid", "datname", "owner", "datallowconn", "datconnlimit", "datistemplate")


def _require(value, reason):
    if not value:
        raise AssertionError(reason)


def _private(path, *, directory=False):
    info = path.lstat()
    expected = 0o700 if directory else 0o600
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    _require(kind and info.st_uid == os.getuid(), "F4 record ownership mismatch")
    _require(stat.S_IMODE(info.st_mode) == expected, "F4 record mode mismatch")


def _read(path, bound):
    _private(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags), "rb") as stream:
        raw = stream.read(bound + 1)
    _require(len(raw) <= bound, "F4 record exceeds its bound")
    return raw


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "Duplicate F4 record key")
        value[key] = item
    return value


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_unique_pairs)


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value)


def _identity(pid):
    _require(type(pid) is int and pid > 0, "Invalid F4 parent PID")
    raw = (Path("/proc") / str(pid) / "stat").read_text()
    fields = raw.rsplit(")", 1)[1].split()
    return {
        "pid": pid,
        "start_ticks": int(fields[19]),
        "pgid": int(fields[2]),
        "sid": int(fields[3]),
    }


@dataclass(frozen=True)
class CaseControl:
    manifest_sha256: str
    group_id: str
    source_sha256: str  # SHA256 of the complete source-map JSON bytes.
    source_commit: str
    source_tree: str
    boot_id: str
    nodeid: str
    namespace: str
    record: Path
    body_deadline: float
    cleanup_deadline: float

    @property
    def database(self):
        return "ar_migration_" + self.namespace

    @property
    def roles(self):
        return {suffix: self.database + "_" + suffix for suffix in ("owner", "app", "group")}


def _check_controller(controller, *, same_process):
    _require(
        isinstance(controller, dict)
        and set(controller)
        == {
            "pid",
            "start_ticks",
            "pgid",
            "sid",
        }
        and all(type(item) is int and item > 0 for item in controller.values()),
        "Invalid F4 runner process identity",
    )
    _require(
        (controller["pid"] == os.getpid()) is same_process
        and _identity(controller["pid"]) == controller,
        "F4 runner identity changed",
    )


def _check_hosted_binding(value, manifest_path):
    """Consume the explicit core-session entry; never infer one from CI presence.

    The session clock is distinct from the Actions job limit, which can end
    earlier. Only the existing core entry may supply the verified service facts
    and its actual selected F4 inventory. This loader launches no controller.
    """
    binding = value["binding"]
    _require(
        set(binding)
        == {
            "kind",
            "controller",
            "identity",
            "job",
            "python",
            "leg",
            "session_origin_monotonic",
            "session_limit_seconds",
            "service",
            "case_count",
            "cases_sha256",
        },
        "Invalid F4 hosted entry fields",
    )
    env = os.environ
    _require(
        env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_JOB") == "core"
        and binding["job"] == "core",
        "F4 requires the explicit Actions core entry",
    )
    runner_temp = Path(env.get("RUNNER_TEMP", ""))
    _require(
        runner_temp.is_absolute()
        and runner_temp.resolve() == runner_temp
        and manifest_path.is_relative_to(runner_temp),
        "Invalid F4 hosted record location",
    )
    _check_controller(binding["controller"], same_process=True)
    identity = binding["identity"]
    _require(
        isinstance(identity, dict)
        and set(identity)
        == {
            "repository",
            "event",
            "source_head",
            "source_tree",
            "checkout_commit",
            "checkout_tree",
            "checkout_parents",
            "workflow_sha",
            "run_id",
            "run_attempt",
        },
        "Invalid F4 core source identity",
    )
    for key, variable in (
        ("repository", "GITHUB_REPOSITORY"),
        ("event", "GITHUB_EVENT_NAME"),
        ("source_head", "CI_SOURCE_HEAD"),
        ("checkout_commit", "GITHUB_SHA"),
        ("workflow_sha", "GITHUB_WORKFLOW_SHA"),
    ):
        _require(identity[key] == env.get(variable), "F4 Actions identity changed")
    for key, variable in (("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT")):
        _require(
            type(identity[key]) is int
            and identity[key] > 0
            and str(identity[key]) == env.get(variable),
            "F4 Actions attempt changed",
        )
    _require(
        identity["checkout_commit"] == value["source_commit"]
        and identity["checkout_tree"] == value["source_tree"]
        and identity["source_tree"] == identity["checkout_tree"],
        "F4 core source differs from case entry",
    )
    for key in ("source_head", "source_tree", "checkout_commit", "checkout_tree", "workflow_sha"):
        _require(_hex(identity[key], 40), "Invalid F4 hosted source hash")
    _require(
        isinstance(identity["checkout_parents"], list)
        and len(identity["checkout_parents"]) in (1, 2)
        and all(_hex(parent, 40) for parent in identity["checkout_parents"]),
        "Invalid F4 core parent identity",
    )
    slots = {("3.11", "early"): 2700, ("3.11", "late"): 2700, ("3.12", "all"): 3900}
    slot = (binding["python"], binding["leg"])
    _require(
        binding["python"] == ".".join(map(str, sys.version_info[:2])), "F4 core interpreter changed"
    )
    _require(
        slot in slots
        and type(binding["session_limit_seconds"]) is int
        and binding["session_limit_seconds"] == slots[slot],
        "Invalid F4 core session limit",
    )
    origin = binding["session_origin_monotonic"]
    _require(
        type(origin) in (int, float) and math.isfinite(origin) and 0 < origin <= time.monotonic(),
        "Invalid F4 core session origin",
    )
    deadline = origin + binding["session_limit_seconds"]
    _require(
        value["body_deadline_monotonic"] == deadline
        and value["cleanup_deadline_monotonic"] == deadline
        and time.monotonic() < deadline,
        "F4 core session deadline unavailable",
    )
    service = binding["service"]
    _require(
        isinstance(service, dict)
        and set(service)
        == {
            "container_id",
            "image",
            "run_label",
            "ordinary_autovacuum_off_verified",
        },
        "Invalid F4 verified service record",
    )
    _require(
        _hex(service["container_id"], 64)
        and service["container_id"] == env.get("REWIND_TEST_POSTGRES_CONTAINER")
        and service["image"] == IMAGE
        and service["run_label"] == f"{identity['run_id']}-{identity['run_attempt']}"
        and service["ordinary_autovacuum_off_verified"] is True,
        "F4 service differs from the verified disposable service",
    )
    expected_url = "postgresql+psycopg://postgres:test-only@127.0.0.1:5432/rewind"
    _require(
        env.get("REWIND_TEST_POSTGRES_URL") == expected_url
        and env.get("REWIND_TEST_POSTGRES") == expected_url,
        "F4 hosted connection differs from the fixed service",
    )
    _require(
        type(binding["case_count"]) is int and binding["case_count"] == len(value["cases"]),
        "F4 hosted case inventory changed",
    )
    encoded_cases = json.dumps(value["cases"], sort_keys=True, separators=(",", ":")).encode()
    _require(
        hashlib.sha256(encoded_cases).hexdigest() == binding["cases_sha256"],
        "F4 hosted case inventory digest changed",
    )


def load_case_control(nodeid):
    """Read the parent's fixed case manifest before opening a database connection."""
    configured = os.environ.get("REWIND_F4_CASE_CONTROL")
    _require(isinstance(configured, str) and configured, "F4 case manifest is required")
    path = Path(configured)
    _require(path.is_absolute() and path.resolve() == path, "Invalid F4 manifest path")
    _require(
        not path.is_relative_to(Path(__file__).resolve().parents[1]),
        "F4 manifest must stay outside checkout",
    )
    _private(path.parent, directory=True)
    raw = _read(path, _MAX_MANIFEST)
    value = _decode(raw)
    _require(
        isinstance(value, dict)
        and set(value)
        == {
            "schema_version",
            "group_id",
            "source_sha256",
            "source_commit",
            "source_tree",
            "fixture_sha256",
            "boot_id",
            "binding",
            "body_deadline_monotonic",
            "cleanup_deadline_monotonic",
            "cases",
        },
        "Invalid F4 case manifest fields",
    )
    _require(
        type(value["schema_version"]) is int and value["schema_version"] == 1,
        "Unsupported F4 case manifest",
    )
    _require(
        isinstance(value["group_id"], str)
        and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value["group_id"]),
        "Invalid F4 group identity",
    )
    for key, length in (
        ("source_sha256", 64),
        ("source_commit", 40),
        ("source_tree", 40),
        ("fixture_sha256", 64),
    ):
        _require(_hex(value[key], length), "Invalid F4 source identity")
    _require(
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == value["fixture_sha256"],
        "F4 fixture source differs from the admitted manifest",
    )
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    _require(value["boot_id"] == boot, "F4 manifest boot changed")
    binding = value["binding"]
    _require(isinstance(binding, dict), "Invalid F4 runner binding")
    body, cleanup = value["body_deadline_monotonic"], value["cleanup_deadline_monotonic"]
    _require(
        all(type(item) in (int, float) and math.isfinite(item) for item in (body, cleanup)),
        "Invalid F4 absolute deadline",
    )
    cases = value["cases"]
    _require(isinstance(cases, list) and cases, "Invalid F4 fixed case inventory")
    if binding.get("kind") == "local_controller":
        _require(set(binding) == {"kind", "controller"}, "Invalid F4 local binding")
        _require(
            len(cases) <= _MAX_CASES and time.monotonic() < body < cleanup and cleanup - body <= 90,
            "F4 local phase unavailable",
        )
        _check_controller(binding["controller"], same_process=False)
    elif binding.get("kind") == "actions_core":
        _check_hosted_binding(value, path)
    else:
        raise AssertionError("F4 runner binding is not admitted")
    selected = None
    nodes, namespaces = set(), set()
    for case in cases:
        _require(
            isinstance(case, dict) and set(case) == {"nodeid", "namespace", "record_path"},
            "Invalid F4 case fields",
        )
        _require(
            isinstance(case["nodeid"], str) and 1 <= len(case["nodeid"]) <= 1024,
            "Invalid F4 node identity",
        )
        _require(_hex(case["namespace"], 32), "Invalid F4 case namespace")
        _require(
            case["nodeid"] not in nodes and case["namespace"] not in namespaces,
            "Repeated F4 node or namespace",
        )
        nodes.add(case["nodeid"])
        namespaces.add(case["namespace"])
        expected = path.parent / "cases" / case["namespace"] / "intent.json"
        _require(case["record_path"] == str(expected), "F4 case path escapes its fixed directory")
        if case["nodeid"] == nodeid:
            selected = case
    _require(selected is not None, "F4 node is not admitted")
    record = Path(selected["record_path"])
    _require(record.parent.resolve() == record.parent, "F4 case directory is redirected")
    _private(record.parent.parent, directory=True)
    _private(record.parent, directory=True)
    _require(
        not record.exists() and not record.with_name("intent.pending").exists(),
        "F4 case already has an attempt",
    )
    return CaseControl(
        hashlib.sha256(raw).hexdigest(),
        value["group_id"],
        value["source_sha256"],
        value["source_commit"],
        value["source_tree"],
        boot,
        nodeid,
        selected["namespace"],
        record,
        body,
        cleanup,
    )


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    _require(remaining > 0, "F4 body deadline exhausted")
    return remaining


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save(control, value, *, first=False):
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    _require(len(raw) <= _MAX_RECORD, "F4 case journal exceeds its bound")
    target = control.record if first else control.record.with_name("intent.pending")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if not first:
        os.replace(target, control.record)
    _sync_directory(control.record.parent)


def _event(control, journal, action, phase, **fields):
    _require(len(journal["events"]) < _MAX_EVENTS, "F4 case event bound exceeded")
    journal["events"].append(
        {"sequence": len(journal["events"]), "action": action, "phase": phase, **fields}
    )
    _save(control, journal)


def _command(connection, deadline, sql, parameters=None):
    remaining = _remaining(deadline)
    milliseconds = max(1, min(5000, int(remaining * 1000)))
    connection.exec_driver_sql(f"SET statement_timeout = {milliseconds}")
    connection.exec_driver_sql(f"SET lock_timeout = {milliseconds}")
    result = connection.execute(text(sql), parameters or {})
    _remaining(deadline)
    return result


def _observe(admin, control, deadline):
    with admin.connect() as connection:
        roles = _command(
            connection,
            deadline,
            "SELECT oid,rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,"
            "rolreplication,rolbypassrls,rolconnlimit,rolvaliduntil FROM pg_roles "
            "WHERE rolname IN (:owner,:app,:group) ORDER BY rolname LIMIT 4",
            control.roles,
        ).all()
        databases = _command(
            connection,
            deadline,
            "SELECT oid,datname,pg_get_userbyid(datdba) AS owner,datallowconn,datconnlimit,"
            "datistemplate FROM pg_database WHERE datname=:database LIMIT 2",
            {"database": control.database},
        ).all()
        memberships = _command(
            connection,
            deadline,
            "SELECT roleid,member,grantor,admin_option FROM pg_auth_members WHERE roleid IN "
            "(SELECT oid FROM pg_roles WHERE rolname IN (:owner,:app,:group)) OR member IN "
            "(SELECT oid FROM pg_roles WHERE rolname IN (:owner,:app,:group)) "
            "ORDER BY roleid,member,grantor LIMIT 10",
            control.roles,
        ).all()
    _require(
        len(roles) <= 3 and len(databases) <= 1 and len(memberships) <= 9,
        "F4 native ownership observation exceeds its bound",
    )
    return {
        "roles": [dict(zip(_ROLE_FIELDS, row, strict=True)) for row in roles],
        "databases": [dict(zip(_DATABASE_FIELDS, row, strict=True)) for row in databases],
        "memberships": [list(row) for row in memberships],
    }


def _expected_role(control, suffix, row):
    expected = {
        "rolname": control.roles[suffix],
        "rolsuper": False,
        "rolinherit": suffix != "app",
        "rolcreaterole": False,
        "rolcreatedb": False,
        "rolcanlogin": suffix != "group",
        "rolreplication": False,
        "rolbypassrls": False,
        "rolconnlimit": -1,
        "rolvaliduntil": None,
    }
    _require(type(row["oid"]) is int and row["oid"] > 0, "Invalid F4 native role OID")
    _require({key: row[key] for key in expected} == expected, "F4 role identity mismatch")


def _owned_observation(control, journal, observed):
    """Validate every retained object before issuing any destructive cleanup."""
    role_oids = {row["oid"] for row in observed["roles"]}
    for row in observed["roles"]:
        suffix = next(key for key, name in control.roles.items() if name == row["rolname"])
        action = journal["creates"][suffix]
        _require(action["started"], "F4 role has no pre-CREATE ownership intent")
        if action["oid"] is None:
            _expected_role(control, suffix, row)
        else:
            _require(row["oid"] == action["oid"], "F4 role OID changed")
        _require(
            not any(
                row[key]
                for key in (
                    "rolsuper",
                    "rolcreaterole",
                    "rolcreatedb",
                    "rolreplication",
                    "rolbypassrls",
                )
            ),
            "F4 role acquired privileged authority",
        )
    for membership in observed["memberships"]:
        _require(
            membership[0] in role_oids and membership[1] in role_oids,
            "F4 role has an external membership",
        )
    for row in observed["databases"]:
        action = journal["creates"]["database"]
        _require(
            action["started"] and row["owner"] == control.roles["owner"],
            "F4 database lacks matching ownership",
        )
        _require(
            row["datallowconn"] is True
            and row["datconnlimit"] == -1
            and row["datistemplate"] is False,
            "F4 database attributes changed",
        )
        _require(action["oid"] is None or row["oid"] == action["oid"], "F4 database OID changed")


def _validate_journal(control, value):
    _require(
        isinstance(value, dict)
        and set(value)
        == {
            "schema_version",
            "manifest_sha256",
            "group_id",
            "source_sha256",
            "source_commit",
            "source_tree",
            "boot_id",
            "nodeid",
            "namespace",
            "database",
            "roles",
            "body_deadline",
            "cleanup_deadline",
            "baseline",
            "creates",
            "events",
            "status",
            "fixture_error_type",
            "cleanup_error_types",
        },
        "Invalid F4 ownership journal",
    )
    expected = {
        "schema_version": 1,
        "manifest_sha256": control.manifest_sha256,
        "group_id": control.group_id,
        "source_sha256": control.source_sha256,
        "source_commit": control.source_commit,
        "source_tree": control.source_tree,
        "boot_id": control.boot_id,
        "nodeid": control.nodeid,
        "namespace": control.namespace,
        "database": control.database,
        "roles": control.roles,
        "body_deadline": control.body_deadline,
        "cleanup_deadline": control.cleanup_deadline,
        "baseline": {"roles": [], "databases": [], "memberships": []},
    }
    _require(
        type(value["schema_version"]) is int
        and all(value[key] == item for key, item in expected.items()),
        "F4 journal ownership binding changed",
    )
    creates = value["creates"]
    _require(
        isinstance(creates, dict) and set(creates) == {"owner", "app", "group", "database"},
        "Invalid F4 CREATE action inventory",
    )
    for action in creates.values():
        _require(
            isinstance(action, dict)
            and set(action) == {"started", "ack", "oid"}
            and type(action["started"]) is bool
            and type(action["ack"]) is bool,
            "Invalid F4 CREATE state",
        )
        _require(not action["ack"] or action["started"], "F4 ACK lacks a started intent")
        _require(
            action["oid"] is None
            or (type(action["oid"]) is int and action["oid"] > 0 and action["ack"]),
            "Invalid F4 created OID",
        )
    events = value["events"]
    _require(isinstance(events, list) and len(events) <= _MAX_EVENTS, "Invalid F4 event count")
    actions = {
        "owner",
        "app",
        "group",
        "database",
        "fixture",
        "cleanup",
        "drop_database",
        "drop_app",
        "drop_group",
        "drop_owner",
    }
    phases = {
        "create_started",
        "create_ack",
        "identity_observed",
        "ready",
        "observed",
        "started",
        "ack",
        "absent",
    }
    for index, event in enumerate(events):
        _require(
            isinstance(event, dict)
            and set(event)
            in (
                {"sequence", "action", "phase"},
                {"sequence", "action", "phase", "native"},
            )
            and type(event["sequence"]) is int
            and event["sequence"] == index
            and event["action"] in actions
            and event["phase"] in phases,
            "Invalid F4 ownership event",
        )
    for key, action in creates.items():
        seen = {event["phase"] for event in events if event["action"] == key}
        _require(
            action["started"] == ("create_started" in seen)
            and action["ack"] == ("create_ack" in seen)
            and (action["oid"] is not None) == ("identity_observed" in seen),
            "F4 action state differs from its durable events",
        )
    _require(
        value["status"] in {"active", "absent", "cleanup_incomplete"}, "Invalid F4 cleanup status"
    )
    _require(isinstance(value["cleanup_error_types"], list), "Invalid F4 cleanup errors")
    errors = [value["fixture_error_type"], *value["cleanup_error_types"]]
    _require(
        len(value["cleanup_error_types"]) <= 8
        and all(
            item is None
            or (isinstance(item, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", item))
            for item in errors
        ),
        "Invalid F4 bounded error types",
    )
    return value


def read_case_journal(control):
    """Validate the committed intent before the parent uses its cleanup authority."""
    return _validate_journal(control, _decode(_read(control.record, _MAX_RECORD)))


def retain_interrupted_write(control):
    """Parent-only recovery after it has verified the original child is absent.

    An incomplete atomic replacement never authorizes another CREATE. Preserve
    its bytes in the one fixed interruption slot before reusing the temp name.
    """
    pending = control.record.with_name("intent.pending")
    if not pending.exists():
        return
    _read(pending, _MAX_RECORD)
    retained = control.record.with_name("intent.interrupted")
    _require(not retained.exists(), "F4 interrupted write was already retained")
    # Exclusive hard-link publication preserves these immutable diagnostic bytes;
    # no dependency installation or mutable source is shared.
    os.link(pending, retained, follow_symlinks=False)
    os.unlink(pending)
    _sync_directory(control.record.parent)


def reconcile_case(admin, control, journal, *, deadline):
    """Reconcile this exact intent; the caller owns the supplied absolute phase.

    The fixture passes body_deadline. The parent may pass cleanup_deadline only
    after it has proved child termination. No baseline-delta discovery is used.
    """
    _require(
        deadline in (control.body_deadline, control.cleanup_deadline),
        "F4 reconciliation deadline is not admitted",
    )
    _validate_journal(control, journal)
    observed = _observe(admin, control, deadline)
    _owned_observation(control, journal, observed)
    _event(control, journal, "cleanup", "observed", native=observed)
    present = {row["rolname"] for row in observed["roles"]}
    drops = []
    if observed["databases"]:
        drops.append(("database", f"DROP DATABASE {control.database} WITH (FORCE)"))
    drops.extend(
        (suffix, f"DROP ROLE {control.roles[suffix]}")
        for suffix in ("app", "group", "owner")
        if control.roles[suffix] in present
    )
    for action, sql in drops:
        _remaining(deadline)
        _event(control, journal, "drop_" + action, "started")
        with admin.connect() as connection:
            _command(connection, deadline, sql).close()
        _event(control, journal, "drop_" + action, "ack")
    after = _observe(admin, control, deadline)
    _require(
        after == {"roles": [], "databases": [], "memberships": []},
        "F4 native objects remain after cleanup",
    )
    journal["status"] = "absent"
    _event(control, journal, "cleanup", "absent", native=after)


def _create(admin, control, journal, key, sql):
    _remaining(control.body_deadline)
    journal["creates"][key]["started"] = True
    _event(control, journal, key, "create_started")
    with admin.connect() as connection:
        _command(connection, control.body_deadline, sql).close()
    journal["creates"][key]["ack"] = True
    _event(control, journal, key, "create_ack")
    observed = _observe(admin, control, control.body_deadline)
    _owned_observation(control, journal, observed)
    if key == "database":
        row = observed["databases"]
    else:
        row = [item for item in observed["roles"] if item["rolname"] == control.roles[key]]
    _require(len(row) == 1, "F4 CREATE did not produce exactly one owned object")
    journal["creates"][key]["oid"] = row[0]["oid"]
    _event(control, journal, key, "identity_observed", native=observed)


@pytest.fixture
def pg(request, monkeypatch, record_property):
    _require(
        request.node.get_closest_marker("f4_owned_postgres") is not None,
        "F4 PostgreSQL fixture requires its explicit collection marker",
    )
    control = load_case_control(request.node.nodeid)
    url = os.environ.get("REWIND_TEST_POSTGRES_URL") or os.environ.get("REWIND_TEST_POSTGRES")
    _require(isinstance(url, str) and url, "F4 synthetic PostgreSQL URL is required")
    admin = create_engine(
        url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"connect_timeout": 5}
    )
    engines = []
    journal = None
    intent_saved = False
    primary = None
    cleanup_errors = []
    try:
        with admin.connect() as connection:
            version = _command(
                connection, control.body_deadline, "SHOW server_version_num"
            ).scalar_one()
            _require(str(version).startswith("16"), "F4 requires synthetic PostgreSQL 16")
        before = _observe(admin, control, control.body_deadline)
        _require(
            before == {"roles": [], "databases": [], "memberships": []},
            "F4 case identities were not absent before CREATE",
        )
        journal = {
            "schema_version": 1,
            "manifest_sha256": control.manifest_sha256,
            "group_id": control.group_id,
            "source_sha256": control.source_sha256,
            "source_commit": control.source_commit,
            "source_tree": control.source_tree,
            "boot_id": control.boot_id,
            "nodeid": control.nodeid,
            "namespace": control.namespace,
            "database": control.database,
            "roles": control.roles,
            "body_deadline": control.body_deadline,
            "cleanup_deadline": control.cleanup_deadline,
            "baseline": before,
            "creates": {
                key: {"started": False, "ack": False, "oid": None}
                for key in ("owner", "app", "group", "database")
            },
            "events": [],
            "status": "active",
            "fixture_error_type": None,
            "cleanup_error_types": [],
        }
        _save(control, journal, first=True)
        intent_saved = True
        password = "synthetic-test-only"
        for suffix, options in (
            ("owner", "LOGIN"),
            ("app", "LOGIN NOINHERIT"),
            ("group", "NOLOGIN"),
        ):
            credentials = "" if suffix == "group" else f" PASSWORD '{password}'"
            _create(
                admin,
                control,
                journal,
                suffix,
                f"CREATE ROLE {control.roles[suffix]} {options}{credentials}",
            )
        _create(
            admin,
            control,
            journal,
            "database",
            f"CREATE DATABASE {control.database} OWNER {control.roles['owner']}",
        )
        target = admin.url.set(database=control.database)
        owner = create_engine(
            target.set(username=control.roles["owner"], password=password),
            poolclass=NullPool,
            connect_args={"connect_timeout": 5},
        )
        engines.append(owner)
        app = create_engine(
            target.set(username=control.roles["app"], password=password),
            poolclass=NullPool,
            connect_args={"connect_timeout": 5},
        )
        engines.append(app)
        privileged = create_engine(target, poolclass=NullPool, connect_args={"connect_timeout": 5})
        engines.append(privileged)
        exclusion = service._postgres_exclusion

        def observed_exclusion(connection, tables):
            observe_exclusion_failure(
                exclusion, connection, tables, control=admin, database=control.database
            )

        monkeypatch.setattr(service, "_postgres_exclusion", observed_exclusion)
        _remaining(control.body_deadline)
        with owner.begin() as connection:
            _command(
                connection, control.body_deadline, "REVOKE CREATE ON SCHEMA public FROM PUBLIC"
            ).close()
        wait_for_database_drain(
            admin, control.database, timeout=min(5, _remaining(control.body_deadline))
        )
        _event(control, journal, "fixture", "ready")
        yield {
            "owner": owner,
            "app": app,
            "admin": privileged,
            "control": admin,
            "owner_role": control.roles["owner"],
            "app_role": control.roles["app"],
            "group_role": control.roles["group"],
        }
        _remaining(control.body_deadline)
    except BaseException as error:
        primary = error
        if journal is not None:
            journal["fixture_error_type"] = type(error).__name__
        raise
    finally:
        for engine in engines:
            try:
                engine.dispose()
            except BaseException as error:
                cleanup_errors.append(error)
        if intent_saved:
            try:
                reconcile_case(admin, control, journal, deadline=control.body_deadline)
            except BaseException as error:
                cleanup_errors.append(error)
                journal["status"] = "cleanup_incomplete"
        try:
            admin.dispose()
        except BaseException as error:
            cleanup_errors.append(error)
        if intent_saved:
            journal["cleanup_error_types"] = [type(error).__name__ for error in cleanup_errors]
            try:
                _save(control, journal)
            except BaseException as error:
                cleanup_errors.append(error)
            try:
                record_property(
                    "f4_case_ownership",
                    json.dumps(
                        {
                            "manifest_sha256": control.manifest_sha256,
                            "namespace": control.namespace,
                            "status": journal["status"],
                            "events": len(journal["events"]),
                            "fixture_error_type": journal["fixture_error_type"],
                            "cleanup_error_types": [
                                type(error).__name__ for error in cleanup_errors
                            ],
                        },
                        sort_keys=True,
                    ),
                )
            except BaseException as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            if primary is not None:
                primary.add_note(
                    "F4 fixture cleanup failed: "
                    + ",".join(type(error).__name__ for error in cleanup_errors)
                )
            else:
                raise AssertionError("F4 fixture cleanup failed") from cleanup_errors[0]
