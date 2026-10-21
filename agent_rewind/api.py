from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Literal, TypeVar

from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint

from .artifact_metadata import ArtifactError, configure_artifact_engine
from .artifact_storage import LocalArtifactStorage
from .auth import Auth
from .config import Settings
from .database import Database
from .errors import ErrorCode, Fault, SafeBoundary, error_response, exception_response
from .legacy_admission import UnavailableAdmission, WorkAdmission, WorkKind
from .legacy_views import LegacyViews
from .middleware import BodyLimit
from .migrations.compatibility import CompatibilityResult
from .models import BranchRequest, StrictModel, StudyRequest, TaskSpec, valid_path
from .published_reader import PublishedRunReader
from .readiness import Readiness
from .request_authority import ProjectDecision, RequestAuthority
from .scoped_actions import ScopedActionError, ScopedActions

ProbeValue = TypeVar("ProbeValue")


class KeyRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    role: Literal["viewer", "operator"]
    days: int = Field(default=30, ge=1, le=90, strict=True)


class InvestigationRequest(StrictModel):
    run_id: str
    screening_trials: int = Field(default=8, ge=2, le=50)
    confirmation_trials: int = Field(default=30, ge=5, le=200)
    seed: int = Field(default=42, ge=0, le=2**31 - 100001)
    budget_usd: float = Field(default=200.0, gt=0, le=200)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    db = Database(settings)
    configure_artifact_engine(db.engine)
    auth = Auth(settings, db)
    authority = RequestAuthority(db.engine)
    actions = ScopedActions(db.engine, authority)
    reader = PublishedRunReader(
        db.engine,
        LocalArtifactStorage(settings.data_dir, auth.cipher, plaintext_limit=64 * 1024 * 1024),
    )
    if settings.storage != "local":
        # No raw S3 client, ambient credential discovery or local-file fallback.
        # The scoped remote storage adapter remains a separate delivery task.
        def unavailable_storage(value: Any) -> bytes:
            raise ArtifactError("artifact_storage_unsupported")

        reader.repositories.artifact_loader = unavailable_storage
    views = LegacyViews(reader, settings.workspace_mb * 1024 * 1024)
    admission: WorkAdmission = UnavailableAdmission()
    readiness = Readiness(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        readiness.start()
        try:
            yield
        finally:
            await readiness.close()

    app = FastAPI(
        title="Agent Rewind",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.db, app.state.auth = db, auth
    app.state.authority, app.state.actions = authority, actions
    app.state.reader, app.state.views = reader, views
    app.state.admission, app.state.readiness = admission, readiness
    app.add_middleware(BodyLimit)
    guard_inflight = 0
    guard_lock = Lock()

    async def database_probe(operation: Callable[[], ProbeValue]) -> ProbeValue | None:
        nonlocal guard_inflight
        # Keep capacity for sync liveness/static handlers. The lock also protects
        # completion in a worker after its requesting ASGI task was cancelled.
        limit = min(4, max(0, int(current_default_thread_limiter().total_tokens) - 1))
        with guard_lock:
            if guard_inflight >= limit:
                return None
            guard_inflight += 1
        started = False
        cancelled = False

        def probe() -> ProbeValue | None:
            nonlocal guard_inflight, started
            with guard_lock:
                if cancelled:
                    # A request cancelled while queued must not start database I/O.
                    return None
                started = True
            try:
                return operation()
            finally:
                with guard_lock:
                    guard_inflight -= 1

        try:
            return await run_in_threadpool(probe)
        finally:
            with guard_lock:
                if not started:
                    cancelled = True
                    guard_inflight -= 1
                # Once started, only the synchronous probe can release its slot.
                # Direct asyncio task cancellation can bypass AnyIO scope shielding.

    @app.middleware("http")
    async def security(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response
        safe_inspection = request.method in {"GET", "HEAD"} and (
            request.url.path in {"/", "/healthz", "/livez", "/readyz"}
            or request.url.path.startswith("/static/")
        )
        if not safe_inspection:
            compatibility = await database_probe(db.schema_compatibility)
            if compatibility is None:
                compatibility = CompatibilityResult("unavailable", "schema_probe_capacity")
            if compatibility.status != "ready":
                response = error_response(
                    request.scope,
                    "schema_incompatible"
                    if compatibility.status == "incompatible"
                    else "dependency_unavailable",
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    # Register last so this pure ASGI layer encloses body/security handlers.
    app.add_middleware(SafeBoundary)

    @app.exception_handler(StarletteHTTPException)
    @app.exception_handler(RequestValidationError)
    @app.exception_handler(Fault)
    async def safe_exception(request: Request, exc: Exception) -> JSONResponse:
        return exception_response(request.scope, exc)

    def decision(
        request: Request,
        action: str = "read",
        *,
        kind: str | None = None,
        resource_id: str | None = None,
    ) -> ProjectDecision:
        principal = auth.principal(request)
        request.state.principal = principal
        return authority.legacy(
            principal.verified, action, resource_kind=kind, resource_id=resource_id
        )

    async def admit(
        request: Request, kind: WorkKind, body: dict[str, Any], source_id: str | None = None
    ) -> dict[str, str]:
        action = {
            "run": "record",
            "branch": "branch",
            "study": "study",
            "investigate": "investigate",
        }[kind]
        context = (
            await run_in_threadpool(
                decision,
                request,
                action,
                kind="run" if source_id is not None else None,
                resource_id=source_id,
            )
        ).context
        # The absent adapter refuses BEFORE any artifact-readiness probe, upload,
        # enqueue, audit, credential creation or provider invocation.
        adapter: WorkAdmission = app.state.admission
        await run_in_threadpool(adapter.require_available)
        result = await readiness.check()
        if result != "ready":
            raise Fault(result)
        return {
            "job_id": await run_in_threadpool(
                adapter.admit, request.state.principal.verified, context, kind, body
            )
        }

    @app.exception_handler(ScopedActionError)
    async def action_exception(request: Request, exc: ScopedActionError) -> JSONResponse:
        codes: dict[str, ErrorCode] = {
            "action_invalid_input": "invalid_request",
            "action_unavailable": "dependency_unavailable",
            "outcome_uncertain": "outcome_uncertain",
        }
        code = codes.get(exc.code, "internal_error")
        return exception_response(request.scope, Fault(code))

    @app.api_route("/readyz", methods=["GET", "HEAD"])
    async def ready(request: Request) -> JSONResponse:
        result = await readiness.check()
        if result != "ready":
            return error_response(request.scope, result)
        return JSONResponse({"status": "ready"})

    @app.api_route("/livez", methods=["GET", "HEAD"])
    def liveness() -> dict[str, str]:
        return {"status": "live"}

    @app.api_route("/healthz", methods=["GET", "HEAD"])
    async def health() -> JSONResponse:
        # Preserve legacy database-connectivity semantics while operators migrate
        # probes. This is neither customer admission nor artifact/sentinel readiness.
        connected = await database_probe(db.ping)
        return JSONResponse(
            {"status": "ok" if connected else "unavailable"},
            status_code=200 if connected else 503,
        )

    @app.get("/auth/login")
    def login() -> RedirectResponse:
        return auth.login()

    @app.get("/auth/callback")
    def callback(request: Request) -> RedirectResponse:
        return auth.callback(request)

    @app.post("/auth/logout")
    def logout(request: Request) -> JSONResponse:
        # Cookie clearing ALWAYS validates that cookie's CSRF/Origin, even if a
        # bearer header is also supplied. Membership is deliberately irrelevant.
        auth.session(request)
        response = JSONResponse({"ok": True})
        response.delete_cookie("rewind_session")
        return response

    @app.get("/api/me")
    def me(request: Request) -> dict[str, str | None]:
        principal = auth.principal(request)
        return {
            "subject": principal.subject,
            "role": authority.legacy_role(principal.verified),
            "csrf": principal.csrf,
        }

    @app.get("/api/schema")
    def schema(request: Request) -> Any:
        context = decision(request).context
        result = app.openapi()
        authority.repositories.require_action(context, "read")
        return result

    @app.get("/api/runs")
    def runs(request: Request) -> Any:
        return views.runs(decision(request, "list").context)

    @app.get("/api/runs/{run_id}")
    def run(request: Request, run_id: str) -> Any:
        context = decision(request, kind="run", resource_id=run_id).context
        result = views.run(context, run_id)
        actions.record_run_read(request.state.principal.verified, context, run_id)
        return result

    @app.get("/api/runs/{run_id}/files/{step}")
    def files(request: Request, run_id: str, step: int, path: str | None = None) -> Any:
        context = decision(request, kind="run", resource_id=run_id).context
        if path is not None:
            try:
                valid_path(path)
            except ValueError:
                raise Fault("invalid_request") from None
        return views.files(context, run_id, step, path)

    @app.post("/api/runs", status_code=202)
    async def submit(request: Request, task: TaskSpec) -> dict[str, str]:
        return await admit(request, "run", task.model_dump())

    @app.post("/api/branches", status_code=202)
    async def branch(request: Request, value: BranchRequest) -> dict[str, str]:
        return await admit(request, "branch", value.model_dump(), value.parent_id)

    @app.post("/api/studies", status_code=202)
    async def study(request: Request, value: StudyRequest) -> dict[str, str]:
        return await admit(request, "study", value.model_dump(), value.run_id)

    @app.post("/api/investigations", status_code=202)
    async def investigate(request: Request, value: InvestigationRequest) -> dict[str, str]:
        return await admit(request, "investigate", value.model_dump(), value.run_id)

    @app.get("/api/compare")
    def compare_runs(request: Request, left: str, right: str) -> dict[str, Any]:
        context = decision(request, kind="run", resource_id=left).context
        return views.compare(context, left, right)

    @app.get("/api/studies")
    def studies(request: Request) -> Any:
        return views.studies(decision(request, "list").context)

    @app.get("/api/studies/{study_id}")
    def get_study(request: Request, study_id: str) -> Any:
        return views.study(decision(request, kind="study", resource_id=study_id).context, study_id)

    @app.get("/api/jobs")
    def get_jobs(request: Request) -> Any:
        return views.jobs(decision(request, "list").context)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(request: Request, job_id: str) -> dict[str, bool]:
        context = decision(request, "cancel", kind="job", resource_id=job_id).context
        actions.cancel(request.state.principal.verified, context, job_id)
        return {"ok": True}

    @app.post("/api/keys", status_code=201)
    def issue_key(request: Request, value: KeyRequest) -> dict[str, str]:
        context = decision(request, "create_key").context
        issued = actions.issue_key(
            request.state.principal.verified,
            context,
            role=value.role,
            name=value.name,
            days=value.days,
        )
        return {"id": issued.id, "token": issued.token, "role": issued.role}

    @app.delete("/api/keys/{key_id}")
    def revoke_key(request: Request, key_id: str) -> dict[str, bool]:
        context = decision(request, "revoke_key", kind="key", resource_id=key_id).context
        actions.revoke_key(request.state.principal.verified, context, key_id)
        return {"ok": True}

    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(web / "index.html")

    return app
