"""Offline integrity checks for the RA-01-A record; no research execution or URL fetch."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "contracts/research/prior-methods.json"
VERSIONS = {
    "dover": "2512.06749v3",
    "car": "2606.08275v1",
    "reflect": "2606.09071v1",
    "daaf": "2609.32498v1",
}
DIMENSIONS = {
    "checkpoint_state",
    "allowed_edits",
    "oracle_access",
    "proposal_generation",
    "allocation",
    "stopping",
    "offline_cost",
    "evaluation_holdout",
    "adaptation_fidelity",
    "unknowns",
}
DOMAINS = {
    "arxiv.org",
    "github.com",
    "api.github.com",
    "mbjinx.github.io",
    "www.microsoft.com",
    "proceedings.mlr.press",
    "www.ijcai.org",
}
STATUSES = {"paper_reported", "source_inspected", "inference", "unknown"}
KINDS = {"paper", "code", "license", "tree", "project"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def object_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == keys, f"{label}: fields")
    return dict(value)


def text_value(value: Any, label: str) -> str:
    require(isinstance(value, str) and 0 < len(value.strip()) <= 2000, f"{label}: text")
    return str(value)


def text_list(value: Any, label: str) -> list[str]:
    require(isinstance(value, list) and 0 < len(value) <= 40, f"{label}: list")
    result = [text_value(item, label) for item in value]
    require(len(result) == len(set(result)), f"{label}: duplicate")
    return result


def indexed(value: Any, label: str) -> dict[str, dict[str, Any]]:
    require(isinstance(value, list) and 0 < len(value) <= 60, f"{label}: list")
    result = {}
    for item in value:
        require(isinstance(item, dict), f"{label}: object")
        identity = text_value(item.get("id"), f"{label}: id")
        require(identity not in result, f"{label}: duplicate id")
        result[identity] = item
    return result


def references(value: Any, evidence: dict[str, dict[str, Any]], label: str) -> list[str]:
    refs = text_list(value, label)
    require(set(refs) <= set(evidence), f"{label}: unknown reference")
    return refs


def validate(record: Any) -> None:
    data = object_keys(
        record,
        {
            "schema_version",
            "audit_id",
            "checked_at",
            "scope",
            "evidence",
            "methods",
            "adjacent",
            "candidate",
            "adapter_estimates",
        },
        "record",
    )
    require(type(data["schema_version"]) is int and data["schema_version"] == 1, "version")
    require(data["audit_id"] == "RA-01-A", "audit identity")
    require(
        isinstance(data["checked_at"], str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["checked_at"]) is not None,
        "inspection date",
    )
    scope = object_keys(
        data["scope"],
        {
            "authorization",
            "third_party_execution",
            "paid_calls",
            "customer_data",
            "algorithm_implemented",
            "search_bounds",
        },
        "scope",
    )
    require(scope["authorization"] == "design_review_only", "authorization")
    for key in ("third_party_execution", "paid_calls", "customer_data", "algorithm_implemented"):
        require(scope[key] is False, f"{key}: audit cannot authorize or claim execution")
    text_list(scope["search_bounds"], "search bounds")

    evidence = indexed(data["evidence"], "evidence")
    for source in evidence.values():
        object_keys(source, {"id", "kind", "url", "locator"}, "evidence")
        require(source["kind"] in KINDS, "source kind")
        text_value(source["locator"], "source locator")
        url = urlsplit(text_value(source["url"], "source URL"))
        require(
            url.scheme == "https"
            and url.hostname in DOMAINS
            and url.username is None
            and url.password is None
            and url.port is None,
            "source URL: primary HTTPS domain",
        )
        if url.hostname == "arxiv.org":
            require(
                re.fullmatch(r"/(?:html|abs)/\d{4}\.\d{4,5}v[1-9]\d*", url.path) is not None,
                "arXiv source must pin version",
            )
        if source["kind"] in {"code", "license"}:
            require(
                url.hostname == "github.com"
                and re.fullmatch(r"/[^/]+/[^/]+/blob/[0-9a-f]{40}/.+", url.path) is not None,
                "code/license source must pin commit",
            )
        if source["kind"] == "tree":
            require(
                url.hostname == "api.github.com"
                and re.fullmatch(r"/repos/[^/]+/[^/]+/git/trees/[0-9a-f]{40}", url.path)
                is not None,
                "tree source must pin object",
            )

    methods = indexed(data["methods"], "methods")
    require(set(methods) == set(VERSIONS), "required methods")
    for identity, method in methods.items():
        object_keys(
            method,
            {
                "id",
                "paper",
                "paper_version",
                "availability",
                "reproduction",
                "disposition",
                "dimensions",
            },
            identity,
        )
        refs = references([method["paper"]], evidence, "paper")
        paper = evidence[refs[0]]
        require(
            paper["kind"] == "paper"
            and method["paper_version"] == VERSIONS[identity]
            and paper["url"] == f"https://arxiv.org/html/{VERSIONS[identity]}",
            "method paper version",
        )
        require(method["reproduction"] == "not_executed", "no baseline reproduced in this audit")
        require(
            method["disposition"]
            in {
                "adaptation_candidate",
                "unavailable_implementation",
                "incompatible_current_intervention",
            },
            "method disposition",
        )
        availability = object_keys(
            method["availability"],
            {
                "status",
                "repository",
                "commit",
                "license_status",
                "license_evidence",
                "evidence",
                "note",
            },
            "availability",
        )
        source_refs = references(availability["evidence"], evidence, "availability evidence")
        license_refs = references(availability["license_evidence"], evidence, "license evidence")
        text_value(availability["note"], "availability limits")
        if availability["status"] == "public_source":
            repository = text_value(availability["repository"], "repository")
            commit = text_value(availability["commit"], "commit")
            require(
                re.fullmatch(r"https://github.com/[^/]+/[^/]+", repository) is not None
                and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
                "repository commit pin",
            )
            require(
                any(
                    evidence[ref]["kind"] == "code"
                    and evidence[ref]["url"].startswith(f"{repository}/blob/{commit}/")
                    for ref in source_refs
                ),
                "public source must cite matching pinned code",
            )
            require(
                availability["license_status"] in {"root_text_inspected", "declaration_unresolved"},
                "public source license status",
            )
        else:
            require(availability["status"] == "not_located", "availability status")
            require(
                availability["repository"] is None and availability["commit"] is None,
                "unlocated source cannot invent a pin",
            )
            require(
                method["disposition"] != "adaptation_candidate",
                "unlocated source needs explicit implementation limitation",
            )
            require(
                availability["license_status"] in {"planned_only", "not_located"},
                "unlocated source cannot claim inspected license",
            )
        if availability["license_status"] == "root_text_inspected":
            require(
                any(evidence[ref]["kind"] == "license" for ref in license_refs),
                "inspected license requires license-text evidence",
            )
        dimensions = object_keys(method["dimensions"], DIMENSIONS, "dimensions")
        for dimension in dimensions.values():
            object_keys(dimension, {"status", "summary", "evidence"}, "dimension")
            require(dimension["status"] in STATUSES, "evidence state")
            text_value(dimension["summary"], "dimension summary")
            refs = references(dimension["evidence"], evidence, "dimension evidence")
            if dimension["status"] == "source_inspected":
                require(availability["status"] == "public_source", "unlocated code inspection")
                require(
                    any(
                        evidence[ref]["kind"] in {"code", "tree"}
                        and (
                            ref in source_refs
                            or evidence[ref]["url"].startswith(
                                f"{availability['repository']}/blob/{availability['commit']}/"
                            )
                        )
                        for ref in refs
                    ),
                    "source inspection requires matching source evidence",
                )
            if dimension["status"] == "paper_reported":
                require(
                    method["paper"] in refs,
                    "paper report requires matching paper evidence",
                )

    adjacent = indexed(data["adjacent"], "adjacent")
    require(len(adjacent) >= 4, "adjacent selection coverage")
    for row in adjacent.values():
        object_keys(row, {"id", "evidence", "objective", "boundary"}, "adjacent")
        refs = references(row["evidence"], evidence, "adjacent evidence")
        require(all(evidence[ref]["kind"] == "paper" for ref in refs), "adjacent primary papers")
        text_value(row["objective"], "adjacent objective")
        text_value(row["boundary"], "adjacent boundary")

    candidate = object_keys(
        data["candidate"], {"status", "claim", "not_claimed", "requires"}, "candidate"
    )
    require(candidate["status"] == "unproven_adaptation_hypothesis", "candidate evidence limit")
    text_value(candidate["claim"], "candidate hypothesis")
    text_list(candidate["not_claimed"], "excluded claims")
    text_list(candidate["requires"], "candidate gates")
    estimates = indexed(data["adapter_estimates"], "adapter estimates")
    for row in estimates.values():
        object_keys(
            row,
            {
                "id",
                "low_days",
                "high_days",
                "confidence",
                "scope",
                "prerequisites",
                "authorized",
            },
            "adapter estimate",
        )
        require(
            type(row["low_days"]) is int
            and type(row["high_days"]) is int
            and 0 < row["low_days"] <= row["high_days"],
            "adapter effort range",
        )
        require(row["confidence"] == "low" and row["authorized"] is False, "adapter authority")
        text_value(row["scope"], "adapter scope")
        text_list(row["prerequisites"], "adapter prerequisites")


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def load_record(path: Path = RECORD) -> Any:
    with path.open(encoding="utf-8") as stream:
        raw = stream.read(262145)
    require(len(raw) <= 262144, "record too large")
    return json.loads(raw, object_pairs_hook=unique_pairs)


def main() -> None:
    try:
        validate(load_record())
    except (ValueError, OSError) as error:
        raise SystemExit(f"Prior-method record invalid: {error}") from None
    print("Prior-method record complete: 4 methods; no baseline execution claimed.")


if __name__ == "__main__":
    main()
