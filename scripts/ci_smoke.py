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
        response = client.get(base)
        if response.status_code != 503 or response.json()["code"] != "schema_incompatible":
            raise RuntimeError("Installed route bypassed the real migration-only guard")
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
            guarded_response = guarded_client.get(base)
            if (
                guarded_response.status_code != 503
                or guarded_response.json()["code"] != "schema_incompatible"
            ):
                raise RuntimeError("Synthetic installed route guard leaked across app instances")
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
):
    shape = json.loads(
        importlib.resources.files("agent_rewind.migrations")
        .joinpath("profiles", profile + ".json")
        .read_text()
    )
    if not isinstance(shape, dict) or "installation_adoptions" not in shape:
        raise RuntimeError("Packaged frozen migration profile is missing or invalid")
if importlib.metadata.version("agent-rewind") != "0.1.0":
    raise RuntimeError("Unexpected installed package identity")
admission_foundation_smoke()
with tempfile.TemporaryDirectory(prefix="rewind-package-migration-") as temporary:
    operation_components_smoke(Path(temporary))
    operation_service_smoke(Path(temporary))
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
