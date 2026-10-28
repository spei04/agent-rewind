"""Finite actual key/visibility competitors around owned P2 acquisition.

Key rows and memberships are synthetic test identities. The unchanged authority
reads their persisted current values; this is not HTTP token-authentication proof.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Event, get_ident

import pytest
from reservation_fixture import build_reservation_case
from reservation_qe_fixture import (
    assert_released,
    claim,
    coordinator,
    identity,
    intent,
    one,
    same,
    snapshot,
)
from sqlalchemy import event, text

from agent_rewind.database import keys
from agent_rewind.request_identity import VerifiedPrincipal
from agent_rewind.scoped_lineage import ResourceNotFound
from agent_rewind.scoped_repositories import members, scopes
from agent_rewind.sqlite_ownership import owned_begin, owned_connect


def build_keyed_case(tmp_path, monkeypatch):
    case = build_reservation_case(tmp_path, monkeypatch)
    try:
        key_id = identity(120001)
        principal = VerifiedPrincipal.service_key(key_id)
        with owned_begin(case.engine) as connection:
            connection.execute(
                keys.insert().values(
                    id=key_id,
                    hash="a" * 64,
                    role="operator",
                    name="synthetic-p2-key",
                    expires=time.time() + 3600,
                    revoked=False,
                )
            )
            connection.execute(
                scopes.insert().values(
                    resource_kind="key",
                    resource_id=key_id,
                    project_id=case.project_id,
                )
            )
            connection.execute(
                members.insert().values(
                    project_id=case.project_id,
                    principal_id=principal.principal_id,
                    role="operator",
                    revoked_at=None,
                    legacy_default=False,
                )
            )
        context = case.authority.named(principal, case.project_id, action="record").context
        return replace(case, principal=principal, context=context)
    except BaseException:
        case.close()
        raise


def denied_after_wait(case, operation, call, mutation):
    """One native writer excludes the distinct P2 BEGIN until its change commits."""
    before = snapshot(case.engine)
    expected = deepcopy(before)
    parent = get_ident()
    started = Event()
    seen = []
    original_check = case.authority.check
    original_denials = []

    def checked(*args, **kwargs):
        try:
            return original_check(*args, **kwargs)
        except ResourceNotFound as error:
            original_denials.append(error)
            raise

    def beginning(connection, _cursor, statement, _parameters, _context, _many):
        if get_ident() != parent and statement == "BEGIN IMMEDIATE":
            seen.append(connection)
            started.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        event.listen(case.engine, "before_cursor_execute", beginning)
        case.authority.check = checked
        try:
            with owned_connect(case.engine) as blocker:
                blocker.exec_driver_sql("BEGIN IMMEDIATE")
                pending = pool.submit(call)
                assert started.wait(timeout=2) and len(seen) == 1 and not pending.done()
                assert (
                    seen[0].connection.driver_connection is not blocker.connection.driver_connection
                )
                mutation(blocker, expected)
                blocker.commit()
            # Established current authority hides revoked/expired keys and
            # revoked project membership through the same visibility refusal.
            with pytest.raises(ResourceNotFound) as caught:
                pending.result(timeout=15)
            assert len(original_denials) == 1 and caught.value is original_denials[0]
        finally:
            case.authority.check = original_check
            event.remove(case.engine, "before_cursor_execute", beginning)
    assert operation.outcome.confirmed_precommit_rollback
    assert not operation.outcome.commit_attempted and not operation.outcome.cleanup_failed
    same(expected, snapshot(case.engine))
    assert_released(case.engine)


def key_mutation(case, mode):
    key_id = case.principal.principal_id.removeprefix("api-key:")

    def mutate(connection, expected):
        if mode == "revoked":
            connection.execute(
                text("UPDATE api_keys SET revoked=true WHERE id=:id"), {"id": key_id}
            )
            one(expected, "api_keys", id=key_id)["revoked"] = 1
        else:
            # A finite test competitor shortens the actual persisted deadline;
            # wait for the unchanged Python-clock policy to observe it expired.
            expires = time.time() + 0.05
            connection.execute(
                text("UPDATE api_keys SET expires=:expires WHERE id=:id"),
                {"expires": expires, "id": key_id},
            )
            one(expected, "api_keys", id=key_id)["expires"] = expires
            deadline = time.monotonic() + 1
            waiter = Event()
            while time.time() < expires:
                assert time.monotonic() < deadline
                waiter.wait(timeout=min(0.01, max(0, expires - time.time())))
            assert time.time() >= expires

    return mutate


@pytest.mark.parametrize("mode", ["revoked", "expired"])
def test_key_waiter_revalidates_current_key(tmp_path, monkeypatch, mode):
    case = build_keyed_case(tmp_path, monkeypatch)
    try:
        fence = claim(case)
        value = intent(case, fence)
        operation = coordinator(case)
        denied_after_wait(
            case,
            operation,
            lambda: operation.reserve(case.principal, case.context, fence, value),
            key_mutation(case, mode),
        )
    finally:
        case.close()


@pytest.mark.parametrize("mode", ["key-revoked", "key-expired", "membership-revoked"])
def test_original_inspection_rechecks_current_authority_after_wait(tmp_path, monkeypatch, mode):
    # Membership and key invalidation preserve existing visibility refusal
    # and never disclose the previously authorized saved call.
    own = mode == "membership-revoked"
    case = (
        build_reservation_case(tmp_path, monkeypatch)
        if own
        else build_keyed_case(tmp_path, monkeypatch)
    )
    try:
        fence = claim(case)
        value = intent(case, fence)
        coordinator(case).reserve(case.principal, case.context, fence, value)
        operation = coordinator(case)
        if own:

            def mutation(connection, expected):
                revoked = "2026-01-01T00:00:00+00:00"
                connection.execute(
                    text(
                        "UPDATE project_memberships SET revoked_at=:at "
                        "WHERE project_id=:p AND principal_id=:u"
                    ),
                    {"at": revoked, "p": case.project_id, "u": case.principal.principal_id},
                )
                one(
                    expected,
                    "project_memberships",
                    project_id=case.project_id,
                    principal_id=case.principal.principal_id,
                )["revoked_at"] = revoked
        else:
            mutation = key_mutation(case, mode.removeprefix("key-"))
        denied_after_wait(
            case,
            operation,
            lambda: operation.inspect_original(case.principal, case.context, case.job_id, value),
            mutation,
        )
    finally:
        case.close()
