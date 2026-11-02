"""Bounded public CI coverage receipts; no baseline-driven test selection."""

import hashlib
import io
import json
import math
import re
import stat
import unicodedata
import zipfile
from datetime import datetime
from pathlib import PurePosixPath

SCHEMA = 1
BOUNDARY = "tests/test_ledger_recovery.py"
LEGS = (("3.11", "early"), ("3.11", "late"), ("3.12", "all"))
MAX_NODES = 20_000
MAX_NODE_BYTES = 128 * 1024
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_RECEIPT_BYTES + 64 * 1024
MAX_API_BYTES = 256 * 1024
IDENTITY_KEYS = {
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
}
RECEIPT_KEYS = {
    "schema",
    "identity",
    "python",
    "leg",
    "full_collection",
    "full_collection_sha256",
    "selected",
    "selected_sha256",
    "outcomes",
    "started_at",
    "finished_at",
    "session_finished",
    "pytest_exit_code",
    "collection_errors",
    "errors",
    "complete",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def object_fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), "Unexpected object fields")
    return value


def integer(value, minimum=0, maximum=MAX_NODES):
    require(type(value) is int and minimum <= value <= maximum, "Invalid integer")
    return value


def public_text(value, maximum=1024):
    require(type(value) is str and bool(value), "Expected nonempty text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as error:
        raise ValueError("Invalid UTF-8 text") from error
    require(size <= maximum, "Text exceeds bound")
    require(not any(unicodedata.category(c).startswith("C") for c in value), "Control text")
    return value


def digest(value, length=64):
    require(
        type(value) is str and re.fullmatch("[0-9a-f]{" + str(length) + "}", value),
        "Invalid digest",
    )
    return value


def load_json(data, limit=MAX_RECEIPT_BYTES):
    require(type(data) is bytes and len(data) <= limit, "JSON exceeds byte bound")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ValueError("Nonfinite JSON number")

    def finite_float(value):
        result = float(value)
        require(math.isfinite(result), "Nonfinite JSON number")
        return result

    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Invalid JSON") from error


def node_file(node, tracked):
    public_text(node, MAX_NODE_BYTES)
    path, separator, tail = node.partition("::")
    pure = PurePosixPath(path)
    require(
        separator and tail and path.startswith("tests/") and path.endswith(".py"),
        "Invalid test node",
    )
    require(
        not pure.is_absolute() and ".." not in pure.parts and str(pure) == path, "Unsafe test path"
    )
    require(path in tracked, "Untracked test file")
    return path


def nodes(value, tracked):
    require(type(value) is list and 0 < len(value) <= MAX_NODES, "Invalid node inventory")
    for node in value:
        node_file(node, tracked)
    require(len(set(value)) == len(value), "Duplicate test node")
    return value


def node_digest(value):
    # Validate scalar strings before this shared, delimiter-safe canonical encoding.
    require(type(value) is list and len(value) <= MAX_NODES, "Invalid node list")
    for node in value:
        public_text(node, MAX_NODE_BYTES)
    require(len(set(value)) == len(value), "Duplicate test node")
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_nodes(full, python, leg):
    require((python, leg) in LEGS, "Unknown interpreter/leg")
    if leg == "all":
        return list(full)
    return [node for node in full if (node.split("::", 1)[0] < BOUNDARY) == (leg == "early")]


def skip_reason(value):
    public_text(value, 512)
    require(not re.search(r"(^|[\s'\"(])(?:/|[A-Za-z]:[/\\])", value), "Private-shaped skip reason")
    return value


def terminal_skip_reason(longrepr):
    require(type(longrepr) is tuple and len(longrepr) == 3, "Malformed terminal skip")
    value = longrepr[2]
    require(type(value) is str, "Malformed terminal skip reason")
    if value.startswith("Skipped: "):
        value = value[len("Skipped: ") :]
    return skip_reason(value)


def validate_identity(value):
    result = object_fields(value, IDENTITY_KEYS)
    require(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", public_text(result["repository"], 200)),
        "Invalid repository",
    )
    require(result["event"] in ("pull_request", "push"), "Unexpected workflow event")
    for key in ("source_head", "source_tree", "checkout_commit", "checkout_tree", "workflow_sha"):
        digest(result[key], 40)
    for key in ("run_id", "run_attempt"):
        integer(result[key], 1, 2**63 - 1)
    parents = result["checkout_parents"]
    require(type(parents) is list and len(parents) <= 8, "Invalid checkout parents")
    for parent in parents:
        digest(parent, 40)
    require(len(set(parents)) == len(parents), "Duplicate checkout parent")
    require(result["source_tree"] == result["checkout_tree"], "Reviewed tree bridge differs")
    if result["event"] == "pull_request":
        require(
            len(parents) == 2 and result["source_head"] in parents,
            "Checkout is not the reviewed PR merge",
        )
    else:
        require(result["source_head"] == result["checkout_commit"], "Main source differs")
    return result


def artifact_name(identity, python, leg):
    validate_identity(identity)
    require((python, leg) in LEGS, "Unknown interpreter/leg")
    return (
        f"core-receipt-{identity['run_id']}-{identity['run_attempt']}-"
        f"{identity['checkout_commit']}-py{python}-{leg}"
    )


def validate_expectations(value, tracked):
    result = object_fields(value, {"schema", "status", "versions"})
    require(type(result["schema"]) is int and result["schema"] == SCHEMA, "Unknown schema")
    require(result["status"] == "accepted", "CI expectations await final inventory review")
    versions = object_fields(result["versions"], {"3.11", "3.12"})
    for baseline in versions.values():
        object_fields(baseline, {"count", "sha256", "skips"})
        integer(baseline["count"], 1)
        digest(baseline["sha256"])
        skips = baseline["skips"]
        require(type(skips) is list and len(skips) <= baseline["count"], "Invalid skip list")
        seen = set()
        for item in skips:
            object_fields(item, {"nodeid", "reason"})
            node_file(item["nodeid"], tracked)
            skip_reason(item["reason"])
            require(item["nodeid"] not in seen, "Duplicate expected skip")
            seen.add(item["nodeid"])
    return versions


def phase_outcome(value):
    object_fields(value, {"nodeid", "phases", "outcome", "skip_reason"})
    phases = value["phases"]
    require(type(phases) is list and 1 <= len(phases) <= 3, "Incomplete phase reports")
    for phase in phases:
        object_fields(phase, {"when", "outcome"})
        require(
            phase["when"] in ("setup", "call", "teardown")
            and phase["outcome"] in ("passed", "skipped", "failed"),
            "Unknown phase",
        )
    sequence = [(p["when"], p["outcome"]) for p in phases]
    passed = [("setup", "passed"), ("call", "passed"), ("teardown", "passed")]
    skipped_setup = [("setup", "skipped"), ("teardown", "passed")]
    skipped_call = [("setup", "passed"), ("call", "skipped"), ("teardown", "passed")]
    require(sequence in (passed, skipped_setup, skipped_call), "Failed or incomplete phases")
    expected = "passed" if sequence == passed else "skipped"
    require(value["outcome"] == expected, "Incorrect terminal outcome")
    if expected == "skipped":
        skip_reason(value["skip_reason"])
    else:
        require(value["skip_reason"] is None, "Unexpected skip reason")
    return expected


def timestamp(value):
    public_text(value, 40)
    require(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value),
        "Invalid UTC encoding",
    )
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Invalid session timestamp") from error
    require(
        result.tzinfo is not None and result.utcoffset().total_seconds() == 0,
        "Session timestamp is not UTC",
    )
    return result


def validate_receipt(value, identity, versions, tracked):
    receipt = object_fields(value, RECEIPT_KEYS)
    require(type(receipt["schema"]) is int and receipt["schema"] == SCHEMA, "Unknown schema")
    require(validate_identity(receipt["identity"]) == identity, "Receipt identity differs")
    python, leg = receipt["python"], receipt["leg"]
    require((python, leg) in LEGS, "Unknown interpreter/leg")
    full = nodes(receipt["full_collection"], tracked)
    selected = nodes(receipt["selected"], tracked)
    require(receipt["full_collection_sha256"] == node_digest(full), "Collection digest differs")
    require(receipt["selected_sha256"] == node_digest(selected), "Selected digest differs")
    require(selected == select_nodes(full, python, leg), "Incorrect selection/order")
    baseline = versions[python]
    require(
        len(full) == baseline["count"] and node_digest(full) == baseline["sha256"],
        "Collection differs from accepted expectations",
    )
    baseline_skips = baseline["skips"]
    expected_nodes = [item["nodeid"] for item in baseline_skips]
    require(all(node in full for node in expected_nodes), "Expected skip missing from collection")
    require(
        expected_nodes == [node for node in full if node in set(expected_nodes)],
        "Expected skips are not in collection order",
    )
    require(
        receipt["session_finished"] is True and receipt["complete"] is True, "Incomplete session"
    )
    require(
        type(receipt["pytest_exit_code"]) is int and receipt["pytest_exit_code"] == 0,
        "Original pytest did not succeed",
    )
    require(
        type(receipt["collection_errors"]) is int and receipt["collection_errors"] == 0,
        "Collection failed",
    )
    require(receipt["errors"] == [] and type(receipt["errors"]) is list, "Receipt errors")
    elapsed = (timestamp(receipt["finished_at"]) - timestamp(receipt["started_at"])).total_seconds()
    maximum_seconds = (60 if (python, leg) == ("3.12", "all") else 45) * 60
    require(0 < elapsed <= maximum_seconds, "Session exceeded core leg bound")
    outcomes = receipt["outcomes"]
    require(type(outcomes) is list and len(outcomes) == len(selected), "Missing terminal outcomes")
    skips = []
    for node, outcome in zip(selected, outcomes, strict=True):
        object_fields(outcome, {"nodeid", "phases", "outcome", "skip_reason"})
        require(outcome["nodeid"] == node, "Duplicate, foreign or reordered terminal outcome")
        if phase_outcome(outcome) == "skipped":
            skips.append({"nodeid": node, "reason": outcome["skip_reason"]})
    require(
        skips == [item for item in baseline_skips if item["nodeid"] in set(selected)],
        "Unexpected or unfulfilled exact skips",
    )
    return receipt


def validate_campaign(receipts, identity, expectations, tracked):
    validate_identity(identity)
    versions = validate_expectations(expectations, tracked)
    require(type(receipts) is list and len(receipts) == 3, "Exactly three receipts required")
    found = {}
    for raw in receipts:
        receipt = validate_receipt(raw, identity, versions, tracked)
        key = receipt["python"], receipt["leg"]
        require(key not in found, "Duplicate leg")
        found[key] = receipt
    require(set(found) == set(LEGS), "Missing core leg")
    early, late = found[("3.11", "early")], found[("3.11", "late")]
    require(early["full_collection"] == late["full_collection"], "3.11 inventories differ")
    require(not set(early["selected"]) & set(late["selected"]), "Overlapping core legs")
    require(
        set(early["selected"]) | set(late["selected"]) == set(early["full_collection"]),
        "Incomplete core union",
    )
    return found


def receipt_bytes(value):
    result = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    require(len(result) <= MAX_RECEIPT_BYTES, "Receipt exceeds byte bound")
    return result


def unpack_receipt(data):
    require(type(data) is bytes and len(data) <= MAX_ARCHIVE_BYTES, "Archive exceeds byte bound")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            require(len(entries) == 1, "Exactly one receipt member required")
            item = entries[0]
            mode = item.external_attr >> 16
            require(
                item.filename == "receipt.json"
                and item.orig_filename == "receipt.json"
                and not item.is_dir(),
                "Unexpected ZIP member",
            )
            require(
                stat.S_IFMT(mode) in (0, stat.S_IFREG)
                and not item.flag_bits & 1
                and not item.external_attr & 0x10,
                "Linked or encrypted ZIP member",
            )
            require(
                item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                "Unexpected ZIP compression",
            )
            require(
                0 < item.file_size <= MAX_RECEIPT_BYTES and item.compress_size <= MAX_ARCHIVE_BYTES,
                "ZIP member exceeds bound",
            )
            with archive.open(item) as stream:
                contents = stream.read(MAX_RECEIPT_BYTES + 1)
            require(len(contents) == item.file_size, "Incorrect ZIP member size")
            return load_json(contents)
    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise ValueError("Invalid receipt archive") from error


def validate_artifacts(value, identity):
    validate_identity(identity)
    require(type(value) is dict, "Invalid artifact listing")
    total = integer(value.get("total_count"), 0, 100)
    artifacts = value.get("artifacts")
    require(type(artifacts) is list and len(artifacts) == total, "Incomplete artifact listing")
    expected = {artifact_name(identity, python, leg) for python, leg in LEGS}
    ids, names, current, ignored = set(), set(), [], []
    prefix = f"core-receipt-{identity['run_id']}-"
    suffix = f"-{identity['checkout_commit']}-py"
    candidate_prefix = f"candidate-{identity['checkout_commit']}-"
    for item in artifacts:
        require(type(item) is dict, "Invalid artifact metadata")
        identifier = integer(item.get("id"), 1, 2**63 - 1)
        name = public_text(item.get("name"), 200)
        require(name not in names and identifier not in ids, "Duplicate artifact")
        ids.add(identifier)
        names.add(name)
        require(type(item.get("expired")) is bool, "Invalid artifact expiry")
        integer(item.get("size_in_bytes"), 1, 2**63 - 1)
        require(
            type(item.get("digest")) is str and item["digest"].startswith("sha256:"),
            "Missing artifact digest",
        )
        digest(item["digest"][len("sha256:") :])
        run = item.get("workflow_run")
        require(
            type(run) is dict
            and type(run.get("id")) is int
            and run["id"] == identity["run_id"]
            and run.get("head_sha") == identity["source_head"],
            "Artifact run/head differs",
        )
        if name in expected:
            require(item["expired"] is False, "Expired artifact")
            integer(item["size_in_bytes"], 1, MAX_ARCHIVE_BYTES)
            current.append(item)
            continue
        kind, attempt = None, None
        if name.startswith(prefix) and suffix in name:
            attempt_text, leg_text = name[len(prefix) :].split(suffix, 1)
            require(re.fullmatch(r"[1-9][0-9]*", attempt_text), "Invalid prior attempt")
            attempt = integer(int(attempt_text), 1, identity["run_attempt"] - 1)
            require(leg_text in {f"{python}-{leg}" for python, leg in LEGS}, "Unknown prior leg")
            integer(item["size_in_bytes"], 1, MAX_ARCHIVE_BYTES)
            kind = "core-receipt"
        elif identity["event"] == "push" and name.startswith(candidate_prefix):
            attempt_text = name[len(candidate_prefix) :]
            require(re.fullmatch(r"[1-9][0-9]*", attempt_text), "Invalid prior candidate attempt")
            attempt = integer(int(attempt_text), 1, identity["run_attempt"] - 1)
            integer(item["size_in_bytes"], 1, MAX_RECEIPT_BYTES - 1)
            kind = "candidate"
        require(kind is not None, "Unknown or current-extra artifact")
        ignored.append({"id": identifier, "name": name, "run_attempt": attempt, "kind": kind})
    require(
        len(current) == 3 and {item["name"] for item in current} == expected,
        "Exactly three current receipt artifacts required",
    )
    return current, ignored


def git_output(root, *arguments):
    import shutil
    import subprocess

    fixed = {
        ("ls-files", "--", "tests"),
        ("rev-parse", "HEAD"),
        ("rev-parse", "HEAD^{tree}"),
        ("rev-list", "--parents", "-n", "1", "HEAD"),
        ("status", "--porcelain=v1", "--untracked-files=no"),
    }
    require(all(type(argument) is str for argument in arguments), "Invalid Git arguments")
    revision = (
        len(arguments) == 2
        and arguments[0] == "rev-parse"
        and len(arguments[1]) == 47
        and arguments[1][40:] == "^{tree}"
        and re.fullmatch("[0-9a-f]{40}", arguments[1][:40])
    )
    require(arguments in fixed or revision, "Git command is outside source observation")
    binary = shutil.which("git", path="/usr/bin:/bin")
    require(binary is not None and PurePosixPath(binary).is_absolute(), "Missing absolute Git")
    try:
        # Only the allowlisted read commands and a full validated Git hash reach this call.
        result = subprocess.run(  # noqa: S603
            [binary, "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        raise ValueError("Git source observation failed") from None
    return result.stdout.strip()


def tracked_tests(root):
    return set(git_output(root, "ls-files", "--", "tests").splitlines())


def observe_identity(root, environment):
    # Every producer and the gate independently read their checkout, not receipt claims.
    source_head = digest(environment["CI_SOURCE_HEAD"], 40)
    checkout = git_output(root, "rev-parse", "HEAD")
    require(checkout == environment["GITHUB_SHA"], "Actual checkout differs from workflow")
    identity = {
        "repository": environment["GITHUB_REPOSITORY"],
        "event": environment["GITHUB_EVENT_NAME"],
        "source_head": source_head,
        "source_tree": git_output(root, "rev-parse", source_head + "^{tree}"),
        "checkout_commit": checkout,
        "checkout_tree": git_output(root, "rev-parse", "HEAD^{tree}"),
        "checkout_parents": git_output(root, "rev-list", "--parents", "-n", "1", "HEAD").split()[
            1:
        ],
        "workflow_sha": environment["GITHUB_WORKFLOW_SHA"],
        "run_id": int(environment["GITHUB_RUN_ID"]),
        "run_attempt": int(environment["GITHUB_RUN_ATTEMPT"]),
    }
    require(
        not git_output(root, "status", "--porcelain=v1", "--untracked-files=no"),
        "Tracked checkout changed",
    )
    return validate_identity(identity)
