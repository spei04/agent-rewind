"""Independent collision attribution for distinct, well-formed provision intents."""

from copy import deepcopy

from ledger_provisioning_fixture import END, ROLLOVER, identity
from test_ledger_competing_sqlite import prove_intent_absent

from agent_rewind.migrations.ledger_inputs import validate_ledger_manifest

CASES = ("account-id", "scope-start", "shared-organization")


def rows(snapshot, table):
    value = snapshot["tables"][table]
    return [dict(zip(value["columns"], row, strict=True)) for row in value["rows"]]


def period_key(account):
    return tuple(account[key] for key in ("organization_id", "scope", "scope_id", "period_start"))


def collision_sets(first, second):
    return {
        "account_ids": sorted({row["id"] for row in first} & {row["id"] for row in second}),
        "scope_starts": sorted(
            {period_key(row) for row in first} & {period_key(row) for row in second}
        ),
    }


def intents(first, case, *, project, other_project=None):
    assert case in CASES
    organization = first["accounts"][0]["organization_id"]

    def account(number, scope, target):
        return {
            "id": identity(number),
            "organization_id": organization,
            "scope": scope,
            "scope_id": target,
            "project_id": target if scope == "project" else None,
            "job_id": None,
            "period_start": ROLLOVER,
            "period_end": END,
            "limit_microusd": 245000,
        }

    base = {
        **deepcopy(first),
        "operation": "provision",
        "parent_manifest_digest": validate_ledger_manifest(first).digest,
        "opening_accounts": None,
    }
    winner = {**deepcopy(base), "manifest_id": identity(1001)}
    loser = {**deepcopy(base), "manifest_id": identity(1002)}
    winner["accounts"] = [account(400, "organization", organization)]
    loser["accounts"] = [account(401, "organization", organization)]
    if case == "account-id":
        loser["accounts"][0].update(
            id=identity(400), period_start=END, period_end="2300-01-01T00:00:00.000000Z"
        )
    elif case == "shared-organization":
        assert other_project is not None and other_project != project
        winner["accounts"].append(account(402, "project", project))
        loser["accounts"].append(account(403, "project", other_project))
    for manifest in (winner, loser):
        validate_ledger_manifest(manifest)
    return winner, loser


def prove_collision(before, winner, loser, case):
    """Exclude other early refusals before interpreting the common refusal code."""
    assert case in CASES
    left, right = (validate_ledger_manifest(value) for value in (winner, loser))
    assert left.operation == right.operation == "provision"
    assert left.manifest_id != right.manifest_id
    assert left.installation_key == right.installation_key
    assert left.source_digest == right.source_digest
    assert left.parent_manifest_digest == right.parent_manifest_digest
    assert left.parent_manifest_digest is not None
    absence = [prove_intent_absent(before, value) for value in (winner, loser)]
    collisions = collision_sets(winner["accounts"], loser["accounts"])
    if case == "account-id":
        assert len(winner["accounts"]) == len(loser["accounts"]) == 1
        assert collisions == {"account_ids": [winner["accounts"][0]["id"]], "scope_starts": []}
        left_account, right_account = winner["accounts"][0], loser["accounts"][0]
        assert (
            left_account["period_end"] <= right_account["period_start"]
            or right_account["period_end"] <= left_account["period_start"]
        )
    else:
        assert collisions == {
            "account_ids": [],
            "scope_starts": [period_key(winner["accounts"][0])],
        }
    organizations = rows(before, "organizations")
    assert len(organizations) == 1
    organization = organizations[0]["id"]
    assert {row["organization_id"] for value in (winner, loser) for row in value["accounts"]} == {
        organization
    }
    for value in (winner, loser):
        organization_account = value["accounts"][0]
        assert organization_account["scope"] == "organization"
        assert organization_account["scope_id"] == organization
    projects = []
    if case == "shared-organization":
        assert len(winner["accounts"]) == len(loser["accounts"]) == 2
        for value in (winner, loser):
            account = value["accounts"][1]
            assert account["scope"] == "project"
            assert account["scope_id"] == account["project_id"]
            matches = [
                row for row in rows(before, "projects") if row["id"] == account["project_id"]
            ]
            assert len(matches) == 1 and matches[0]["organization_id"] == organization
            projects.append(matches[0])
        assert projects[0]["id"] != projects[1]["id"]
    elif case == "scope-start":
        assert len(winner["accounts"]) == len(loser["accounts"]) == 1
    return {"absence": absence, "collisions": collisions, "projects": projects}


def changed_parent(loser, head):
    """This is an explicit new request; preserve the unused ID and account content."""
    result = deepcopy(loser)
    assert result["parent_manifest_digest"] != head["manifest_digest"]
    result["parent_manifest_digest"] = head["manifest_digest"]
    validate_ledger_manifest(result)
    assert result != loser
    assert {key: value for key, value in result.items() if key != "parent_manifest_digest"} == {
        key: value for key, value in loser.items() if key != "parent_manifest_digest"
    }
    return result


def assert_conflict_context(message, target, expected_state, expected_accounts, history, expected):
    witness = message["witness"]
    (classification,) = witness["classifications"]
    assert classification["raw_id"] == message["raw_id"]
    assert classification["engine_id"] == message["engine_id"]
    assert classification["state"] == expected_state
    assert classification["manifest"] == target
    assert classification["manifest_digest"] == validate_ledger_manifest(target).digest
    assert classification["history"] == history
    assert sorted(classification["accounts"], key=lambda row: row["id"]) == sorted(
        expected_accounts, key=lambda row: row["id"]
    )
    head = classification["state"]["head"]
    assert classification["state"]["revision"] == "ar_0007_ledger"
    assert classification["state"]["status"] == "complete"
    assert target["operation"] == "provision"
    assert target["installation_key"] == classification["state"]["installation_key"]
    assert target["parent_manifest_digest"] == head["manifest_digest"]
    assert target["manifest_id"] not in {row["manifest"]["manifest_id"] for row in history}
    actual = collision_sets(classification["accounts"], target["accounts"])
    assert actual == expected and (actual["account_ids"] or actual["scope_starts"])
    assert classification["refusal"] == {
        "type": "MigrationRefused",
        "code": "ledger_manifest_conflict",
    }
    assert witness["refusal"] == classification["refusal"] and witness["receipt"] is None


def assert_sqlite_conflict(message):
    """Require one actual exclusion/rollback and no application writes or retry."""
    from ledger_provisioning_fixture import assert_no_writes

    witness, raw = message["witness"], message["raw_id"]
    observed = witness["observation"]
    events = observed["native_trace"]
    assert len(observed["work"]) == len(observed["outcomes"]) == 1
    assert not observed["faults"]
    assert [event[2] for event in events if event[0] == "connect_return"] == [raw]
    assert all(event[2] == raw for event in events if len(event) >= 3)
    sql = [event[3] for event in events if event[0] == "sql"]
    assert sql.count("BEGIN EXCLUSIVE") == sql.count("ROLLBACK") == 1
    assert "COMMIT" not in sql
    assert not any(
        event[0] == "c_call" and event[3] == "commit" for event in events if len(event) > 3
    )
    (outcome,) = observed["outcomes"]
    assert outcome["begin_attempted"] and outcome["begun"]
    assert outcome["rollback_attempted"] and outcome["rollback_acknowledged"]
    assert not any(
        outcome[key] for key in ("commit_attempted", "commit_acknowledged", "cleanup_failed")
    )
    boundary = observed["command_boundary"]
    assert boundary["raw_id"] == raw and boundary["connection_closed"]
    assert boundary["checkedout"] == 0 and not boundary["lease_present"]
    assert boundary["receipt_completed"] and boundary["receipt_clean"]
    assert not boundary["in_transaction"] and not boundary["tainted"] and not boundary["borrowed"]
    expected_names = (
        "conflict.classify.enter",
        "conflict.classify.refused",
        "rollback.before_native",
        "rollback.native_ack",
        "command.exit",
    )
    selected = [row for row in observed["markers"] if row[0] in expected_names]
    assert [row[0] for row in selected] == list(expected_names)
    assert all(row[1] == raw for row in selected)
    positions = [row[2] for row in selected]
    assert positions == sorted(positions) and positions[-1] == boundary["trace_end"]
    physical = [
        event[0]
        for event in events[positions[2] : positions[3]]
        if len(event) > 3 and event[3] == "rollback" and event[0].startswith("c_")
    ]
    assert physical == ["c_call", "c_return"]
    assert all(event[1] != "harness-dispose" for event in events[: positions[-1]])
    assert_no_writes(observed["native_authorizer"])
    assert witness["native_errors"] == [
        {
            "type": "MigrationRefused",
            "sqlite_errorcode": None,
            "mapped_type": "MigrationRefused",
            "mapped_code": "ledger_manifest_conflict",
        }
    ]
