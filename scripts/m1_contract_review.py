"""Cross-file design review checks; never runtime acceptance or approval authority."""

from __future__ import annotations

import re
from datetime import datetime

ROLES = {"BE", "PL", "FE", "RS", "QE", "SEC", "TL"}
REVISION = "m1-review-2"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def bounded_text(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and value.strip() == value
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def check_review(
    api: dict, data: dict, acceptance: dict, links: dict, obs: dict, freeze: dict
) -> str:
    """Validate declared evidence shape; a human still verifies review authenticity."""
    try:
        return _check_review(api, data, acceptance, links, obs, freeze)
    except (KeyError, TypeError, AttributeError):
        raise ValueError("Invalid M1 review contract shape") from None


def _check_review(api, data, acceptance, links, obs, freeze):
    require(
        {
            api["x-contract-revision"],
            *(row["contract_revision"] for row in (data, acceptance, links, obs, freeze)),
        }
        == {REVISION},
        "M1 contract revisions disagree",
    )
    states = {
        api["x-approval-status"],
        data["approval_status"],
        links["approval_status"],
        freeze["approval_status"],
    }
    require(
        len(states) == 1 and states <= {"pending", "reviewed"},
        "M1 review states disagree or are unsupported",
    )
    status = next(iter(states))
    require(
        freeze["contract"] == "C04" and freeze["schema_version"] == 1, "Unsupported review record"
    )
    require(
        freeze["behavior_status"]
        == acceptance["status"]
        == links["acceptance_status"]
        == "planned-not-executed",
        "Review cannot claim runtime behavior passed",
    )
    require(
        freeze["runtime_implemented"] is False and freeze["production_authorized"] is False,
        "Review does not authorize production or certify runtime",
    )
    require(
        set(freeze["dispositions"]) == {f"IF-{number:02}" for number in range(1, 9)},
        "Missing interface disposition",
    )
    require(
        freeze["first_slice"] == ["AR-005-B", "AR-005-C"],
        "First migration slice changed without review",
    )
    require(
        freeze["required_readiness_prerequisites"] == ["AR-005-C"],
        "Readiness requires revision guard",
    )
    require(
        freeze["migration_owners"]["adoption-v1"] == "AR-005-B"
        and freeze["migration_owners"]["ownership-v1"] == "AR-007-A",
        "Migration ownership overlaps",
    )
    reviews = freeze["reviews"]
    require(
        len(reviews) == len(ROLES) and {row["role"] for row in reviews} == ROLES,
        "Missing or duplicate consumer review role",
    )
    for row in reviews:
        require(
            row["status"] in {"pending", "accepted", "changes-required"},
            "Unknown consumer disposition",
        )
        if row["status"] == "pending":
            require(status == "pending", "Reviewed freeze has pending consumer")
            continue
        reviewed_commit = row["reviewed_source_commit"]
        require(
            isinstance(reviewed_commit, str)
            and re.fullmatch(r"[0-9a-f]{40}", reviewed_commit) is not None
            and reviewed_commit == freeze["reviewed_source_commit"],
            "Consumer review must identify the exact reviewed source commit",
        )
        require(
            all(
                bounded_text(row[key], maximum)
                for key, maximum in (("reviewer", 128), ("scope", 1000), ("evidence", 2048))
            ),
            "Consumer review lacks bounded reviewer/scope/evidence",
        )
        require(bounded_text(row["date"], 32), "Consumer review lacks date")
        try:
            reviewed_at = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Consumer review date is invalid") from None
        require(
            reviewed_at.tzinfo is not None and "T" in row["date"],
            "Consumer review date needs timezone",
        )
        require(
            status != "reviewed" or row["status"] == "accepted",
            "Reviewed freeze has unresolved consumer",
        )
    require(bounded_text(freeze["scope"], 1000), "Review scope missing")

    schemas = api["components"]["schemas"]
    require(
        set(schemas["Error"]["properties"]["code"]["enum"]) == set(obs["error_rules"]),
        "Central error vocabulary differs from observability",
    )
    require(
        obs["reconciliation"]["add_error_codes"] == []
        and obs["reconciliation"]["add_responses"] == [],
        "Unresolved observability reconciliation",
    )
    for path in api["paths"].values():
        for method in {"get", "post"} & path.keys():
            op = path[method]
            headers = {item["name"] for item in op.get("parameters", []) if item["in"] == "header"}
            require("X-CSRF-Token" not in headers, "Conflicting CSRF header")
            if op["x-csrf-required-for-cookie-auth"]:
                require("X-Rewind-CSRF" in headers, "Cookie mutation lacks existing CSRF contract")
            require(
                {"500", "413"} <= op["responses"].keys(),
                "Safe fault or body-limit response missing",
            )
            for code, response in op["responses"].items():
                response_headers = response["headers"]
                require(
                    response_headers["Cache-Control"]["schema"]["const"] == "no-store",
                    "Response cache policy missing",
                )
                require(
                    response_headers["X-Request-ID"]["schema"]["pattern"] == "^[0-9a-f]{32}$",
                    "Response request ID policy missing",
                )
                if code == "429":
                    retry = response_headers["Retry-After"]["schema"]
                    require(
                        retry["minimum"] == 1 and retry["maximum"] == 60,
                        "Retry delay is not bounded",
                    )
    policy = obs["readiness_policy"]
    require(
        policy["schema_guard_prerequisite"] == "AR-005-C", "Readiness guard prerequisite missing"
    )
    require(
        (
            policy["sentinel_maximum_bytes"],
            policy["sentinel_maximum_ciphertext_bytes"],
            policy["maximum_probe_seconds"],
            policy["positive_cache_seconds"],
        )
        == (4096, 5560, 1, 5),
        "Sentinel or readiness bounds changed",
    )
    needed = {
        "project_memberships": {"legacy_default"},
        "run_index": {"published_seq", "projection_reason"},
        "operations": {
            "execution_config_digest",
            "payload_version",
            "job_resource_kind",
            "failure_correlation_id",
        },
        "budget_accounts": {"project_id", "job_id", "opening_held_microusd"},
        "provider_calls": {
            "organization_id",
            "job_resource_kind",
            "lease_generation",
            "organization_account_id",
            "project_account_id",
            "job_account_id",
        },
        "budget_entries": {"project_id", "evidence_owner_kind", "evidence_role"},
    }
    for entity, fields in needed.items():
        require(
            fields <= data["entities"][entity]["fields"].keys(),
            "Required M1 ownership/compatibility field missing",
        )
    require(
        data["migration_metadata"]["owner"] == "AR-005-B"
        and {"installation_adoptions", "migration_progress"} <= data["migration_metadata"].keys(),
        "Durable adoption metadata missing",
    )
    require(
        {"payload_version", "lease_generation", "legacy_reserved_microusd"}
        <= data["legacy_extensions"]["jobs"]["fields"].keys(),
        "Legacy job extension contract missing",
    )
    return status
