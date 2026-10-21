"""GET composition on actual ar6 rows and an owned one-slot SQLite read pool."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import event, text
from test_admission_coordinator import snapshot as sql_snapshot
from test_admission_envelope import descriptor
from test_admission_schema import JOB, OPERATION, PRINCIPAL, PROJECT, SECOND_JOB
from test_operation_reads import admission_engine, repository, stored
from test_operation_sources import roots

from agent_rewind import operation_service, operation_work
from agent_rewind.artifact_metadata import ArtifactError, record_verified, register_ref
from agent_rewind.artifact_storage import LocalArtifactStorage
from agent_rewind.database import Database
from agent_rewind.errors import Fault
from agent_rewind.migrations.compatibility import CompatibilityResult, load_release_profile
from agent_rewind.models import canonical
from agent_rewind.operation_service import OperationService
from agent_rewind.operation_work import OperationWork
from agent_rewind.request_authority import RequestAuthority
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_repositories import ProjectContext
from agent_rewind.sqlite_ownership import create_owned_sqlite_engine, owned_connect

__all__ = ["admission_engine", "repository", "stored"]


@pytest.fixture
def get_fixture(stored, monkeypatch, tmp_path):
    f = stored
    engine = create_owned_sqlite_engine(
        str(f.engine.url), connect_timeout=3, pool_timeout=1, pool_size=1, max_overflow=0
    )
    service = OperationService(engine, RequestAuthority(engine))
    monkeypatch.setattr(
        service, "schema_compatibility", lambda: CompatibilityResult("ready", "ready")
    )
    work = []
    books = []
    real_book = operation_service.ReceiptBook

    def make_work():
        value = OperationWork()
        work.append(value)
        return value

    def make_book():
        value = real_book()
        books.append(value)
        return value

    monkeypatch.setattr(operation_service, "OperationWork", make_work)
    monkeypatch.setattr(operation_service, "ReceiptBook", make_book)
    value = SimpleNamespace(**vars(f))
    value.service, value.reader_engine, value.work, value.books = service, engine, work, books
    value.storage = LocalArtifactStorage(
        tmp_path / "encrypted", Fernet(Fernet.generate_key()), plaintext_limit=4096
    )
    value.storage.root.mkdir(mode=0o700)
    value.loads = []
    try:
        yield value
    finally:
        assert engine.pool.checkedout() == 0
        assert all(item._started is None for item in work)
        engine.dispose()


def invoke(f, **updates):
    args = dict(principal=f.principal, context=f.context, operation_id=OPERATION)
    args.update(updates)
    return f.service.read_operation(**args)


def publish_result(f, data, *, publish=True, object_id="9" * 32):
    value = descriptor(data, object_id=object_id, project=PROJECT)
    f.storage.put_verified(value, data)
    with f.engine.begin() as connection:
        record_verified(connection, value)
        register_ref(
            connection,
            project_id=PROJECT,
            owner_kind="job",
            owner_id=JOB,
            role="result",
            artifact_id=value.id,
        )
        if publish:
            connection.execute(
                text("UPDATE jobs SET result=:v WHERE id=:id"), {"v": value.digest, "id": JOB}
            )

    def load(observed):
        assert f.reader_engine.pool.checkedout() == 0
        f.loads.append(observed)
        return f.storage.read_verified(observed)

    f.service.artifact_loader = load
    return value


def expect_dependency(call):
    with pytest.raises(Fault) as caught:
        call()
    assert caught.value.code == "dependency_unavailable"
    assert caught.value.__suppress_context__ and caught.value.__cause__ is None


def test_exact_view_null_false_and_no_side_effects(get_fixture):
    f = get_fixture
    before = sql_snapshot(f)
    view = invoke(f)
    assert view == dict(
        id=OPERATION,
        project_id=PROJECT,
        job_id=JOB,
        client_operation_id=f.value.intent.client_operation_id,
        status="succeeded",
        cancel_requested=False,
        result_run_id=None,
        budget_microusd=f.value.intent.budget_microusd,
        reserved_microusd=245000,
        error=None,
    )
    assert sql_snapshot(f) == before
    assert f.loads == []
    assert f.work[0].statements == 40
    assert f.books[0].source_visits == 1
    assert len(f.books[0].receipts) == 3


@pytest.mark.parametrize("status", ["queued", "running", "succeeded", "cancelled"])
@pytest.mark.parametrize("cancel", [0, 1])
def test_supported_status_preserves_execution_and_integer_budget(get_fixture, status, cancel):
    f = get_fixture
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET status=:s,cancel=:c,reserved=:r WHERE id=:id"),
            {"s": status, "c": cancel, "r": 2**53 + 1, "id": JOB},
        )
        connection.execute(text("UPDATE operations SET failure_correlation_id=NULL"))
    value = invoke(f)
    assert value["status"] == status and value["cancel_requested"] is bool(cancel)
    assert value["reserved_microusd"] == 2**53 + 1 > value["budget_microusd"]
    assert value["error"] is None


@pytest.mark.parametrize(
    "status,error",
    [
        ("failed", None),
        ("running", ""),
        ("succeeded", "private-canary"),
        ("cancelled", '{"code":"outcome_uncertain","request_id":"old"}'),
        ("queued", " "),
        ("failed", "RuntimeError"),
    ],
)
def test_unsupported_failure_refuses_before_loader(get_fixture, status, error):
    f = get_fixture
    with f.engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET status=:s,error=:e WHERE id=:id"),
            {"s": status, "e": error, "id": JOB},
        )
    f.service.artifact_loader = lambda _d: pytest.fail("unsupported failure loaded storage")
    before = sql_snapshot(f)
    expect_dependency(lambda: invoke(f))
    assert sql_snapshot(f) == before
    assert len(f.work) == 1
    assert f.work[0].statements < 512


@pytest.mark.parametrize("count,distractors", [(0, False), (255, False), (0, True), (255, True)])
def test_whole_get_max_and_distractor_work_after_cleanup(get_fixture, count, distractors):
    f = get_fixture
    ids = roots(f, count) if count else []
    if distractors:
        from test_artifact_metadata import OTHER

        roots(f, 2000, start=1000, job=SECOND_JOB)
        roots(f, 2000, start=4000, project=OTHER, update={"parent_id": "bad"})
        roots(f, 1, start=7000, job=SECOND_JOB, update={"padding": "x" * (2 * 1024 * 1024)})
    if ids:
        publish_result(f, canonical({"run_id": ids[-1]}))
    before = sql_snapshot(f)
    value = invoke(f)
    assert value["result_run_id"] == (ids[-1] if ids else None)
    assert sql_snapshot(f) == before
    work, book = f.work[0], f.books[0]
    assert work.statements == 40 and work._started is None
    assert work.instructions < 20_000_000 and work.seconds < 10
    assert book.source_visits == count + 1 and book.edges == count * 2
    assert len(book.receipts) == count + (4 if count else 3)
    assert len(book.encoded()) <= 4 * 1024 * 1024
    print(
        f"GET SQLite roots={count} distractors={distractors} attempts={work.statements} "
        f"vm={work.instructions} seconds={work.seconds:.6f}"
    )


def test_exact_4096_encrypted_loader_boundary_and_multiple_roots(get_fixture):
    f = get_fixture
    ids = roots(f, 3)
    body = canonical({"run_id": ids[1]})
    body += b" " * (4096 - len(body))
    value = publish_result(f, body)
    assert invoke(f)["result_run_id"] == ids[1]
    assert f.loads == [value]
    assert f.work[0]._started is None


@pytest.mark.parametrize(
    "body",
    [
        b'{"run_id":"bad"}',
        b'{"run_id":null}',
        b'{"run_id":NaN}',
        b'{"run_id":"00000000000000000000000000000001","extra":1}',
        b'{"run_id":"00000000000000000000000000000001","run_id":"00000000000000000000000000000001"}',
        '{"run_id":"00000000000000000000000000000001"}'.encode("utf-16"),
        '{"run_id":"00000000000000000000000000000001"}'.encode("utf-32"),
        b'\xef\xbb\xbf{"run_id":"00000000000000000000000000000001"}',
        b'{"run_id":"ffffffffffffffffffffffffffffffff"}',
    ],
)
def test_strict_verified_result_parser_refuses(get_fixture, body):
    f = get_fixture
    roots(f, 1)
    publish_result(f, body)
    expect_dependency(lambda: invoke(f))
    assert len(f.loads) == 1 and len(f.work) == 1
    assert f.work[0].statements < 512


@pytest.mark.parametrize("mode", ["missing", "bytes", "type", "oserror", "async"])
def test_loader_failure_or_malformed_result_is_finite(get_fixture, mode):
    f = get_fixture
    ids = roots(f, 1)
    publish_result(f, canonical({"run_id": ids[0]}))

    def fail(_value):
        raise OSError("private storage path")

    async def asynchronous(_value):
        return b"wrong"

    f.service.artifact_loader = {
        "missing": None,
        "bytes": lambda _v: b"wrong",
        "type": lambda _v: {},
        "oserror": fail,
        "async": asynchronous,
    }[mode]
    expect_dependency(lambda: invoke(f))
    assert f.reader_engine.pool.checkedout() == 0


def test_null_result_observes_ref_without_loading_or_inferring(get_fixture):
    f = get_fixture
    ids = roots(f, 1)
    publish_result(f, canonical({"run_id": ids[0]}), publish=False)
    f.service.artifact_loader = lambda _v: pytest.fail("NULL result loaded")
    assert invoke(f)["result_run_id"] is None
    assert f.books[0].observations["result_count", JOB] == (1,)


def test_real_schema_guard_has_no_customer_or_loader_calls(settings, monkeypatch):
    database = Database(settings)
    try:
        database.migrate(installation_key="operation-get-real-guard")
        service = OperationService(database.engine, RequestAuthority(database.engine))
        assert service.schema_compatibility().code == "migration_only"
        original = load_release_profile().model_dump()
        monkeypatch.setattr(service, "_read", lambda *_a: pytest.fail("customer read"))
        principal = VerifiedPrincipal(PRINCIPAL)
        context = ProjectContext("8" * 32, PROJECT, principal.principal_id)
        with pytest.raises(Fault, match="^schema_incompatible$"):
            service.read_operation(principal, context, OPERATION)
        assert load_release_profile().model_dump() == original
        assert database.engine.pool.checkedout() == 0
    finally:
        database.engine.dispose()


def test_unowned_engine_refuses_before_even_schema_acquisition(stored, monkeypatch):
    service = OperationService(stored.engine, stored.authority)
    monkeypatch.setattr(service, "schema_compatibility", lambda: pytest.fail("inspection"))
    expect_dependency(lambda: service.read_operation(stored.principal, stored.context, OPERATION))


def test_viewer_is_not_required_to_be_creator(get_fixture):
    f = get_fixture
    viewer = VerifiedPrincipal("oidc:" + "f" * 64)
    with f.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:v,'viewer',NULL,false)"),
            {"p": PROJECT, "v": viewer.principal_id},
        )
    context = replace(f.context, principal_id=viewer.principal_id)
    assert invoke(f, principal=viewer, context=context)["job_id"] == JOB


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("change", ["revoke", "scope", "operation", "foreign_result"])
def test_storage_race_preserves_primary_visibility_and_secondary_refusal(
    get_fixture, change, failure
):
    f = get_fixture
    ids = roots(f, 1)
    publish_result(f, canonical({"run_id": ids[0]}))
    load = f.service.artifact_loader

    def racing(value):
        data = load(value)
        with f.engine.begin() as connection:
            if change == "revoke":
                connection.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at='2026-01-01' "
                        "WHERE principal_id=:id"
                    ),
                    {"id": PRINCIPAL},
                )
            elif change == "scope":
                connection.execute(
                    text("DELETE FROM artifact_refs WHERE owner_kind='job' AND owner_id=:id"),
                    {"id": JOB},
                )
                connection.execute(text("DELETE FROM operations WHERE id=:id"), {"id": OPERATION})
                connection.execute(
                    text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": JOB}
                )
            elif change == "operation":
                connection.execute(text("DELETE FROM operations WHERE id=:id"), {"id": OPERATION})
            else:
                connection.execute(
                    text("DELETE FROM resource_scopes WHERE resource_id=:id"), {"id": ids[0]}
                )
        if failure:
            raise ArtifactError("artifact_integrity")
        return data

    f.service.artifact_loader = racing
    if change == "foreign_result":
        expect_dependency(lambda: invoke(f))
    else:
        with pytest.raises(ResourceNotFound):
            invoke(f)
    assert len(f.loads) == 1


@pytest.mark.parametrize(
    "change",
    [
        "phantom",
        "native_blob",
        "job_created",
        "op_association",
        "ref_absent_new",
        "ref_removed",
        "ref_extra",
        "descriptor",
    ],
)
def test_final_single_statement_refuses_original_receipt_races(get_fixture, monkeypatch, change):
    f = get_fixture
    ids = roots(f, 1)
    if change in {"ref_removed", "ref_extra", "descriptor"}:
        value = publish_result(f, canonical({"run_id": ids[0]}), publish=False)
    original = f.service._load_result

    def mutate(job, descriptor_value, cohort):
        result = original(job, descriptor_value, cohort)
        if change == "phantom":
            roots(f, 1, start=2)
        elif change in {"ref_absent_new", "ref_extra"}:
            publish_result(f, canonical({"run_id": "e" * 32}), publish=False, object_id="8" * 32)
        else:
            with f.engine.begin() as connection:
                if change == "native_blob":
                    connection.execute(
                        text("UPDATE records SET data=CAST(data AS BLOB) WHERE id=:id"),
                        {"id": ids[0]},
                    )
                elif change == "job_created":
                    connection.execute(
                        text("UPDATE jobs SET created=created+1 WHERE id=:id"), {"id": JOB}
                    )
                elif change == "op_association":
                    connection.execute(
                        text(
                            "UPDATE operations SET job_id=:job,accepted_response=:response "
                            "WHERE id=:id"
                        ),
                        {
                            "job": SECOND_JOB,
                            "id": OPERATION,
                            "response": json.dumps(
                                {"job_id": SECOND_JOB, "operation_id": OPERATION},
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        },
                    )
                elif change == "ref_removed":
                    connection.execute(
                        text("DELETE FROM artifact_refs WHERE role='result' AND owner_id=:id"),
                        {"id": JOB},
                    )
                else:
                    connection.execute(
                        text("UPDATE artifact_objects SET created_at='2026-10-22' WHERE id=:id"),
                        {"id": value.id},
                    )
        return result

    monkeypatch.setattr(f.service, "_load_result", mutate)
    expect_dependency(lambda: invoke(f))
    assert (
        len(f.work) == 1 and f.work[0].statements == 50
    )  # final authority is skipped on receipt refusal
    assert f.books[0].source_visits == 2  # never reload original job/source bodies
    assert f.reader_engine.pool.checkedout() == 0


@pytest.mark.parametrize("kind", ["overflow", "study", "parent", "aggregate"])
def test_cohort_refusal_precedes_any_load(get_fixture, kind):
    f = get_fixture
    if kind == "overflow":
        roots(f, 256)
    elif kind == "study":
        roots(f, 1, kind="study")
    elif kind == "parent":
        roots(f, 1, update={"parent_id": "f" * 32})
    else:
        roots(f, 3, update={"padding": "x" * 1500000})
    f.service.artifact_loader = lambda _v: pytest.fail("invalid cohort loaded")
    expect_dependency(lambda: invoke(f))
    assert len(f.work) == 1 and f.work[0].instructions < 20_000_000


def test_changed_default_keeps_named_context(get_fixture):
    from test_artifact_metadata import OTHER

    f = get_fixture
    with f.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,true)"),
            {"p": OTHER, "id": PRINCIPAL},
        )
    assert f.authority.legacy(f.principal).context.project_id == OTHER
    assert invoke(f)["project_id"] == PROJECT
    with pytest.raises(ResourceNotFound):
        invoke(f, context=replace(f.context, project_id=OTHER))


def key_context(f, role="viewer"):
    from agent_rewind.database import keys

    key_id = "d" * 32
    principal = VerifiedPrincipal.service_key(key_id)
    with f.engine.begin() as connection:
        connection.execute(
            keys.insert().values(
                id=key_id,
                hash="f" * 64,
                name="synthetic",
                role=role,
                expires=4102444800,
                revoked=False,
            )
        )
        connection.execute(
            text("INSERT INTO resource_scopes VALUES('key',:id,:p)"), {"id": key_id, "p": PROJECT}
        )
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'maintainer',NULL,false)"),
            {"id": principal.principal_id, "p": PROJECT},
        )
    return principal, replace(f.context, principal_id=principal.principal_id)


@pytest.mark.parametrize("role", ["viewer", "operator", "administrator"])
def test_actual_key_intersection_and_post_cleanup_trace(get_fixture, role):
    f = get_fixture
    principal, context = key_context(f, role)
    assert invoke(f, principal=principal, context=context)["job_id"] == JOB
    assert f.work[0].statements == 48
    print(f"GET SQLite api-key role={role} attempts={f.work[0].statements}")


@pytest.mark.parametrize("change", ["expiry", "revoked", "scope", "role", "membership"])
def test_key_rechecked_after_loader(get_fixture, change):
    f = get_fixture
    principal, context = key_context(f)
    ids = roots(f, 1)
    publish_result(f, canonical({"run_id": ids[0]}))
    load = f.service.artifact_loader

    def mutate(value):
        data = load(value)
        with f.engine.begin() as connection:
            if change == "expiry":
                connection.exec_driver_sql("UPDATE api_keys SET expires=1")
            elif change == "revoked":
                connection.exec_driver_sql("UPDATE api_keys SET revoked=TRUE")
            elif change == "scope":
                connection.exec_driver_sql("DELETE FROM resource_scopes WHERE resource_kind='key'")
            elif change == "role":
                connection.exec_driver_sql("UPDATE api_keys SET role='unknown'")
            else:
                connection.execute(
                    text("DELETE FROM project_memberships WHERE principal_id=:id"),
                    {"id": principal.principal_id},
                )
        return data

    f.service.artifact_loader = mutate
    with pytest.raises(ResourceNotFound):
        invoke(f, principal=principal, context=context)
    assert len(f.loads) == 1 and len(f.work) == 1


def test_verified_cookie_identity_noncreator_viewer(get_fixture):
    from agent_rewind.request_identity import SessionIdentity, decode_v2_session, encode_v2_session

    f = get_fixture
    cipher = Fernet(Fernet.generate_key())
    principal = VerifiedPrincipal.oidc("https://synthetic.invalid", "viewer")
    identity = SessionIdentity(principal, "https://synthetic.invalid", "viewer", "c" * 32)
    authenticated = decode_v2_session(cipher, encode_v2_session(cipher, identity), identity.issuer)
    with f.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO project_memberships VALUES(:p,:id,'viewer',NULL,false)"),
            {"p": PROJECT, "id": principal.principal_id},
        )
    context = replace(f.context, principal_id=principal.principal_id)
    assert invoke(f, principal=authenticated.principal, context=context)["id"] == OPERATION


def test_final_authority_is_last_protected_sql_and_revocation_denies(get_fixture, monkeypatch):
    f = get_fixture
    original = f.service.authority.check
    calls, statements = [], []
    event.listen(
        f.reader_engine, "before_cursor_execute", lambda _c, _u, s, *_a: statements.append(s)
    )

    def check(connection, *args, **kwargs):
        calls.append(connection)
        if len(calls) == 4:
            with f.engine.begin() as writer:
                writer.execute(
                    text("DELETE FROM project_memberships WHERE principal_id=:id"),
                    {"id": PRINCIPAL},
                )
        return original(connection, *args, **kwargs)

    monkeypatch.setattr(f.service.authority, "check", check)
    with pytest.raises(ResourceNotFound):
        invoke(f)
    assert len(calls) == 4
    assert "project_memberships" in statements[-1]
    assert "expected_receipts" in statements[-2]


@pytest.mark.parametrize("failure", ["deadline", "close", "recheck_unavailable"])
def test_final_or_recheck_fault_never_returns_success_and_releases_pool(
    get_fixture, monkeypatch, failure
):
    f = get_fixture
    before = sql_snapshot(f)
    if failure == "deadline":
        now = [0.0]
        monkeypatch.setattr(operation_work, "perf_counter", lambda: now[0])
        original = f.service.authority.check
        calls = []

        def check(connection, *args, **kwargs):
            result = original(connection, *args, **kwargs)
            calls.append(1)
            if len(calls) == 4:
                now[0] = 10.0
            return result

        monkeypatch.setattr(f.service.authority, "check", check)
    elif failure == "close":
        original = operation_work.close_owned
        calls = []

        def close(connection, receipt):
            original(connection, receipt)
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("private close canary")

        monkeypatch.setattr(operation_work, "close_owned", close)
    else:
        with f.engine.begin() as writer:
            writer.execute(text("UPDATE jobs SET status='failed' WHERE id=:id"), {"id": JOB})
        before = sql_snapshot(f)
        connect = f.reader_engine.connect
        calls = []

        def unavailable():
            calls.append(1)
            if len(calls) == 2:
                from sqlalchemy.exc import OperationalError

                raise OperationalError("private connect", {}, Exception("canary"))
            return connect()

        monkeypatch.setattr(f.reader_engine, "connect", unavailable)
    expect_dependency(lambda: invoke(f))
    assert sql_snapshot(f) == before
    assert len(f.work) == 1 and f.work[0]._started is None
    assert f.reader_engine.pool.checkedout() == 0
    monkeypatch.undo()
    with owned_connect(f.reader_engine) as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 0


def test_programming_error_and_primary_interruption_are_not_reclassified(get_fixture, monkeypatch):
    f = get_fixture
    for error in (
        RuntimeError("private programmer canary"),
        KeyboardInterrupt("private interruption"),
    ):

        def fail(*_args, error=error):
            raise error

        monkeypatch.setattr(f.service, "_load_result", fail)
        with pytest.raises(type(error)) as caught:
            invoke(f)
        assert caught.value is error
        assert f.reader_engine.pool.checkedout() == 0


def test_no_hidden_lineage_sql_or_nested_connection(get_fixture, monkeypatch):
    from agent_rewind.scoped_lineage import Lineage

    f = get_fixture
    # Cohort legitimately calls pure cached Lineage; any repository-backed
    # resource path would call this forbidden _Reads.resource instead.
    from agent_rewind.scoped_repositories import _Reads

    monkeypatch.setattr(_Reads, "resource", lambda *_a: pytest.fail("hidden resource read"))
    monkeypatch.setattr(f.service.authority, "named", lambda *_a: pytest.fail("new context"))
    original = Lineage.validate
    calls = []

    def validate(self, kind, identifier):
        calls.append((kind, identifier))
        return original(self, kind, identifier)

    monkeypatch.setattr(Lineage, "validate", validate)
    assert invoke(f)["id"] == OPERATION
    assert calls == [("job", JOB)]


@pytest.mark.parametrize("revoke", [False, True])
def test_loader_missing_secondary_is_not_primary_not_found(get_fixture, revoke):
    f = get_fixture
    ids = roots(f, 1)
    publish_result(f, canonical({"run_id": ids[0]}))

    def missing(_descriptor):
        if revoke:
            with f.engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM project_memberships WHERE principal_id=:id"),
                    {"id": PRINCIPAL},
                )
        raise ResourceNotFound()

    f.service.artifact_loader = missing
    if revoke:
        with pytest.raises(ResourceNotFound):
            invoke(f)
    else:
        expect_dependency(lambda: invoke(f))


@pytest.mark.parametrize("missing", ["id", "context", "principal"])
def test_primary_visibility_inputs_never_load(get_fixture, missing):
    from agent_rewind.request_identity import IdentityInvalid

    f = get_fixture
    f.service.artifact_loader = lambda _v: pytest.fail("primary denial loaded")
    if missing == "id":
        with pytest.raises(ResourceNotFound):
            invoke(f, operation_id="not-an-id")
    elif missing == "context":
        from test_artifact_metadata import OTHER

        with pytest.raises(ResourceNotFound):
            invoke(f, context=replace(f.context, project_id=OTHER))
    else:
        with pytest.raises(IdentityInvalid):
            invoke(f, principal=None)


@pytest.mark.parametrize("change", ["digest", "missing_ref", "oversize", "actor"])
def test_metadata_association_refuses_before_loader(get_fixture, change):
    f = get_fixture
    with f.engine.begin() as connection:
        if change == "digest":
            connection.execute(
                text("UPDATE jobs SET result=:v WHERE id=:id"), {"v": "b" * 64, "id": JOB}
            )
        elif change == "missing_ref":
            connection.execute(
                text("DELETE FROM artifact_refs WHERE role='admission_config' AND owner_id=:id"),
                {"id": JOB},
            )
        elif change == "actor":
            connection.execute(
                text("UPDATE jobs SET actor=:v WHERE id=:id"), {"v": "oidc:" + "f" * 64, "id": JOB}
            )
        else:
            value = descriptor(b"x" * 4097, object_id="9" * 32, project=PROJECT)
            record_verified(connection, value)
            register_ref(
                connection,
                project_id=PROJECT,
                owner_kind="job",
                owner_id=JOB,
                role="result",
                artifact_id=value.id,
            )
    f.service.artifact_loader = lambda _v: pytest.fail("invalid metadata loaded")
    expect_dependency(lambda: invoke(f))


def test_readonly_native_mode_blocks_injected_write_and_recovers(get_fixture, monkeypatch):
    f = get_fixture
    before = sql_snapshot(f)
    original = operation_service.read_operation

    def writing(connection, *args, **kwargs):
        connection.execute(text("UPDATE jobs SET cancel=TRUE WHERE id=:id"), {"id": JOB})
        return original(connection, *args, **kwargs)

    monkeypatch.setattr(operation_service, "read_operation", writing)
    expect_dependency(lambda: invoke(f))
    assert sql_snapshot(f) == before
    monkeypatch.setattr(operation_service, "read_operation", original)
    assert invoke(f)["cancel_requested"] is False


def test_final_receipt_scope_is_one_statement_and_authority_last(get_fixture):
    f = get_fixture
    statements = []
    event.listen(
        f.reader_engine, "before_cursor_execute", lambda _c, _u, s, *_a: statements.append(s)
    )
    assert invoke(f)["id"] == OPERATION
    assert sum("expected_receipts" in sql for sql in statements) == 1
    assert "project_memberships" in statements[-1]
    assert "expected_receipts" in statements[-2]
    assert all(
        not sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements
    )
