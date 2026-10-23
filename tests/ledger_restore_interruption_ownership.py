"""The isolated five-tool profile; ordinary restore fixtures retain four tools."""

import ledger_restore_tools as tools
import pytest
from ledger_restore_interruption_contracts import PROFILE
from ledger_restore_postgres_fixture import save
from ledger_restore_tool_ownership import ToolOwnership, install_tool_guard


class InterruptedOwnership(ToolOwnership):
    def __init__(self, popen, runner):
        super().__init__(popen, runner, tool_limit=5)
        self.control = self.invocation = None
        self.data_launch = False
        self.steps = []

    def bind_control(self, control):
        assert self.control is None and self.prior_tools_terminal()
        self.control = control

    def prior_tools_terminal(self):
        return len(self.children) == 4 and super().resolved()

    def resolved(self):
        return super().resolved() and (
            self.control is None or self.control.completed and not self.control.uncertain
        )

    def before_database(self, boundary):
        if (
            boundary == "next-tool-launch"
            and self.data_launch
            and self.control is not None
            and self.control.prepared
            and not self.control.uncertain
            and self.prior_tools_terminal()
        ):
            return
        super().before_database(boundary)

    def spawn(self, *args, **kwargs):
        assert self.invocation is not None
        command, environment, label = self.invocation
        assert args == (command,) and kwargs["env"] == environment
        assert PROFILE[len(self.children)] == label
        child = super().spawn(*args, **kwargs)
        self.steps.append({"label": label, "pid": child.pid, "argv": list(command)})
        return child

    def run_tool(self, command, *args, **kwargs):
        assert self.invocation is None and len(self.children) < 4
        assert kwargs["label"] == PROFILE[len(self.children)]
        self.invocation = (command, kwargs["env"], kwargs["label"])
        try:
            return super().run_tool(command, *args, **kwargs)
        finally:
            self.invocation = None

    def spawn_data(self, command, environment, **kwargs):
        assert self.invocation is None and self.prior_tools_terminal()
        assert self.control is not None and self.control.prepared
        self.invocation = (command, environment, "data-restore")
        self.data_launch = True
        try:
            return self.spawn(command, env=environment, **kwargs)
        finally:
            self.data_launch, self.invocation = False, None

    def report(self):
        return {
            **super().report(),
            "profile": list(PROFILE),
            "steps": self.steps,
            "control": None if self.control is None else self.control.report(),
        }


@pytest.fixture(autouse=True)
def interrupted_tool_ownership(monkeypatch, tmp_path, record_property, request):
    owner = InterruptedOwnership(tools.subprocess.Popen, tools.run_tool)
    install_tool_guard(monkeypatch, request.module, owner=owner)
    try:
        yield owner
    finally:
        owner.finish(
            lambda report: save(
                tmp_path,
                "tool-ownership",
                {"fixture_order": request.fixturenames, **report},
                record_property,
            )
        )
