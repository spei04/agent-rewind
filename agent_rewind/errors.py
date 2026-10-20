"""Fixed public faults and a trusted request boundary without exception serialization."""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from typing import Literal

from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ErrorCode = Literal[
    "invalid_request",
    "unauthenticated",
    "forbidden",
    "not_found",
    "invalid_cursor",
    "idempotency_conflict",
    "budget_exhausted",
    "quota_exceeded",
    "dependency_unavailable",
    "schema_incompatible",
    "internal_error",
    "outcome_uncertain",
]
RULES: dict[ErrorCode, tuple[int, str, bool]] = {
    "invalid_request": (422, "Request does not match the supported input contract.", False),
    "unauthenticated": (401, "Authentication is required.", False),
    "forbidden": (403, "This action is not permitted.", False),
    "not_found": (404, "Resource not found.", False),
    "invalid_cursor": (422, "Cursor is invalid for this request.", False),
    "idempotency_conflict": (409, "Request identity was already used with different input.", False),
    "budget_exhausted": (409, "The permitted budget is exhausted.", False),
    "quota_exceeded": (429, "Admission quota is temporarily exceeded.", True),
    "dependency_unavailable": (503, "A required service is temporarily unavailable.", True),
    "schema_incompatible": (503, "Service schema is not compatible with this release.", False),
    "internal_error": (500, "The request could not be completed.", False),
    "outcome_uncertain": (
        503,
        "The operation outcome is not yet known; reconcile the original request.",
        False,
    ),
}


@dataclass(frozen=True)
class Fault(Exception):
    code: ErrorCode

    def __post_init__(self) -> None:
        if type(self.code) is not str or self.code not in RULES:
            object.__setattr__(self, "code", "internal_error")


def error_response(scope: Scope, code: ErrorCode, *, body_limit: bool = False) -> JSONResponse:
    status, message, retryable = RULES[code]
    if body_limit:
        status, message = 413, "Request body exceeds 9 MiB."
    identifier = scope["state"]["request_id"]
    headers = {"X-Request-ID": identifier, "Cache-Control": "no-store"}
    if code == "unauthenticated":
        headers["WWW-Authenticate"] = "Bearer"
    if code == "quota_exceeded":
        headers["Retry-After"] = "5"
    if scope["path"].startswith("/api/v1/") or scope["path"] == "/readyz":
        body = {"code": code, "message": message, "request_id": identifier, "retryable": retryable}
    else:
        body = {"detail": message}
    return JSONResponse(body, status_code=status, headers=headers)


def classified(scope: Scope, error: Exception) -> ErrorCode:
    if isinstance(error, Fault) and error.code in RULES:
        return error.code
    if isinstance(error, RequestValidationError):
        return "invalid_request"
    if isinstance(error, HTTPException):
        statuses: dict[int, ErrorCode] = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            422: "invalid_request",
            429: "quota_exceeded",
            503: "dependency_unavailable",
        }
        return (
            statuses.get(error.status_code, "internal_error")
            if type(error.status_code) is int
            else "internal_error"
        )
    if isinstance(error, SQLAlchemyError):
        # A mutation may already have committed. Never promise an automatic retry.
        return (
            "dependency_unavailable"
            if scope["method"] in {"GET", "HEAD", "OPTIONS"}
            else "outcome_uncertain"
        )
    return "internal_error"


def diagnostic(scope: Scope, code: ErrorCode) -> None:
    # The complete record is built from finite/generated values, never exc_info,
    # exception type names, request paths/headers/bodies or exception attributes.
    identifier = scope["state"]["request_id"]
    record = {"event": "request_failed", "request_id": identifier, "error_code": code}
    try:
        # The default formatter emits message text: correlation must live in it,
        # not only in optional structured-handler attributes.
        logging.getLogger("agent_rewind.safe").error(
            json.dumps(record, separators=(",", ":")),
            extra={"request_id": identifier, "error_code": code},
        )
    except Exception:
        # A failed sink loses this bounded diagnostic. Never log its exception or
        # replace the safe HTTP result with a second, potentially private failure.
        return


def exception_response(scope: Scope, error: Exception) -> JSONResponse:
    # Existing legacy endpoints retain status semantics without inventing v1 codes.
    if (
        isinstance(error, HTTPException)
        and type(error.status_code) is int
        and error.status_code in {405, 409}
        and not scope["path"].startswith("/api/v1/")
    ):
        return JSONResponse(
            {"detail": "The request conflicts with the supported operation."},
            status_code=error.status_code,
        )
    code = classified(scope, error)
    if RULES[code][0] >= 500:
        diagnostic(scope, code)
    return error_response(scope, code)


class SafeBoundary:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        identifier = secrets.token_hex(16)
        scope.setdefault("state", {})["request_id"] = identifier
        started = False

        async def correlated(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in {b"x-request-id", b"cache-control"}
                ]
                message = {
                    **message,
                    "headers": headers
                    + [(b"x-request-id", identifier.encode()), (b"cache-control", b"no-store")],
                }
            await send(message)

        try:
            await self.app(scope, receive, correlated)
        except Exception as error:
            if started:
                # A streamed response cannot be replaced after headers. Do not
                # propagate a secret-bearing traceback into the server logger.
                diagnostic(scope, "internal_error")
                return
            await exception_response(scope, error)(scope, receive, correlated)
