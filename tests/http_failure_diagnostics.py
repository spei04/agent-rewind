"""Failure-only test evidence; never changes production error disclosure.

Remove this scoped witness when the original hosted HTTP failure is understood.
All labels are fixed, and neither SQL, exception messages nor arbitrary locals
are serialized. The caller includes the report only in its failed assertion.
"""

import builtins
import json
import math
import sqlite3
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from types import CodeType
from typing import get_args

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError

from agent_rewind import api, errors
from agent_rewind.admission_records import AdmissionStorageError, StorageCode
from agent_rewind.admission_request import AdmissionPreparationError, PreparationCode
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.listing_session import SQLWork
from agent_rewind.migrations import compatibility as guard
from agent_rewind.operation_work import OperationWork
from agent_rewind.scoped_repositories import RepositoryUnavailable

MAX_EXCEPTIONS = 8
MAX_FRAMES = 32
MAX_BYTES = 16384
ROOT = Path(errors.__file__).parent
FRAME_FUNCTIONS = {
    "api.py": {"named_read", "list_project_runs"},
    "migrations/compatibility.py": {
        "runtime_schema_compatibility",
        "_check_schema_compatibility",
        "_inspection",
        "remaining",
        "check",
        "before",
        "after",
        "progress",
    },
    "scoped_run_listing.py": {"list", "_context", "_receipts", "_finish", "_summaries"},
    "listing_session.py": {"listing_connection", "before", "after", "remaining", "progress"},
    "listing_projection.py": {
        "fail",
        "bounded",
        "entry",
        "safe_columns",
        "safe_created",
        "candidates",
        "by_ids",
        "matching_query",
        "summary",
        "receipt",
    },
    "listing_sources.py": {"wanted", "__init__", "_records", "_jobs", "_links", "load", "add"},
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
    builtins.TimeoutError: "TimeoutError",
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
    if type(error) in (sqlite3.Error, sqlite3.OperationalError):
        native = attributes.get("sqlite_errorcode")
        labels = {
            sqlite3.SQLITE_BUSY: "busy",
            sqlite3.SQLITE_LOCKED: "locked",
            sqlite3.SQLITE_INTERRUPT: "interrupt",
            sqlite3.SQLITE_ERROR: "error",
        }
        if type(native) is int and native in labels:
            value["sqlite_reason"] = labels[native]
    return value


def _work(value):
    if type(value) not in (OperationWork, SQLWork):
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
    if type(value) is SQLWork:
        result["started_is_none"] = vars(value).get("started") is None
    return result


@dataclass
class _EvidenceBudget:
    exceptions: int = MAX_EXCEPTIONS
    frames: int = MAX_FRAMES
    seen: set[int] = field(default_factory=set)


def exception_evidence(error, *, budget=None):
    pending = [("classified", error)]
    budget = _EvidenceBudget() if budget is None else budget
    nodes = []
    while pending and budget.exceptions:
        relation, current = pending.pop(0)
        if id(current) in budget.seen:
            continue
        budget.seen.add(id(current))
        budget.exceptions -= 1
        item = {"relation": relation, **_identity(current), "frames": []}
        trace = current.__traceback__
        while trace is not None and budget.frames:
            budget.frames -= 1
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
                    ("listing_session.py", "listing_connection"),
                    ("scoped_run_listing.py", "list"),
                    ("scoped_run_listing.py", "_finish"),
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
                if (filename, name) == ("listing_session.py", "listing_connection"):
                    row["phase"] = {
                        key: frame.f_locals[key]
                        for key in ("entered", "broken", "failed", "progress")
                        if type(frame.f_locals.get(key)) is bool
                    }
                    row["primary_is_none"] = frame.f_locals.get("primary") is None
                    for key in ("primary", "cleanup_interruption"):
                        retained = frame.f_locals.get(key)
                        if isinstance(retained, BaseException):
                            row[key] = _identity(retained)
                            if len(pending) < MAX_EXCEPTIONS:
                                pending.append(("retained_" + key, retained))
                item["frames"].append(row)
            trace = trace.tb_next
        nodes.append(item)
        for relation, next_error in (
            ("cause", current.__cause__),
            ("context", current.__context__),
        ):
            if next_error is not None and len(pending) < MAX_EXCEPTIONS:
                pending.append((relation, next_error))
    return {"exceptions": nodes, "truncated": bool(pending) or budget.frames == 0}


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


# These constructors/statuses are observed, never substituted as readiness.
_COMPATIBILITY_RESULT = guard.CompatibilityResult
_COMPATIBILITY_CODES = frozenset(
    {
        "schema_probe_capacity",
        "schema_unavailable",
        "schema_incompatible",
        "migration_only",
        "release_profile_invalid",
        "release_profile_or_connection_invalid",
        "backfill_incomplete",
    }
)


def _compatibility_result(value):
    if type(value) is not _COMPATIBILITY_RESULT:
        return {"status": "other", "code": "other"}
    return {
        "status": value.status
        if type(value.status) is str and value.status in ("ready", "incompatible", "unavailable")
        else "other",
        "code": value.code
        if type(value.code) is str and value.code in _COMPATIBILITY_CODES
        else "other",
    }


def _route_message(report):
    encoded = json.dumps(report, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) <= MAX_BYTES:
        return encoded
    # Retain finite phase/reason identities if frame details exhaust the byte cap.
    summary = {"phase": report["phase"], "diagnostic_truncated": True}
    for name in ("probes", "guard", "security", "classified"):
        summary[name] = [
            {key: value for key, value in event.items() if key in ("stage", "result", "error")}
            for event in report[name]
        ]
    return json.dumps(summary, separators=(",", ":"), allow_nan=False)


def _capture(report, budget, bucket, event, error=None):
    # A shared budget bounds all exception/frame visits in this request.
    if len(report[bucket]) >= (1 if bucket == "classified" else 4):
        return
    try:
        if error is not None:
            event = {
                **event,
                "error": _identity(error),
                **exception_evidence(error, budget=budget),
            }
        report[bucket].append(event)
    except Exception:
        report[bucket].append({"diagnostic_unavailable": True})


def _compatibility_observers(original_probe, original_constructor, capture):
    """Share only the owned probe/constructor seam, without an HTTP application."""
    owned = threading.local()
    token = object()
    guard_codes = {
        guard._check_schema_compatibility.__code__,
        guard.runtime_schema_compatibility.__code__,
    }

    def probe(*args, **kwargs):
        previous = getattr(owned, "token", None)
        owned.token = token
        try:
            try:
                result = original_probe(*args, **kwargs)
            except BaseException as error:
                capture("probes", {"stage": "raised"}, error)
                raise
            try:
                capture("probes", {"stage": "returned", "result": _compatibility_result(result)})
            except Exception:
                capture("probes", {"diagnostic_unavailable": True})
            return result
        finally:
            owned.token = previous

    def constructor(*args, **kwargs):
        result = original_constructor(*args, **kwargs)
        frame = sys._getframe(1)
        try:
            if (
                getattr(owned, "token", None) is token
                and frame.f_code in guard_codes
                and type(result) is _COMPATIBILITY_RESULT
                and (result.status, result.code) == ("unavailable", "schema_unavailable")
            ):
                error = sys.exception()
                if isinstance(error, BaseException):
                    capture(
                        "guard",
                        {"stage": frame.f_code.co_name, "result": _compatibility_result(result)},
                        error,
                    )
        except Exception:
            capture("guard", {"diagnostic_unavailable": True})
        finally:
            del frame
        return result

    return probe, constructor


@contextmanager
def compatibility_failure(service):
    """Observe the existing predecessor call; report only when its assertion fails."""
    report = {
        "phase": "predecessor_compatibility_expected_migration_only",
        "probes": [],
        "guard": [],
        "security": [],
        "classified": [],
    }
    capture = partial(_capture, report, _EvidenceBudget())
    probe, constructor = _compatibility_observers(
        service.schema_compatibility, guard.CompatibilityResult, capture
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(service, "schema_compatibility", probe)
        patch.setattr(guard, "CompatibilityResult", constructor)
        yield lambda: _route_message(report)


@contextmanager
def route_failure(monkeypatch, app, *, phase):
    """One request's real probe/security/classifier calls, with no extra clock or SQL."""
    if phase not in ("schema_guard_expected_incompatible", "listing_continuation_expected_200"):
        raise ValueError("unsupported diagnostic phase")
    report = {"phase": phase, "probes": [], "guard": [], "security": [], "classified": []}
    budget = _EvidenceBudget()
    db = app.state.db
    original_response = api.error_response
    original_classifier = errors.classified
    security_code = next(
        code
        for code in api.create_app.__code__.co_consts
        if isinstance(code, CodeType) and code.co_name == "security"
    )

    capture = partial(_capture, report, budget)
    probe, constructor = _compatibility_observers(
        db.schema_compatibility, guard.CompatibilityResult, capture
    )

    def response(*args, **kwargs):
        result = original_response(*args, **kwargs)
        frame = sys._getframe(1)
        try:
            if frame.f_code is security_code and frame.f_locals.get("db") is db:
                capture(
                    "security",
                    {
                        "stage": "security",
                        "result": _compatibility_result(frame.f_locals.get("compatibility")),
                    },
                )
        except Exception:
            capture("security", {"diagnostic_unavailable": True})
        finally:
            del frame
        return result

    def classify(scope, error):
        result = original_classifier(scope, error)
        if scope.get("app") is app:
            capture(
                "classified",
                {
                    "result": result if type(result) is str and result in errors.RULES else "other",
                },
                error,
            )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(db, "schema_compatibility", probe)
        patch.setattr(guard, "CompatibilityResult", constructor)
        patch.setattr(api, "error_response", response)
        patch.setattr(errors, "classified", classify)
        yield lambda: _route_message(report)
