"""Synthetic boundary controls for complete CI coverage and artifact transport."""

import hashlib
import http.client
import io
import json
import os
import stat
import subprocess
import sys
import traceback
import urllib.error
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ci_core, ci_gate
from scripts import ci_receipts as receipts

FULL = [
    "tests/test_alpha.py::test_first",
    "tests/test_alpha.py::test_skip",
    "tests/test_ledger_recovery.py::test_boundary[a,b]",
    "tests/test_zeta.py::test_unicode[雪]",
]
TRACKED = {node.split("::")[0] for node in FULL}
IDENTITY = {
    "repository": "example/project",
    "event": "pull_request",
    "source_head": "a" * 40,
    "source_tree": "d" * 40,
    "checkout_commit": "c" * 40,
    "checkout_tree": "d" * 40,
    "checkout_parents": ["b" * 40, "a" * 40],
    "workflow_sha": "e" * 40,
    "run_id": 123,
    "run_attempt": 2,
}


def outcome(node, reason=None):
    phases = (
        [("setup", "skipped"), ("teardown", "passed")]
        if reason is not None
        else [("setup", "passed"), ("call", "passed"), ("teardown", "passed")]
    )
    return {
        "nodeid": node,
        "phases": [{"when": when, "outcome": result} for when, result in phases],
        "outcome": "skipped" if reason is not None else "passed",
        "skip_reason": reason,
    }


def campaign():
    expectations = {
        "schema": 1,
        "status": "accepted",
        "versions": {
            version: {
                "count": len(FULL),
                "sha256": receipts.node_digest(FULL),
                "skips": [{"nodeid": FULL[1], "reason": "controlled skip"}],
            }
            for version in ("3.11", "3.12")
        },
    }
    result = []
    for python, leg in receipts.LEGS:
        selected = receipts.select_nodes(FULL, python, leg)
        result.append(
            {
                "schema": 1,
                "identity": deepcopy(IDENTITY),
                "python": python,
                "leg": leg,
                "full_collection": list(FULL),
                "full_collection_sha256": receipts.node_digest(FULL),
                "selected": selected,
                "selected_sha256": receipts.node_digest(selected),
                "outcomes": [
                    outcome(node, "controlled skip" if node == FULL[1] else None)
                    for node in selected
                ],
                "started_at": "2026-10-28T00:00:00+00:00",
                "finished_at": "2026-10-28T00:01:00Z",
                "session_finished": True,
                "pytest_exit_code": 0,
                "collection_errors": 0,
                "errors": [],
                "complete": True,
            }
        )
    return result, expectations


def check(items, baseline):
    return receipts.validate_campaign(items, IDENTITY, baseline, TRACKED)


def archive(value, name="receipt.json", mode=stat.S_IFREG | 0o600):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as output:
        info = zipfile.ZipInfo(name)
        info.external_attr = mode << 16
        output.writestr(info, receipts.receipt_bytes(value))
    return buffer.getvalue()


def artifact_metadata():
    items, _ = campaign()
    artifacts = []
    for index, item in enumerate(items, 1):
        data = archive(item)
        artifacts.append(
            {
                "id": index,
                "name": receipts.artifact_name(IDENTITY, item["python"], item["leg"]),
                "size_in_bytes": len(data),
                "expired": False,
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "workflow_run": {"id": IDENTITY["run_id"], "head_sha": IDENTITY["source_head"]},
            }
        )
    return {"total_count": 3, "artifacts": artifacts}


def test_complete_campaign_preserves_unicode_order_and_whole_file_boundary():
    items, baseline = campaign()
    accepted = check(items, baseline)
    assert accepted[("3.12", "all")]["selected"] == FULL
    assert accepted[("3.11", "early")]["selected"] == FULL[:2]
    assert accepted[("3.11", "late")]["selected"] == FULL[2:]
    assert receipts.unpack_receipt(archive(items[2])) == items[2]


def test_digest_has_exact_utf8_json_encoding_and_unambiguous_delimiters():
    expected = json.dumps(FULL, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert receipts.node_digest(FULL) == hashlib.sha256(expected).hexdigest()
    assert receipts.node_digest(FULL) != receipts.node_digest(list(reversed(FULL)))
    assert receipts.node_digest(["a,b", "c"]) != receipts.node_digest(["a", "b,c"])
    assert receipts.node_digest(["雪"]) == hashlib.sha256(b'["\xe9\x9b\xaa"]').hexdigest()


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema":1,"schema":1}',
        b'{"versions":{"3.11":{},"3.11":{}}}',
        b'{"artifacts":[{"id":1,"id":2}]}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e999}',
        b"\xff",
    ],
)
def test_every_json_boundary_rejects_ambiguous_or_invalid_json(payload):
    with pytest.raises(ValueError):
        receipts.load_json(payload)


@pytest.mark.parametrize(
    "nodes",
    [
        [FULL[0], FULL[0]],
        ["tests/../secret.py::test_x"],
        ["/tmp/test_x.py::test_x"],
        ["tests/test_unknown.py::test_x"],
        ["tests//test_alpha.py::test_x"],
        ["tests/test_alpha.py"],
        ["tests/test_alpha.py::test_x\n"],
        [True],
        ["tests/test_alpha.py::test_x[\ud800]"],
    ],
)
def test_inventory_rejects_duplicate_untracked_noncanonical_or_invalid_nodes(nodes):
    with pytest.raises(ValueError):
        receipts.nodes(nodes, TRACKED)


@pytest.mark.parametrize(
    "change",
    [
        "missing-leg",
        "duplicate-leg",
        "foreign-version",
        "wrong-selection",
        "reordered-all",
        "different-311-inventory",
        "missing-outcome",
        "duplicate-outcome",
        "wrong-attempt",
        "wrong-head",
        "wrong-tree",
        "wrong-parent",
        "not-merge",
        "wrong-digest",
        "incomplete",
        "interrupted",
        "collection-error",
        "producer-error",
    ],
)
def test_coverage_identity_and_completion_fail_closed(change):
    items, baseline = campaign()
    if change == "missing-leg":
        items.pop()
    elif change == "duplicate-leg":
        items[1] = deepcopy(items[0])
    elif change == "foreign-version":
        items[0]["python"] = "3.13"
    elif change == "wrong-selection":
        items[0]["selected"] = list(FULL)
        items[0]["selected_sha256"] = receipts.node_digest(FULL)
    elif change == "reordered-all":
        items[2]["selected"].reverse()
        items[2]["selected_sha256"] = receipts.node_digest(items[2]["selected"])
    elif change == "different-311-inventory":
        items[1]["full_collection"].reverse()
        items[1]["full_collection_sha256"] = receipts.node_digest(items[1]["full_collection"])
    elif change == "missing-outcome":
        items[2]["outcomes"].pop()
    elif change == "duplicate-outcome":
        items[2]["outcomes"][1] = deepcopy(items[2]["outcomes"][0])
    elif change == "wrong-attempt":
        items[0]["identity"]["run_attempt"] = 1
    elif change == "wrong-head":
        items[0]["identity"]["source_head"] = "f" * 40
    elif change == "wrong-tree":
        items[0]["identity"]["source_tree"] = "f" * 40
    elif change == "wrong-parent":
        items[0]["identity"]["checkout_parents"] = ["b" * 40, "f" * 40]
    elif change == "not-merge":
        items[0]["identity"]["checkout_parents"] = ["a" * 40]
    elif change == "wrong-digest":
        items[0]["full_collection_sha256"] = "f" * 64
    elif change == "incomplete":
        items[0]["session_finished"] = False
    elif change == "interrupted":
        items[0]["pytest_exit_code"] = 2
    elif change == "collection-error":
        items[0]["collection_errors"] = 1
    else:
        items[0]["errors"] = ["duplicate-phase"]
    with pytest.raises(ValueError):
        check(items, baseline)


@pytest.mark.parametrize("field", ["schema", "pytest_exit_code", "collection_errors"])
def test_boolean_receipt_fields_are_not_integer_results(field):
    items, baseline = campaign()
    items[0][field] = field == "schema"
    with pytest.raises(ValueError):
        check(items, baseline)


@pytest.mark.parametrize("field", ["run_id", "run_attempt"])
def test_boolean_identity_fields_are_not_integer_ids(field):
    identity = deepcopy(IDENTITY)
    identity[field] = True
    with pytest.raises(ValueError):
        receipts.validate_identity(identity)


@pytest.mark.parametrize("when", ["setup", "call", "teardown"])
def test_passing_call_cannot_hide_any_failed_phase(when):
    items, baseline = campaign()
    row = items[2]["outcomes"][0]
    next(phase for phase in row["phases"] if phase["when"] == when)["outcome"] = "failed"
    with pytest.raises(ValueError, match="phases"):
        check(items, baseline)


@pytest.mark.parametrize("variant", ["missing-call", "missing-teardown", "duplicate", "reordered"])
def test_terminal_phase_sequence_must_be_complete_once_and_in_order(variant):
    items, baseline = campaign()
    phases = items[2]["outcomes"][0]["phases"]
    if variant == "missing-call":
        phases.pop(1)
    elif variant == "missing-teardown":
        phases.pop()
    elif variant == "duplicate":
        phases[1] = deepcopy(phases[0])
    else:
        phases.reverse()
    with pytest.raises(ValueError):
        check(items, baseline)


@pytest.mark.parametrize("variant", ["unexpected", "unfulfilled", "changed-reason", "wrong-node"])
def test_skips_are_exact_nodes_and_reasons_not_counts(variant):
    items, baseline = campaign()
    if variant == "unexpected":
        items[2]["outcomes"][0] = outcome(FULL[0], "another skip")
    elif variant == "unfulfilled":
        items[2]["outcomes"][1] = outcome(FULL[1])
    elif variant == "changed-reason":
        items[2]["outcomes"][1]["skip_reason"] = "controlled skip "
    else:
        baseline["versions"]["3.12"]["skips"][0]["nodeid"] = FULL[0]
    with pytest.raises(ValueError):
        check(items, baseline)


def test_skip_encoding_only_removes_one_fixed_prefix():
    assert receipts.terminal_skip_reason(("/private/path", 100, "Skipped: reason")) == "reason"
    assert (
        receipts.terminal_skip_reason(("ignored", 1, "Skipped: Skipped: reason"))
        == "Skipped: reason"
    )
    assert receipts.terminal_skip_reason(("ignored", 1, " reason ")) == " reason "
    for value in [("ignored", 1, "/private/path"), ("ignored", 1, "reason\ntrace"), "traceback"]:
        with pytest.raises(ValueError):
            receipts.terminal_skip_reason(value)


@pytest.mark.parametrize("variant", ["pending", "bool-count", "changed-count", "changed-digest"])
def test_baseline_must_be_final_reviewed_exact_inventory(variant):
    items, baseline = campaign()
    if variant == "pending":
        baseline = {"schema": 1, "status": "pending", "versions": {"3.11": None, "3.12": None}}
    elif variant == "bool-count":
        baseline["versions"]["3.11"]["count"] = True
    elif variant == "changed-count":
        baseline["versions"]["3.11"]["count"] += 1
    else:
        baseline["versions"]["3.11"]["sha256"] = "f" * 64
    with pytest.raises(ValueError):
        check(items, baseline)


@pytest.mark.parametrize(
    "python,leg,seconds", [("3.11", "early", 2700), ("3.11", "late", 2700), ("3.12", "all", 3600)]
)
@pytest.mark.parametrize("position", ["negative", "zero", "positive", "exact", "over"])
def test_session_duration_has_exact_per_leg_bound(python, leg, seconds, position):
    items, baseline = campaign()
    receipt = next(item for item in items if (item["python"], item["leg"]) == (python, leg))
    microseconds = {
        "negative": -1,
        "zero": 0,
        "positive": 1,
        "exact": seconds * 1_000_000,
        "over": seconds * 1_000_000 + 1,
    }[position]
    receipt["finished_at"] = (
        datetime.fromisoformat(receipt["started_at"]) + timedelta(microseconds=microseconds)
    ).isoformat()
    if position in ("positive", "exact"):
        assert check(items, baseline)[(python, leg)] == receipt
    else:
        with pytest.raises(ValueError, match="Session exceeded core leg bound"):
            check(items, baseline)


@pytest.mark.parametrize(
    "finish",
    [
        "2026-10-27T23:59:59Z",
        "2026-10-28T00:45:01+00:00",
        "2026-10-28T00:01:00",
        "2026-10-28T00:01:00+01:00",
        "2026-10-28 00:01:00+00:00",
    ],
)
def test_session_timestamps_are_bounded_utc_without_deadline_expansion(finish):
    items, baseline = campaign()
    items[0]["finished_at"] = finish
    with pytest.raises(ValueError):
        check(items, baseline)


@pytest.mark.parametrize(
    "variant",
    [
        "missing",
        "extra",
        "duplicate-name",
        "duplicate-id",
        "old-attempt",
        "wrong-head",
        "wrong-run",
        "expired",
        "oversize",
        "bool-size",
        "bool-id",
        "bool-count",
        "digest",
    ],
)
def test_artifact_metadata_is_an_exact_current_allowlist(variant):
    metadata = artifact_metadata()
    first = metadata["artifacts"][0]
    if variant == "missing":
        metadata["artifacts"].pop()
    elif variant == "extra":
        metadata["total_count"] = 4
    elif variant == "duplicate-name":
        metadata["artifacts"][1]["name"] = first["name"]
    elif variant == "duplicate-id":
        metadata["artifacts"][1]["id"] = first["id"]
    elif variant == "old-attempt":
        first["name"] = first["name"].replace("-123-2-", "-123-1-")
    elif variant == "wrong-head":
        first["workflow_run"]["head_sha"] = IDENTITY["checkout_commit"]
    elif variant == "wrong-run":
        first["workflow_run"]["id"] += 1
    elif variant == "expired":
        first["expired"] = True
    elif variant == "oversize":
        first["size_in_bytes"] = receipts.MAX_ARCHIVE_BYTES + 1
    elif variant == "bool-size":
        first["size_in_bytes"] = True
    elif variant == "bool-id":
        first["id"] = True
    elif variant == "bool-count":
        metadata["total_count"] = True
    else:
        first["digest"] = "sha256:invalid"
    with pytest.raises(ValueError):
        receipts.validate_artifacts(metadata, IDENTITY)


@pytest.mark.parametrize(
    "name", ["../receipt.json", "/receipt.json", "nested/receipt.json", "receipt.json/"]
)
def test_archive_rejects_traversal_extra_layout_and_directory(name):
    with pytest.raises(ValueError):
        receipts.unpack_receipt(archive({}, name=name))


def test_archive_rejects_links_extra_members_and_local_header_mismatch():
    with pytest.raises(ValueError):
        receipts.unpack_receipt(archive({}, mode=stat.S_IFLNK | 0o777))
    data = io.BytesIO(archive({}))
    with zipfile.ZipFile(data, "a") as output:
        output.writestr("extra.txt", b"unexpected")
    with pytest.raises(ValueError):
        receipts.unpack_receipt(data.getvalue())
    data = archive({}).replace(b"receipt.json", b"changed.json", 1)
    with pytest.raises(ValueError):
        receipts.unpack_receipt(data)


def test_json_and_archive_byte_limits_refuse_one_byte_over_boundary():
    assert receipts.load_json(b"{}  ", 4) == {}
    with pytest.raises(ValueError):
        receipts.load_json(b"{}   ", 4)
    with pytest.raises(ValueError):
        receipts.unpack_receipt(b"x" * (receipts.MAX_ARCHIVE_BYTES + 1))
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("receipt.json", b" " * (receipts.MAX_RECEIPT_BYTES + 1))
    with pytest.raises(ValueError):
        receipts.unpack_receipt(data.getvalue())


class Response(io.BytesIO):
    def __init__(self, data=b"", *, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class Opener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def redirect(location="https://unit.blob.core.windows.net/artifact?signature=synthetic"):
    return urllib.error.HTTPError(
        "https://api.github.com/repos/example/project/actions/artifacts/1/zip",
        302,
        "Found",
        {"Location": location},
        io.BytesIO(),
    )


def test_storage_redirect_gets_no_api_token_and_archive_digest_is_verified():
    data = archive(campaign()[0][0])
    metadata = artifact_metadata()["artifacts"][0]
    opener = Opener([redirect(), Response(data)])
    reader = ci_gate.ArtifactReader("synthetic-token", opener=opener)
    assert reader.download("example/project", metadata) == data
    api, storage = [request for request, _ in opener.calls]
    assert api.get_header("Authorization") == "Bearer synthetic-token"
    assert storage.get_header("Authorization") is None
    assert len(opener.calls) == 2
    assert ci_gate.NoRedirect().redirect_request(None, None, 302, "", {}, "https://x") is None


@pytest.mark.parametrize(
    "location",
    [
        "http://unit.blob.core.windows.net/a",
        "https://user:secret@unit.blob.core.windows.net/a",
        "https://localhost/a",
        "https://127.0.0.1/a",
        "https://unit.blob.core.windows.net:444/a",
        "https://attacker.example/a",
        "//unit.blob.core.windows.net/a",
    ],
)
def test_unsafe_signed_redirect_never_reaches_second_request(location):
    opener = Opener([redirect(location)])
    reader = ci_gate.ArtifactReader("synthetic-token", opener=opener)
    with pytest.raises(ValueError):
        reader.download("example/project", artifact_metadata()["artifacts"][0])
    assert len(opener.calls) == 1


def test_second_redirect_and_digest_mismatch_fail_without_retry():
    for second in [redirect(), Response(b"wrong archive")]:
        opener = Opener([redirect(), second])
        reader = ci_gate.ArtifactReader("synthetic-token", opener=opener)
        with pytest.raises(ValueError):
            reader.download("example/project", artifact_metadata()["artifacts"][0])
        assert len(opener.calls) == 2


def test_api_json_duplicate_key_is_rejected_before_artifact_selection():
    opener = Opener([Response(b'{"total_count":3,"total_count":0,"artifacts":[]}')])
    reader = ci_gate.ArtifactReader("synthetic-token", opener=opener)
    with pytest.raises(ValueError, match="Duplicate"):
        reader.list_artifacts(IDENTITY)


@pytest.mark.parametrize(
    "response",
    [
        Response(b"12345"),
        Response(b"", headers={"Content-Length": "5"}),
        Response(b"{}", headers={"Content-Encoding": "gzip"}),
    ],
)
def test_transport_refuses_actual_declared_or_encoded_excess(response):
    reader = ci_gate.ArtifactReader("synthetic-token")
    with pytest.raises(ValueError):
        reader.read(response, 4)


def test_transport_total_deadline_and_alarm_are_restored(monkeypatch):
    now = [0.0]
    events = []
    monkeypatch.setattr(ci_gate.signal, "getsignal", lambda _: "previous-handler")
    monkeypatch.setattr(ci_gate.signal, "getitimer", lambda _: (0.0, 0.0))
    monkeypatch.setattr(ci_gate.signal, "signal", lambda *args: events.append(("handler", args)))
    monkeypatch.setattr(ci_gate.signal, "setitimer", lambda *args: events.append(("timer", args)))
    with ci_gate.ArtifactReader("synthetic-token", clock=lambda: now[0]) as reader:
        now[0] = 121.0
        with pytest.raises(ValueError, match="deadline"):
            reader.read(Response(b"{}"), 4)
    assert events[-2] == ("timer", (ci_gate.signal.ITIMER_REAL, 0))
    assert events[-1] == ("handler", (ci_gate.signal.SIGALRM, "previous-handler"))


@pytest.fixture
def observer(tmp_path, monkeypatch):
    monkeypatch.setattr(ci_core, "observe_identity", lambda *_: deepcopy(IDENTITY))
    monkeypatch.setattr(ci_core, "tracked_tests", lambda _: TRACKED)
    python = ".".join(map(str, ci_core.sys.version_info[:2]))
    leg = "all" if python == "3.12" else "early"
    instance = ci_core.CoreReceipt(
        SimpleNamespace(rootpath=tmp_path), leg, tmp_path / "receipt.json"
    )
    items = [SimpleNamespace(nodeid=node) for node in FULL]
    omitted = []
    hook = SimpleNamespace(pytest_deselected=lambda items: omitted.extend(items))
    instance.pytest_collection_modifyitems(None, SimpleNamespace(hook=hook), items)
    instance.pytest_collection_finish(SimpleNamespace(items=items))
    return instance, items, omitted


def report(node, when, result="passed", reason=None):
    return SimpleNamespace(
        nodeid=node,
        when=when,
        outcome=result,
        skipped=result == "skipped",
        longrepr=("/unretained/private/path.py", 42, "Skipped: " + reason) if reason else None,
    )


def pass_selected(instance):
    for node in instance.receipt["selected"]:
        for when in ("setup", "call", "teardown"):
            instance.pytest_runtest_logreport(report(node, when))


def finish(instance, status=0):
    instance.pytest_sessionfinish(None, status)
    return receipts.load_json(instance.output.read_bytes())


def test_opt_in_observer_records_original_order_and_only_ordinary_deselection(observer):
    instance, items, omitted = observer
    pass_selected(instance)
    result = finish(instance)
    assert result["complete"] is True
    assert result["full_collection"] == FULL
    assert result["selected"] == [item.nodeid for item in items]
    assert len(omitted) == len(FULL) - len(items)
    assert [row["nodeid"] for row in result["outcomes"]] == result["selected"]


@pytest.mark.parametrize("when", ["setup", "call", "teardown"])
def test_observer_cannot_manufacture_pass_from_failed_terminal_phase(observer, when):
    instance, _, _ = observer
    node = instance.receipt["selected"][0]
    for selected in instance.receipt["selected"]:
        for phase in ("setup", "call", "teardown"):
            if selected == node and when == "setup" and phase == "call":
                continue
            instance.pytest_runtest_logreport(
                report(
                    selected, phase, "failed" if selected == node and phase == when else "passed"
                )
            )
    result = finish(instance, 1)
    assert result["complete"] is False
    assert result["pytest_exit_code"] == 1
    assert result["outcomes"][0]["outcome"] == "failed"
    assert {"when": when, "outcome": "failed"} in result["outcomes"][0]["phases"]


@pytest.mark.parametrize("fault", ["duplicate-phase", "missing-node", "interrupted", "collection"])
def test_observer_preserves_incomplete_or_repeated_execution(observer, fault):
    instance, _, _ = observer
    pass_selected(instance)
    if fault == "duplicate-phase":
        instance.pytest_runtest_logreport(report(instance.receipt["selected"][0], "call"))
    elif fault == "missing-node":
        instance.reports.pop(instance.receipt["selected"][-1])
    elif fault == "collection":
        instance.pytest_collectreport(SimpleNamespace(failed=True))
    result = finish(instance, 2 if fault == "interrupted" else 0)
    assert result["complete"] is False


def test_observer_excludes_private_skip_coordinates_and_retains_exact_reason(observer):
    instance, _, _ = observer
    first = instance.receipt["selected"][0]
    for node in instance.receipt["selected"]:
        if node == first:
            instance.pytest_runtest_logreport(report(node, "setup", "skipped", " exact reason "))
            instance.pytest_runtest_logreport(report(node, "teardown"))
        else:
            for when in ("setup", "call", "teardown"):
                instance.pytest_runtest_logreport(report(node, when))
    result = finish(instance)
    assert result["complete"] is True
    assert result["outcomes"][0]["skip_reason"] == " exact reason "
    assert b"/unretained/private/path.py" not in instance.output.read_bytes()


def test_observer_requires_source_preservation_before_completing(observer, monkeypatch):
    instance, _, _ = observer
    pass_selected(instance)

    def changed(*_):
        raise ValueError("controlled source difference")

    monkeypatch.setattr(ci_core, "observe_identity", changed)
    result = finish(instance)
    assert result["complete"] is False
    assert result["errors"] == ["source-changed"]


def test_plugin_is_inert_without_options_and_collect_only_remains_ordinary():
    calls = []
    config = SimpleNamespace(
        getoption=lambda _: None,
        pluginmanager=SimpleNamespace(register=lambda *args: calls.append(args)),
    )
    ci_core.pytest_configure(config)
    assert calls == []


def test_archive_rejects_dos_directory_without_filename_slash():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        info = zipfile.ZipInfo("receipt.json")
        info.create_system = 0
        info.external_attr = 0x10
        output.writestr(info, b"{}")
    with pytest.raises(ValueError):
        receipts.unpack_receipt(buffer.getvalue())


def test_prior_receipts_are_recorded_but_never_borrowed_or_downloaded():
    metadata = artifact_metadata()
    historical = deepcopy(metadata["artifacts"][0])
    historical.update(id=100, name=historical["name"].replace("-123-2-", "-123-1-"), expired=True)
    metadata["artifacts"].append(historical)
    metadata["total_count"] = 4
    current, ignored = receipts.validate_artifacts(metadata, IDENTITY)
    assert [item["id"] for item in current] == [1, 2, 3]
    assert ignored == [
        {"id": 100, "name": historical["name"], "run_attempt": 1, "kind": "core-receipt"}
    ]
    metadata["artifacts"].pop(0)
    metadata["total_count"] = 3
    with pytest.raises(ValueError, match="three current"):
        receipts.validate_artifacts(metadata, IDENTITY)


@pytest.mark.parametrize(
    "name",
    [
        "core-receipt-123-3-" + "c" * 40 + "-py3.11-early",
        "core-receipt-123-01-" + "c" * 40 + "-py3.11-early",
        "core-receipt-123-1-" + "c" * 40 + "-py3.11-unknown",
        "core-receipt-123-1-" + "f" * 40 + "-py3.11-early",
        "candidate-" + "c" * 40 + "-1",
        "unrelated-artifact",
    ],
)
def test_history_allowlist_rejects_future_unknown_foreign_and_pr_candidates(name):
    metadata = artifact_metadata()
    extra = deepcopy(metadata["artifacts"][0])
    extra.update(id=100, name=name)
    metadata["artifacts"].append(extra)
    metadata["total_count"] = 4
    with pytest.raises(ValueError):
        receipts.validate_artifacts(metadata, IDENTITY)


def test_only_main_can_retain_prior_candidate_but_current_candidate_is_not_gate_credit():
    identity = deepcopy(IDENTITY)
    identity.update(event="push", source_head=identity["checkout_commit"])
    metadata = artifact_metadata()
    for item in metadata["artifacts"]:
        item["workflow_run"]["head_sha"] = identity["source_head"]
    extra = deepcopy(metadata["artifacts"][0])
    extra.update(id=100, name="candidate-" + identity["checkout_commit"] + "-1", expired=True)
    metadata["artifacts"].append(extra)
    metadata["total_count"] = 4
    current, ignored = receipts.validate_artifacts(metadata, identity)
    assert len(current) == 3 and ignored[0]["kind"] == "candidate"
    extra["name"] = "candidate-" + identity["checkout_commit"] + "-2"
    with pytest.raises(ValueError):
        receipts.validate_artifacts(metadata, identity)


def test_artifact_listing_must_fit_one_complete_bounded_page():
    metadata = artifact_metadata()
    metadata["total_count"] = 101
    with pytest.raises(ValueError):
        receipts.validate_artifacts(metadata, IDENTITY)


def test_archive_rejects_raw_nul_name_before_zipfile_normalization():
    data = archive({}, name="receipt.jsonX")
    assert data.count(b"receipt.jsonX") == 2
    altered = data.replace(b"receipt.jsonX", b"receipt.json\x00")
    with pytest.raises(ValueError):
        receipts.unpack_receipt(altered)


def test_real_pytest_plugin_collection_phases_skips_and_terminal_validation(tmp_path):
    """Small committed synthetic fixture; no project checkout, service or network."""
    root = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "synthetic"
    (fixture / "scripts").mkdir(parents=True)
    (fixture / "tests").mkdir()
    for filename in ("ci_core.py", "ci_receipts.py"):
        (fixture / "scripts" / filename).write_bytes((root / "scripts" / filename).read_bytes())
    (fixture / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    (fixture / "conftest.py").write_text(
        "import os\nfrom pathlib import Path\nimport pytest\n"
        "def record(stage, node):\n"
        "    with Path(os.environ['CI_FIXTURE_EVENTS']).open('a') as output:\n"
        "        output.write(stage + ':' + node + '\\n')\n"
        "def pytest_runtest_call(item):\n"
        "    record('call', item.nodeid)\n"
        "@pytest.fixture(autouse=True)\n"
        "def cleanup_probe(request):\n"
        "    yield\n"
        "    record('teardown', request.node.nodeid)\n"
        "    if os.environ.get('CI_FIXTURE_FAIL_TEARDOWN') == '1':\n"
        "        raise RuntimeError('controlled teardown')\n"
    )
    (fixture / "tests/test_alpha.py").write_text(
        "import os\nimport pytest\n"
        "def test_alpha():\n"
        "    assert os.environ.get('CI_FIXTURE_FAIL_CALL') != '1', 'controlled call'\n"
        "@pytest.mark.skip(reason='controlled skip')\n"
        "def test_skip():\n    raise AssertionError('must stay skipped')\n"
    )
    (fixture / "tests/test_ledger_recovery.py").write_text(
        "import os\n"
        "def test_boundary():\n"
        "    assert os.environ.get('CI_FIXTURE_FAIL_CALL') != '1', 'controlled call'\n"
        "def test_last():\n    assert True\n"
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("REWIND_TEST_")}
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Synthetic Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Synthetic Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONPATH=str(fixture),
    )
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Synthetic receipt fixture",
        ],
    ):
        subprocess.run(
            ["git", *args], cwd=fixture, env=env, check=True, capture_output=True, timeout=10
        )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=fixture, env=env, text=True, timeout=10
    ).strip()
    env.update(
        GITHUB_REPOSITORY="example/project",
        GITHUB_EVENT_NAME="push",
        CI_SOURCE_HEAD=head,
        GITHUB_SHA=head,
        GITHUB_WORKFLOW_SHA=head,
        GITHUB_RUN_ID="123",
        GITHUB_RUN_ATTEMPT="2",
    )
    expected = [
        "tests/test_alpha.py::test_alpha",
        "tests/test_alpha.py::test_skip",
        "tests/test_ledger_recovery.py::test_boundary",
        "tests/test_ledger_recovery.py::test_last",
    ]
    tracked = {"tests/test_alpha.py", "tests/test_ledger_recovery.py"}
    baseline = {
        "schema": 1,
        "status": "accepted",
        "versions": {
            version: {
                "count": 4,
                "sha256": receipts.node_digest(expected),
                "skips": [{"nodeid": expected[1], "reason": "controlled skip"}],
            }
            for version in ("3.11", "3.12")
        },
    }
    versions = receipts.validate_expectations(baseline, tracked)
    identity = receipts.observe_identity(fixture, env)
    python = ".".join(map(str, sys.version_info[:2]))
    legs = ("all",) if python == "3.12" else ("early", "late")
    for leg in legs:
        for failing in (None, "teardown", "call"):
            output = tmp_path / (leg + "-" + (failing or "positive")) / "receipt.json"
            output.parent.mkdir()
            events = output.parent / "events.txt"
            command = [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-q",
                "--maxfail=1",
                "-p",
                "no:cacheprovider",
                "-p",
                "scripts.ci_core",
                "--core-leg",
                leg,
                "--core-receipt",
                str(output),
            ]
            result = subprocess.run(
                command,
                cwd=fixture,
                env={
                    **env,
                    "CI_FIXTURE_FAIL_TEARDOWN": "1" if failing == "teardown" else "0",
                    "CI_FIXTURE_FAIL_CALL": "1" if failing == "call" else "0",
                    "CI_FIXTURE_EVENTS": str(events),
                },
                capture_output=True,
                text=True,
                timeout=45,
            )
            actual = receipts.load_json(output.read_bytes())
            assert actual["full_collection"] == expected
            assert actual["selected"] == receipts.select_nodes(expected, python, leg)
            if failing:
                assert result.returncode == actual["pytest_exit_code"] == 1
                assert actual["session_finished"] is True and actual["complete"] is False
                assert len(actual["outcomes"]) == 1 < len(actual["selected"])
                first = actual["selected"][0]
                assert events.read_text().splitlines() == [f"call:{first}", f"teardown:{first}"]
                phases = actual["outcomes"][0]["phases"]
                if failing == "teardown":
                    assert {"when": "call", "outcome": "passed"} in phases
                    assert {"when": "teardown", "outcome": "failed"} in phases
                    assert "RuntimeError: controlled teardown" in result.stdout
                else:
                    assert {"when": "call", "outcome": "failed"} in phases
                    assert {"when": "teardown", "outcome": "passed"} in phases
                    assert "AssertionError: controlled call" in result.stdout
                assert "stopping after 1 failures" in result.stdout
                assert b"controlled " not in output.read_bytes()
                with pytest.raises(ValueError):
                    receipts.validate_receipt(actual, identity, versions, tracked)
                for exit_code in (1, 0):
                    forged = deepcopy(actual)
                    forged.update(complete=True, pytest_exit_code=exit_code)
                    with pytest.raises(ValueError):
                        receipts.validate_receipt(forged, identity, versions, tracked)
            else:
                assert result.returncode == 0, result.stdout + result.stderr
                assert receipts.validate_receipt(actual, identity, versions, tracked) == actual
                if leg == "all":
                    assert "deselected" not in result.stdout
                else:
                    assert "2 deselected" in result.stdout


@pytest.mark.parametrize(
    "arguments",
    [
        ("config", "--global", "x", "y"),
        ("rev-parse", "--upload-pack=unexpected"),
        ("rev-parse", "a" * 40 + "^{tree};unexpected"),
        ("status", "--porcelain=v1"),
        ("ls-files", "--", "/private"),
        (True,),
    ],
)
def test_git_observer_rejects_every_non_allowlisted_argument_form(tmp_path, arguments, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(ValueError):
        receipts.git_output(tmp_path, *arguments)
    assert calls == []


def test_git_observer_resolves_system_executable_and_never_uses_shell(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(stdout="value\n"),
    )
    assert receipts.git_output(tmp_path, "rev-parse", "a" * 40 + "^{tree}") == "value"
    command = calls[0][0][0]
    assert Path(command[0]).is_absolute() and Path(command[0]).name == "git"
    assert command[1:] == ["-C", str(tmp_path), "rev-parse", "a" * 40 + "^{tree}"]
    assert calls[0][1].get("shell", False) is False


@pytest.mark.parametrize(
    "path",
    [
        "file:///private",
        "/repos/example/project/../x",
        "/repos/example/project/actions/runs/1/artifacts?per_page=100&extra=1",
        "/repos/example/project/actions/runs/0/artifacts?per_page=100",
        "/repos/example/project/actions/artifacts/1/zip#fragment",
        "/repos/example/project/actions/artifacts/1/zip\n",
    ],
)
def test_api_token_request_requires_exact_fixed_https_endpoint_path(path):
    reader = ci_gate.ArtifactReader("synthetic-token")
    with pytest.raises(ValueError):
        reader.api_request(path)


@pytest.mark.parametrize("bad", [" ", "\n", "\x00", "\x7f", "雪"])
def test_raw_redirect_text_is_rejected_without_exposing_signed_selector(bad):
    location = "https://unit.blob.core.windows.net/a" + bad + "?signature=DO_NOT_SURFACE"
    opener = Opener([redirect(location)])
    reader = ci_gate.ArtifactReader("synthetic-token", opener=opener)
    with pytest.raises(ValueError, match="Unsafe artifact redirect text") as caught:
        reader.download("example/project", artifact_metadata()["artifacts"][0])
    assert "DO_NOT_SURFACE" not in "".join(traceback.format_exception(caught.value))
    assert len(opener.calls) == 1


def test_storage_http_exception_is_sanitized_without_signed_url_context():
    failure = http.client.InvalidURL("signed selector?signature=DO_NOT_SURFACE")
    opener = Opener([redirect(), failure])
    reader = ci_gate.ArtifactReader("synthetic-token", opener=opener)
    with pytest.raises(ValueError, match="Artifact storage transport failed") as caught:
        reader.download("example/project", artifact_metadata()["artifacts"][0])
    assert caught.value.__suppress_context__ is True
    assert "DO_NOT_SURFACE" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "size, accepted",
    [
        (receipts.MAX_RECEIPT_BYTES - 1, True),
        (receipts.MAX_RECEIPT_BYTES, False),
    ],
)
def test_prior_main_candidate_retains_original_strict_compressed_size_bound(size, accepted):
    identity = deepcopy(IDENTITY)
    identity.update(event="push", source_head=identity["checkout_commit"])
    metadata = artifact_metadata()
    for item in metadata["artifacts"]:
        item["workflow_run"]["head_sha"] = identity["source_head"]
    previous = deepcopy(metadata["artifacts"][0])
    previous.update(
        id=100, name="candidate-" + identity["checkout_commit"] + "-1", size_in_bytes=size
    )
    metadata["artifacts"].append(previous)
    metadata["total_count"] = 4
    if accepted:
        current, ignored = receipts.validate_artifacts(metadata, identity)
        assert len(current) == 3 and ignored[0]["id"] == 100
    else:
        with pytest.raises(ValueError):
            receipts.validate_artifacts(metadata, identity)


def test_invalid_redirect_port_has_fixed_diagnostic_without_signed_text():
    location = "https://unit.blob.core.windows.net:DO_NOT_SURFACE/a?signature=DO_NOT_SURFACE"
    opener = Opener([redirect(location)])
    reader = ci_gate.ArtifactReader("synthetic-token", opener=opener)
    with pytest.raises(ValueError, match="Unsafe artifact redirect") as caught:
        reader.download("example/project", artifact_metadata()["artifacts"][0])
    assert "DO_NOT_SURFACE" not in "".join(traceback.format_exception(caught.value))
    assert len(opener.calls) == 1


@pytest.mark.parametrize("extra_bytes", [0, 1])
def test_large_parameter_node_has_exact_utf8_byte_bound(extra_bytes):
    prefix = "tests/test_alpha.py::test_parameter["
    # Keep the collected control IDs small while exercising real long parameter IDs.
    payload_bytes = receipts.MAX_NODE_BYTES - len(prefix.encode()) - 1 + extra_bytes
    node = prefix + "雪" * (payload_bytes // 3) + "x" * (payload_bytes % 3) + "]"
    assert len(node.encode("utf-8")) == receipts.MAX_NODE_BYTES + extra_bytes
    if extra_bytes:
        with pytest.raises(ValueError, match="Text exceeds bound"):
            receipts.nodes([node], TRACKED)
        with pytest.raises(ValueError, match="Text exceeds bound"):
            receipts.node_digest([node])
    else:
        assert receipts.nodes([node], TRACKED) == [node]
        expected = json.dumps([node], ensure_ascii=False, separators=(",", ":")).encode()
        assert receipts.node_digest([node]) == hashlib.sha256(expected).hexdigest()
