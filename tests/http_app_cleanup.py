"""Release completed HTTP test applications retained by pinned FastAPI caches.

This is test isolation, not runtime cache policy. Module teardown runs after
function-scoped clients, worker threads, listeners and engines have been closed.
It clears process-local classifier caches; the LRU API has no per-app eviction.
"""

import gc

import pytest
from fastapi.dependencies import models

_CACHE_NAMES = (
    "_is_gen_callable_cached",
    "_is_async_gen_callable_cached",
    "_is_coroutine_callable_cached",
)


def release_cached_applications():
    # FastAPI 0.142.2 retains _CallIdentity.call in three classifier LRUs.
    # Their endpoint closures keep completed apps/engines reachable, so plain
    # GC alone cannot reclaim them. This uses the standard LRU clear method;
    # missing/changed private classifier names deliberately fail visibly.
    # Remove/revise when the pinned dependency releases completed callables
    # or provides app-scoped cleanup, rechecking the weakref regression.
    for name in _CACHE_NAMES:
        getattr(models, name).cache_clear()
    gc.collect()


@pytest.fixture(scope="module", autouse=True)
def http_application_cache_cleanup():
    yield
    release_cached_applications()
