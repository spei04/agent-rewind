import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_rewind.database import BudgetExceeded, Database

pytestmark = pytest.mark.skipif(
    not os.getenv("REWIND_TEST_POSTGRES"), reason="Opt-in PostgreSQL integration"
)


def test_postgres_skip_locked_claims_and_budget_fences(settings):
    settings.database_url = os.environ["REWIND_TEST_POSTGRES"]
    db = Database(settings)
    db.migrate()
    ids = {db.enqueue("test", "0" * 64, 0.0001, "integration-test") for _ in range(8)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        claimed = list(pool.map(lambda i: db.claim(f"pg-worker-{i}"), range(8)))
    assert {j["id"] for j in claimed if j} == ids
    job = claimed[0]
    owner = db.job(job["id"])["owner"]

    def reserve(_):
        try:
            db.reserve(job["id"], owner, 60)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(8))) == 1
    for claimed_job in claimed:
        current = db.job(claimed_job["id"])
        db.complete_job(current["id"], current["owner"], None, None)
    db.engine.dispose()
