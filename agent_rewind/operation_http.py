"""Three frozen operation routes; services own authorization and durable effects."""

from __future__ import annotations

import hashlib
import re
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Request
from fastapi import Path as ApiPath
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from .admission_envelope import OriginCorrelation
from .admission_request import AdmissionPreparationError, parse_submit
from .admission_transaction import AdmissionError
from .auth import Auth
from .errors import ErrorCode, Fault, error_response
from .models import StrictModel, TaskSpec
from .request_authority import RequestAuthority
from .request_identity import IdentityInvalid
from .scoped_repositories import ProjectContext

_ID = "^[0-9a-f]{32}$"
_KEY = re.compile(rb"[A-Za-z0-9._:-]{8,128}")
_MEDIA = re.compile(
    rb'application/json(?:[ \t]*;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8"))?',
    re.IGNORECASE,
)
Status = Literal["queued", "running", "succeeded", "failed", "cancelled"]
Identifier = Annotated[str, Field(pattern=_ID)]
PathIdentifier = Annotated[str, ApiPath(json_schema_extra={"pattern": _ID})]


class OperationError(StrictModel):
    code: ErrorCode
    message: str = Field(max_length=300)
    request_id: Identifier
    retryable: bool


class Accepted(StrictModel):
    operation_id: Identifier
    job_id: Identifier


class Operation(StrictModel):
    id: Identifier
    project_id: Identifier
    job_id: Identifier
    client_operation_id: Identifier
    status: Status
    cancel_requested: bool
    result_run_id: Identifier | None
    budget_microusd: int = Field(ge=1)
    reserved_microusd: int = Field(ge=0)
    error: OperationError | None


class Cancellation(StrictModel):
    operation_id: Identifier
    cancel_requested: Literal[True]
    status: Status


def _values(request: Request, name: bytes) -> list[bytes]:
    return [value for key, value in request.scope["headers"] if key.lower() == name]


def _encoding(request: Request) -> None:
    values = _values(request, b"content-encoding")
    if len(values) > 1 or values and values[0].strip(b" \t").lower() != b"identity":
        raise Fault("invalid_request")


def _key(request: Request) -> str:
    values = _values(request, b"idempotency-key")
    if len(values) != 1 or _KEY.fullmatch(values[0]) is None:
        raise Fault("invalid_request")
    return hashlib.sha256(values[0]).hexdigest()


def _media(request: Request) -> None:
    values = _values(request, b"content-type")
    if len(values) != 1 or _MEDIA.fullmatch(values[0].strip(b" \t")) is None:
        raise Fault("invalid_request")


def _responses(success: int, *, conflict: bool = False) -> dict[int | str, dict[str, Any]]:
    common: dict[str, dict[str, Any]] = {
        "X-Request-ID": {"schema": {"type": "string", "pattern": _ID}},
        "Cache-Control": {"schema": {"type": "string", "const": "no-store"}},
    }
    result: dict[int | str, dict[str, Any]] = {success: {"headers": common}}
    for status in (401, 403, 404, 413, 422, 429, 500, 503, *((409,) if conflict else ())):
        headers = dict(common)
        if status == 401:
            headers["WWW-Authenticate"] = {"schema": {"type": "string", "const": "Bearer"}}
        if status == 429:
            headers["Retry-After"] = {"schema": {"type": "integer", "minimum": 1, "maximum": 60}}
        result[status] = {
            "model": OperationError,
            "description": "Fixed safe error response.",
            "headers": headers,
        }
    return result


class OperationAPI(FastAPI):
    """Keep raw-body OpenAPI metadata lazy and local to this application."""

    def openapi(self) -> dict[str, Any]:
        result = super().openapi()
        return _metadata(result)


def _metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Document raw SubmitRun parsing without adding eager body validation."""
    components = result.setdefault("components", {})
    definitions = components.setdefault("schemas", {})
    task = TaskSpec.model_json_schema()
    task["title"] = "TaskDefinition"
    for name in ("seed", "budget_usd"):
        task["properties"].pop(name)
    task["required"] = [name for name in task["required"] if name not in {"seed", "budget_usd"}]
    # TaskSpec enforces this cross-field limit in its semantic validator.
    task["properties"]["redact_patterns"]["items"]["maxLength"] = 120
    definitions["TaskDefinition"] = task
    # The frozen schema expresses this as const:true without a redundant type.
    definitions["Cancellation"]["properties"]["cancel_requested"].pop("type", None)
    definitions["SubmitRun"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "client_operation_id": {"type": "string", "pattern": _ID},
            "adapter_config_id": {"type": "string", "enum": ["native-v1"]},
            "task": {"$ref": "#/components/schemas/TaskDefinition"},
            "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647},
            "budget_microusd": {"type": "integer", "minimum": 1, "maximum": 200000000},
        },
        "required": [
            "client_operation_id",
            "adapter_config_id",
            "task",
            "seed",
            "budget_microusd",
        ],
    }
    security = components.setdefault("securitySchemes", {})
    security["serviceKey"] = {"type": "http", "scheme": "bearer"}
    security["sessionCookie"] = {"type": "apiKey", "in": "cookie", "name": "rewind_session"}
    return result


def register_operation_routes(app: FastAPI, *, auth: Auth, authority: RequestAuthority) -> None:
    """Register only operation HTTP adapters; dependencies remain per-app."""

    def named(request: Request, project_id: str, action: str) -> ProjectContext:
        authorization = _values(request, b"authorization")
        if len(authorization) > 1:
            raise IdentityInvalid()
        principal = auth.principal(request)
        request.state.principal = principal
        if (
            not authorization
            and request.method == "POST"
            and any(len(_values(request, name)) > 1 for name in (b"x-rewind-csrf", b"origin"))
        ):
            raise Fault("forbidden")
        return authority.named(principal.verified, project_id, action).context

    security: list[dict[str, list[str]]] = [{"serviceKey": []}, {"sessionCookie": []}]
    csrf = {
        "name": "X-Rewind-CSRF",
        "in": "header",
        "required": False,
        "schema": {"type": "string", "minLength": 1, "maxLength": 256},
    }

    @app.post(
        "/api/v1/projects/{project_id}/runs",
        operation_id="submitProjectRun",
        status_code=202,
        response_model=Accepted,
        responses=_responses(202, conflict=True),
        openapi_extra={
            "security": security,
            "x-minimum-role": "operator",
            "x-csrf-required-for-cookie-auth": True,
            "parameters": [
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {
                        "type": "string",
                        "minLength": 8,
                        "maxLength": 128,
                        "pattern": "^[A-Za-z0-9._:-]+$",
                    },
                },
                csrf,
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/SubmitRun"}}
                },
            },
        },
    )
    async def submit_project_run(
        request: Request, project_id: PathIdentifier
    ) -> Accepted | JSONResponse:
        context = await run_in_threadpool(named, request, project_id, "record")
        _encoding(request)
        if request.query_params.multi_items():
            raise Fault("invalid_request")
        _media(request)
        key_hash = _key(request)
        raw = await request.body()
        try:
            intent = await run_in_threadpool(parse_submit, raw)
        except AdmissionPreparationError as error:
            if error.code == "admission_invalid_input":
                raise Fault("invalid_request") from None
            if error.code == "admission_body_limit":
                return error_response(request.scope, "invalid_request", body_limit=True)
            if error.code == "admission_task_limit":
                return error_response(request.scope, "invalid_request", task_limit=True)
            raise
        origin = OriginCorrelation(request.scope["state"]["request_id"])
        try:
            value = await run_in_threadpool(
                app.state.operation_coordinator.submit,
                request.state.principal.verified,
                context,
                intent,
                key_hash,
                origin,
            )
        except AdmissionError as error:
            raise Fault(error.code) from None
        return Accepted.model_validate(value)

    @app.get(
        "/api/v1/projects/{project_id}/operations/{operation_id}",
        operation_id="getProjectOperation",
        response_model=Operation,
        responses=_responses(200),
        openapi_extra={
            "security": security,
            "x-minimum-role": "viewer",
            "x-csrf-required-for-cookie-auth": False,
        },
    )
    async def get_project_operation(
        request: Request, project_id: PathIdentifier, operation_id: PathIdentifier
    ) -> Operation:
        context = await run_in_threadpool(named, request, project_id, "read")
        _encoding(request)
        return Operation.model_validate(
            await run_in_threadpool(
                app.state.operation_service.read_operation,
                request.state.principal.verified,
                context,
                operation_id,
            )
        )

    @app.post(
        "/api/v1/projects/{project_id}/operations/{operation_id}/cancel",
        operation_id="cancelProjectOperation",
        status_code=202,
        response_model=Cancellation,
        responses=_responses(202),
        openapi_extra={
            "security": security,
            "x-minimum-role": "operator",
            "x-csrf-required-for-cookie-auth": True,
            "parameters": [csrf],
        },
    )
    async def cancel_project_operation(
        request: Request, project_id: PathIdentifier, operation_id: PathIdentifier
    ) -> Cancellation:
        context = await run_in_threadpool(named, request, project_id, "read")
        _encoding(request)
        return Cancellation.model_validate(
            await run_in_threadpool(
                app.state.operation_service.cancel_operation,
                request.state.principal.verified,
                context,
                operation_id,
            )
        )
