"""Run with the isolated runtime interpreter from outside the source checkout."""

import importlib.metadata
import importlib.resources
import json
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

import agent_rewind
import agent_rewind.api
import agent_rewind.cli
import agent_rewind.scoped_artifacts
from agent_rewind.artifact_metadata import configure_artifact_engine
from agent_rewind.migrations.compatibility import runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.service import install, schema_status
from agent_rewind.run_projection import utc_created
from agent_rewind.scoped_repositories import ProjectContext, ResourceNotFound, ScopedRepositories


def operation_components_smoke(root: Path) -> None:
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from agent_rewind.admission_coordinator import AdmissionCoordinator
    from agent_rewind.admission_transaction import AdmissionError
    from agent_rewind.config import Settings
    from agent_rewind.database import Database
    from agent_rewind.operation_reads import ReceiptBook
    from agent_rewind.operation_work import OperationWork, operation_connection
    from agent_rewind.request_authority import RequestAuthority
    from agent_rewind.request_identity import VerifiedPrincipal
    from agent_rewind.scoped_repositories import ProjectContext
    from agent_rewind.sqlite_ownership import (
        create_owned_sqlite_engine,
        owned_begin,
        owned_connect,
        require_owned_sqlite,
    )

    # File-backed Database uses owned connections; the real schema guard still
    # refuses customer admission. No service/profile readiness is implied.
    ReceiptBook()
    database = Database(
        Settings(
            _env_file=None,
            data_dir=root / "default",
            database_url=f"sqlite:///{root / 'default.sqlite'}",
            encryption_key=SecretStr(Fernet.generate_key().decode()),
            bootstrap_key=SecretStr("synthetic-package-bootstrap-default-factory"),
        )
    )
    try:
        require_owned_sqlite(database.engine)
        database.migrate(installation_key="synthetic-owned-package")
        observed = database.schema_compatibility()
        if (observed.status, observed.code) != ("incompatible", "migration_only"):
            raise RuntimeError("Owned Database changed the real migration-only guard")
        if not database.ping():
            raise RuntimeError("Owned Database connectivity failed")
        record = database.add("example", {"value": "synthetic-package"})
        if database.get(record)["value"] != "synthetic-package":
            raise RuntimeError("Installed owned Database changed ordinary records")
        database.audit("synthetic-package", "example.read", record)
        principal = VerifiedPrincipal("oidc:" + "a" * 64)
        context = ProjectContext("8" * 32, "9" * 32, principal.principal_id)
        coordinator = AdmissionCoordinator(database.engine, RequestAuthority(database.engine))
        try:
            coordinator.reconcile(principal, context, "1" * 32, "2" * 64, "3" * 64)
        except AdmissionError as error:
            if error.code != "schema_incompatible":
                raise RuntimeError("Owned factory changed customer admission refusal") from None
        else:
            raise RuntimeError("Owned factory enabled customer admission")
        with owned_connect(database.engine) as connection:
            if connection.exec_driver_sql("SELECT count(*) FROM jobs").scalar_one() != 0:
                raise RuntimeError("Owned factory guard created a job")
            if connection.exec_driver_sql("SELECT count(*) FROM audit").scalar_one() != 1:
                raise RuntimeError("Owned factory guard changed audit")
            if connection.exec_driver_sql("PRAGMA query_only").scalar_one() != 0:
                raise RuntimeError("Owned inspection leaked read-only state")
        if database.engine.pool.checkedout() != 0:
            raise RuntimeError("Owned Database leaked a checkout")
    finally:
        database.engine.dispose()

    engine = create_owned_sqlite_engine(
        f"sqlite:///{root / 'owned.sqlite'}", pool_size=1, max_overflow=0
    )
    try:
        with owned_begin(engine) as connection:
            connection.exec_driver_sql("CREATE TABLE proof (id INTEGER)")
            connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
        work = OperationWork()
        with operation_connection(engine, work) as connection:
            if connection.exec_driver_sql("SELECT id FROM proof").scalar_one() != 1:
                raise RuntimeError("Installed owned read changed synthetic data")
        if work.statements <= 0 or work._started is not None:
            raise RuntimeError("Installed operation work lost accounting or cleanup")
        try:
            with operation_connection(engine, OperationWork()) as connection:
                connection.exec_driver_sql("INSERT INTO proof VALUES(2)")
        except AdmissionError as error:
            if error.code != "dependency_unavailable":
                raise RuntimeError("Installed read-only refusal changed") from None
        else:
            raise RuntimeError("Installed operation read allowed a write")
        with owned_connect(engine) as connection:
            if connection.exec_driver_sql("SELECT count(*) FROM proof").scalar_one() != 1:
                raise RuntimeError("Installed denied read scope changed data")
    finally:
        engine.dispose()


def operation_service_smoke(root: Path) -> None:
    """Synthetic installed service behavior; no HTTP or customer-ready profile."""
    import hashlib
    from datetime import UTC, datetime

    from cryptography.fernet import Fernet
    from sqlalchemy import text

    from agent_rewind.artifact_metadata import (
        ArtifactObject,
        configure_artifact_engine,
        object_locator,
        record_verified,
        register_ref,
    )
    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.database import records
    from agent_rewind.errors import Fault
    from agent_rewind.migrations.admission_service import initialize_admission
    from agent_rewind.migrations.artifact_service import initialize_artifacts
    from agent_rewind.migrations.compatibility import CompatibilityResult
    from agent_rewind.migrations.ownership_service import initialize_ownership
    from agent_rewind.migrations.projection_service import initialize_projection
    from agent_rewind.migrations.service import install
    from agent_rewind.models import canonical
    from agent_rewind.operation_service import OperationService
    from agent_rewind.request_authority import ActionForbidden, RequestAuthority
    from agent_rewind.request_identity import VerifiedPrincipal
    from agent_rewind.scoped_repositories import ResourceNotFound
    from agent_rewind.sqlite_ownership import (
        create_owned_sqlite_engine,
        owned_begin,
        owned_connect,
    )

    project, job, operation, run = "9" * 32, "2" * 32, "3" * 32, "4" * 32
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    viewer = VerifiedPrincipal("oidc:" + "b" * 64)
    engines = []

    def database(name):
        engine = create_owned_sqlite_engine(
            f"sqlite:///{root / (name + '.sqlite')}", pool_size=1, max_overflow=0
        )
        engines.append(engine)
        configure_artifact_engine(engine)
        install(engine, name)
        initialize_ownership(
            engine,
            {
                "schema_version": 1,
                "installation_key": name,
                "organization_id": "8" * 32,
                "project_id": project,
                "project_name": "Synthetic installed operation service",
                "principal_grants": [
                    {
                        "principal_id": principal.principal_id,
                        "role": "maintainer",
                        "legacy_default": False,
                    }
                ],
            },
        )
        initialize_artifacts(engine)
        initialize_projection(engine)
        initialize_admission(engine)
        return engine

    def descriptor(content, identifier):
        digest = hashlib.sha256(content).hexdigest()
        return ArtifactObject(
            identifier,
            project,
            digest,
            object_locator(project, digest),
            1,
            len(content),
            datetime(2026, 10, 21, tzinfo=UTC),
        )

    def fixed_failure(call, code):
        try:
            call()
        except Fault as error:
            if (
                error.code != code
                or str(error) != code
                or not error.__suppress_context__
                or error.__cause__ is not None
            ):
                raise RuntimeError("Installed service changed fixed failure") from None
        else:
            raise RuntimeError("Installed service unexpectedly accepted refused evidence")

    try:
        engine = database("operation-positive")
        guard_engine = database("operation-real-guard")
        authority = RequestAuthority(engine)
        context = authority.named(principal, project).context
        guard_authority = RequestAuthority(guard_engine)
        guard_context = guard_authority.named(principal, project).context
        guarded = OperationService(guard_engine, guard_authority)

        def forbidden_loader(_value):
            raise RuntimeError("Installed cancellation or guard attempted artifact I/O")

        guarded.artifact_loader = forbidden_loader

        def real_guard():
            observed = guarded.schema_compatibility()
            if (observed.status, observed.code) != ("incompatible", "migration_only"):
                raise RuntimeError("Installed operation guard is not real migration-only")
            for method in (guarded.read_operation, guarded.cancel_operation):
                fixed_failure(
                    lambda method=method: method(principal, guard_context, operation),
                    "schema_incompatible",
                )
            with owned_connect(guard_engine) as connection:
                counts = connection.exec_driver_sql(
                    "SELECT (SELECT count(*) FROM jobs),(SELECT count(*) FROM audit)"
                ).one()
            if tuple(counts) != (0, 0) or guard_engine.pool.checkedout() != 0:
                raise RuntimeError("Installed guarded service changed rows or retained a checkout")

        real_guard()
        service = OperationService(engine, authority)
        # Only this instance accepts the explicitly seeded synthetic row shape.
        # The descriptor is metadata evidence, not a new-work admission proof.
        service.schema_compatibility = lambda: CompatibilityResult("ready", "ready")
        service.artifact_loader = forbidden_loader
        configuration = descriptor(canonical({"synthetic": "configuration"}), "5" * 32)
        with owned_begin(engine) as connection:
            connection.execute(
                text(
                    "INSERT INTO jobs(id,kind,created,payload,status,owner,lease_until,cancel,"
                    "budget,reserved,result,error,actor,payload_version,execution_config_ref,"
                    "execution_config_digest) VALUES(:job,'run',1700000000.125,:payload,'queued',"
                    "'preserved-worker',1900000000,false,7,:reserved,NULL,NULL,:actor,2,:config,:config)"
                ),
                {
                    "job": job,
                    "payload": "6" * 64,
                    "reserved": 2**53 + 1,
                    "actor": principal.principal_id,
                    "config": configuration.digest,
                },
            )
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('job',:job,:project)"),
                {"job": job, "project": project},
            )
            record_verified(connection, configuration)
            register_ref(
                connection,
                project_id=project,
                owner_kind="job",
                owner_id=job,
                role="admission_config",
                artifact_id=configuration.id,
            )
            connection.execute(
                text(
                    "INSERT INTO operations(id,project_id,principal_id,kind,client_operation_id,"
                    "request_digest,job_id,accepted_response,created_at,retain_until,"
                    "job_resource_kind,execution_config_digest,payload_version,"
                    "failure_correlation_id) VALUES(:operation,:project,:principal,'run',:client,"
                    ":request,:job,:accepted,'2026-10-21T00:00:00+00:00',"
                    "'2027-01-21T00:00:00+00:00','job',:config,2,:origin)"
                ),
                {
                    "operation": operation,
                    "project": project,
                    "principal": principal.principal_id,
                    "client": "7" * 32,
                    "request": "8" * 64,
                    "job": job,
                    "accepted": canonical({"operation_id": operation, "job_id": job}).decode(),
                    "config": configuration.digest,
                    "origin": "a" * 32,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO project_memberships VALUES(:project,:viewer,'viewer',NULL,false)"
                ),
                {"project": project, "viewer": viewer.principal_id},
            )
        viewer_context = authority.named(viewer, project).context

        def snapshot():
            with owned_connect(engine) as connection:
                row = dict(connection.exec_driver_sql("SELECT * FROM jobs").mappings().one())
                original = dict(
                    connection.exec_driver_sql("SELECT * FROM operations").mappings().one()
                )
                audits = connection.exec_driver_sql(
                    "SELECT actor,action,target FROM audit ORDER BY id"
                ).all()
            return row, original, [tuple(item) for item in audits]

        before = snapshot()
        expected = {
            "id": operation,
            "project_id": project,
            "job_id": job,
            "client_operation_id": "7" * 32,
            "status": "queued",
            "cancel_requested": False,
            "result_run_id": None,
            "budget_microusd": 7,
            "reserved_microusd": 2**53 + 1,
            "error": None,
        }
        observed = service.read_operation(viewer, viewer_context, operation)
        if (
            observed != expected
            or observed["cancel_requested"] is not False
            or type(observed["budget_microusd"]) is not int
            or type(observed["reserved_microusd"]) is not int
        ):
            raise RuntimeError("Installed viewer GET changed required nulls, false or integers")
        try:
            service.cancel_operation(viewer, viewer_context, operation)
        except ActionForbidden:
            pass
        else:
            raise RuntimeError("Installed viewer cancelled an operation")
        if snapshot() != before:
            raise RuntimeError("Installed GET or denied cancellation mutated metadata")
        cancelled = {"operation_id": operation, "cancel_requested": True, "status": "cancelled"}
        for _ in range(2):
            response = service.cancel_operation(principal, context, operation)
            if response != cancelled or response["cancel_requested"] is not True:
                raise RuntimeError("Installed cancellation changed its captured response")
        after = snapshot()
        if after != (
            {**before[0], "cancel": 1, "status": "cancelled"},
            before[1],
            [(principal.principal_id, "job.cancel", job)] * 2,
        ):
            raise RuntimeError("Installed cancellation changed preserved rows or repeated audit")

        body = canonical({"run_id": run})
        result = descriptor(body, "b" * 32)
        storage_root = root / "operation-encrypted"
        storage_root.mkdir(mode=0o700)
        storage = LocalArtifactStorage(
            storage_root, Fernet(Fernet.generate_key()), plaintext_limit=4096
        )
        storage.put_verified(result, body)
        with owned_begin(engine) as connection:
            connection.execute(
                records.insert(),
                {
                    "id": run,
                    "kind": "run",
                    "created": 1700000000.125,
                    "data": {"job_id": job, "parent_id": None, "success": False},
                },
            )
            connection.execute(
                text("INSERT INTO resource_scopes VALUES('run',:run,:project)"),
                {"run": run, "project": project},
            )
            record_verified(connection, result)
            register_ref(
                connection,
                project_id=project,
                owner_kind="job",
                owner_id=job,
                role="result",
                artifact_id=result.id,
            )
            connection.execute(
                text("UPDATE jobs SET status='succeeded',result=:result WHERE id=:job"),
                {"result": result.digest, "job": job},
            )
        loads = []

        def load(value):
            if engine.pool.checkedout() != 0 or value != result:
                raise RuntimeError("Installed GET loaded under SQL or changed descriptor")
            loads.append(value)
            return storage.read_verified(value)

        service.artifact_loader = load
        published = snapshot()
        if (
            service.read_operation(principal, context, operation)
            != {
                **expected,
                "status": "succeeded",
                "cancel_requested": True,
                "result_run_id": run,
            }
            or loads != [result]
            or snapshot() != published
        ):
            raise RuntimeError("Installed verified result GET changed execution status or metadata")
        with owned_begin(engine) as connection:
            connection.execute(text("UPDATE jobs SET error='private-legacy-canary'"))
        fixed_failure(
            lambda: service.read_operation(principal, context, operation), "dependency_unavailable"
        )
        if loads != [result]:
            raise RuntimeError("Installed unsupported failure loaded result bytes")
        service.artifact_loader = forbidden_loader
        terminal = snapshot()
        if service.cancel_operation(principal, context, operation) != {
            **cancelled,
            "status": "succeeded",
        }:
            raise RuntimeError("Installed terminal cancellation changed status")
        if snapshot() != (
            terminal[0],
            terminal[1],
            [(principal.principal_id, "job.cancel", job)] * 3,
        ):
            raise RuntimeError("Installed terminal cancellation changed legacy outcome")
        with owned_begin(engine) as connection:
            connection.execute(
                text(
                    "UPDATE project_memberships SET revoked_at='2026-10-21T00:00:00+00:00' "
                    "WHERE principal_id=:viewer"
                ),
                {"viewer": viewer.principal_id},
            )
        try:
            service.read_operation(viewer, viewer_context, operation)
        except ResourceNotFound:
            pass
        else:
            raise RuntimeError("Installed GET retained revoked viewer authority")
        if engine.pool.checkedout() != 0:
            raise RuntimeError("Installed operation service leaked a checkout")
        real_guard()  # The synthetic instance did not alter another instance's guard.
    finally:
        for engine in engines:
            engine.dispose()
    print("operation_service_installed_smoke_verified")


def operation_http_smoke(root: Path) -> None:
    """Installed real transport over explicit synthetic adapters; guard stays real."""
    import asyncio
    import hashlib

    import httpx
    from cryptography.fernet import Fernet
    from pydantic import SecretStr
    from sqlalchemy import text

    from agent_rewind.admission_adapters import AdmissionReady, ProcessorPermission
    from agent_rewind.admission_configuration import (
        SEED_STRATEGY,
        NativeConfiguration,
        NativeRegistry,
    )
    from agent_rewind.admission_coordinator import AdmissionCoordinator
    from agent_rewind.admission_journal import AdmissionJournal
    from agent_rewind.admission_transaction import AdmissionError
    from agent_rewind.api import create_app
    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.config import Settings
    from agent_rewind.migrations.admission_service import initialize_admission
    from agent_rewind.migrations.artifact_service import initialize_artifacts
    from agent_rewind.migrations.compatibility import CompatibilityResult
    from agent_rewind.migrations.ownership_service import initialize_ownership
    from agent_rewind.migrations.projection_service import initialize_projection
    from agent_rewind.migrations.service import install
    from agent_rewind.models import canonical
    from agent_rewind.request_identity import SessionIdentity, VerifiedPrincipal, encode_v2_session
    from agent_rewind.sqlite_ownership import owned_connect

    project, organization = "9" * 32, "8" * 32
    issuer, subject, csrf = "https://installed-operation.invalid", "synthetic", "c" * 32
    principal = VerifiedPrincipal.oidc(issuer, subject)
    applications = []

    def application(name):
        settings = Settings(
            _env_file=None,
            data_dir=root / name,
            database_url=f"sqlite:///{root / (name + '.sqlite')}",
            encryption_key=SecretStr(Fernet.generate_key().decode()),
            bootstrap_key=SecretStr("synthetic-package-operation-http-bootstrap"),
            oidc_issuer=issuer,
        )
        app = create_app(settings)
        applications.append(app)
        engine = app.state.db.engine
        install(engine, name)
        initialize_ownership(
            engine,
            {
                "schema_version": 1,
                "installation_key": name,
                "organization_id": organization,
                "project_id": project,
                "project_name": "Synthetic HTTP package",
                "principal_grants": [
                    {
                        "principal_id": principal.principal_id,
                        "role": "maintainer",
                        "legacy_default": False,
                    }
                ],
            },
        )
        initialize_artifacts(engine)
        initialize_projection(engine)
        initialize_admission(engine)
        token = encode_v2_session(
            app.state.auth.cipher, SessionIdentity(principal, issuer, subject, csrf)
        )
        headers = {
            "Cookie": "rewind_session=" + token,
            "X-Rewind-CSRF": csrf,
            "Origin": settings.public_url.rstrip("/"),
            "Content-Type": "application/json",
            "Idempotency-Key": "installed-http-key",
        }
        return app, headers

    raw = canonical(
        {
            "client_operation_id": "7" * 32,
            "adapter_config_id": "native-v1",
            "seed": 0,
            "budget_microusd": 1,
            "task": {
                "name": "synthetic-installed-http",
                "instruction": "No external execution.",
                "image": "synthetic-image",
                "files": {"main.py": ""},
                "evaluator_files": {"check.py": ""},
                "evaluator_command": "true",
            },
        }
    )

    def response_check(response, status, code=None):
        if response.status_code != status:
            raise RuntimeError("Installed operation HTTP changed response status")
        value = response.json()
        request_id = response.headers.get("x-request-id", "")
        if (
            len(request_id) != 32
            or any(char not in "0123456789abcdef" for char in request_id)
            or response.headers.get("cache-control") != "no-store"
        ):
            raise RuntimeError("Installed operation HTTP lost safe response headers")
        if code is not None and (
            set(value) != {"code", "message", "request_id", "retryable"}
            or value["code"] != code
            or value["request_id"] != request_id
        ):
            raise RuntimeError("Installed operation HTTP changed the finite error envelope")
        return value

    async def run():
        app, headers = application("operation-http-positive")
        guarded, guard_headers = application("operation-http-real-guard")
        engine = app.state.db.engine
        base = f"/api/v1/projects/{project}"
        guarded_paths = [
            ("POST", base + "/runs"),
            ("GET", base + "/operations/" + "0" * 32),
            ("POST", base + "/operations/" + "0" * 32 + "/cancel"),
        ]

        def guard_refusal(*_args):
            raise RuntimeError("Installed real schema guard reached an HTTP route")

        guarded.state.auth.principal = guard_refusal

        def guard_state():
            with owned_connect(guarded.state.db.engine) as connection:
                return tuple(
                    connection.exec_driver_sql(
                        "SELECT (SELECT count(*) FROM jobs),(SELECT count(*) FROM audit),"
                        "(SELECT count(*) FROM operations),(SELECT count(*) FROM operation_keys),"
                        "(SELECT count(*) FROM artifact_objects),"
                        "(SELECT count(*) FROM artifact_refs)"
                    ).one()
                )

        before_guard = guard_state()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=guarded), base_url="http://package.invalid"
        ) as client:
            for method, path in guarded_paths:
                observed = guarded.state.db.schema_compatibility()
                if (observed.status, observed.code) != ("incompatible", "migration_only"):
                    raise RuntimeError("Installed HTTP real schema guard was changed")
                response_check(
                    await client.request(method, path, headers=guard_headers, content=raw),
                    503,
                    "schema_incompatible",
                )

        for owner in (app.state.db, app.state.operation_coordinator, app.state.operation_service):
            owner.schema_compatibility = lambda: CompatibilityResult("ready", "synthetic_http_only")

        configuration_bytes = canonical(
            {
                "schema": 1,
                "kind": "native-v1",
                "image_identity": "sha256:" + "a" * 64,
                "endpoint_profile": "synthetic-installed",
                "endpoint_revision": "revision-1",
                "model_revision": "model-1",
                "adapter_digest": "b" * 64,
                "prompt_digest": "c" * 64,
                "tool_policy_digest": "d" * 64,
                "configuration_digest": "e" * 64,
                "processor_profile": "synthetic-installed",
                "max_input_tokens": 2048,
                "max_output_tokens": 32,
                "reasoning_effort": "",
                "seed_supported": False,
                "seed_strategy": SEED_STRATEGY,
                "price_version": "synthetic-prices-1",
                "input_microusd_per_million_tokens": 1,
                "output_microusd_per_million_tokens": 1,
            }
        )
        configuration = NativeConfiguration(
            configuration_bytes, expected_digest=hashlib.sha256(configuration_bytes).hexdigest()
        )

        class Policy:
            def require_available(self):
                return None

            def permission(self, actor, context, intent, candidate):
                if engine.pool.checkedout() or actor != principal or candidate != configuration:
                    raise RuntimeError("Installed synthetic permission changed context")
                return ProcessorPermission(candidate.digest, candidate.processor_profile)

            def prepare(self, actor, context, intent, config):
                if engine.pool.checkedout():
                    raise RuntimeError("Installed policy preparation held SQL")
                return dict(
                    schema=1,
                    organization_id=context.organization_id,
                    project_id=context.project_id,
                    principal_id=actor.principal_id,
                    request_digest=intent.request_digest,
                    task_digest=intent.task_digest,
                    configuration_digest=config.digest,
                    permitted_processor_profile=config.processor_profile,
                    version="synthetic-installed-1",
                    state={},
                )

            def recheck(self, connection, actor, context, intent, config, evidence):
                value = connection.execute(
                    text("SELECT name FROM projects WHERE id=:id"), {"id": context.project_id}
                ).scalar_one()
                if (
                    value != "Synthetic HTTP package"
                    or actor != principal
                    or evidence["configuration_digest"] != config.digest
                    or not connection.in_transaction()
                ):
                    raise AdmissionError("dependency_unavailable")

        class Ready:
            def check(self, *_args):
                if engine.pool.checkedout():
                    raise RuntimeError("Installed synthetic readiness held SQL")
                return AdmissionReady(True)

        journal_root = root / "operation-http-journal"
        journal_root.mkdir(mode=0o700)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://package.invalid"
        ) as client:
            response_check(
                await client.post(base + "/runs", headers=headers, content=raw),
                503,
                "dependency_unavailable",
            )
            coordinator = AdmissionCoordinator(
                engine,
                app.state.authority,
                policy=Policy(),
                readiness=Ready(),
                registry=NativeRegistry(configuration, ["synthetic-image"]),
                journal=AdmissionJournal(journal_root),
                storage=LocalArtifactStorage(
                    app.state.auth.settings.data_dir,
                    app.state.auth.cipher,
                    plaintext_limit=8 * 1024 * 1024,
                ),
            )
            coordinator.schema_compatibility = lambda: CompatibilityResult(
                "ready", "synthetic_http_only"
            )
            app.state.operation_coordinator = coordinator
            accepted_response = await client.post(base + "/runs", headers=headers, content=raw)
            accepted = response_check(accepted_response, 202)
            if set(accepted) != {"operation_id", "job_id"}:
                raise RuntimeError("Installed submit changed Accepted fields")
            path = base + "/operations/" + accepted["operation_id"]
            view = response_check(await client.get(path, headers=headers), 200)
            if view != {
                "id": accepted["operation_id"],
                "project_id": project,
                "job_id": accepted["job_id"],
                "client_operation_id": "7" * 32,
                "status": "queued",
                "cancel_requested": False,
                "result_run_id": None,
                "budget_microusd": 1,
                "reserved_microusd": 0,
                "error": None,
            }:
                raise RuntimeError("Installed operation HTTP changed required view fields")
            cancellation = response_check(await client.post(path + "/cancel", headers=headers), 202)
            if cancellation != {
                "operation_id": accepted["operation_id"],
                "cancel_requested": True,
                "status": "cancelled",
            }:
                raise RuntimeError("Installed operation HTTP changed Cancellation fields")
            unavailable = AdmissionCoordinator(engine, app.state.authority)
            unavailable.schema_compatibility = lambda: CompatibilityResult(
                "ready", "synthetic_http_only"
            )
            app.state.operation_coordinator = unavailable
            replay = response_check(
                await client.post(base + "/runs", headers=headers, content=raw), 202
            )
            if replay != accepted:
                raise RuntimeError("Installed outage replay changed original identity")
            with owned_connect(engine) as connection:
                observed = connection.execute(text("SELECT count(*) FROM operations")).scalar_one()
                origin = connection.execute(
                    text("SELECT failure_correlation_id FROM operations")
                ).scalar_one()
            if observed != 1 or origin != accepted_response.headers["x-request-id"]:
                raise RuntimeError("Installed HTTP did not retain original server correlation")
            if engine.pool.checkedout():
                raise RuntimeError("Installed operation HTTP retained SQL after response")
        after_guard = guarded.state.db.schema_compatibility()
        if (
            (after_guard.status, after_guard.code) != ("incompatible", "migration_only")
            or guard_state() != before_guard
            or guarded.state.db.engine.pool.checkedout()
        ):
            raise RuntimeError("Synthetic HTTP instance changed the separate real guard")

    try:
        asyncio.run(run())
    finally:
        for app in applications:
            app.state.db.engine.dispose()
    print("operation_http_installed_smoke_verified")


def repository_smoke(engine: Engine) -> None:
    repository = ScopedRepositories(engine)
    # Synthetic trusted identity matches only the explicit smoke initialization.
    context = ProjectContext("8" * 32, "9" * 32, "oidc:" + "a" * 64)
    if repository.list_resources(context, "run") != []:
        raise RuntimeError("Installed scoped repository did not preserve the empty project")
    try:
        repository.list_resources(ProjectContext("8" * 32, "7" * 32, context.principal_id), "run")
    except ResourceNotFound as error:
        if str(error) != "Resource not found.":
            raise RuntimeError("Installed scoped denial changed its public message") from None
    else:
        raise RuntimeError("Installed scoped repository admitted a foreign project")


def artifact_smoke(engine: Engine, root: Path) -> None:
    import hashlib
    from datetime import UTC, datetime

    from cryptography.fernet import Fernet

    from agent_rewind.artifact_metadata import ArtifactObject
    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.migrations.artifact_service import initialize_artifacts

    state = initialize_artifacts(engine)
    if state["revision"] != "ar_0004_artifacts" or state["customer_ready"]:
        raise RuntimeError("Installed artifact revision failed its explicit transition")
    content = b"synthetic-installed-object"
    digest = hashlib.sha256(content).hexdigest()
    value = ArtifactObject(
        id="a" * 32,
        project_id="9" * 32,
        digest=digest,
        locator=f"objects/{'9' * 32}/v1/{digest}",
        format_version=1,
        byte_count=len(content),
        created_at=datetime.now(UTC),
    )
    store = LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
    store.put_verified(value, content)
    if store.read_verified(value) != content:
        raise RuntimeError("Installed bounded artifact format did not round trip")


def projection_smoke(engine: Engine) -> None:
    from agent_rewind.migrations.projection_service import backfill_run_index, initialize_projection

    result = initialize_projection(engine)
    if result["revision"] != "ar_0005_run_index" or result["projection_status"] != "complete":
        raise RuntimeError("Installed empty projection transition failed")

    def forbidden(*args: object) -> bytes:
        raise RuntimeError("Empty installed projection attempted artifact I/O")

    if backfill_run_index(engine, forbidden) != result:
        raise RuntimeError("Installed empty projection retry changed progress")


def run_listing_smoke(engine: Engine) -> None:
    import base64
    from datetime import UTC, datetime
    from pathlib import Path

    from cryptography.fernet import Fernet
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from sqlalchemy import text

    from agent_rewind.api import create_app
    from agent_rewind.config import Settings
    from agent_rewind.cursor_config import cursor_codec
    from agent_rewind.migrations.compatibility import CompatibilityResult
    from agent_rewind.request_identity import SessionIdentity, VerifiedPrincipal, encode_v2_session
    from agent_rewind.run_cursor import CursorPosition, initial_expiry
    from agent_rewind.scoped_run_listing import ScopedRunReader

    def check_real_guard(
        application: FastAPI, route_client: TestClient, path: str, phase: str
    ) -> None:
        from time import monotonic

        original = application.state.db.schema_compatibility
        calls = 0
        observed: CompatibilityResult | None = None
        elapsed = 0.0
        started: float | None = None
        completed = False
        raised = False

        def observe() -> CompatibilityResult:
            nonlocal calls, observed, elapsed, started, completed, raised
            calls += 1
            started = monotonic()
            try:
                observed = original()
                return observed
            except BaseException:
                raised = True
                raise
            finally:
                elapsed = monotonic() - started
                completed = True

        # Observe the existing call only. Restore even if the request or guard raises.
        application.state.db.schema_compatibility = observe
        try:
            response = route_client.get(path)
        finally:
            application.state.db.schema_compatibility = original
        try:
            body = response.json()
        except ValueError:
            body = None
        code = body.get("code") if isinstance(body, dict) else None
        if response.status_code == 503 and code == "schema_incompatible":
            return

        # Only fixed protocol labels enter packaging diagnostics, never response
        # messages, credentials, URLs, exception text or arbitrary guard codes.
        safe_codes = {
            "schema_incompatible",
            "dependency_unavailable",
            "unauthenticated",
            "not_found",
            "migration_only",
            "schema_unavailable",
            "schema_probe_capacity",
            "release_profile_or_connection_invalid",
            "release_profile_invalid",
            "backfill_incomplete",
        }

        def safe_code(value: object) -> str:
            return value if isinstance(value, str) and value in safe_codes else "unknown"

        status = response.status_code
        http_status = str(status) if type(status) is int and 100 <= status <= 599 else "unknown"
        probe_status = "not_invoked"
        probe_code = "unknown"
        if started is not None:
            # A bounded API request may return while its existing probe is still
            # running. Report elapsed time so far without joining or probing again.
            probe_status = "raised" if raised else "unknown"
            if not completed:
                probe_status = "pending"
                elapsed = monotonic() - started
        if completed and isinstance(observed, CompatibilityResult):
            probe_status = (
                observed.status
                if isinstance(observed.status, str)
                and observed.status in {"ready", "incompatible", "unavailable"}
                else "unknown"
            )
            probe_code = safe_code(observed.code)
        raise RuntimeError(
            f"Installed listing {phase} guard mismatch: "
            f"http_status={http_status} http_code={safe_code(code)} "
            f"probe_calls={calls} probe_status={probe_status} probe_code={probe_code} "
            f"probe_elapsed_ms={elapsed * 1000:.3f}"
        )

    settings = Settings(
        _env_file=None,
        encryption_key=SecretStr(Fernet.generate_key().decode()),
        bootstrap_key=SecretStr("synthetic-package-bootstrap-not-a-cursor-key"),
        cursor_signing_key=SecretStr(base64.urlsafe_b64encode(b"c" * 32).decode().rstrip("=")),
    )
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    codec = cursor_codec(settings)
    position = CursorPosition(50, 0, now, "1" * 32, initial_expiry(now))
    token = codec.encode("9" * 32, principal.principal_id, position, now=now)
    if codec.decode(token, "9" * 32, principal.principal_id, now=now) != position:
        raise RuntimeError("Installed run cursor did not round trip")
    reader = ScopedRunReader(engine, settings)
    page = reader.list(principal, "9" * 32, now=now)
    if page.items or page.next_cursor is not None:
        raise RuntimeError("Installed scoped list changed the empty projection")
    try:
        reader.detail(principal, "9" * 32, "1" * 32)
    except ResourceNotFound:
        pass
    else:
        raise RuntimeError("Installed scoped detail invented an unpublished run")

    # Actual installed HTTP route wiring, using only this synthetic database.
    # First retain the real migration-only guard; successful reads below use a
    # per-instance test substitution, not a customer-ready profile or runtime flag.
    settings.database_url = engine.url.render_as_string(hide_password=False)
    settings.data_dir = Path(str(engine.url.database)).parent
    settings.oidc_issuer = "https://installed-route.invalid"
    identity = SessionIdentity(
        VerifiedPrincipal.oidc(settings.oidc_issuer, "installed-viewer"),
        settings.oidc_issuer,
        "installed-viewer",
        "d" * 32,
    )
    app = create_app(settings)
    client = TestClient(app)  # Do not start readiness or any external service.
    original_guard = app.state.db.schema_compatibility
    base = "/api/v1/projects/" + "9" * 32 + "/runs"
    try:
        check_real_guard(app, client, base, "first")
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,false)"),
                {"p": "9" * 32, "id": identity.principal.principal_id},
            )
        app.state.db.schema_compatibility = lambda: CompatibilityResult(
            "ready", "synthetic_installed_route_smoke"
        )
        # The instance-only fixture must not make a separately constructed app ready.
        guarded_app = create_app(settings)
        guarded_client = TestClient(guarded_app)
        try:
            check_real_guard(guarded_app, guarded_client, base, "fresh-instance")
        finally:
            guarded_client.close()
            guarded_app.state.db.engine.dispose()
        cookie = {"Cookie": "rewind_session=" + encode_v2_session(app.state.auth.cipher, identity)}
        response = client.get(base, headers=cookie)
        if response.status_code != 200 or response.json() != {"items": [], "next_cursor": None}:
            raise RuntimeError("Installed HTTP listing changed its exact empty response")
        if response.headers["cache-control"] != "no-store":
            raise RuntimeError("Installed HTTP listing lost cache protection")
        for path, status, code in [
            (base + "/" + "1" * 32, 404, "not_found"),
            (base + "?cursor=", 422, "invalid_cursor"),
        ]:
            response = client.get(path, headers=cookie)
            body = response.json()
            if (
                response.status_code != status
                or set(body) != {"code", "message", "request_id", "retryable"}
                or body["code"] != code
                or response.headers["x-request-id"] != body["request_id"]
            ):
                raise RuntimeError("Installed HTTP read changed its fixed error envelope")
        settings.cursor_signing_key = None
        if client.get(base).status_code != 401:
            raise RuntimeError("Installed missing-key error preceded credential authentication")
        foreign = "/api/v1/projects/" + "7" * 32 + "/runs"
        if client.get(foreign, headers=cookie).status_code != 404:
            raise RuntimeError("Installed missing-key error preceded project visibility")
        if client.get(base, headers=cookie).status_code != 503:
            raise RuntimeError("Installed list ignored its missing cursor key")
        if client.get(base + "/" + "1" * 32, headers=cookie).status_code != 404:
            raise RuntimeError("Installed detail incorrectly required the cursor key")
    finally:
        app.state.db.schema_compatibility = original_guard
        client.close()
        app.state.db.engine.dispose()
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM project_memberships WHERE project_id=:p AND principal_id=:id"),
                {"p": "9" * 32, "id": identity.principal.principal_id},
            )


def publication_smoke(engine: Engine, root: Path) -> None:
    from cryptography.fernet import Fernet

    from agent_rewind.artifact_graph import verify_run_graph
    from agent_rewind.artifact_metadata import ArtifactError
    from agent_rewind.artifact_publication import RunPublisher, UnavailableLiveWriter
    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.projection_publication import ProjectionPublicationWriter
    from agent_rewind.publication_journal import PublicationJournal

    journal_root = root / "publication-journal"
    journal_root.mkdir(mode=0o700)
    journal = PublicationJournal(journal_root)
    # Synthetic packaging evidence only; a deployment provisions/fsyncs its root.
    with journal.open("b" * 32) as session:
        session.freeze({"synthetic_package": True})
    with journal.open("b" * 32) as session:
        if session.intent != {"synthetic_package": True}:
            raise RuntimeError("Installed publication journal did not round trip")
    publisher = RunPublisher(
        engine,
        LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096),
        journal,
        writer=ProjectionPublicationWriter(UnavailableLiveWriter()),
    )
    try:
        publisher.prepare(
            ProjectContext("8" * 32, "9" * 32, "oidc:" + "a" * 64),
            "c" * 32,
            worker_id="synthetic",
            generation=1,
            source=lambda ref, limit: b"",
        )
    except ArtifactError as error:
        if str(error) != "publication_live_fence_unavailable":
            raise RuntimeError("Installed live publisher refused with unexpected code") from None
    else:
        raise RuntimeError("Installed publisher incorrectly enabled a legacy live writer")
    try:
        verify_run_graph(b'{"schema":1}', lambda ref, limit: b"")
    except ArtifactError:
        pass
    else:
        raise RuntimeError("Installed publication parser accepted a legacy root")


def request_foundation_smoke(engine: Engine, root: Path) -> None:
    from cryptography.fernet import Fernet

    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.published_reader import PublishedRunReader
    from agent_rewind.request_authority import RequestAuthority
    from agent_rewind.request_identity import (
        SessionIdentity,
        VerifiedPrincipal,
        decode_v2_session,
        encode_v2_session,
    )

    issuer = "https://installed-smoke.invalid"
    identity = SessionIdentity(
        VerifiedPrincipal.oidc(issuer, "synthetic"), issuer, "synthetic", "c" * 32
    )
    cipher = Fernet(Fernet.generate_key())
    if decode_v2_session(cipher, encode_v2_session(cipher, identity), issuer) != identity:
        raise RuntimeError("Installed v2 session did not preserve issuer-bound identity")
    authority = RequestAuthority(engine)
    # A trusted synthetic authenticated principal matches the explicit smoke
    # grant. There is deliberately no explicit default membership in this DB.
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    decision = authority.named(principal, "9" * 32)
    if decision.role != "maintainer" or authority.legacy_role(principal) is not None:
        raise RuntimeError("Installed authority inferred an unregistered default")
    reader = PublishedRunReader(engine, LocalArtifactStorage(root, cipher, plaintext_limit=4096))
    try:
        reader.read_current(decision.context, "c" * 32)
    except ResourceNotFound:
        pass
    else:
        raise RuntimeError("Installed reader inferred an unpublished run root")


def existing_routes_smoke(engine: Engine, root: Path) -> None:
    from cryptography.fernet import Fernet

    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.errors import Fault
    from agent_rewind.legacy_admission import UnavailableAdmission
    from agent_rewind.legacy_views import LegacyViews
    from agent_rewind.published_reader import PublishedRunReader
    from agent_rewind.request_authority import RequestAuthority
    from agent_rewind.request_identity import VerifiedPrincipal
    from agent_rewind.scoped_actions import ScopedActions

    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    authority = RequestAuthority(engine)
    context = authority.named(principal, "9" * 32).context
    reader = PublishedRunReader(
        engine, LocalArtifactStorage(root, Fernet(Fernet.generate_key()), plaintext_limit=4096)
    )
    views = LegacyViews(reader, 4096)
    if views.runs(context) != [] or views.jobs(context) != [] or views.studies(context) != []:
        raise RuntimeError("Installed bounded view changed empty scoped metadata")
    try:
        ScopedActions(engine, authority).record_run_read(principal, context, "c" * 32)
    except ResourceNotFound:
        pass
    else:
        raise RuntimeError("Installed audit accepted a missing run")
    try:
        UnavailableAdmission().require_available()
    except Fault as error:
        if error.code != "dependency_unavailable":
            raise RuntimeError(
                "Installed unavailable admission changed its fixed refusal"
            ) from None
    else:
        raise RuntimeError("Installed admission unexpectedly available")


def admission_foundation_smoke() -> None:
    """Synthetic pure preparation from the installed package, with no admission."""
    import hashlib
    from datetime import UTC, datetime

    from agent_rewind.admission_configuration import NativeConfiguration, NativeRegistry
    from agent_rewind.admission_envelope import (
        ArtifactBinding,
        OriginCorrelation,
        prepare_admission,
        restore_admission,
    )
    from agent_rewind.admission_request import AdmissionPreparationError, parse_submit
    from agent_rewind.artifact_metadata import ArtifactObject, object_locator
    from agent_rewind.models import canonical

    raw = canonical(
        {
            "client_operation_id": "a" * 32,
            "adapter_config_id": "native-v1",
            "seed": 0,
            "budget_microusd": 1,
            "task": {
                "name": "installed",
                "instruction": "Synthetic preparation only.",
                "image": "installed-fixture",
                "files": {},
                "evaluator_files": {},
                "evaluator_command": "true",
            },
        }
    )
    intent = parse_submit(raw)
    config_bytes = canonical(
        {
            "schema": 1,
            "kind": "native-v1",
            "image_identity": "sha256:" + "1" * 64,
            "endpoint_profile": "installed-fixture",
            "endpoint_revision": "revision-1",
            "model_revision": "model-1",
            "adapter_digest": "2" * 64,
            "prompt_digest": "3" * 64,
            "tool_policy_digest": "4" * 64,
            "configuration_digest": "5" * 64,
            "processor_profile": "fixture",
            "max_input_tokens": 1000,
            "max_output_tokens": 1,
            "reasoning_effort": "",
            "seed_supported": False,
            "seed_strategy": "trial-plus-step-mod-2147483647",
            "price_version": "prices-1",
            "input_microusd_per_million_tokens": 1,
            "output_microusd_per_million_tokens": 1,
        }
    )
    config = NativeConfiguration(
        config_bytes, expected_digest=hashlib.sha256(config_bytes).hexdigest()
    )
    registry = NativeRegistry(config, ["installed-fixture"])
    project, job = "6" * 32, "7" * 32

    def metadata(content: bytes, identifier: str) -> ArtifactObject:
        digest = hashlib.sha256(content).hexdigest()
        return ArtifactObject(
            identifier,
            project,
            digest,
            object_locator(project, digest),
            1,
            len(content),
            datetime(2026, 10, 21, tzinfo=UTC),
        )

    task = ArtifactBinding(
        project_id=project,
        job_id=job,
        role="task",
        descriptor=metadata(intent.task_bytes, "8" * 32),
        plaintext=intent.task_bytes,
    )
    configuration = ArtifactBinding(
        project_id=project,
        job_id=job,
        role="admission_config",
        descriptor=metadata(config_bytes, "9" * 32),
        plaintext=config_bytes,
    )
    result = prepare_admission(
        intent,
        registry,
        project_id=project,
        job_id=job,
        origin=OriginCorrelation("b" * 32),
        task_binding=task,
        configuration_binding=configuration,
        permitted_processor_profile="fixture",
    )
    restored = restore_admission(
        intent,
        frozen_configuration=config_bytes,
        expected_configuration_digest=config.digest,
        expected_envelope_digest=result.envelope_digest,
        project_id=project,
        job_id=job,
        origin=result.origin,
        task_binding=task,
        configuration_binding=configuration,
    )
    if restored != result:
        raise RuntimeError("Installed frozen restoration changed original identities")
    payload = result.bind_payload(metadata(result.envelope_bytes, "c" * 32))
    envelope = json.loads(payload.plaintext)
    if (
        len(envelope) != 11
        or envelope["schema"] != 2
        or envelope["budget_microusd"] != 1
        or envelope["execution_config_ref"] != config.digest
        or envelope["task_ref"] != intent.task_digest
        or payload.descriptor.digest != result.envelope_digest
    ):
        raise RuntimeError("Installed admission foundation changed frozen identities")
    try:
        registry.resolve_new("native-v1", "installed-fixture", permitted_processor_profile=None)
    except AdmissionPreparationError as error:
        if error.code != "admission_configuration_unavailable":
            raise RuntimeError("Installed configuration refusal changed") from None
    else:
        raise RuntimeError("Installed configuration expanded processor permission")


def admission_storage_smoke(engine: Engine) -> None:
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from sqlalchemy import text

    from agent_rewind.admission_adapters import UnavailableAdmissionPolicy
    from agent_rewind.admission_coordinator import AdmissionCoordinator
    from agent_rewind.admission_envelope import OriginCorrelation
    from agent_rewind.admission_journal import AdmissionJournal
    from agent_rewind.admission_journal_state import JournalIdentity
    from agent_rewind.admission_publication import select_descriptor
    from agent_rewind.admission_records import verify_job_configuration
    from agent_rewind.admission_repository import AdmissionRepository
    from agent_rewind.admission_transaction import AdmissionError
    from agent_rewind.artifact_metadata import ArtifactError, ArtifactObject, object_locator
    from agent_rewind.migrations.admission_service import initialize_admission
    from agent_rewind.request_authority import RequestAuthority
    from agent_rewind.request_identity import VerifiedPrincipal

    result = initialize_admission(engine)
    if result["revision"] != "ar_0006_admission" or result["customer_ready"]:
        raise RuntimeError("Installed admission storage transition failed")
    if initialize_admission(engine) != result:
        raise RuntimeError("Installed admission storage reentry changed metadata")
    authority = RequestAuthority(engine)
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    context = authority.named(principal, "9" * 32).context
    repository = AdmissionRepository(authority)
    coordinator = AdmissionCoordinator(engine, authority)
    try:
        UnavailableAdmissionPolicy().require_available()
    except AdmissionError as error:
        if error.code != "dependency_unavailable":
            raise RuntimeError("Installed default admission policy refusal changed") from None
    else:
        raise RuntimeError("Installed default admission policy enabled work")
    try:
        coordinator.reconcile(principal, context, "1" * 32, "2" * 64, "3" * 64)
    except AdmissionError as error:
        if error.code != "schema_incompatible":
            raise RuntimeError("Installed coordinator schema refusal changed") from None
    else:
        raise RuntimeError("Installed coordinator bypassed migration-only guard")
    # Exercise only private journal binding/refusal, never preparation/publication.
    with TemporaryDirectory(prefix="admission-journal-") as folder:
        journal = AdmissionJournal(Path(folder))
        identity = JournalIdentity(
            context.organization_id,
            context.project_id,
            principal.principal_id,
            "1" * 32,
            "2" * 64,
            "3" * 64,
        )
        with journal.open(identity) as session:
            if session.route != "new":
                raise RuntimeError("Installed journal fresh routing changed")
            session.bind(OriginCorrelation("4" * 32))
        try:
            with journal.open(identity):
                raise RuntimeError("Installed journal inferred missing attempt absence")
        except ArtifactError:
            pass
    with engine.connect() as connection:
        from datetime import UTC, datetime

        authority.check(connection, principal, context, "record")
        prospective = ArtifactObject(
            "7" * 32,
            context.project_id,
            "8" * 64,
            object_locator(context.project_id, "8" * 64),
            1,
            0,
            datetime(2026, 1, 1, tzinfo=UTC),
        )
        if select_descriptor(connection, prospective) != prospective:
            raise RuntimeError("Installed bounded descriptor selection changed")
        empty = repository.resolve_identities(
            connection,
            principal,
            context,
            client_operation_id="1" * 32,
            key_hash="2" * 64,
            request_digest="3" * 64,
        )
        if empty.operation is not None or empty.needs_alias:
            raise RuntimeError("Installed empty admission namespace changed")
        for lookup in (
            lambda: repository.get_operation(connection, principal, context, operation_id="4" * 32),
            lambda: verify_job_configuration(
                connection, context=context, job_id="5" * 32, payload_version=1
            ),
        ):
            try:
                lookup()
            except ResourceNotFound:
                pass
            else:
                raise RuntimeError("Installed missing admission resource was accessible")
        counts = connection.execute(
            text("SELECT (SELECT count(*) FROM operations),(SELECT count(*) FROM operation_keys)")
        ).one()
        if tuple(counts) != (0, 0):
            raise RuntimeError("Installed read primitives created admission identities")


def readiness_smoke(root: Path, database_url: str) -> None:
    import asyncio
    import time

    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    from agent_rewind.config import Settings
    from agent_rewind.readiness import Readiness
    from agent_rewind.sentinel import SentinelSettings, provision, read_system_sentinel

    key = SecretStr(Fernet.generate_key().decode())
    sentinel = SentinelSettings(
        _env_file=None,
        data_dir=root,
        encryption_key=key,
        installation_key=SecretStr("synthetic-package-smoke"),
    )
    provision(sentinel)
    read_system_sentinel(sentinel, time.monotonic() + 1, installation_key="synthetic-package-smoke")
    settings = Settings(
        _env_file=None, data_dir=root, database_url=database_url, encryption_key=key
    )

    async def check() -> None:
        manager = Readiness(settings)
        manager.start()
        try:
            async with asyncio.timeout(5):
                while not manager._warm:
                    await asyncio.sleep(0.01)
            if await manager.check() != "schema_incompatible":
                raise RuntimeError("Installed readiness process admitted migration-only metadata")
        finally:
            await manager.close()

    asyncio.run(check())


def failure_evidence_smoke(root: Path) -> None:
    """Exercise the installed dormant successor through real services on synthetic data."""
    import sqlite3
    from contextlib import ExitStack, closing

    from agent_rewind.migrations.admission_service import initialize_admission
    from agent_rewind.migrations.artifact_service import initialize_artifacts
    from agent_rewind.migrations.failure_catalog import inspect_failure_catalog
    from agent_rewind.migrations.failure_service import (
        initialize_failure_evidence,
        inspect_failure_evidence,
    )
    from agent_rewind.migrations.failure_transaction import failure_transaction
    from agent_rewind.migrations.ledger_engine import create_ledger_engine
    from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
    from agent_rewind.migrations.ledger_inspection import inspect_ledger_state
    from agent_rewind.migrations.ledger_service import initialize_ledger
    from agent_rewind.migrations.ledger_source import source_digest
    from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
    from agent_rewind.migrations.ledger_work import LedgerWork
    from agent_rewind.migrations.projection_service import initialize_projection
    from agent_rewind.migrations.schema import FAILURE, LEDGER, MigrationRefused, catalog, checksum
    from agent_rewind.sqlite_ownership import create_owned_sqlite_engine, owned_connect

    path = root / "failure-evidence.sqlite"
    url = f"sqlite:///{path}"
    key = "synthetic-installed-failure"

    def snapshot():
        # Native lexical rows and original schema are separate from typed history.
        with closing(sqlite3.connect(path)) as raw:
            raw.execute("PRAGMA query_only=ON")
            objects = {
                (kind, name): (table, sql)
                for kind, name, table, sql in raw.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
                )
            }
            dump = tuple(raw.iterdump())
            retained_rows = tuple(
                line
                for line in dump
                if line.startswith("INSERT INTO ")
                and not line.startswith('INSERT INTO "alembic_version"')
            )
            return objects, retained_rows, dump

    with ExitStack() as engines:
        seed = create_engine(url)
        engines.callback(seed.dispose)
        install(seed, key)
        initialize_ownership(
            seed,
            {
                "schema_version": 1,
                "installation_key": key,
                "organization_id": "6" * 32,
                "project_id": "7" * 32,
                "project_name": "Synthetic installed failure evidence",
                "principal_grants": [
                    {
                        "principal_id": "oidc:" + "8" * 64,
                        "role": "maintainer",
                        "legacy_default": False,
                    }
                ],
            },
        )
        initialize_artifacts(seed)
        initialize_projection(seed)
        initialize_admission(seed)
        seed.dispose()

        operator = create_ledger_engine(url)
        engines.callback(operator.dispose)
        work = LedgerWork()
        with ledger_transaction(operator, LedgerOutcome(), work=work) as connection:
            if inspect_ledger_state(connection).status != "absent":
                raise RuntimeError("Installed synthetic predecessor already has a ledger")
            original_source = source_digest(connection, work)
        manifest = validate_ledger_manifest(
            {
                "schema_version": 1,
                "installation_key": key,
                "manifest_id": "9" * 32,
                "operation": "initialize",
                "source_digest": original_source,
                "parent_manifest_digest": None,
                "backup_evidence_digest": "a" * 64,
                "drain_evidence_digest": "b" * 64,
                "accounts": [],
                "opening_accounts": {"organization_account_id": None, "projects": []},
            }
        )
        initialize_ledger(operator, manifest)
        before = inspect_failure_evidence(operator, installation_key=key)
        if (before.status, before.revision, before.catalog_profile) != (
            "absent",
            LEDGER,
            "ledger_v1",
        ):
            raise RuntimeError("Installed failure inspection mislabeled its predecessor")
        predecessor_objects, predecessor_rows, _ = snapshot()
        installed = initialize_failure_evidence(operator, installation_key=key)
        observed = inspect_failure_evidence(operator, installation_key=key)
        if (
            installed.outcome != "complete"
            or (observed.status, observed.revision, observed.catalog_profile)
            != ("complete", FAILURE, "failure_evidence_v1")
            or installed.model_dump(mode="json", exclude={"outcome"})
            != observed.model_dump(mode="json")
            or observed.retained_ar7 != before.retained_ar7
        ):
            raise RuntimeError("Installed failure transition changed retained ledger identity")
        work = LedgerWork()
        with failure_transaction(operator, LedgerOutcome(), work=work) as connection:
            full = inspect_failure_catalog(connection, work)
            packaged = json.loads(
                importlib.resources.files("agent_rewind.migrations")
                .joinpath("profiles", "sqlite_failure_evidence.json")
                .read_text()
            )
            if full.catalog != packaged or observed.installed_profile_sha256 != checksum(
                full.catalog
            ):
                raise RuntimeError("Installed failure catalog/profile identity differs")
            if connection.exec_driver_sql("SELECT 1 FROM job_failure_evidence LIMIT 1").first():
                raise RuntimeError("Installed dormant transition created failure evidence")
            if connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version LIMIT 2"
            ).all() != [(FAILURE,)]:
                raise RuntimeError(
                    "Installed failure transition did not advance the actual revision"
                )
        successor_objects, successor_rows, successor_dump = snapshot()
        if {
            name: successor_objects.get(name) for name in predecessor_objects
        } != predecessor_objects or successor_rows != predecessor_rows:
            raise RuntimeError("Installed failure transition changed original schema or row bytes")
        if initialize_failure_evidence(operator, installation_key=key) != installed:
            raise RuntimeError("Installed failure reentry changed its original result")
        try:
            inspect_failure_evidence(operator, installation_key=key + "-wrong")
        except MigrationRefused as error:
            if str(error) != "installation_key_mismatch":
                raise RuntimeError("Installed failure key refusal changed") from None
        else:
            raise RuntimeError("Installed failure inspection accepted the wrong installation")
        try:
            with ledger_transaction(operator, LedgerOutcome(), work=LedgerWork()) as connection:
                inspect_ledger_state(connection)
        except MigrationRefused as error:
            if str(error) != "schema_incompatible":
                raise RuntimeError("Installed predecessor ledger refusal changed") from None
        else:
            raise RuntimeError("Installed predecessor ledger accepted the successor")

        runtime = create_owned_sqlite_engine(url, connect_timeout=3, pool_timeout=1)
        engines.callback(runtime.dispose)
        with owned_connect(runtime) as connection:
            try:
                catalog(connection)
            except MigrationRefused as error:
                if str(error) != "schema_incompatible":
                    raise RuntimeError("Installed old catalog refusal changed") from None
            else:
                raise RuntimeError("Installed old catalog accepted the successor")
        result = runtime_schema_compatibility(runtime)
        if (result.status, result.code) != ("incompatible", "migration_only"):
            raise RuntimeError("Installed successor incorrectly permits runtime admission")
        if runtime.pool.checkedout() or snapshot() != (
            successor_objects,
            successor_rows,
            successor_dump,
        ):
            raise RuntimeError("Installed inspection, refusal or reentry changed native state")
    print("Installed dormant failure evidence service and profiles verified outside checkout.")


def failure_terminal_smoke(root: Path) -> None:
    """Synthetic installed component execution, not a provider or live-worker proof."""
    import hashlib
    import sqlite3
    from contextlib import ExitStack, closing
    from dataclasses import asdict
    from datetime import UTC, datetime

    from cryptography.fernet import Fernet

    from agent_rewind.admission_configuration import (
        MAX_CONFIG_BYTES,
        NativeConfiguration,
        NativeRegistry,
    )
    from agent_rewind.admission_envelope import (
        ArtifactBinding,
        OriginCorrelation,
        prepare_admission,
    )
    from agent_rewind.admission_publication import publish_rows
    from agent_rewind.admission_repository import AdmissionRepository
    from agent_rewind.admission_request import parse_submit
    from agent_rewind.admission_transaction import TransactionOutcome, admission_transaction
    from agent_rewind.artifact_metadata import ArtifactObject, object_locator
    from agent_rewind.artifact_storage import LocalArtifactStorage
    from agent_rewind.failure_evidence import CreatedFailure, FailureRefusal, MatchingOriginal
    from agent_rewind.failure_persistence import _FailureExecutionOwner
    from agent_rewind.failure_terminal import TerminalCoordinator
    from agent_rewind.migrations.admission_service import initialize_admission
    from agent_rewind.migrations.artifact_service import initialize_artifacts
    from agent_rewind.migrations.failure_service import initialize_failure_evidence
    from agent_rewind.migrations.ledger_engine import create_ledger_engine
    from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest
    from agent_rewind.migrations.ledger_service import initialize_ledger
    from agent_rewind.migrations.ledger_source import source_digest
    from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
    from agent_rewind.migrations.ledger_work import LedgerWork
    from agent_rewind.migrations.projection_service import initialize_projection
    from agent_rewind.models import canonical
    from agent_rewind.request_authority import RequestAuthority
    from agent_rewind.request_identity import VerifiedPrincipal
    from agent_rewind.reservation_types import ClaimIntent
    from agent_rewind.scoped_locks import lock_authority
    from agent_rewind.sqlite_ownership import create_owned_sqlite_engine

    fixture = root / "failure-terminal"
    fixture.mkdir(mode=0o700)
    path = fixture / "metadata.sqlite"
    url = f"sqlite:///{path}"
    key = "synthetic-installed-terminal"
    organization, project, job = "1" * 32, "2" * 32, "3" * 32
    # A local fixture identity receives actual native membership below. This is
    # not an authentication test or a public admission/readiness override.
    principal = VerifiedPrincipal("oidc:" + "4" * 64)
    context = ProjectContext(organization, project, principal.principal_id)
    configuration_bytes = canonical(
        {
            "schema": 1,
            "kind": "native-v1",
            "image_identity": "sha256:" + "1" * 64,
            "endpoint_profile": "installed-fixture",
            "endpoint_revision": "revision-1",
            "model_revision": "model-1",
            "adapter_digest": "2" * 64,
            "prompt_digest": "3" * 64,
            "tool_policy_digest": "4" * 64,
            "configuration_digest": "5" * 64,
            "processor_profile": "fixture",
            "max_input_tokens": 1000,
            "max_output_tokens": 1,
            "reasoning_effort": "",
            "seed_supported": False,
            "seed_strategy": "trial-plus-step-mod-2147483647",
            "price_version": "prices-1",
            "input_microusd_per_million_tokens": 1,
            "output_microusd_per_million_tokens": 1,
        }
    )
    configuration = NativeConfiguration(
        configuration_bytes, expected_digest=hashlib.sha256(configuration_bytes).hexdigest()
    )
    dependency = fixture / "installed-configuration.json"
    with dependency.open("xb") as stream:
        dependency.chmod(0o600)
        stream.write(configuration_bytes)

    class OfflineConfigurationProbe:
        """Reads a real private dependency; never implements provider execution."""

        @property
        def configuration(self) -> NativeConfiguration:
            with dependency.open("rb") as stream:
                data = stream.read(MAX_CONFIG_BYTES + 1)
            return NativeConfiguration(data, expected_digest=configuration.digest)

        def validate_request(self, request: bytes, reserved_microusd: int) -> None:
            raise RuntimeError("The installed component fixture cannot dispatch")

        def send(self, request: bytes) -> object:
            raise RuntimeError("The installed component fixture cannot call a provider")

    def snapshot():
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA query_only=ON")
            schema = tuple(
                connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
                )
            )
            retained = tuple(
                line
                for line in connection.iterdump()
                if line.startswith("INSERT INTO ")
                and not line.startswith('INSERT INTO "jobs"')
                and not line.startswith('INSERT INTO "job_failure_evidence"')
            )
            result = connection.execute("SELECT * FROM jobs ORDER BY id")
            jobs = [
                dict(zip([column[0] for column in result.description], row, strict=True))
                for row in result.fetchall()
            ]
            result = connection.execute("SELECT * FROM job_failure_evidence ORDER BY job_id")
            evidence = [
                dict(zip([column[0] for column in result.description], row, strict=True))
                for row in result.fetchall()
            ]
            return schema, retained, jobs, evidence

    with ExitStack() as resources:
        seed = create_engine(url)
        resources.callback(seed.dispose)
        install(seed, key)
        initialize_ownership(
            seed,
            {
                "schema_version": 1,
                "installation_key": key,
                "organization_id": organization,
                "project_id": project,
                "project_name": "Synthetic installed terminal component",
                "principal_grants": [
                    {
                        "principal_id": principal.principal_id,
                        "role": "maintainer",
                        "legacy_default": False,
                    }
                ],
            },
        )
        initialize_artifacts(seed)
        initialize_projection(seed)
        initialize_admission(seed)
        seed.dispose()

        # Invoke the existing internal publisher with actual upload receipts.
        # No customer-facing coordinator is made ready for this controlled setup.
        admission = create_owned_sqlite_engine(url)
        configure_artifact_engine(admission)
        resources.callback(admission.dispose)
        authority = RequestAuthority(admission)
        repository = AdmissionRepository(authority)
        intent = parse_submit(
            canonical(
                {
                    "client_operation_id": "5" * 32,
                    "adapter_config_id": "native-v1",
                    "seed": 0,
                    "budget_microusd": 1,
                    "task": {
                        "name": "installed-component",
                        "instruction": "No execution requested.",
                        "image": "installed-fixture",
                        "files": {},
                        "evaluator_files": {},
                        "evaluator_command": "true",
                    },
                }
            )
        )
        at = datetime.now(UTC)

        def metadata(data: bytes, identifier: str) -> ArtifactObject:
            digest = hashlib.sha256(data).hexdigest()
            return ArtifactObject(
                identifier, project, digest, object_locator(project, digest), 1, len(data), at
            )

        task = ArtifactBinding(
            project_id=project,
            job_id=job,
            role="task",
            descriptor=metadata(intent.task_bytes, "6" * 32),
            plaintext=intent.task_bytes,
        )
        config = ArtifactBinding(
            project_id=project,
            job_id=job,
            role="admission_config",
            descriptor=metadata(configuration_bytes, "7" * 32),
            plaintext=configuration_bytes,
        )
        prepared = prepare_admission(
            intent,
            NativeRegistry(configuration, ["installed-fixture"]),
            project_id=project,
            job_id=job,
            origin=OriginCorrelation("8" * 32),
            task_binding=task,
            configuration_binding=config,
            permitted_processor_profile="fixture",
        )
        payload = prepared.bind_payload(metadata(prepared.envelope_bytes, "9" * 32))
        artifact_root = fixture / "artifacts"
        artifact_root.mkdir(mode=0o700)
        storage = LocalArtifactStorage(
            artifact_root, Fernet(Fernet.generate_key()), plaintext_limit=65536
        )
        receipts = tuple(
            storage.put_verified(binding.descriptor, binding.plaintext)
            for binding in (task, config, payload)
        )
        outcome = TransactionOutcome()
        with admission_transaction(admission, outcome) as connection:
            lock_authority(authority, connection, principal, context, None, None)
            arguments = dict(
                client_operation_id=intent.client_operation_id,
                key_hash="a" * 64,
                request_digest=intent.request_digest,
            )
            if (
                repository.resolve_identities(connection, principal, context, **arguments).operation
                is not None
            ):
                raise RuntimeError("Installed fixture admission identity already exists")
            operation = publish_rows(
                connection,
                authority,
                repository,
                principal,
                context,
                operation_id="b" * 32,
                key_hash="a" * 64,
                prepared=prepared,
                payload=payload,
                receipts=receipts,
                created_at=at,
            )
            resolved = repository.resolve_identities(connection, principal, context, **arguments)
            if resolved.operation != operation or resolved.needs_alias:
                raise RuntimeError("Installed fixture admission identity did not reconcile")
        if not outcome.commit_acknowledged or outcome.cleanup_failed:
            raise RuntimeError("Installed fixture admission did not exit cleanly")
        admission.dispose()

        operator = create_ledger_engine(url)
        resources.callback(operator.dispose)
        work = LedgerWork()
        with ledger_transaction(operator, LedgerOutcome(), work=work) as connection:
            original_source = source_digest(connection, work)

        def account(identifier, scope, target, project_id=None, job_id=None):
            return {
                "id": identifier,
                "organization_id": organization,
                "scope": scope,
                "scope_id": target,
                "project_id": project_id,
                "job_id": job_id,
                "period_start": "2000-01-01T00:00:00.000000Z",
                "period_end": "2100-01-01T00:00:00.000000Z",
                "limit_microusd": 1,
            }

        manifest = validate_ledger_manifest(
            {
                "schema_version": 1,
                "installation_key": key,
                "manifest_id": "c" * 32,
                "operation": "initialize",
                "source_digest": original_source,
                "parent_manifest_digest": None,
                "backup_evidence_digest": "d" * 64,
                "drain_evidence_digest": "e" * 64,
                "accounts": [
                    account("d" * 32, "organization", organization),
                    account("e" * 32, "project", project, project),
                    account("f" * 32, "job", job, project, job),
                ],
                "opening_accounts": {
                    "organization_account_id": "d" * 32,
                    "projects": [{"project_id": project, "account_id": "e" * 32}],
                },
            }
        )
        initialize_ledger(operator, manifest)
        initialize_failure_evidence(operator, installation_key=key)
        operator.dispose()

        engine = create_owned_sqlite_engine(url)
        configure_artifact_engine(engine)
        resources.callback(engine.dispose)
        authority = RequestAuthority(engine)
        before = snapshot()
        if len(before[2]) != 1 or before[2][0]["status"] != "queued" or before[3]:
            raise RuntimeError("Installed fixture did not create one eligible queued admission")
        ciphertexts = {
            file.relative_to(artifact_root).as_posix(): hashlib.sha256(
                file.read_bytes()
            ).hexdigest()
            for file in artifact_root.rglob("*")
            if file.is_file()
        }
        probe = OfflineConfigurationProbe()
        if probe.configuration != configuration:
            raise RuntimeError("Installed dependency differs from admitted configuration")
        owner = _FailureExecutionOwner(engine, authority, probe)
        resources.callback(owner.close)
        fence = owner.claim(principal, context, ClaimIntent(job, "0" * 32, 0, 60))
        if not owner.outcome.commit_acknowledged or owner.outcome.cleanup_failed:
            raise RuntimeError("Installed private claim did not exit cleanly")
        claimed = snapshot()
        if (
            claimed[:2] != before[:2]
            or claimed[3]
            or len(claimed[2]) != 1
            or claimed[2][0]
            != {
                **before[2][0],
                "status": "running",
                "owner": fence.owner_uuid,
                "lease_generation": fence.generation,
                "lease_until": claimed[2][0]["lease_until"],
            }
            or fence.job_id != job
            or fence.generation != 1
            or claimed[2][0]["lease_until"] is None
        ):
            raise RuntimeError("Installed claim changed an unexpected native value")

        # Real dependency loss is observed by the registered installed owner.
        # No event, cause, capability or registration is manufactured by the smoke.
        dependency.unlink()
        event = owner._check_installed_binding()
        if event is None or dependency.exists():
            raise RuntimeError("Installed dependency loss did not issue its fixed event")
        terminal = TerminalCoordinator(engine, authority)
        result = terminal.complete_failure(principal, context, event)
        if (
            type(result) is not CreatedFailure
            or terminal.original != result.original
            or not terminal.outcome.commit_acknowledged
            or terminal.outcome.cleanup_failed
            or result.original.fence != fence
            or result.original.record.cause != "dependency_failed"
            or result.original.record.phase != "outcome_unknown"
            or result.original.record.job_status != "failed"
        ):
            raise RuntimeError(
                "Installed completion did not retain its original acknowledged result"
            )
        completed = snapshot()
        if (
            completed[:2] != claimed[:2]
            or completed[2] != [{**claimed[2][0], "status": "failed"}]
            or completed[3] != [asdict(result.original.record)]
        ):
            raise RuntimeError("Installed completion changed more than status and one evidence row")
        inspector = TerminalCoordinator(engine, authority)
        inspected = inspector.inspect_original(principal, context, result.original)
        if (
            type(inspected) is not MatchingOriginal
            or inspected.original != result.original
            or not inspector.outcome.commit_acknowledged
            or inspector.outcome.cleanup_failed
            or snapshot() != completed
        ):
            raise RuntimeError("Installed original inspection changed or regenerated the result")
        try:
            TerminalCoordinator(engine, authority).complete_failure(principal, context, event)
        except FailureRefusal as error:
            if error.reason != "capability_not_issued":
                raise RuntimeError("Installed consumed-event refusal changed") from None
        else:
            raise RuntimeError("Installed component reused a consumed completion event")
        compatibility = runtime_schema_compatibility(engine)
        if (
            compatibility.status != "incompatible"
            or compatibility.code != "migration_only"
            or snapshot() != completed
            or ciphertexts
            != {
                file.relative_to(artifact_root).as_posix(): hashlib.sha256(
                    file.read_bytes()
                ).hexdigest()
                for file in artifact_root.rglob("*")
                if file.is_file()
            }
        ):
            raise RuntimeError("Installed component altered preserved data or customer readiness")


package = Path(agent_rewind.__file__).resolve()
if not package.is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError("Smoke imported a source checkout instead of the installed wheel")
if utc_created(1 / 128).microsecond != 7812:
    raise RuntimeError("Installed projection timestamp rule changed")
for development_tool in ("pytest", "ruff", "mypy", "pip-audit", "setuptools"):
    try:
        importlib.metadata.version(development_tool)
    except importlib.metadata.PackageNotFoundError:
        continue
    raise RuntimeError("Runtime smoke environment contains development dependencies")
for asset in ("index.html", "style.css", "app.js"):
    content = importlib.resources.files("agent_rewind").joinpath("web", asset).read_bytes()
    if not content:
        raise RuntimeError("Packaged web asset is empty")
for profile in (
    "sqlite",
    "postgresql16",
    "sqlite_ownership",
    "postgresql16_ownership",
    "sqlite_artifacts",
    "postgresql16_artifacts",
    "sqlite_projection",
    "sqlite_admission",
    "postgresql16_admission",
    "sqlite_failure_evidence",
    "postgresql16_failure_evidence",
):
    shape = json.loads(
        importlib.resources.files("agent_rewind.migrations")
        .joinpath("profiles", profile + ".json")
        .read_text()
    )
    if not isinstance(shape, dict) or "installation_adoptions" not in shape:
        raise RuntimeError("Packaged frozen migration profile is missing or invalid")
    if profile.endswith("_failure_evidence") and (
        "job_failure_evidence" not in shape
        or len([name for name in shape if not name.startswith("$")]) != 21
    ):
        raise RuntimeError("Packaged failure evidence profile is missing its successor shape")
if importlib.metadata.version("agent-rewind") != "0.1.0":
    raise RuntimeError("Unexpected installed package identity")
admission_foundation_smoke()
with tempfile.TemporaryDirectory(prefix="rewind-package-migration-") as temporary:
    operation_components_smoke(Path(temporary))
    operation_service_smoke(Path(temporary))
    operation_http_smoke(Path(temporary))
    failure_evidence_smoke(Path(temporary))
    failure_terminal_smoke(Path(temporary))
    database = Path(temporary) / "metadata.sqlite"
    engine = create_engine(f"sqlite:///{database}")
    configure_artifact_engine(engine)
    try:
        if schema_status(engine)["state"] != "empty" or database.exists():
            raise RuntimeError("Installed schema inspection modified an empty database")
        prepared = install(engine, "synthetic-package-smoke")
        if (
            prepared["state"] != "prepared"
            or prepared["customer_ready"] is not False
            or schema_status(engine) != prepared
            or install(engine, "synthetic-package-smoke") != prepared
        ):
            raise RuntimeError("Installed Alembic revisions/profile failed the migration smoke")
        compatibility = runtime_schema_compatibility(engine)
        if compatibility.status != "incompatible" or compatibility.code != "migration_only":
            raise RuntimeError("Installed release manifest incorrectly permits customer admission")
        ownership = initialize_ownership(
            engine,
            {
                "schema_version": 1,
                "installation_key": "synthetic-package-smoke",
                "organization_id": "8" * 32,
                "project_id": "9" * 32,
                "project_name": "Synthetic installed package",
                "principal_grants": [
                    {
                        "principal_id": "oidc:" + "a" * 64,
                        "role": "maintainer",
                        "legacy_default": False,
                    }
                ],
            },
        )
        if ownership["state"] != "ownership_complete" or ownership["customer_ready"]:
            raise RuntimeError("Installed ownership revision failed the explicit transition")
        repository_smoke(engine)
        artifact_smoke(engine, Path(temporary))
        projection_smoke(engine)
        run_listing_smoke(engine)
        publication_smoke(engine, Path(temporary))
        request_foundation_smoke(engine, Path(temporary))
        existing_routes_smoke(engine, Path(temporary))
        admission_storage_smoke(engine)
        compatibility = runtime_schema_compatibility(engine)
        if compatibility.status != "incompatible" or compatibility.code != "migration_only":
            raise RuntimeError(
                "Installed ownership/artifact revision incorrectly permits admission"
            )
    finally:
        engine.dispose()
    readiness_smoke(Path(temporary), f"sqlite:///{database}")
print("Installed runtime, web assets, migration revisions and profile verified outside checkout.")
