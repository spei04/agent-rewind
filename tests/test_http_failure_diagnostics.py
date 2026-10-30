"""Original-call, safe-output and retained-primary controls for the HTTP witness."""

import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from types import FunctionType, SimpleNamespace

import http_failure_diagnostics
import pytest
from http_app_cleanup import http_application_cache_cleanup as http_application_cache_cleanup
from http_failure_diagnostics import (
    MAX_BYTES,
    MAX_EXCEPTIONS,
    compatibility_failure,
    first_get_failure,
    route_failure,
)
from sqlalchemy.exc import OperationalError
from test_admission_transaction import engine
from test_operation_http import admission_engine, http_operation, publication
from test_sqlite_ownership import engine as owned_engine

from agent_rewind import api, errors, listing_session
from agent_rewind.admission_transaction import AdmissionError
from agent_rewind.migrations import compatibility as guard
from agent_rewind.operation_work import OperationWork, operation_connection
from agent_rewind.scoped_repositories import RepositoryUnavailable

__all__ = ["engine", "admission_engine", "http_operation", "publication", "owned_engine"]


def test_witness_preserves_original_classifier_calls_and_restores_on_exit(monkeypatch, capsys):
    original = errors.classified
    error = RuntimeError("private-canary")
    scope = {"method": "GET"}
    calls = []

    def classify(actual_scope, actual_error):
        calls.append((actual_scope, actual_error))
        return original(actual_scope, actual_error)

    monkeypatch.setattr(errors, "classified", classify)
    interruption = KeyboardInterrupt()
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        first_get_failure(monkeypatch) as report,
    ):
        assert errors.classified(scope, error) == "internal_error"
        assert json.loads(report())["classified"][0]["exceptions"][0]["type"] == "RuntimeError"
        raise interruption
    assert caught.value is interruption
    assert errors.classified is classify
    assert calls == [(scope, error)]
    assert capsys.readouterr() == ("", "")
    errors.classified(scope, error)
    assert len(calls) == 2  # Later requests no longer enter the witness.

    def observer_failure(_error):
        raise ValueError("private-observer-canary")

    monkeypatch.setattr(http_failure_diagnostics, "exception_evidence", observer_failure)
    with first_get_failure(monkeypatch) as report:
        assert errors.classified(scope, error) == "internal_error"
        assert json.loads(report())["classified"][0]["diagnostic_unavailable"]
    assert calls == [(scope, error)] * 3

    def classifier_failure(_scope, _error):
        raise interruption

    monkeypatch.setattr(errors, "classified", classifier_failure)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        first_get_failure(monkeypatch) as report,
    ):
        errors.classified(scope, error)
    assert caught.value is interruption and errors.classified is classifier_failure
    assert json.loads(report())["classified"] == []


def test_witness_bounds_and_redacts_sql_exception_payloads_and_cycles(monkeypatch):
    secret = "private-canary"
    database = OperationalError(secret, {"secret": secret}, RuntimeError(secret))
    unknown_type = type(secret, (RuntimeError,), {})
    root = unknown_type(secret)
    root.code = secret
    root.__cause__ = database
    previous = database
    for _ in range(30):
        following = RuntimeError(secret)
        previous.__context__ = following
        previous = following
    previous.__context__ = root

    def raise_root():
        raise root

    spoofed = FunctionType(
        raise_root.__code__.replace(co_filename=secret, co_name=secret),
        globals(),
        closure=raise_root.__closure__,
    )
    with pytest.raises(unknown_type) as caught:
        spoofed()
    assert caught.value is root
    with first_get_failure(monkeypatch) as report:
        assert errors.classified({"method": "GET", "path": secret}, root) == "internal_error"
        encoded = report()
    assert secret not in encoded and len(encoded.encode()) <= MAX_BYTES
    evidence = json.loads(encoded)["classified"][0]
    assert len(evidence["exceptions"]) == MAX_EXCEPTIONS and evidence["truncated"]
    assert evidence["exceptions"][0]["type"] == "OtherException"
    assert any(item["type"] == "OperationalError" for item in evidence["exceptions"])

    def refused_probe():
        raise root

    app = SimpleNamespace(
        state=SimpleNamespace(
            db=SimpleNamespace(
                schema_compatibility=refused_probe,
            )
        )
    )
    with route_failure(monkeypatch, app, phase="schema_guard_expected_incompatible") as report:
        with pytest.raises(unknown_type) as caught:
            app.state.db.schema_compatibility()
        assert caught.value is root
        assert errors.classified({"method": "GET", "app": app}, root) == "internal_error"
        encoded = report()
    assert app.state.db.schema_compatibility is refused_probe
    assert secret not in encoded and len(encoded.encode()) <= MAX_BYTES
    report_data = json.loads(encoded)
    assert (
        sum(
            len(event.get("exceptions", []))
            for name in ("probes", "guard", "security", "classified")
            for event in report_data[name]
        )
        == MAX_EXCEPTIONS
    )
    assert report_data["classified"][0]["error"]["type"] == "OtherException"
    assert report_data["classified"][0]["exceptions"] == []


def test_witness_observes_pre_service_named_authority_failure(http_operation, monkeypatch):
    original_error = RepositoryUnavailable()
    original_error.args = ("private-canary",)
    calls = []

    def unavailable(*args, **kwargs):
        calls.append((args, kwargs))
        raise original_error

    monkeypatch.setattr(http_operation.f.authority, "named", unavailable)
    with first_get_failure(monkeypatch) as report:
        response = http_operation.client.get(
            http_operation.base + "/operations/" + "a" * 32, headers=http_operation.headers
        )
        encoded = report()
    assert response.status_code == 503 and response.json()["code"] == "dependency_unavailable"
    assert len(calls) == 1 and "private-canary" not in encoded
    evidence = json.loads(encoded)["classified"][0]
    assert evidence["exceptions"][0]["type"] == "RepositoryUnavailable"
    assert any(
        frame["file"] == "operation_http.py" and frame["function"] == "named"
        for item in evidence["exceptions"]
        for frame in item["frames"]
    )


def test_witness_retains_real_connection_primary_and_cleanup_without_payloads(engine, monkeypatch):
    original_error = sqlite3.OperationalError("private-sql-and-parameters")
    work = OperationWork()
    with first_get_failure(monkeypatch) as report:
        try:
            with operation_connection(engine, work):
                raise original_error
        except AdmissionError as outward:
            assert outward is not original_error
            assert errors.classified({"method": "GET"}, outward) == "internal_error"
        else:
            pytest.fail("Expected the original connection refusal")
        encoded = report()
    evidence = json.loads(encoded)["classified"][0]
    phases = [
        frame
        for item in evidence["exceptions"]
        for frame in item["frames"]
        if frame["file"] == "operation_work.py" and frame["function"] == "operation_connection"
    ]
    assert phases and phases[0]["primary"]["type"] == "SQLiteOperationalError"
    assert phases[0]["phase"]["setup_ok"] and not phases[0]["phase"]["cleanup_failed"]
    assert phases[0]["work"]["statements"] == work.statements
    assert any(item["relation"] == "retained_primary" for item in evidence["exceptions"])
    assert "private-sql-and-parameters" not in encoded
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("kind", ["timeout", "sqlalchemy"])
def test_route_witness_attributes_only_owned_swallowed_guard_errors(settings, monkeypatch, kind):
    app = api.create_app(settings)
    app.state.db.migrate(installation_key="synthetic-diagnostic-control")
    canary = "private-guard-sql-and-parameters"
    original_error = (
        TimeoutError(canary)
        if kind == "timeout"
        else OperationalError(canary, {"canary": canary}, RuntimeError(canary))
    )
    calls = []
    returned = []
    original_probe = app.state.db.schema_compatibility
    original_constructor = guard.CompatibilityResult
    original_response = api.error_response
    original_classifier = errors.classified
    original_evidence = http_failure_diagnostics.exception_evidence
    serialized = []

    def evidence_spy(error, **kwargs):
        serialized.append(error)
        return original_evidence(error, **kwargs)

    monkeypatch.setattr(http_failure_diagnostics, "exception_evidence", evidence_spy)

    def failing_step(*args, **kwargs):
        calls.append(1)
        raise original_error

    def counted_probe():
        result = original_probe()
        returned.append(result)
        return result

    monkeypatch.setattr(app.state.db, "schema_compatibility", counted_probe)
    target = "load_release_profile" if kind == "timeout" else "schema_table_names"
    monkeypatch.setattr(guard, target, failing_step)
    try:
        with route_failure(monkeypatch, app, phase="schema_guard_expected_incompatible") as report:
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(app.state.db.schema_compatibility).result(timeout=5)
            assert result is returned[0] and type(result) is original_constructor
            assert (result.status, result.code) == ("unavailable", "schema_unavailable")
            before = report()
            # An inherited active exception in an unowned thread is not this probe.
            try:
                raise RuntimeError(canary)
            except RuntimeError:
                unrelated = guard.CompatibilityResult("unavailable", "schema_unavailable")
            assert type(unrelated) is original_constructor and report() == before
            encoded = report()
        assert app.state.db.schema_compatibility is counted_probe
        assert guard.CompatibilityResult is original_constructor
        assert api.error_response is original_response and errors.classified is original_classifier
        evidence = json.loads(encoded)
        assert calls == [1] and len(evidence["guard"]) == 1
        assert len(serialized) == 1 and serialized[0] is original_error
        observed = evidence["guard"][0]
        assert observed["error"]["type"] == (
            "TimeoutError" if kind == "timeout" else "OperationalError"
        )
        assert observed["stage"] == (
            "runtime_schema_compatibility" if kind == "timeout" else "_check_schema_compatibility"
        )
        assert evidence["probes"] == [
            {
                "stage": "returned",
                "result": {"status": "unavailable", "code": "schema_unavailable"},
            }
        ]
        assert evidence["security"] == [] and evidence["classified"] == []
        assert canary not in encoded and len(encoded.encode()) <= MAX_BYTES

        failed_observations = []

        def observer_failed(error, **_kwargs):
            failed_observations.append(error)
            raise ValueError("private-observer-canary")

        with monkeypatch.context() as patch:
            patch.setattr(http_failure_diagnostics, "exception_evidence", observer_failed)
            with route_failure(
                monkeypatch, app, phase="schema_guard_expected_incompatible"
            ) as failed_report:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    preserved = pool.submit(app.state.db.schema_compatibility).result(timeout=5)
                assert preserved is returned[-1] and type(preserved) is original_constructor
                assert (preserved.status, preserved.code) == ("unavailable", "schema_unavailable")
            assert json.loads(failed_report())["guard"] == [{"diagnostic_unavailable": True}]
            assert "private-observer-canary" not in failed_report()
        assert calls == [1, 1] and len(returned) == 2
        assert len(failed_observations) == 1 and failed_observations[0] is original_error
        assert app.state.db.schema_compatibility is counted_probe
        assert guard.CompatibilityResult is original_constructor
        assert http_failure_diagnostics.exception_evidence is evidence_spy

        # A raised probe, unlike a swallowed guard refusal, preserves the same interruption.
        interruption = KeyboardInterrupt(canary)

        def interrupted():
            raise interruption

        monkeypatch.setattr(app.state.db, "schema_compatibility", interrupted)
        with (
            pytest.raises(KeyboardInterrupt) as caught,
            route_failure(monkeypatch, app, phase="schema_guard_expected_incompatible") as report,
        ):
            app.state.db.schema_compatibility()
        assert caught.value is interruption and app.state.db.schema_compatibility is interrupted
        assert json.loads(report())["probes"][0]["stage"] == "raised"
        assert guard.CompatibilityResult is original_constructor
    finally:
        app.state.db.engine.dispose()


def test_route_witness_retains_listing_primary_work_and_finite_native_reason(
    owned_engine, monkeypatch
):
    app = SimpleNamespace(
        state=SimpleNamespace(
            db=SimpleNamespace(
                schema_compatibility=lambda: guard.CompatibilityResult("ready", "test-only"),
            )
        )
    )
    original_error = sqlite3.OperationalError("private-listing-sql-and-parameters")
    original_error.sqlite_errorcode = sqlite3.SQLITE_INTERRUPT
    original_error.sqlite_errorname = "private-untrusted-name"
    work = listing_session.SQLWork()
    original_classifier = errors.classified
    with route_failure(monkeypatch, app, phase="listing_continuation_expected_200") as report:
        try:
            with listing_session.listing_connection(owned_engine, work) as connection:
                assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
                raise original_error
        except errors.Fault as outward:
            assert outward is not original_error
            trace = outward.__traceback__
            while (
                trace.tb_frame.f_code is not listing_session.listing_connection.__wrapped__.__code__
            ):
                trace = trace.tb_next
            assert trace.tb_frame.f_locals["primary"] is original_error
            del trace
            assert (
                errors.classified({"method": "GET", "app": app}, outward)
                == "dependency_unavailable"
            )
        else:
            pytest.fail("Expected original listing refusal")
        encoded = report()
    assert errors.classified is original_classifier
    evidence = json.loads(encoded)["classified"][0]
    frames = [
        frame
        for item in evidence["exceptions"]
        if item["relation"] == "classified"
        for frame in item["frames"]
        if frame["file"] == "listing_session.py" and frame["function"] == "listing_connection"
    ]
    assert len(frames) == 1
    frame = frames[0]
    # Broken owned SQLite generations are quarantined, not certified clean.
    assert frame["phase"] == {"entered": True, "broken": True, "failed": True, "progress": True}
    assert frame["primary"] == {"type": "SQLiteOperationalError", "sqlite_reason": "interrupt"}
    assert not frame["primary_is_none"]
    assert frame["work"]["statements"] == work.statements and work.statements > 0
    assert frame["work"]["started_is_none"] and work.started is None
    primaries = [item for item in evidence["exceptions"] if item["relation"] == "retained_primary"]
    assert len(primaries) == 1 and primaries[0]["type"] == "SQLiteOperationalError"
    retained_frames = [
        frame
        for frame in primaries[0]["frames"]
        if frame["file"] == "listing_session.py" and frame["function"] == "listing_connection"
    ]
    assert len(retained_frames) == 1 and retained_frames[0]["phase"] == frames[0]["phase"]
    assert "private-" not in encoded and len(encoded.encode()) <= MAX_BYTES
    assert owned_engine.pool.checkedout() == 0
    # Unknown attributes never become labels, even when their names look native.
    original_error.sqlite_errorcode = 999999
    assert http_failure_diagnostics._identity(original_error) == {"type": "SQLiteOperationalError"}

    interruption = KeyboardInterrupt("private-classifier")

    def interrupted(_scope, _error):
        raise interruption

    monkeypatch.setattr(errors, "classified", interrupted)
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        route_failure(monkeypatch, app, phase="listing_continuation_expected_200") as report,
    ):
        errors.classified({"app": app}, original_error)
    assert caught.value is interruption and errors.classified is interrupted
    assert json.loads(report())["classified"] == []


def test_route_witness_distinguishes_cleanup_generated_listing_refusal(owned_engine, monkeypatch):
    app = SimpleNamespace(
        state=SimpleNamespace(
            db=SimpleNamespace(
                schema_compatibility=lambda: guard.CompatibilityResult("ready", "test-only"),
            )
        )
    )
    work = listing_session.SQLWork()
    original_finish = listing_session.finish_owned
    calls = []

    def finished_then_failed(*args):
        result = original_finish(*args)
        calls.append(result)
        raise RuntimeError("private-cleanup-canary")

    with monkeypatch.context() as patch:
        patch.setattr(listing_session, "finish_owned", finished_then_failed)
        with route_failure(monkeypatch, app, phase="listing_continuation_expected_200") as report:
            with (
                pytest.raises(errors.Fault) as caught,
                listing_session.listing_connection(owned_engine, work) as connection,
            ):
                assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
            assert (
                errors.classified({"method": "GET", "app": app}, caught.value)
                == "dependency_unavailable"
            )
            encoded = report()
    assert len(calls) == 1 and listing_session.finish_owned is original_finish
    evidence = json.loads(encoded)["classified"][0]
    frames = [
        frame
        for item in evidence["exceptions"]
        for frame in item["frames"]
        if frame["file"] == "listing_session.py" and frame["function"] == "listing_connection"
    ]
    assert len(frames) == 1 and frames[0]["primary_is_none"]
    assert frames[0]["phase"]["entered"] and frames[0]["phase"]["failed"]
    assert not frames[0]["phase"]["broken"] and "primary" not in frames[0]
    assert frames[0]["work"]["statements"] == work.statements
    assert frames[0]["work"]["started_is_none"] and work.started is None
    assert "private-cleanup-canary" not in encoded and owned_engine.pool.checkedout() == 0
    with listing_session.listing_connection(owned_engine, listing_session.SQLWork()) as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


@pytest.mark.parametrize("kind", ["timeout", "sqlalchemy"])
def test_standalone_compatibility_witness_preserves_guard_errors(owned_engine, monkeypatch, kind):
    from ledger_eligibility_fixture import predecessor_compatibility

    canary = "private-standalone-sql-and-parameters"
    original_error = (
        TimeoutError(canary)
        if kind == "timeout"
        else OperationalError(canary, {"canary": canary}, RuntimeError(canary))
    )
    original_constructor = guard.CompatibilityResult
    original_evidence = http_failure_diagnostics.exception_evidence
    calls, returned, serialized = [], [], []

    def evidence_spy(error, **kwargs):
        serialized.append(error)
        return original_evidence(error, **kwargs)

    def failing_step(*args, **kwargs):
        calls.append(1)
        raise original_error

    def original_probe():
        return guard.runtime_schema_compatibility(owned_engine)

    def counted_probe():
        result = original_probe()
        returned.append(result)
        return result

    service = SimpleNamespace(schema_compatibility=counted_probe)
    if kind == "sqlalchemy":
        from agent_rewind.sqlite_ownership import owned_connect

        # Reach the inner guard through a real file, without bypassing its missing-file gate.
        with owned_connect(owned_engine):
            pass
    monkeypatch.setattr(http_failure_diagnostics, "exception_evidence", evidence_spy)
    target = "load_release_profile" if kind == "timeout" else "schema_table_names"
    monkeypatch.setattr(guard, target, failing_step)
    with compatibility_failure(service) as report:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(service.schema_compatibility).result(timeout=5)
            before = report()
            # The same worker's unwrapped original call has no owned probe token.
            unowned = pool.submit(original_probe).result(timeout=5)
        assert result is returned[0] and type(result) is original_constructor
        assert unowned == result and report() == before
        encoded = report()
    assert service.schema_compatibility is counted_probe
    assert guard.CompatibilityResult is original_constructor
    evidence = json.loads(encoded)
    assert calls == [1, 1] and returned == [result]
    assert len(serialized) == 1 and serialized[0] is original_error
    assert evidence["probes"] == [
        {"stage": "returned", "result": {"status": "unavailable", "code": "schema_unavailable"}}
    ]
    assert len(evidence["guard"]) == 1
    observed = evidence["guard"][0]
    assert observed["stage"] == (
        "runtime_schema_compatibility" if kind == "timeout" else "_check_schema_compatibility"
    )
    assert observed["error"]["type"] == (
        "TimeoutError" if kind == "timeout" else "OperationalError"
    )
    assert evidence["security"] == evidence["classified"] == []
    assert canary not in encoded and len(encoded.encode()) <= MAX_BYTES

    failed_observations = []

    def observer_failed(error, **kwargs):
        failed_observations.append(error)
        raise ValueError("private-observer-canary")

    with monkeypatch.context() as patch:
        patch.setattr(http_failure_diagnostics, "exception_evidence", observer_failed)
        with compatibility_failure(service) as report:
            preserved = service.schema_compatibility()
        assert preserved is returned[-1] and type(preserved) is original_constructor
        assert (preserved.status, preserved.code) == ("unavailable", "schema_unavailable")
        assert json.loads(report())["guard"] == [{"diagnostic_unavailable": True}]
        assert "private-observer-canary" not in report()
    assert failed_observations == [original_error] and calls == [1, 1, 1]
    assert service.schema_compatibility is counted_probe
    assert guard.CompatibilityResult is original_constructor

    success = original_constructor("incompatible", "migration_only")
    successful = SimpleNamespace(schema_compatibility=lambda: success)
    saved_success = successful.schema_compatibility
    records = []
    assert predecessor_compatibility(successful, lambda *row: records.append(row)) is success
    assert successful.schema_compatibility is saved_success and len(records) == 1

    interruption = KeyboardInterrupt(canary)

    def interrupted():
        raise interruption

    service.schema_compatibility = interrupted
    with pytest.raises(KeyboardInterrupt) as caught, compatibility_failure(service) as report:
        service.schema_compatibility()
    assert caught.value is interruption and service.schema_compatibility is interrupted
    assert guard.CompatibilityResult is original_constructor
    assert json.loads(report())["probes"][0]["stage"] == "raised"
    assert canary not in report()

    # Rendering and note-attachment failures cannot replace the strict assertion.
    failed_result = original_constructor("unavailable", "schema_unavailable")
    service.schema_compatibility = lambda: failed_result
    saved_probe = service.schema_compatibility
    for mode in ("render", "attach"):
        assertions = []

        def broken_report(_report, mode=mode, assertions=assertions):
            assertions.append(sys.exception())
            if mode == "render":
                raise ValueError("private-render-canary")
            return object()

        with monkeypatch.context() as patch:
            patch.setattr(http_failure_diagnostics, "_route_message", broken_report)
            with pytest.raises(AssertionError) as caught:
                predecessor_compatibility(service, lambda *_: None)
        assert assertions == [caught.value] and caught.value.args == (failed_result,)
        assert getattr(caught.value, "__notes__", []) == []
        assert service.schema_compatibility is saved_probe
        assert guard.CompatibilityResult is original_constructor


@pytest.mark.parametrize("stage", ["inner", "outer", "raised"])
def test_cancellation_compatibility_witness_preserves_guard_mapping(
    owned_engine, monkeypatch, stage
):
    from test_admission_schema import OPERATION, PRINCIPAL, PROJECT
    from test_operation_cancel_service_postgres import fault

    from agent_rewind.operation_service import OperationService
    from agent_rewind.request_authority import RequestAuthority
    from agent_rewind.request_identity import VerifiedPrincipal
    from agent_rewind.scoped_repositories import ProjectContext
    from agent_rewind.sqlite_ownership import owned_begin, owned_connect

    canary = "private-cancellation-error-sql-and-parameters"
    original_error = (
        TimeoutError(canary)
        if stage == "outer"
        else OperationalError(canary, {"private": canary}, RuntimeError(canary))
    )
    # A real file/owned connection reaches the inner guard without bypassing its gate.
    with owned_begin(owned_engine) as connection:
        connection.exec_driver_sql("CREATE TABLE cancellation_witness (value INTEGER)")
        connection.exec_driver_sql("INSERT INTO cancellation_witness VALUES (1)")

    def state():
        with owned_connect(owned_engine) as connection:
            return connection.exec_driver_sql(
                "SELECT value FROM cancellation_witness ORDER BY value"
            ).all()

    before = state()
    service = OperationService(owned_engine, RequestAuthority(owned_engine))
    principal = VerifiedPrincipal(PRINCIPAL)
    context = ProjectContext("8" * 32, PROJECT, PRINCIPAL)
    original_probe = service.schema_compatibility
    original_constructor = guard.CompatibilityResult
    original_evidence = http_failure_diagnostics.exception_evidence
    original_render = http_failure_diagnostics._route_message
    calls, failed_steps, returned, constructed, serialized, targets, faults = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )

    def failing_step(*args, **kwargs):
        failed_steps.append(1)
        raise original_error

    def counted_probe():
        calls.append(1)
        if stage == "raised":
            raise original_error
        result = original_probe()
        returned.append(result)
        return result

    def constructor(*args, **kwargs):
        result = original_constructor(*args, **kwargs)
        constructed.append(result)
        return result

    def evidence(error, **kwargs):
        serialized.append(error)
        return original_evidence(error, **kwargs)

    def forbidden_target(*args, **kwargs):
        targets.append(1)
        pytest.fail("guard entered cancellation target")

    def cancel():
        try:
            return service.cancel_operation(principal, context, OPERATION)
        except errors.Fault as error:
            faults.append(error)
            raise

    monkeypatch.setattr(service, "schema_compatibility", counted_probe)
    monkeypatch.setattr(service, "_cancel", forbidden_target)
    monkeypatch.setattr(guard, "CompatibilityResult", constructor)
    monkeypatch.setattr(http_failure_diagnostics, "exception_evidence", evidence)
    if stage != "raised":
        target = "load_release_profile" if stage == "outer" else "schema_table_names"
        monkeypatch.setattr(guard, target, failing_step)

    if stage == "inner":
        with (
            pytest.raises(ValueError, match="^unsupported diagnostic phase$"),
            compatibility_failure(service, phase=canary),
        ):
            pytest.fail("unsupported phase entered observer")
        assert calls == [] and service.schema_compatibility is counted_probe
        assert guard.CompatibilityResult is constructor

    for count, mode in enumerate(("normal", "render", "attach"), start=1):
        observed_assertions = []

        def render(report, mode=mode, observed_assertions=observed_assertions):
            observed_assertions.append((sys.exception(), sys.exception().args))
            if mode == "render":
                raise ValueError("private-render-canary")
            if mode == "attach":
                return object()
            return original_render(report)

        with monkeypatch.context() as patch:
            patch.setattr(http_failure_diagnostics, "_route_message", render)
            with (
                pytest.raises(AssertionError) as caught,
                compatibility_failure(
                    service, phase="cancel_guard_expected_schema_incompatible"
                ) as report,
            ):
                fault(cancel, "schema_incompatible")
        assert len(observed_assertions) == 1
        assert observed_assertions[0][0] is caught.value
        assert observed_assertions[0][1] == caught.value.args
        assert caught.value.__context__ is faults[-1]
        assert str(faults[-1]) == "dependency_unavailable"
        assert faults[-1].__suppress_context__ is True and faults[-1].__cause__ is None
        assert len(calls) == count and serialized == [original_error] * count
        assert len(failed_steps) == (0 if stage == "raised" else count)
        assert targets == [] and state() == before
        assert service.schema_compatibility is counted_probe
        assert guard.CompatibilityResult is constructor
        if stage == "raised":
            assert returned == constructed == []
            assert faults[-1].__context__ is original_error
        else:
            assert len(returned) == len(constructed) == count
            assert returned[-1] is constructed[-1]
            assert type(returned[-1]) is original_constructor

        encoded = report()
        observed = json.loads(encoded)
        assert observed["phase"] == "cancel_guard_expected_schema_incompatible"
        assert observed["security"] == observed["classified"] == []
        if stage == "raised":
            assert observed["probes"][0]["stage"] == "raised"
            assert observed["guard"] == []
        else:
            assert observed["probes"] == [
                {
                    "stage": "returned",
                    "result": {"status": "unavailable", "code": "schema_unavailable"},
                }
            ]
            assert len(observed["guard"]) == 1
            assert observed["guard"][0]["stage"] == (
                "_check_schema_compatibility"
                if stage == "inner"
                else "runtime_schema_compatibility"
            )
        assert canary not in encoded and len(encoded.encode()) <= MAX_BYTES
        if mode == "normal":
            assert caught.value.__notes__ == [encoded]
        else:
            assert getattr(caught.value, "__notes__", []) == []
