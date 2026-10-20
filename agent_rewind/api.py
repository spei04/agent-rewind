from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from .artifacts import Artifacts
from .auth import Auth
from .compare import compare
from .config import Settings
from .database import Database
from .engine import read_events
from .experiments import locate
from .middleware import BodyLimit
from .migrations.compatibility import CompatibilityResult
from .models import BranchRequest, StrictModel, StudyRequest, TaskSpec, valid_path


class KeyRequest(StrictModel):
    name: str
    role: Literal["viewer", "operator", "administrator"]
    days: int = Field(default=30, ge=1, le=90)


class InvestigationRequest(StrictModel):
    run_id: str
    screening_trials: int = Field(default=8, ge=2, le=50)
    confirmation_trials: int = Field(default=30, ge=5, le=200)
    seed: int = Field(default=42, ge=0, le=2**31 - 100001)
    budget_usd: float = Field(default=200.0, gt=0, le=200)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    db, artifacts = Database(settings), Artifacts(settings)
    auth = Auth(settings, db)
    app = FastAPI(
        title="Agent Rewind", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.db, app.state.artifacts, app.state.auth = db, artifacts, auth
    app.add_middleware(BodyLimit)
    guard_inflight = 0

    async def admission_status() -> CompatibilityResult:
        nonlocal guard_inflight
        # Keep capacity for sync liveness/static handlers. This counter is touched
        # only on the app event loop, with no await between admission and increment.
        limit = min(4, max(0, int(current_default_thread_limiter().total_tokens) - 1))
        if guard_inflight >= limit:
            return CompatibilityResult("unavailable", "schema_probe_capacity")
        guard_inflight += 1
        try:
            # The framework shields this bounded worker slot until its call returns;
            # cancellation must not abandon a probe and free its admission slot early.
            return await run_in_threadpool(db.schema_compatibility)
        finally:
            guard_inflight -= 1

    @app.middleware("http")
    async def security(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response
        safe_inspection = request.method in {"GET", "HEAD"} and (
            request.url.path in {"/", "/healthz"} or request.url.path.startswith("/static/")
        )
        if not safe_inspection:
            compatibility = await admission_status()
            if compatibility.status != "ready":
                response = JSONResponse(
                    {
                        "detail": "Customer access is unavailable for this database schema.",
                        "code": compatibility.code,
                    },
                    status_code=503,
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

    @app.exception_handler(KeyError)
    async def not_found(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": "Record not found."}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo submitted payloads, which can contain private source or credentials.
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}, status_code=422
        )

    @app.get("/healthz")
    def health() -> dict[str, str]:
        # Process liveness only. Schema compatibility is checked at each customer
        # boundary; full storage/sentinel readiness belongs to a later slice.
        return {"status": "ok"}

    @app.get("/auth/login")
    def login() -> RedirectResponse:
        return auth.login()

    @app.get("/auth/callback")
    def callback(request: Request) -> RedirectResponse:
        return auth.callback(request)

    @app.post("/auth/logout")
    def logout(request: Request) -> JSONResponse:
        auth.principal(request)
        response = JSONResponse({"ok": True})
        response.delete_cookie("rewind_session")
        return response

    @app.get("/api/me")
    def me(request: Request) -> dict[str, str]:
        principal = auth.principal(request)
        return {"subject": principal.subject, "role": principal.role, "csrf": principal.csrf}

    @app.get("/api/schema")
    def schema(request: Request) -> Any:
        auth.principal(request)
        return app.openapi()

    @app.get("/api/runs")
    def runs(request: Request) -> Any:
        auth.principal(request)
        return db.list_records("run")

    @app.get("/api/runs/{run_id}")
    def run(request: Request, run_id: str) -> Any:
        auth.principal(request)
        result = db.get(run_id, "run")
        result["events"] = read_events(db, artifacts, run_id)
        result["locations"] = locate(result["events"])
        if result.get("evaluation_ref"):
            result["evaluation"] = artifacts.json(result["evaluation_ref"])
        db.audit(auth.principal(request).subject, "run.read", run_id)
        return result

    @app.get("/api/runs/{run_id}/files/{step}")
    def files(request: Request, run_id: str, step: int, path: str | None = None) -> Any:
        auth.principal(request)
        history = read_events(db, artifacts, run_id)
        if not 1 <= step <= len(history):
            raise HTTPException(404, "Decision not found.")
        snapshot = artifacts.json(history[step - 1]["checkpoint"])
        workspace = artifacts.workspace(snapshot["workspace"], settings.workspace_mb * 1024 * 1024)
        if path is None:
            return [
                {"path": p, "bytes": len(f.data), "mode": oct(f.mode)}
                for p, f in sorted(workspace.items())
            ]
        valid_path(path)
        if path not in workspace:
            raise HTTPException(404, "File not found.")
        return {
            "path": path,
            "content": workspace[path].data[:100000].decode("utf-8", errors="replace"),
            "truncated": len(workspace[path].data) > 100000,
        }

    @app.post("/api/runs", status_code=202)
    def submit(request: Request, task: TaskSpec) -> dict[str, str]:
        actor = auth.principal(request, "operator")
        return {
            "job_id": db.enqueue(
                "run", artifacts.put_json(task.model_dump()), task.budget_usd, actor.subject
            )
        }

    @app.post("/api/branches", status_code=202)
    def branch(request: Request, value: BranchRequest) -> dict[str, str]:
        actor = auth.principal(request, "operator")
        source = db.get(value.parent_id, "run")
        if source["status"] != "complete" or not source["branchable"]:
            raise HTTPException(409, "Source run is not branchable.")
        return {
            "job_id": db.enqueue(
                "branch", artifacts.put_json(value.model_dump()), value.budget_usd, actor.subject
            )
        }

    @app.post("/api/studies", status_code=202)
    def study(request: Request, value: StudyRequest) -> dict[str, str]:
        actor = auth.principal(request, "operator")
        db.get(value.run_id, "run")
        return {
            "job_id": db.enqueue(
                "study", artifacts.put_json(value.model_dump()), value.budget_usd, actor.subject
            )
        }

    @app.post("/api/investigations", status_code=202)
    def investigate(request: Request, value: InvestigationRequest) -> dict[str, str]:
        actor = auth.principal(request, "operator")
        db.get(value.run_id, "run")
        return {
            "job_id": db.enqueue(
                "investigate",
                artifacts.put_json(value.model_dump()),
                value.budget_usd,
                actor.subject,
            )
        }

    @app.get("/api/compare")
    def compare_runs(request: Request, left: str, right: str) -> dict[str, Any]:
        auth.principal(request)
        return compare(db, artifacts, left, right, settings.workspace_mb * 1024 * 1024)

    @app.get("/api/studies")
    def studies(request: Request) -> Any:
        auth.principal(request)
        return db.list_records("study")

    @app.get("/api/studies/{study_id}")
    def get_study(request: Request, study_id: str) -> Any:
        auth.principal(request)
        return db.get(study_id, "study")

    @app.get("/api/jobs")
    def get_jobs(request: Request) -> Any:
        auth.principal(request)
        result = db.list_jobs()
        for job in result:
            if job["result"]:
                job["result"] = artifacts.json(job["result"])
        return result

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(request: Request, job_id: str) -> dict[str, bool]:
        actor = auth.principal(request, "operator")
        db.cancel(job_id, actor.subject)
        return {"ok": True}

    @app.post("/api/keys", status_code=201)
    def issue_key(request: Request, value: KeyRequest) -> dict[str, str]:
        actor = auth.principal(request, "administrator")
        return auth.issue(value.role, value.name, value.days, actor.subject)

    @app.delete("/api/keys/{key_id}")
    def revoke_key(request: Request, key_id: str) -> dict[str, bool]:
        actor = auth.principal(request, "administrator")
        db.revoke_key(key_id, actor.subject)
        return {"ok": True}

    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(web / "index.html")

    return app
