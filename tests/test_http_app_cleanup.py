"""Behavioral proof of completed-app release and unchanged classification."""

import gc
import weakref
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.dependencies import models
from fastapi.testclient import TestClient
from http_app_cleanup import release_cached_applications
from sqlalchemy import text

from agent_rewind.api import create_app
from agent_rewind.sqlite_ownership import owned_connect


def completed_application(settings):
    app = create_app(settings)
    engine = app.state.db.engine
    with owned_connect(engine) as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
    client = TestClient(app)
    try:
        assert client.get("/livez").json() == {"status": "live"}
    finally:
        client.close()
        assert client.is_closed and engine.pool.checkedout() == 0
        engine.dispose()
    return weakref.ref(app), weakref.ref(engine)


def test_closed_http_application_is_released_and_new_app_still_serves(settings):
    application, engine = completed_application(settings)
    # Both ordinary owners have left scope. Plain GC cannot remove the pinned
    # classifier's strong endpoint -> closure -> application reference.
    gc.collect()
    assert application() is not None and engine() is not None
    release_cached_applications()
    assert application() is None and engine() is None

    replacement, replacement_engine = completed_application(settings)
    assert replacement() is not None and replacement_engine() is not None
    release_cached_applications()
    assert replacement() is None and replacement_engine() is None


def test_cache_release_preserves_live_app_dependency_classification():
    app = FastAPI()
    steps = []

    def synchronous():
        steps.append("sync-enter")
        try:
            yield "sync"
        finally:
            steps.append("sync-exit")

    async def asynchronous():
        steps.append("async-enter")
        try:
            yield "async"
        finally:
            steps.append("async-exit")

    @app.get("/")
    async def endpoint(
        left: Annotated[str, Depends(synchronous)],
        right: Annotated[str, Depends(asynchronous)],
    ):
        return [left, right]

    client = TestClient(app)
    try:
        for clear in (False, True):
            if clear:
                release_cached_applications()
            steps.clear()
            assert client.get("/").json() == ["sync", "async"]
            assert steps == ["sync-enter", "async-enter", "async-exit", "sync-exit"]
    finally:
        client.close()
        del app, client
        release_cached_applications()


def test_changed_dependency_cache_interface_is_not_silently_ignored(monkeypatch):
    with monkeypatch.context() as patch:
        patch.delattr(models, "_is_coroutine_callable_cached")
        with pytest.raises(AttributeError):
            release_cached_applications()
    release_cached_applications()
