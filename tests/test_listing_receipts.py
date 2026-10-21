"""Maximum mixed source/projection receipt work, separate from public page size."""

import pytest
import test_scoped_run_listing as listing_tests
from sqlalchemy import event, text
from test_scoped_run_listing import PRINCIPAL, PROJECT, RUN1
from test_scoped_run_listing_bounds import add_runs

from agent_rewind.errors import Fault
from agent_rewind.legacy_reads import ReadBudget
from agent_rewind.listing_projection import by_ids
from agent_rewind.listing_session import SQLWork, listing_connection
from agent_rewind.listing_sources import Sources

listing = listing_tests.listing
legacy = listing_tests.legacy


@pytest.mark.parametrize("mutation", [None, "missing_scope", "changed_source", "new_member"])
def test_maximum_initial_frontier_and_composed_receipts_share_budget(listing, mutation):
    _, engine, reader = listing
    with engine.begin() as connection:
        ids = add_runs(connection, 682, parent=RUN1)
    # 682 represented projections + 683 source runs + 683 owning jobs = 2048.
    # This exercises the internal shared closure/receipt ceiling, not a 682-row
    # public page (the public limit remains 200).
    work = SQLWork()
    statements = []

    def observed(_connection, _cursor, statement, parameters, _context, _many):
        strings = parameters.values() if isinstance(parameters, dict) else parameters
        json_bytes = sum(
            len(x.encode()) for x in strings if isinstance(x, str) and x.startswith("[")
        )
        statements.append((statement, len(parameters), json_bytes))

    event.listen(engine, "before_cursor_execute", observed)
    try:
        with listing_connection(engine, work) as connection:
            context = reader._context(connection, PRINCIPAL, PROJECT)
            entries = list(by_ids(connection, PROJECT, set(ids)).values())
            sources = Sources(context, ReadBudget(nodes=len(entries)))
            sources.load(connection, ids)
            initial_instructions = work.instructions
        assert len(sources.records) == len(sources.jobs) == 683
        assert sources.budget.nodes == 2048
        if mutation is not None:
            with engine.begin() as writer:
                if mutation == "missing_scope":
                    writer.execute(
                        text(
                            "DELETE FROM resource_scopes "
                            "WHERE resource_kind='job' AND resource_id=:id"
                        ),
                        {"id": next(iter(sources.jobs))},
                    )
                elif mutation == "changed_source":
                    writer.execute(
                        text("UPDATE records SET created=created+1 WHERE id=:id"), {"id": ids[0]}
                    )
                else:
                    writer.execute(
                        text(
                            "INSERT INTO records SELECT :id,kind,created,data "
                            "FROM records WHERE id=:old"
                        ),
                        {"id": "3" * 32, "old": RUN1},
                    )
                    writer.execute(
                        text("INSERT INTO resource_scopes VALUES('run',:id,:project)"),
                        {"id": "3" * 32, "project": PROJECT},
                    )
            with pytest.raises(Fault, match="dependency_unavailable"):
                reader._finish(PRINCIPAL, context, entries, sources, work)
        else:
            reader._finish(PRINCIPAL, context, entries, sources, work)
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert work.instructions <= 20_000_000
    assert initial_instructions > 0 and work.instructions > initial_instructions
    assert work.statements < 40
    final = [item for item in statements if "matching_projections" in item[0]]
    assert len(final) == 1 and final[0][1] <= 64 and final[0][2] <= 4 * 1024 * 1024
    assert engine.pool.checkedout() == 0
    print(
        {
            "initial_vm": initial_instructions,
            "total_vm": work.instructions,
            "statements": work.statements,
            "final_binds": final[0][1],
            "final_input_bytes": final[0][2],
        }
    )
