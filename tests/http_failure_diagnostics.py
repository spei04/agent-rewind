"""Failure-only test evidence; never changes production error disclosure.

Remove this scoped witness when the original hosted HTTP failure is understood.
All labels are fixed, and neither SQL, exception messages nor arbitrary locals
are serialized. The caller includes the report only in its failed assertion.
"""

import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import get_args

from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError

from agent_rewind import errors
from agent_rewind.admission_records import AdmissionStorageError, StorageCode
from agent_rewind.admission_request import AdmissionPreparationError, PreparationCode
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.operation_work import OperationWork
from agent_rewind.scoped_repositories import RepositoryUnavailable

MAX_EXCEPTIONS = 8
MAX_FRAMES = 32
MAX_BYTES = 16384
ROOT = Path(errors.__file__).parent
FRAME_FUNCTIONS = {
    "operation_http.py": {"named", "get_project_operation"},
    "request_authority.py": {"check", "named", "_resolve", "_context"},
    "scoped_repositories.py": {"effective_role", "key", "resource", "job"},
    "operation_service.py": {"read_operation", "_read", "_load_result", "_result_id"},
    "operation_reads.py": {"read_job", "read_operation", "read_descriptor", "observe_result"},
    "operation_sources.py": {"verify_read_snapshot", "_matching_query", "read_run_cohort"},
    "operation_work.py": {
        "operation_connection",
        "check",
        "_limits",
        "_charge",
        "_native_limits",
        "remaining_timeouts_ms",
        "attach",
        "detach",
        "finish",
        "_before",
        "_after",
    },
    "sqlite_ownership.py": {
        "connect_owned",
        "close_owned",
        "finish_owned",
        "require_owned_sqlite",
    },
    "artifact_storage.py": {"read_verified", "_read"},
}
FRAME_PATHS = {str(ROOT / name): name for name in FRAME_FUNCTIONS}
ERROR_TYPES = {
    errors.Fault: "Fault",
    AdmissionError: "AdmissionError",
    AdmissionStorageError: "AdmissionStorageError",
    AdmissionPreparationError: "AdmissionPreparationError",
    ArtifactError: "ArtifactError",
    RepositoryUnavailable: "RepositoryUnavailable",
    OperationalError: "OperationalError",
    DBAPIError: "DBAPIError",
    SQLAlchemyError: "SQLAlchemyError",
    TimeoutError: "SQLAlchemyTimeoutError",
    sqlite3.OperationalError: "SQLiteOperationalError",
    sqlite3.Error: "SQLiteError",
    OSError: "OSError",
    ValueError: "ValueError",
    RuntimeError: "RuntimeError",
}
CODES = (
    frozenset(errors.RULES)
    | frozenset(get_args(StorageCode))
    | frozenset(get_args(PreparationCode))
)


def _identity(error):
    value = {"type": ERROR_TYPES.get(type(error), "OtherException")}
    attributes = vars(error)
    code = attributes.get("_code") if type(error) is errors.Fault else attributes.get("code")
    if type(code) is str and code in CODES:
        value["code"] = code
    return value


def _work(value):
    if type(value) is not OperationWork:
        return None
    result = {}
    for name in ("statements", "seconds", "instructions"):
        number = vars(value).get(name)
        if type(number) in (int, float) and 0 <= number <= 1_000_000_000 and math.isfinite(number):
            result[name] = number
    for name in ("_ready", "_detached", "_failed"):
        flag = vars(value).get(name)
        if type(flag) is bool:
            result[name] = flag
    return result


def exception_evidence(error):
    pending = [("classified", error)]
    seen = set()
    nodes = []
    remaining = MAX_FRAMES
    while pending and len(nodes) < MAX_EXCEPTIONS:
        relation, current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        item = {"relation": relation, **_identity(current), "frames": []}
        trace = current.__traceback__
        while trace is not None and remaining:
            remaining -= 1
            frame = trace.tb_frame
            filename = FRAME_PATHS.get(frame.f_code.co_filename)
            if filename is not None:
                name = frame.f_code.co_name
                row = {
                    "file": filename,
                    "function": name if name in FRAME_FUNCTIONS[filename] else "other",
                    "line": trace.tb_lineno if 0 < trace.tb_lineno < 1_000_000 else 0,
                }
                if (filename, name) in {
                    ("operation_service.py", "_read"),
                    ("operation_work.py", "operation_connection"),
                }:
                    work = _work(frame.f_locals.get("work"))
                    if work is not None:
                        row["work"] = work
                if (filename, name) == ("operation_work.py", "operation_connection"):
                    row["phase"] = {
                        key: frame.f_locals[key]
                        for key in ("attached", "cleanup_failed", "setup_ok", "discard_retry_used")
                        if type(frame.f_locals.get(key)) is bool
                    }
                    primary = frame.f_locals.get("primary")
                    if isinstance(primary, BaseException):
                        row["primary"] = _identity(primary)
                        if len(pending) < MAX_EXCEPTIONS:
                            pending.append(("retained_primary", primary))
                item["frames"].append(row)
            trace = trace.tb_next
        nodes.append(item)
        for relation, next_error in (
            ("cause", current.__cause__),
            ("context", current.__context__),
        ):
            if next_error is not None and len(pending) < MAX_EXCEPTIONS:
                pending.append((relation, next_error))
    return {"exceptions": nodes, "truncated": bool(pending) or remaining == 0}


@contextmanager
def first_get_failure(monkeypatch):
    """Observe only the positive first GET; the deliberate second 503 is outside."""
    report = {"phase": "first_get_expected_200", "classified": []}
    original = errors.classified

    def observe(scope, error):
        result = original(scope, error)
        if scope.get("method") == "GET" and not report["classified"]:
            try:
                evidence = exception_evidence(error)
            except Exception:
                # Diagnostic failure cannot replace the original classification.
                evidence = {"diagnostic_unavailable": True}
            classification = result if type(result) is str and result in errors.RULES else "other"
            report["classified"].append({"result": classification, **evidence})
        return result

    with monkeypatch.context() as patch:
        patch.setattr(errors, "classified", observe)

        def message():
            encoded = json.dumps(report, separators=(",", ":"), allow_nan=False)
            if len(encoded.encode()) > MAX_BYTES:
                return '{"phase":"first_get_expected_200","diagnostic_truncated":true}'
            return encoded

        yield message
