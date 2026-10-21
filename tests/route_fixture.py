"""Explicit synthetic HTTP grants; never alters the application's release profile."""

import json

from sqlalchemy import text
from test_artifact_metadata import prepare
from test_ownership import FRESH

from agent_rewind.api import create_app
from agent_rewind.request_identity import SessionIdentity, VerifiedPrincipal, encode_v2_session
from agent_rewind.sqlite_ownership import owned_begin

ISSUER = "https://route-fixture.invalid"
SUBJECT = "route-human"
PRINCIPAL = VerifiedPrincipal.oidc(ISSUER, SUBJECT)
PROJECT = FRESH["project_id"]
CSRF = "c" * 32


def prepared_app(settings):
    settings.oidc_issuer = ISSUER
    app = create_app(settings)
    prepare(app.state.db.engine)
    with owned_begin(app.state.db.engine) as connection:
        connection.execute(
            text(
                "INSERT INTO project_memberships"
                "(project_id,principal_id,role,revoked_at,legacy_default) "
                "VALUES(:p,:principal,'maintainer',NULL,true)"
            ),
            {"p": PROJECT, "principal": PRINCIPAL.principal_id},
        )
    return app


def cookie(app):
    return encode_v2_session(
        app.state.auth.cipher, SessionIdentity(PRINCIPAL, ISSUER, SUBJECT, CSRF)
    )


def cookie_headers(app):
    return {
        "Cookie": "rewind_session=" + cookie(app),
        "X-Rewind-CSRF": CSRF,
        "Origin": app.state.auth.settings.public_url.rstrip("/"),
    }


def source_run(app):
    """Trusted scope metadata only; explicitly not a published run graph."""
    run_id, job_id = "1" * 32, "2" * 32
    with owned_begin(app.state.db.engine) as connection:
        connection.execute(
            text(
                "INSERT INTO jobs(id,kind,created,payload,status,cancel,budget,reserved) "
                "VALUES(:id,'run',1,:digest,'queued',false,1,0)"
            ),
            {"id": job_id, "digest": "0" * 64},
        )
        connection.execute(
            text("INSERT INTO records(id,kind,created,data) VALUES(:id,'run',1,:body)"),
            {"id": run_id, "body": json.dumps({"parent_id": None, "job_id": job_id})},
        )
        for kind, value in (("job", job_id), ("run", run_id)):
            connection.execute(
                text("INSERT INTO resource_scopes VALUES(:kind,:id,:project)"),
                {"kind": kind, "id": value, "project": PROJECT},
            )
    return run_id, job_id


def work_bodies(run_id, task):
    intervention = {"step": 1, "kind": "action", "action": {"tool": "finish"}}
    return [
        ("/api/runs", task.model_dump()),
        ("/api/branches", {"parent_id": run_id, "intervention": intervention}),
        ("/api/studies", {"run_id": run_id, "candidates": [intervention]}),
        ("/api/investigations", {"run_id": run_id}),
    ]
