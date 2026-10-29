"""Independent whole-state oracles for the private P2 reservation contract.

Expected mutations are built from the retained input and the prior SQL state.
These helpers neither call the reservation reducer nor create financial history.
"""

import math
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime

from ledger_restore_authority import typed
from sqlalchemy import event

from agent_rewind.migrations.schema import catalog
from agent_rewind.sqlite_ownership import owned_begin, owned_connect


def identity(number):
    return f"{number:032x}"


def snapshot(engine):
    """Read every table after the invocation releases its owned connection."""
    with owned_connect(engine) as connection:
        shape = catalog(connection)
        tables = {}
        for name in sorted(shape):
            if name.startswith("$"):
                continue
            quoted = connection.dialect.identifier_preparer.quote(name)
            result = connection.exec_driver_sql(f"SELECT * FROM {quoted}")
            tables[name] = {
                "columns": tuple(result.keys()),
                "rows": sorted((dict(row) for row in result.mappings()), key=repr),
            }
    return {"catalog": shape, "tables": tables}


def rows(state, table):
    return state["tables"][table]["rows"]


def one(state, table, **fields):
    (row,) = [row for row in rows(state, table) if all(row[k] == v for k, v in fields.items())]
    return row


def same(expected, actual):
    """Compare unordered SQL rows without allowing bool/int/float equivalence."""
    left, right = deepcopy(expected), deepcopy(actual)
    for state in (left, right):
        for table in state["tables"].values():
            table["rows"].sort(key=lambda row: repr(typed(row)))
    assert typed(left) == typed(right)


def assert_claim(before, after, fence):
    expected = deepcopy(before)
    job = one(expected, "jobs", id=fence.job_id)
    actual = one(after, "jobs", id=fence.job_id)
    assert job["status"] == "queued" and job["owner"] is job["lease_until"] is None
    assert type(job["lease_generation"]) is int
    assert fence.generation == job["lease_generation"] + 1
    assert type(actual["lease_until"]) in (int, float)
    assert math.isfinite(actual["lease_until"])
    job.update(
        status="running",
        owner=fence.owner_uuid,
        lease_until=actual["lease_until"],
        lease_generation=fence.generation,
    )
    same(expected, after)


def expected_reservation(before, after, intent, organization):
    """Exactly one call/scope/triple and gross/held deltas; all other cells survive."""
    expected = deepcopy(before)
    call = one(after, "provider_calls", id=intent.call_id)
    created = call["created_at"]
    assert isinstance(created, str | datetime)
    stamp = (
        datetime.fromisoformat(created.replace("Z", "+00:00"))
        if isinstance(created, str)
        else created
    )
    assert stamp.tzinfo is not None
    account_ids = (
        intent.organization_account_id,
        intent.project_account_id,
        intent.job_account_id,
    )
    assert len(set(account_ids)) == 3
    expected_call = {
        "id": intent.call_id,
        "project_id": intent.project_id,
        "job_id": intent.job_id,
        "logical_call_id": intent.logical_call_id,
        "purpose": intent.purpose,
        "request_digest": intent.request_digest,
        "price_version": intent.price_version,
        "state": "reserved",
        "reserved_microusd": intent.reserved_microusd,
        "usage_estimate_microusd": None,
        "provider_request_id": None,
        "created_at": created,
        "organization_id": organization,
        "job_resource_kind": "job",
        "lease_generation": intent.lease_generation,
        "organization_account_id": account_ids[0],
        "project_account_id": account_ids[1],
        "job_account_id": account_ids[2],
    }
    rows(expected, "provider_calls").append(expected_call)
    rows(expected, "resource_scopes").append(
        {
            "resource_kind": "provider_call",
            "resource_id": intent.call_id,
            "project_id": intent.project_id,
        }
    )
    for account_id in account_ids:
        rows(expected, "budget_entries").append(
            {
                "call_id": intent.call_id,
                "account_id": account_id,
                "entry_kind": "reserve",
                "amount_microusd": intent.reserved_microusd,
                "evidence_ref": None,
                "created_at": created,
                "project_id": intent.project_id,
                "evidence_owner_kind": "provider_call",
                "evidence_role": "budget_evidence",
            }
        )
        account = one(expected, "budget_accounts", id=account_id)
        assert type(account["held_microusd"]) is type(intent.reserved_microusd) is int
        account["held_microusd"] += intent.reserved_microusd
    job = one(expected, "jobs", id=intent.job_id)
    assert type(job["reserved"]) is int
    job["reserved"] += intent.reserved_microusd
    return expected


def assert_reservation(before, after, intent, organization):
    same(expected_reservation(before, after, intent, organization), after)


def remaining_capacity(state, case):
    """Use independently observed native microdollars, never a USD conversion."""
    job = one(state, "jobs", id=case.job_id)
    assert type(job["budget"]) is type(job["reserved"]) is int
    assert 1 <= job["budget"] <= 200_000_000
    limits = [job["budget"] - job["reserved"]]
    for account_id in case.account_ids:
        account = one(state, "budget_accounts", id=account_id)
        limit, held, accounted = (
            account["limit_microusd"],
            account["held_microusd"],
            account["accounted_microusd"],
        )
        assert type(limit) is type(held) is type(accounted) is int
        limits.append(limit - held - accounted)
    return min(limits)


def assert_released(engine):
    checkedout = getattr(engine.pool, "checkedout", None)
    if checkedout is not None:
        assert checkedout() == 0
    with owned_connect(engine) as connection:
        raw = connection.connection.driver_connection
        assert not connection.in_transaction()
        assert connection.info.get("operation_work") is None
        if connection.dialect.name == "sqlite":
            assert not raw.in_transaction
        else:
            assert int(raw.info.transaction_status) == 0


@contextmanager
def fail_after_write(engine, table, occurrence=1):
    """Fail after the selected real DML returned, preserving its prior effects."""
    observed = []

    def fail(connection, cursor, statement, parameters, context, many):
        del connection, cursor, parameters, context, many
        words = statement.strip().upper().replace('"', "").split()
        target = (
            len(words) > 2
            and words[:2] == ["INSERT", "INTO"]
            and words[2].split("(")[0] == table.upper()
        ) or (len(words) > 1 and words[0] == "UPDATE" and words[1] == table.upper())
        if target:
            observed.append(statement)
            if len(observed) == occurrence:
                raise RuntimeError("synthetic P2 publication failure")

    event.listen(engine, "after_cursor_execute", fail)
    try:
        yield observed
    finally:
        event.remove(engine, "after_cursor_execute", fail)


def claim(case, *, owner=90001):
    from agent_rewind.reservation_service import ReservationCoordinator
    from agent_rewind.reservation_types import ClaimIntent

    coordinator = ReservationCoordinator(case.engine, case.authority)
    fence = coordinator.claim_generation(
        case.principal,
        case.context,
        ClaimIntent(case.job_id, identity(owner), 0, 60),
    )
    assert coordinator.outcome.commit_acknowledged and not coordinator.outcome.cleanup_failed
    assert_released(case.engine)
    return fence


def intent(case, fence, *, amount=7, number=91000):
    from agent_rewind.reservation_types import ReservationIntent

    return ReservationIntent(
        call_id=identity(number),
        project_id=case.project_id,
        job_id=case.job_id,
        logical_call_id=identity(number + 1),
        request_digest="b" * 64,
        purpose="continuation",
        price_version=case.price_version,
        reserved_microusd=amount,
        lease_generation=fence.generation,
        organization_account_id=case.account_ids[0],
        project_account_id=case.account_ids[1],
        job_account_id=case.account_ids[2],
    )


def coordinator(case):
    from agent_rewind.reservation_service import ReservationCoordinator

    return ReservationCoordinator(case.engine, case.authority)


def build_prior_hold_case(tmp_path, monkeypatch, *, opening):
    """Change only legitimate legacy source money before real admission and P1."""
    import reservation_fixture as shared
    from ledger_eligibility_fixture import refreshed

    maximum = 2**63 - 1
    assert type(opening) is int and 0 <= opening <= maximum
    original = shared.build_case

    def predecessor(path, *, legacy):
        assert legacy is True
        fixture = original(path, legacy=True)
        try:
            before = snapshot(fixture.case.engine)
            assert "budget_accounts" not in before["tables"]
            jobs = sorted(rows(before, "jobs"), key=lambda row: row["id"])
            assert len(jobs) == 3 and all(row["payload_version"] == 1 for row in jobs)
            target = jobs[0]["id"]
            expected = deepcopy(before)
            with owned_begin(fixture.case.engine) as connection:
                for job in jobs:
                    changed = one(expected, "jobs", id=job["id"])
                    if job["id"] == target:
                        changed.update(budget=opening, reserved=opening)
                        result = connection.exec_driver_sql(
                            "UPDATE jobs SET budget=?,reserved=? WHERE id=?",
                            (opening, opening, target),
                        )
                    else:
                        changed["reserved"] = 0
                        result = connection.exec_driver_sql(
                            "UPDATE jobs SET reserved=0 WHERE id=?", (job["id"],)
                        )
                    assert result.rowcount == 1
            same(expected, snapshot(fixture.case.engine))
            retained = refreshed(fixture)
            assert sum(row["reserved"] for row in retained.jobs) == opening
            assert retained.encrypted == fixture.encrypted
            return retained
        except BaseException:
            fixture.close()
            raise

    # Only the existing setup builder changes, before admission and ar7. The
    # runtime, signed v2 admission, P1 writer, and immutable ar7 state stay real.
    with monkeypatch.context() as patch:
        patch.setattr(shared, "build_case", predecessor)
        return shared.build_reservation_case(
            tmp_path, patch, budget=1_000_000, account_limit=maximum, legacy=True
        )


def build_two_project_case(tmp_path, monkeypatch, *, account_limit=1_000_000):
    """Reuse actual post-P1 admission/provisioning for two genuine P2 targets."""
    from dataclasses import replace
    from datetime import UTC
    from types import SimpleNamespace

    from ledger_eligibility_fixture import admit_existing_fixture, refreshed
    from ledger_provisioning_fixture import digest, inspect, invoke
    from reservation_fixture import build_reservation_case
    from sqlalchemy import text

    from agent_rewind.scoped_repositories import members

    first = build_reservation_case(tmp_path, monkeypatch, account_limit=account_limit)
    try:
        before = snapshot(first.engine)
        project = identity(99000)
        created = datetime.now(UTC).isoformat()
        with owned_begin(first.engine) as connection:
            connection.execute(
                text(
                    "INSERT INTO projects(id,organization_id,name,created_at) "
                    "VALUES(:id,:org,'independent-second-project',:created)"
                ),
                {"id": project, "org": first.organization_id, "created": created},
            )
            connection.execute(
                members.insert().values(
                    project_id=project,
                    principal_id=first.principal.principal_id,
                    role="maintainer",
                    revoked_at=None,
                    legacy_default=False,
                )
            )
        expected = deepcopy(before)
        rows(expected, "projects").append(
            {
                "id": project,
                "organization_id": first.organization_id,
                "name": "independent-second-project",
                "created_at": created,
                "run_sequence": 0,
            }
        )
        rows(expected, "project_memberships").append(
            {
                "project_id": project,
                "principal_id": first.principal.principal_id,
                "role": "maintainer",
                "revoked_at": None,
                "legacy_default": 0,
            }
        )
        same(expected, snapshot(first.engine))
        fixture = refreshed(first.provisioning)
        namespace = tmp_path / "independent-second-admission"
        namespace.mkdir(mode=0o700)
        fixture, admission = admit_existing_fixture(
            fixture,
            monkeypatch,
            lambda name, value: first.setup_events.append((name, value)),
            principal=first.principal,
            project_id=project,
            client_operation_id=identity(99001),
            key_hash="4" * 64,
            admission_root=namespace,
        )
        assert admission.compatibility == {
            "status": "incompatible",
            "code": "migration_only",
            "installation_key": None,
        }
        assert admission.journal != first.admission.journal
        assert admission.objects != first.admission.objects
        assert admission.accepted["job_id"] != first.job_id
        initial = first.admission.manifest
        project_account = next(row for row in initial["accounts"] if row["scope"] == "project")
        job_account = next(row for row in initial["accounts"] if row["scope"] == "job")
        job_id = admission.accepted["job_id"]
        provision = {
            **initial,
            "manifest_id": identity(99002),
            "operation": "provision",
            "source_digest": fixture.source,
            "parent_manifest_digest": digest(initial),
            "opening_accounts": None,
            "accounts": [
                {
                    **project_account,
                    "id": identity(99003),
                    "scope_id": project,
                    "project_id": project,
                },
                {
                    **job_account,
                    "id": identity(99004),
                    "scope_id": job_id,
                    "project_id": project,
                    "job_id": job_id,
                    "limit_microusd": admission.association["job"]["budget"],
                },
            ],
        }
        prior = snapshot(first.engine)
        receipt = invoke(fixture, provision)
        after = snapshot(first.engine)
        assert receipt.sequence == 1 and receipt.account_rows == 2
        assert rows(prior, "jobs") == rows(after, "jobs")
        old_accounts = {row["id"]: row for row in rows(prior, "budget_accounts")}
        final_accounts = {row["id"]: row for row in rows(after, "budget_accounts")}
        assert all(final_accounts[key] == row for key, row in old_accounts.items())
        assert set(final_accounts) == set(old_accounts) | {identity(99003), identity(99004)}
        state = inspect(refreshed(fixture))
        assert state.account_count == 5 and state.manifest_count == 2
        assert len(rows(after, "organizations")) == 1
        second = replace(
            first,
            project_id=project,
            job_id=job_id,
            context=first.authority.named(first.principal, project, action="record").context,
            account_ids=(first.account_ids[0], identity(99003), identity(99004)),
            provisioning=fixture,
            admission=SimpleNamespace(
                **vars(admission), manifest=provision, initialization_receipt=receipt
            ),
        )
        return first, second
    except BaseException:
        first.close()
        raise


def build_released_legacy_history_case(tmp_path, monkeypatch):
    """Native synthetic historical releases; no provider, invoice or P2 replay.

    Two separate legacy jobs each have a valid signed64 gross. Only the shared
    accounts' lifetime sum exceeds signed64; their present held/accounted is0.
    """
    import reservation_fixture as shared
    from ledger_eligibility_fixture import refreshed
    from ledger_provisioning_fixture import ciphertexts, inspect
    from sqlalchemy import text
    from test_admission_envelope import descriptor

    from agent_rewind.artifact_metadata import record_verified, register_ref

    maximum = 2**63 - 1
    original = shared.build_case
    historical_jobs = []

    def predecessor(path, *, legacy):
        assert legacy is True
        fixture = original(path, legacy=True)
        try:
            before = snapshot(fixture.case.engine)
            jobs = sorted(rows(before, "jobs"), key=lambda row: row["id"])
            assert len(jobs) == 3 and all(row["payload_version"] == 1 for row in jobs)
            historical_jobs.extend(row["id"] for row in jobs[:2])
            expected = deepcopy(before)
            with owned_begin(fixture.case.engine) as connection:
                for job in jobs:
                    budget = maximum if job["id"] in historical_jobs else job["budget"]
                    connection.execute(
                        text("UPDATE jobs SET budget=:budget,reserved=0 WHERE id=:id"),
                        {"budget": budget, "id": job["id"]},
                    )
                    one(expected, "jobs", id=job["id"]).update(budget=budget, reserved=0)
            same(expected, snapshot(fixture.case.engine))
            assert ciphertexts(fixture.case) == fixture.encrypted
            return refreshed(fixture)
        except BaseException:
            fixture.close()
            raise

    with monkeypatch.context() as patch:
        patch.setattr(shared, "build_case", predecessor)
        case = shared.build_reservation_case(
            tmp_path, patch, budget=1_000_000, account_limit=maximum, legacy=True
        )
    try:
        before = snapshot(case.engine)
        assert one(before, "jobs", id=case.job_id)["budget"] == 1_000_000
        assert all(row["legacy_reserved_microusd"] == 0 for row in rows(before, "jobs"))
        assert all(row["opening_held_microusd"] == 0 for row in rows(before, "budget_accounts"))
        calls = []

        def insert(connection, table, row):
            # Fixed test-owned table/column names and parameterized values only.
            connection.execute(
                text(
                    f"INSERT INTO {table}({','.join(row)}) VALUES("
                    + ",".join(":" + key for key in row)
                    + ")"
                ),
                row,
            )

        with owned_begin(case.engine) as connection:
            for number, job_id in enumerate(historical_jobs):
                account = one(before, "budget_accounts", job_id=job_id)
                triple = (case.account_ids[0], case.account_ids[1], account["id"])
                call_id = identity(99500 + number)
                stamp = "2026-10-22T00:00:00.000000Z"
                call = {
                    "id": call_id,
                    "project_id": case.project_id,
                    "job_id": job_id,
                    "logical_call_id": identity(99510 + number),
                    "purpose": "continuation",
                    "request_digest": "e" * 64,
                    "price_version": case.price_version,
                    "state": "reconciled",
                    "reserved_microusd": maximum,
                    "created_at": stamp,
                    "organization_id": case.organization_id,
                    "job_resource_kind": "job",
                    "lease_generation": 1,
                    "organization_account_id": triple[0],
                    "project_account_id": triple[1],
                    "job_account_id": triple[2],
                }
                insert(connection, "provider_calls", call)
                insert(
                    connection,
                    "resource_scopes",
                    {
                        "resource_kind": "provider_call",
                        "resource_id": call_id,
                        "project_id": case.project_id,
                    },
                )
                proof = descriptor(
                    b"synthetic retained release metadata " + bytes([number]),
                    object_id=identity(99520 + number),
                    project=case.project_id,
                )
                record_verified(connection, proof)
                register_ref(
                    connection,
                    project_id=case.project_id,
                    owner_kind="provider_call",
                    owner_id=call_id,
                    role="budget_evidence",
                    artifact_id=proof.id,
                )
                for account_id in triple:
                    for kind in ("reserve", "release"):
                        insert(
                            connection,
                            "budget_entries",
                            {
                                "call_id": call_id,
                                "account_id": account_id,
                                "entry_kind": kind,
                                "amount_microusd": maximum,
                                "created_at": stamp,
                                "project_id": case.project_id,
                                "evidence_ref": proof.id if kind == "release" else None,
                                "evidence_owner_kind": "provider_call",
                                "evidence_role": "budget_evidence",
                            },
                        )
                connection.execute(
                    text("UPDATE jobs SET reserved=:money,lease_generation=1 WHERE id=:id"),
                    {"money": maximum, "id": job_id},
                )
                calls.append((call_id, job_id, triple, proof))
        after = snapshot(case.engine)
        assert rows(before, "budget_accounts") == rows(after, "budget_accounts")
        assert one(before, "jobs", id=case.job_id) == one(after, "jobs", id=case.job_id)
        assert rows(before, "operations") == rows(after, "operations")
        for call_id, job_id, triple, proof in calls:
            job = one(after, "jobs", id=job_id)
            assert type(job["reserved"]) is int and job["reserved"] == job["budget"] == maximum
            cohort = [row for row in rows(after, "budget_entries") if row["call_id"] == call_id]
            assert len(cohort) == 6
            for account_id in triple:
                selected = [row for row in cohort if row["account_id"] == account_id]
                assert {row["entry_kind"] for row in selected} == {"reserve", "release"}
                assert all(
                    type(row["amount_microusd"]) is int and row["amount_microusd"] == maximum
                    for row in selected
                )
                assert (
                    next(row for row in selected if row["entry_kind"] == "reserve")["evidence_ref"]
                    is None
                )
                assert (
                    next(row for row in selected if row["entry_kind"] == "release")["evidence_ref"]
                    == proof.id
                )
            assert (
                one(
                    after,
                    "artifact_refs",
                    owner_kind="provider_call",
                    owner_id=call_id,
                    role="budget_evidence",
                )["artifact_id"]
                == proof.id
            )
            assert one(after, "artifact_objects", id=proof.id)["digest"] == proof.digest
        assert (
            sum(
                row["amount_microusd"]
                for row in rows(after, "budget_entries")
                if row["account_id"] == case.account_ids[0] and row["entry_kind"] == "reserve"
            )
            == 2 * maximum
        )
        assert all(
            row["held_microusd"] == row["accounted_microusd"] == 0
            for row in rows(after, "budget_accounts")
        )
        # Existing full retained-history reader must accept the native fixture.
        inspect(refreshed(case.provisioning))
        return case
    except BaseException:
        case.close()
        raise
