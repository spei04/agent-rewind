"""Execute the installed-package helper body against explicit synthetic migrations."""

import ast
import re
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from test_ownership import FRESH

from agent_rewind.api import create_app
from agent_rewind.migrations.artifact_service import initialize_artifacts
from agent_rewind.migrations.compatibility import CompatibilityResult, runtime_schema_compatibility
from agent_rewind.migrations.ownership_service import initialize_ownership
from agent_rewind.migrations.projection_service import initialize_projection
from agent_rewind.migrations.service import install
from agent_rewind.scoped_repositories import ResourceNotFound


def test_actual_package_helper_round_trip_scoped_reader_and_http_routes(tmp_path):
    script = Path(__file__).parents[1] / "scripts/ci_smoke.py"
    node = next(
        n
        for n in ast.parse(script.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "run_listing_smoke"
    )
    namespace = {"Engine": Engine, "ResourceNotFound": ResourceNotFound}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(script), "exec"), namespace)
    engine = create_engine(f"sqlite:///{tmp_path / 'package.sqlite'}")
    try:
        install(engine, FRESH["installation_key"])
        initialize_ownership(engine, FRESH)
        initialize_artifacts(engine)
        initialize_projection(engine)
        with engine.connect() as connection:
            before = connection.execute(text("SELECT * FROM project_memberships")).all()
        namespace["run_listing_smoke"](engine)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT * FROM project_memberships")).all() == before
        assert runtime_schema_compatibility(engine).code == "migration_only"
    finally:
        engine.dispose()


@pytest.fixture
def check_real_guard():
    """Load the shipped nested checker without running unrelated package smokes."""
    script = Path(__file__).parents[1] / "scripts/ci_smoke.py"
    listing = next(
        node
        for node in ast.parse(script.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "run_listing_smoke"
    )
    checker = next(
        node
        for node in listing.body
        if isinstance(node, ast.FunctionDef) and node.name == "check_real_guard"
    )
    namespace = {
        "FastAPI": FastAPI,
        "TestClient": TestClient,
        "CompatibilityResult": CompatibilityResult,
    }
    exec(compile(ast.Module(body=[checker], type_ignores=[]), str(script), "exec"), namespace)
    return namespace["check_real_guard"]


@pytest.mark.parametrize("phase", ["first", "fresh-instance"])
@pytest.mark.parametrize(
    "verdict,status,code",
    [
        (CompatibilityResult("unavailable", "schema_unavailable"), 503, "dependency_unavailable"),
        (CompatibilityResult("ready", "PRIVATE-GUARD-CANARY"), 401, "unauthenticated"),
    ],
)
def test_real_http_guard_failure_still_refuses_with_bounded_observations(
    settings, check_real_guard, phase, verdict, status, code
):
    app = create_app(settings)
    calls = []

    def original():
        calls.append(verdict)
        return verdict

    app.state.db.schema_compatibility = original
    client = TestClient(app)
    try:
        with pytest.raises(RuntimeError) as caught:
            check_real_guard(app, client, "/api/v1/projects/" + "9" * 32 + "/runs", phase)
        message = str(caught.value)
        assert f"Installed listing {phase} guard mismatch:" in message
        assert f"http_status={status} http_code={code}" in message
        assert f"probe_calls=1 probe_status={verdict.status}" in message
        expected_code = "schema_unavailable" if verdict.status == "unavailable" else "unknown"
        assert f"probe_code={expected_code}" in message
        assert re.search(r"probe_elapsed_ms=\d+\.\d{3}$", message)
        assert "PRIVATE-GUARD-CANARY" not in message
        assert calls == [verdict]
        assert app.state.db.schema_compatibility is original
    finally:
        client.close()
        app.state.db.engine.dispose()


def test_observer_returns_the_original_result_once_and_restores_guard(check_real_guard):
    verdict = CompatibilityResult("incompatible", "migration_only")
    calls = []

    def original():
        calls.append("guard")
        return verdict

    app = SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(schema_compatibility=original)))

    class Client:
        def get(self, path):
            calls.append(path)
            assert app.state.db.schema_compatibility() is verdict
            return httpx.Response(503, json={"code": "schema_incompatible"})

    check_real_guard(app, Client(), "/synthetic-only", "first")
    assert calls == ["/synthetic-only", "guard"]
    assert app.state.db.schema_compatibility is original


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, content=b"not-json PRIVATE-RESPONSE-CANARY"),
        httpx.Response(503, json=None),
        httpx.Response(503, json=[]),
        httpx.Response(503, json={"message": "PRIVATE-RESPONSE-CANARY"}),
        httpx.Response(503, json={"code": ["PRIVATE-RESPONSE-CANARY"]}),
        httpx.Response(503, json={"code": "PRIVATE-RESPONSE-CANARY"}),
        httpx.Response(200, json={"code": "schema_incompatible"}),
    ],
)
def test_malformed_or_wrong_status_response_never_passes_or_leaks(check_real_guard, response):
    calls = []
    verdict = CompatibilityResult("incompatible", "PRIVATE-GUARD-CANARY")

    def original():
        calls.append("guard")
        return verdict

    app = SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(schema_compatibility=original)))

    class Client:
        def get(self, path):
            assert app.state.db.schema_compatibility() is verdict
            return response

    with pytest.raises(RuntimeError) as caught:
        check_real_guard(app, Client(), "/synthetic-only", "first")
    message = str(caught.value)
    assert f"http_status={response.status_code}" in message
    assert "probe_calls=1 probe_status=incompatible probe_code=unknown" in message
    assert "PRIVATE-" not in message
    assert calls == ["guard"]
    assert app.state.db.schema_compatibility is original


def test_missing_probe_is_reported_without_inventing_an_extra_call(check_real_guard):
    def original():
        pytest.fail("The observer invented an additional compatibility probe")

    app = SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(schema_compatibility=original)))
    client = SimpleNamespace(
        get=lambda path: httpx.Response(503, json={"code": "dependency_unavailable"})
    )
    with pytest.raises(RuntimeError) as caught:
        check_real_guard(app, client, "/synthetic-only", "first")
    assert "probe_calls=0 probe_status=not_invoked probe_code=unknown" in str(caught.value)
    assert app.state.db.schema_compatibility is original


@pytest.mark.parametrize("failure", [RuntimeError("PRIVATE-EXCEPTION"), KeyboardInterrupt()])
def test_original_guard_exception_identity_and_cleanup_are_preserved(check_real_guard, failure):
    calls = []

    def original():
        calls.append("guard")
        raise failure

    app = SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(schema_compatibility=original)))

    class Client:
        def get(self, path):
            return app.state.db.schema_compatibility()

    with pytest.raises(type(failure)) as caught:
        check_real_guard(app, Client(), "/synthetic-only", "first")
    assert caught.value is failure
    assert calls == ["guard"]
    assert app.state.db.schema_compatibility is original


def test_pending_probe_is_observed_without_waiting_or_retrying(check_real_guard):
    entered = Event()
    release = Event()
    calls = []
    verdict = CompatibilityResult("incompatible", "migration_only")

    def original():
        calls.append("guard")
        entered.set()
        assert release.wait(5), "Test must release the original probe"
        return verdict

    app = SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(schema_compatibility=original)))
    worker = None
    results = []

    class Client:
        def get(self, path):
            nonlocal worker
            observed_guard = app.state.db.schema_compatibility
            worker = Thread(target=lambda: results.append(observed_guard()))
            worker.start()
            assert entered.wait(5), "Original probe did not start"
            return httpx.Response(503, json={"code": "dependency_unavailable"})

    try:
        with pytest.raises(RuntimeError) as caught:
            check_real_guard(app, Client(), "/synthetic-only", "first")
        message = str(caught.value)
        assert "probe_calls=1 probe_status=pending probe_code=unknown" in message
        assert re.search(r"probe_elapsed_ms=\d+\.\d{3}$", message)
        assert worker is not None and worker.is_alive()
        assert app.state.db.schema_compatibility is original
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
            assert not worker.is_alive()
    assert calls == ["guard"]
    assert results == [verdict]
    assert results[0] is verdict


def test_malformed_probe_result_is_preserved_and_reported_as_unknown(check_real_guard):
    calls = []

    def original():
        calls.append("guard")
        return None

    app = SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(schema_compatibility=original)))

    class Client:
        def get(self, path):
            assert app.state.db.schema_compatibility() is None
            return httpx.Response(503, json={"code": "dependency_unavailable"})

    with pytest.raises(RuntimeError) as caught:
        check_real_guard(app, Client(), "/synthetic-only", "first")
    assert "probe_calls=1 probe_status=unknown probe_code=unknown" in str(caught.value)
    assert calls == ["guard"]
    assert app.state.db.schema_compatibility is original
