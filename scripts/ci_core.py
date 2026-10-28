"""Opt-in pytest full-collection partition and bounded terminal receipt observer."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.ci_receipts import (
    LEGS,
    SCHEMA,
    node_digest,
    nodes,
    observe_identity,
    phase_outcome,
    receipt_bytes,
    require,
    select_nodes,
    terminal_skip_reason,
    tracked_tests,
)


def pytest_addoption(parser):
    group = parser.getgroup("core receipt")
    group.addoption("--core-leg", choices=("early", "late", "all"))
    group.addoption("--core-receipt")


def pytest_configure(config):
    leg, output = config.getoption("--core-leg"), config.getoption("--core-receipt")
    if leg is None and output is None:
        return
    if not leg or not output or config.option.collectonly:
        raise pytest.UsageError("Core receipts require both options and test execution")
    config.pluginmanager.register(CoreReceipt(config, leg, output), "core-terminal-receipt")


class CoreReceipt:
    def __init__(self, config, leg, output):
        self.root = Path(config.rootpath)
        self.output = Path(output)
        self.python = ".".join(map(str, sys.version_info[:2]))
        require((self.python, leg) in LEGS, "Unknown interpreter/leg")
        self.identity = observe_identity(self.root, os.environ)
        self.tracked = tracked_tests(self.root)
        self.reports = {}
        self.selected_set = set()
        self.receipt = {
            "schema": SCHEMA,
            "identity": self.identity,
            "python": self.python,
            "leg": leg,
            "full_collection": [],
            "full_collection_sha256": node_digest([]),
            "selected": [],
            "selected_sha256": node_digest([]),
            "outcomes": [],
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "session_finished": False,
            "pytest_exit_code": None,
            "collection_errors": 0,
            "errors": [],
            "complete": False,
        }
        self.save()

    def error(self, code):
        if code not in self.receipt["errors"] and len(self.receipt["errors"]) < 32:
            self.receipt["errors"].append(code)

    def save(self):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        encoded = receipt_bytes(self.receipt)
        temporary = self.output.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        temporary.replace(self.output)

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session, config, items):
        full = nodes([item.nodeid for item in items], self.tracked)
        selected = select_nodes(full, self.python, self.receipt["leg"])
        require(bool(selected), "Empty core leg")
        self.receipt["full_collection"] = full
        self.receipt["full_collection_sha256"] = node_digest(full)
        self.receipt["selected"] = selected
        self.receipt["selected_sha256"] = node_digest(selected)
        selected_set = set(selected)
        self.selected_set = selected_set
        omitted = [item for item in items if item.nodeid not in selected_set]
        if omitted:
            config.hook.pytest_deselected(items=omitted)
        items[:] = [item for item in items if item.nodeid in selected_set]
        self.save()

    def pytest_collection_finish(self, session):
        if [item.nodeid for item in session.items] != self.receipt["selected"]:
            self.error("selection-changed-after-observation")

    def pytest_collectreport(self, report):
        if report.failed:
            self.receipt["collection_errors"] += 1

    def pytest_runtest_logreport(self, report):
        if report.nodeid not in self.selected_set:
            self.error("unselected-report")
            return
        if hasattr(report, "wasxfail"):
            self.error("xfail-report")
        row = self.reports.setdefault(
            report.nodeid,
            {
                "nodeid": report.nodeid,
                "phases": [],
                "outcome": "failed",
                "skip_reason": None,
            },
        )
        if report.when not in ("setup", "call", "teardown") or report.outcome not in (
            "passed",
            "failed",
            "skipped",
        ):
            self.error("unknown-phase")
            return
        if any(p["when"] == report.when for p in row["phases"]):
            self.error("duplicate-phase")
            return
        row["phases"].append({"when": report.when, "outcome": report.outcome})
        if report.skipped:
            try:
                reason = terminal_skip_reason(report.longrepr)
                require(row["skip_reason"] is None, "Repeated skip")
                row["skip_reason"] = reason
            except ValueError:
                self.error("malformed-skip")
        if report.when == "teardown":
            row["outcome"] = "skipped" if row["skip_reason"] is not None else "passed"
            try:
                phase_outcome(row)
            except ValueError:
                row["outcome"] = "failed"

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        self.receipt["finished_at"] = datetime.now(UTC).isoformat()
        self.receipt["session_finished"] = True
        self.receipt["pytest_exit_code"] = int(exitstatus)
        self.receipt["outcomes"] = [
            self.reports[node] for node in self.receipt["selected"] if node in self.reports
        ]
        try:
            require(observe_identity(self.root, os.environ) == self.identity, "Source changed")
        except (ValueError, OSError, KeyError):
            self.error("source-changed")
        complete = (
            exitstatus == 0
            and not self.receipt["collection_errors"]
            and not self.receipt["errors"]
            and bool(self.receipt["selected"])
            and len(self.receipt["outcomes"]) == len(self.receipt["selected"])
        )
        if complete:
            try:
                for outcome in self.receipt["outcomes"]:
                    phase_outcome(outcome)
            except ValueError:
                complete = False
        self.receipt["complete"] = complete
        self.save()
