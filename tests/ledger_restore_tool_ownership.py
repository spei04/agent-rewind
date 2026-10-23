"""Keep database teardown behind the actual restore-tool ownership boundary."""

import sys
from types import SimpleNamespace

import ledger_restore_postgres_fixture as restore_fixture
import ledger_restore_tools as tools
import pytest
from sqlalchemy import Connection, Engine

MAX_TOOLS = 4
MAX_BLOCKED = 128


class ToolOwnership:
    def __init__(self, popen, runner, *, tool_limit=MAX_TOOLS):
        assert type(tool_limit) is int and tool_limit in (4, 5)
        self.tool_limit = tool_limit
        self.popen, self.runner = popen, runner
        self.children = []
        self.pending = False
        self.uncertain = False
        self.first_error = None
        self.blocked = []
        self.last_status = []

    def remember(self, error):
        if self.first_error is None:
            self.first_error = error

    def resolved(self):
        status = []
        for child in self.children:
            try:
                code = child.poll()
                status.append({"pid": child.pid, "returncode": code, "poll_error": None})
            except BaseException as error:
                self.uncertain = True
                self.remember(error)
                status.append(
                    {"pid": child.pid, "returncode": None, "poll_error": type(error).__name__}
                )
        self.last_status = status
        return (
            not self.pending
            and not self.uncertain
            and all(row["returncode"] is not None for row in status)
        )

    def before_database(self, boundary):
        if self.resolved():
            return
        if len(self.blocked) < MAX_BLOCKED:
            self.blocked.append({"boundary": boundary, "children": self.last_status})
        self.remember(
            sys.exception() or AssertionError("restore tool ownership remains unresolved")
        )
        raise self.first_error

    def spawn(self, *args, **kwargs):
        self.before_database("next-tool-launch")
        assert len(self.children) < self.tool_limit, "restore tool launch bound exceeded"
        self.pending = True
        try:
            child = self.popen(*args, **kwargs)
            self.children.append(child)
            assert type(child.pid) is int and child.pid > 0
            self.pending = False
            return child
        except BaseException as error:
            # A constructor can be interrupted after fork, before returning a
            # handle. Only the outer controller can settle that uncertainty.
            self.uncertain = True
            self.remember(error)
            raise

    def run_tool(self, *args, **kwargs):
        try:
            return self.runner(*args, **kwargs)
        except BaseException as error:
            self.remember(error)
            raise

    def finish(self, record):
        report = self.report()
        try:
            record(report)
        except BaseException as error:
            if not report["resolved"] and self.first_error is not None:
                self.first_error.add_note("ownership record failed; unresolved tool retained")
                raise self.first_error from error
            raise
        if not report["resolved"]:
            self.before_database("fixture-completion")

    def report(self):
        resolved = self.resolved()
        return {
            "resolved": resolved,
            "pending_launch": self.pending,
            "uncertain": self.uncertain,
            "children": self.last_status,
            "first_error": None if self.first_error is None else type(self.first_error).__name__,
            "blocked": self.blocked,
            "limits": {"tools": self.tool_limit, "blocked_records": MAX_BLOCKED},
            "authority": "retained Popen handles and nonblocking poll; not tool receipts",
        }


def install_tool_guard(patch, native_module, *, owner=None):
    """Install before pg/legacy setup and retain until their finalizers complete."""
    subprocess = tools.subprocess
    if owner is None:
        owner = ToolOwnership(subprocess.Popen, tools.run_tool)
    assert isinstance(owner, ToolOwnership)
    patch.setattr(
        tools,
        "subprocess",
        SimpleNamespace(
            Popen=owner.spawn,
            PIPE=subprocess.PIPE,
            DEVNULL=subprocess.DEVNULL,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    patch.setattr(restore_fixture, "run_tool", owner.run_tool)
    patch.setattr(native_module, "run_tool", owner.run_tool)

    def protect(kind, name):
        original = getattr(kind, name)

        def guarded(*args, **kwargs):
            owner.before_database(kind.__name__ + "." + name)
            return original(*args, **kwargs)

        patch.setattr(kind, name, guarded)

    for kind, names in (
        (Engine, ("connect", "raw_connection")),
        (Connection, ("execute", "exec_driver_sql")),
    ):
        for name in names:
            protect(kind, name)
    return owner


@pytest.fixture(autouse=True)
def restore_tool_ownership(monkeypatch, tmp_path, record_property, request):
    # Autouse runs before the function-scoped pg/legacy fixtures. Its dependency
    # on monkeypatch keeps these guards installed through both fixture teardowns.
    owner = install_tool_guard(monkeypatch, request.module)
    order = request.fixturenames
    try:
        yield owner
    finally:
        owner.finish(
            lambda report: restore_fixture.save(
                tmp_path, "tool-ownership", {"fixture_order": order, **report}, record_property
            )
        )
