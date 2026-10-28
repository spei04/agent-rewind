"""P2 opt-in work/lock semantics preserve the existing defaults."""

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from test_admission_transaction import engine, rows

from agent_rewind import operation_work, scoped_locks
from agent_rewind.admission_transaction import (
    AdmissionError,
    TransactionOutcome,
    admission_transaction,
)
from agent_rewind.operation_work import OperationWork
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_repositories import ProjectContext

__all__ = ["engine"]


@pytest.mark.parametrize("include", [False, True], ids=["existing", "acquisition-inclusive"])
def test_acquisition_clock_is_opt_in_and_does_not_reset_on_attach(engine, monkeypatch, include):
    clock = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: clock[0])
    work = OperationWork(include_acquisition=include)
    clock[0] = 9.5
    outcome = TransactionOutcome()
    if include:
        with (
            pytest.raises(AdmissionError, match="^dependency_unavailable$"),
            admission_transaction(engine, outcome, work=work) as connection,
        ):
            connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
            clock[0] = 10.0
        assert outcome.confirmed_precommit_rollback and rows(engine) == []
    else:
        with admission_transaction(engine, outcome, work=work) as connection:
            connection.exec_driver_sql("INSERT INTO proof VALUES(1)")
            clock[0] = 10.0
        assert outcome.commit_acknowledged and rows(engine) == [1]


def test_expired_acquisition_budget_never_enters_a_transaction(engine, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(operation_work, "perf_counter", lambda: clock[0])
    work = OperationWork(include_acquisition=True)
    clock[0] = 10.0
    outcome = TransactionOutcome()
    with (
        pytest.raises(AdmissionError, match="^dependency_unavailable$"),
        admission_transaction(engine, outcome, work=work),
    ):
        pytest.fail("body")
    assert not outcome.begun and not outcome.commit_attempted
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("exclusive", [False, True], ids=["default-share", "initial-update"])
def test_authority_lock_order_and_first_organization_mode(monkeypatch, exclusive):
    observed = []
    principal = VerifiedPrincipal("oidc:" + "a" * 64)
    context = ProjectContext("1" * 32, "2" * 32, principal.principal_id)
    authority = SimpleNamespace(check=lambda *args, **kwargs: observed.append(("visibility", None)))

    def lock(_connection, statement, *, shared):
        sql = str(statement.with_for_update(read=shared).compile(dialect=postgresql.dialect()))
        observed.append((str(statement.get_final_froms()[0]), sql))

    monkeypatch.setattr(scoped_locks, "_lock_row", lock)
    scoped_locks.lock_authority(
        authority,
        object(),
        principal,
        context,
        "job",
        "3" * 32,
        exclusive_organization=exclusive,
    )
    assert [table for table, _sql in observed] == [
        "visibility",
        "projects",
        "organizations",
        "project_memberships",
        "resource_scopes",
        "jobs",
    ]
    assert observed[1][1].endswith("FOR UPDATE")
    assert observed[2][1].endswith("FOR UPDATE" if exclusive else "FOR SHARE")
    assert observed[3][1].endswith("FOR SHARE")
    assert observed[5][1].endswith("FOR UPDATE")
