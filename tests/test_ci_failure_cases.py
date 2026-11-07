import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ci_core
from scripts import ci_failure_cases as cases
from scripts.ci_postgres import IMAGE
from scripts.ci_receipts import session_limit_seconds

IDENTITY = {
    "repository": "example/project",
    "event": "push",
    "source_head": "a" * 40,
    "source_tree": "b" * 40,
    "checkout_commit": "a" * 40,
    "checkout_tree": "b" * 40,
    "checkout_parents": ["c" * 40],
    "workflow_sha": "a" * 40,
    "run_id": 123,
    "run_attempt": 2,
}
NODE = "tests/test_failure_consumer_native_oracle.py::test_owned[postgres]"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "tests").mkdir()
    fixture_source = Path(__file__).with_name("failure_postgres_fixture.py").read_bytes()
    (root / "tests/failure_postgres_fixture.py").write_bytes(fixture_source)
    (root / "README.md").write_text("source fixture\n")
    runner = tmp_path / "runner"
    runner.mkdir(mode=0o700)
    environment = {
        "RUNNER_TEMP": str(runner),
        "GITHUB_ACTIONS": "true",
        "GITHUB_JOB": "core",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_REPOSITORY": "example/project",
        "GITHUB_EVENT_NAME": "push",
        "CI_SOURCE_HEAD": "a" * 40,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "REWIND_CI_POSTGRES_CONTAINER": "d" * 64,
        "REWIND_TEST_POSTGRES_CONTAINER": "d" * 64,
        "REWIND_CI_POSTGRES_RECEIPT": str(runner / "postgres/receipt.json"),
        "REWIND_TEST_POSTGRES": cases.FIXED_DSN,
        "REWIND_TEST_POSTGRES_URL": cases.FIXED_DSN,
    }
    clock = [90.0]
    monkeypatch.setattr(cases.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(cases, "observe_identity", lambda *_: dict(IDENTITY))
    monkeypatch.setattr(
        cases, "git_output", lambda *_: "README.md\0tests/failure_postgres_fixture.py\0"
    )
    cases.write_service_receipt(environment, image=IMAGE)
    clock[0] = 105.0
    python = ".".join(map(str, sys.version_info[:2]))
    leg = "all" if python == "3.12" else "early"
    arguments = {
        "root": root,
        "output": str(runner / "control/manifest.json"),
        "identity": dict(IDENTITY),
        "python": python,
        "leg": leg,
        "session_origin": 100.0,
        "session_limit": session_limit_seconds(python, leg),
        "nodeids": [NODE],
        "environment": environment,
    }
    return arguments, clock


def publish(entry):
    arguments, _ = entry
    path = Path(cases.publish_actions_control(**arguments))
    return path, json.loads(path.read_bytes())


def test_producer_manifest_is_consumed_by_the_real_fixture_without_connecting(entry, monkeypatch):
    import failure_postgres_fixture as fixture

    def no_connection(*_args, **_kwargs):
        pytest.fail("Manifest loading must not open a database connection")

    monkeypatch.setattr(fixture, "create_engine", no_connection)

    arguments, _ = entry
    path, manifest = publish(entry)
    for key, value in arguments["environment"].items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("REWIND_F4_CASE_CONTROL", str(path))
    control = fixture.load_case_control(NODE)
    source_bytes = path.with_name("source-map.json").read_bytes()
    source = json.loads(source_bytes)
    assert control.source_sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert {row["path"] for row in source["files"]} == {
        "README.md",
        "tests/failure_postgres_fixture.py",
    }
    for row in source["files"]:
        data = (arguments["root"] / row["path"]).read_bytes()
        assert row["bytes"] == len(data)
        assert row["sha256"] == hashlib.sha256(data).hexdigest()
    assert control.source_commit == IDENTITY["checkout_commit"]
    assert control.source_tree == IDENTITY["checkout_tree"]
    assert control.body_deadline == control.cleanup_deadline == 100.0 + arguments["session_limit"]
    assert manifest["binding"]["controller"]["pid"] == os.getpid()
    assert not control.record.exists()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_hosted_inventory_is_actual_selection_not_the_local_64_case_limit(entry):
    arguments, _ = entry
    arguments["nodeids"] = [f"tests/test_case.py::test_owned[{index}]" for index in range(65)]
    _, manifest = publish(entry)
    assert manifest["binding"]["case_count"] == 65
    assert [case["nodeid"] for case in manifest["cases"]] == arguments["nodeids"]
    assert len({case["namespace"] for case in manifest["cases"]}) == 65


@pytest.mark.parametrize("field", ["RUNNER_TEMP", "GITHUB_ACTIONS", "GITHUB_JOB"])
def test_missing_hosted_context_refuses_before_manifest_creation(entry, field):
    arguments, _ = entry
    arguments["environment"].pop(field)
    with pytest.raises((ValueError, KeyError)):
        cases.publish_actions_control(**arguments)
    assert not Path(arguments["output"]).exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("container_id", "e" * 64),
        ("image", "postgres:latest"),
        ("run_label", "123-1"),
        ("ordinary_autovacuum_off_verified", 1),
        ("ordinary_autovacuum_off_verified", False),
    ],
)
def test_stale_or_unverified_service_cannot_publish_control(entry, field, value):
    arguments, _ = entry
    path = Path(arguments["environment"]["REWIND_CI_POSTGRES_RECEIPT"])
    receipt = json.loads(path.read_bytes())
    receipt["service"][field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Service receipt"):
        cases.publish_actions_control(**arguments)
    assert not Path(arguments["output"]).exists()


@pytest.mark.parametrize("variable", ["REWIND_TEST_POSTGRES", "REWIND_TEST_POSTGRES_URL"])
def test_external_dsn_is_never_admitted(entry, variable):
    arguments, _ = entry
    arguments["environment"][variable] = "postgresql://external/production"
    with pytest.raises(ValueError, match="DSN"):
        cases.publish_actions_control(**arguments)


def test_expired_shared_clock_cannot_be_reset_by_publication(entry):
    arguments, clock = entry
    clock[0] = arguments["session_origin"] + arguments["session_limit"]
    with pytest.raises(ValueError, match="deadline"):
        cases.publish_actions_control(**arguments)
    assert not Path(arguments["output"]).exists()


def test_source_hashing_consumes_the_original_session_deadline(entry, monkeypatch):
    arguments, clock = entry
    original = cases._source_map

    def delayed(root, deadline):
        result = original(root, deadline)
        clock[0] = deadline
        return result

    monkeypatch.setattr(cases, "_source_map", delayed)
    with pytest.raises(ValueError, match="deadline"):
        cases.publish_actions_control(**arguments)
    assert not Path(arguments["output"]).exists()


def test_source_drift_refuses_publication_after_map_observation(entry, monkeypatch):
    arguments, _ = entry
    identities = iter([dict(IDENTITY), {**IDENTITY, "checkout_tree": "f" * 40}])
    monkeypatch.setattr(cases, "observe_identity", lambda *_: next(identities))
    with pytest.raises(ValueError, match="Source changed"):
        cases.publish_actions_control(**arguments)
    assert not Path(arguments["output"]).exists()


def test_existing_records_are_preserved_without_replacing_or_reusing(entry):
    arguments, _ = entry
    path, _ = publish(entry)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        cases.publish_actions_control(**arguments)
    assert path.read_bytes() == original


@pytest.mark.parametrize("redirect", ["output", "source"])
def test_symlinked_source_or_output_is_refused(entry, tmp_path, redirect):
    arguments, _ = entry
    if redirect == "output":
        runner = Path(arguments["environment"]["RUNNER_TEMP"])
        (runner / "redirect").symlink_to(tmp_path, target_is_directory=True)
        arguments["output"] = str(runner / "redirect/manifest.json")
    else:
        source = arguments["root"] / "README.md"
        source.unlink()
        source.symlink_to(tmp_path / "outside.txt")
        (tmp_path / "outside.txt").write_text("external")
    with pytest.raises(ValueError, match="symlink"):
        cases.publish_actions_control(**arguments)


def test_oversized_inventory_fails_before_creating_case_directories(entry):
    arguments, _ = entry
    arguments["nodeids"] = [f"tests/test_case.py::test_owned[{index}]" for index in range(2000)]
    with pytest.raises(ValueError, match="manifest exceeds"):
        cases.publish_actions_control(**arguments)
    assert not Path(arguments["output"]).parent.exists()


def test_inherited_control_is_not_an_implicit_hosted_permission(entry):
    arguments, _ = entry
    arguments["environment"]["REWIND_F4_CASE_CONTROL"] = "/unrelated/old-manifest.json"
    with pytest.raises(ValueError, match="already supplied"):
        cases.publish_actions_control(**arguments)


@pytest.mark.parametrize("initial_control", [None, "/existing/control.json"])
def test_core_binds_final_marked_selection_to_its_original_clock(
    tmp_path, monkeypatch, initial_control
):
    monkeypatch.setattr(ci_core, "observe_identity", lambda *_: dict(IDENTITY))
    early = "tests/test_failure_case.py::test_case[postgres]"
    sqlite = "tests/test_failure_case.py::test_case[sqlite]"
    late = "tests/test_zz_case.py::test_case[postgres]"
    monkeypatch.setattr(
        ci_core,
        "tracked_tests",
        lambda *_: {
            "tests/test_failure_case.py",
            "tests/test_zz_case.py",
        },
    )
    clock = [100.0]
    monkeypatch.setattr(ci_core.time, "monotonic", lambda: clock[0])
    if initial_control is None:
        monkeypatch.delenv("REWIND_F4_CASE_CONTROL", raising=False)
    else:
        monkeypatch.setenv("REWIND_F4_CASE_CONTROL", initial_control)
    python = ".".join(map(str, sys.version_info[:2]))
    leg = "all" if python == "3.12" else "early"
    observer = ci_core.CoreReceipt(
        SimpleNamespace(rootpath=tmp_path),
        leg,
        tmp_path / "receipt.json",
        tmp_path / "control.json",
    )
    items = [
        SimpleNamespace(nodeid=node, get_closest_marker=lambda _, pg=pg: object() if pg else None)
        for node, pg in [(early, True), (sqlite, False), (late, True)]
    ]
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda **_: None))
    observer.pytest_collection_modifyitems(None, config, items)
    observed = []

    def bind(**arguments):
        observed.append(arguments)
        return "/synthetic/control.json"

    monkeypatch.setattr(cases, "publish_actions_control", bind)
    clock[0] = 200.0
    with pytest.MonkeyPatch.context() as owned_environment:
        # Register ownership even if the variable was initially absent; the
        # observer itself writes directly to os.environ after successful binding.
        owned_environment.setenv("REWIND_F4_CASE_CONTROL", "test-owned")
        owned_environment.delenv("REWIND_F4_CASE_CONTROL")
        observer.pytest_collection_finish(SimpleNamespace(items=items))
        assert os.environ["REWIND_F4_CASE_CONTROL"] == "/synthetic/control.json"
    assert os.environ.get("REWIND_F4_CASE_CONTROL") == initial_control
    assert len(observed) == 1
    assert observed[0]["session_origin"] == 100.0
    assert observed[0]["session_limit"] == session_limit_seconds(python, leg)
    assert observed[0]["nodeids"] == ([early, late] if leg == "all" else [early])


def test_core_refuses_binding_when_final_selection_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(ci_core, "observe_identity", lambda *_: dict(IDENTITY))
    monkeypatch.setattr(ci_core, "tracked_tests", lambda *_: set())
    python = ".".join(map(str, sys.version_info[:2]))
    leg = "all" if python == "3.12" else "early"
    observer = ci_core.CoreReceipt(
        SimpleNamespace(rootpath=tmp_path),
        leg,
        tmp_path / "receipt.json",
        tmp_path / "control.json",
    )
    called = []
    monkeypatch.setattr(cases, "publish_actions_control", lambda **kw: called.append(kw))
    with pytest.raises(pytest.UsageError, match="final observed selection"):
        observer.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=NODE)]))
    assert called == []
