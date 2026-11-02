"""Real admitted/P1 setup for internal reservation tests, never live activation."""

import json
from dataclasses import dataclass
from types import SimpleNamespace

import ledger_eligibility_fixture as eligibility
from ledger_provisioning_fixture import build_case, initial_manifest, invoke, snapshot
from sqlalchemy import event
from test_admission_configuration import configuration
from test_admission_request import submission

from agent_rewind.request_authority import RequestAuthority
from agent_rewind.sqlite_ownership import create_owned_sqlite_engine


@dataclass
class ReservationCase:
    engine: object
    authority: object
    principal: object
    context: object
    job_id: str
    organization_id: str
    project_id: str
    account_ids: tuple[str, str, str]
    price_version: str
    case: object
    provisioning: object
    admission: object
    setup_events: list

    def close(self):
        try:
            self.engine.dispose()
        finally:
            self.provisioning.close()

    def snapshot(self):
        return snapshot(self.case.path)


def build_reservation_case(
    tmp_path,
    monkeypatch,
    *,
    budget=1_000_000,
    account_limit=1_000_000,
    legacy=False,
    fresh_ar6_template=None,
):
    if type(budget) is not int or not 1 <= budget <= 200_000_000:
        raise ValueError("invalid_fixture_budget")
    if type(account_limit) is not int or not 0 <= account_limit <= 2**63 - 1:
        raise ValueError("invalid_fixture_account_limit")
    fixture = (
        build_case(tmp_path / "reservations.db", legacy=legacy)
        if fresh_ar6_template is None
        else build_case(
            tmp_path / "reservations.db", legacy=legacy, fresh_ar6_template=fresh_ar6_template
        )
    )
    engine = None
    events = []
    try:
        body = submission()
        body["budget_microusd"] = budget
        with monkeypatch.context() as patch:
            patch.setattr(eligibility, "submission", lambda: body)
            fixture, admission = eligibility.admit_existing_fixture(
                fixture, patch, lambda name, value: events.append((name, value))
            )
        manifest = initial_manifest(fixture)
        for account in manifest["accounts"]:
            if account["scope"] in {"organization", "project"}:
                account["limit_microusd"] = account_limit
        receipt = invoke(fixture, manifest)
        engine = create_owned_sqlite_engine(
            str(fixture.case.engine.url),
            connect_timeout=3,
            pool_timeout=1,
            pool_size=8,
            max_overflow=0,
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(raw, _record):
            raw.execute("PRAGMA foreign_keys=ON")

        principal, _binding = eligibility.existing_admission_principal(fixture)
        authority = RequestAuthority(engine)
        context = authority.named(principal, fixture.project, action="record").context
        job_id = admission.accepted["job_id"]
        org = next(row["id"] for row in manifest["accounts"] if row["scope"] == "organization")
        project = next(row["id"] for row in manifest["accounts"] if row["scope"] == "project")
        job = next(row["id"] for row in manifest["accounts"] if row["job_id"] == job_id)
        return ReservationCase(
            engine=engine,
            authority=authority,
            principal=principal,
            context=context,
            job_id=job_id,
            organization_id=fixture.organization,
            project_id=fixture.project,
            account_ids=(org, project, job),
            price_version=json.loads(configuration().canonical_bytes)["price_version"],
            case=fixture.case,
            provisioning=fixture,
            admission=SimpleNamespace(
                **vars(admission), manifest=manifest, initialization_receipt=receipt
            ),
            setup_events=events,
        )
    except BaseException:
        if engine is not None:
            engine.dispose()
        fixture.close()
        raise
