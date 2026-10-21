"""Independent frozen wire-contract and accepted OpenAPI preservation checks.

No route schema builder is imported. Expected operation shapes come only from
C04's frozen document; the prior metadata fingerprint was captured from accepted
P1 source d70044494322f0135f36c4ff4778ae7445a4d24d with the pinned dependencies.
The app is constructed without migration, requests, lifespan or readiness I/O.
"""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_rewind.api import create_app

PREFIX = "/api/v1/projects/{project_id}"
OPERATIONS = (
    (PREFIX + "/runs", "post"),
    (PREFIX + "/operations/{operation_id}", "get"),
    (PREFIX + "/operations/{operation_id}/cancel", "post"),
)
ANNOTATIONS = {"title", "description", "summary"}
BASELINE_SOURCE = "d70044494322f0135f36c4ff4778ae7445a4d24d"
# Exact prior metadata, separate from the frozen contract for the three new routes.
BASELINE_PATH_DIGESTS = {
    "/": "7cdf7e25f7cca90b73ca439c8b6ce363b5391cee9bd51c83673f2d36560b880d",
    "/api/branches": "249e819cf30b98bd94d65cf09d54806922eced2bc3e17a01a5ab67de5d20b312",
    "/api/compare": "a556f2753a16c54f04d91d3ec0876b6ec53d22845028b5cf9c8ba0068d13a01c",
    "/api/investigations": "f6cf3784158b1120e52b6589b2bcddba5611de7efaacb7214e262eb14a22fe80",
    "/api/jobs": "e2f6979e76c4b48d0dda3c1ba5f9cb4974db50b30c6d84ef215f1cf84a439213",
    "/api/jobs/{job_id}/cancel": "f1a8490f584ae77d494c0b20662d417cf0f45525578fc20a666edf86ae2a7282",
    "/api/keys": "170123a18019c516dd7c0cded0e20077407e2c2bb462f4c036812c71b61d7753",
    "/api/keys/{key_id}": "101ca9014e36d57e4f507c1b30f1541a095feeb9821d7227a167e08ca5df4c94",
    "/api/me": "e7b122279f48a7fac81ae47d60e193be7db32324e2da01f867ca2c9d66f38dcb",
    "/api/runs": "561d43dab826b4e0569d59f1050b4ed15b98403408246d241547ad696006e1ab",
    "/api/runs/{run_id}": "c8deeea89a985a77a4511b3e2b6b9fa9e535be71a33b538d6e566bd009e4d67f",
    "/api/runs/{run_id}/files/{step}": (
        "cc775c7fb27a72116d39c944f792571ea99f700addd27cd6291b2e400fcbdb7d"
    ),
    "/api/schema": "e627793f86f47ecd58957740fc3a309bea0c0a1f13da3af376109516f6d0931f",
    "/api/studies": "162d3ccfd47abe8746d94d8db050a96779317ee0dd24d364a4878d3bef86450d",
    "/api/studies/{study_id}": "62614a87fe1e6b4bbe51a44ebbf43fdb575803f08dc3aba8120be3227a281d40",
    "/api/v1/projects/{project_id}/runs": (
        "bd37ac12e536f9bd95860b14bcce2d69e99cfb736cf71913d3d280d110b12d2d"
    ),
    "/api/v1/projects/{project_id}/runs/{run_id}": (
        "fd57e224d6bcac60dba9e87ed1dd8c48a567149ffa3a5e51a7b369ff8538d040"
    ),
    "/auth/callback": "ff9ddaa3afb6f0969c1093c9517f5352774aa371c521dd28c77cbbb6a5efe4aa",
    "/auth/login": "3487184c13d517a57a5f4a6f620cef39ade399c40d405596db606ba99501eecc",
    "/auth/logout": "c65bc450f159406766783afbe97e28c39d3d085e243f1562fcbc36e8fe6ae74e",
    "/healthz": "da727151760d57fc4a0321473f37e68a23dedc1686d957af4c6c46f17acad042",
    "/livez": "c37deed7ad81847904e512d795bfc3f18969a7483ddd252ea9ae2d46ccf5026f",
    "/readyz": "36f65f4de45e17a3fc24ce183bdca5008716bb20437d789f3f750a23db3960af",
}
BASELINE_SCHEMA_DIGESTS = {
    "Action": "dcb85f78110d3df4e56e04b38f3143cc3e3a25b0811605502c1ad4c7c2d1ff4f",
    "BranchRequest": "f70b80e900de9a783198938ec9b0e224ff51ad05c8c67f01a8154da394c0c114",
    "HTTPValidationError": "7373c21f1389312367e27e440140ba11d587693c56d8aa27249b36d3f58c10c6",
    "Intervention": "b62cd0c203c069d6da88ff24db293ee35f4db0b40afc020cca1daba5443fdaab",
    "InvestigationRequest": "eacc2156966618344cbaede7c7397f10e2c4eb4943e37d68aa10c2516aa1d4e5",
    "KeyRequest": "0785a830005155dcee7dc131e41ec4c1e22dd9e4849949e877eb107611bf8c1a",
    "RunPage": "267fa52b7bffaf4e616fe7375b0ee82ea5e7e58834408d142998603239eb1ccb",
    "RunReadError": "0a8d3ecee7343ac5658ae1a8aa71c4c29cbdbb96c428d53354175f1da2b8afd8",
    "RunSummary": "002b57d7a7429c77111576d5cab04a4504de7556e0f1687b7c1521f3cc1fc8d5",
    "StudyRequest": "2ecf26265246cafe7dedb1d9f7853eadc0468df7f5c7cf33874dd32572d1f692",
    "TaskSpec": "eb390f8674335e217b7050b08af037839b7a2be0047e5d5687e9bd1f2ed21a48",
    "ValidationError": "ca285d0c0e64c42844efd2e860edb239e77cc49d87f065c5ccb7d2f55331b862",
}


@pytest.fixture
def documents(settings):
    app = create_app(settings)
    try:
        yield (
            app.openapi(),
            json.loads(
                (Path(__file__).parents[1] / "contracts/proposals/m1.openapi.json").read_text()
            ),
        )
    finally:
        app.state.db.engine.dispose()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _resolved(value, document, trail=()):
    """Resolve local refs without discarding siblings or validation constraints."""
    if isinstance(value, list):
        return [_resolved(item, document, trail) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        reference = value["$ref"]
        assert reference.startswith("#/"), "Only local frozen references are supported"
        assert reference not in trail, "Unexpected recursive operation contract"
        target = document
        for part in reference[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        result = _resolved(target, document, (*trail, reference))
        siblings = _resolved({key: item for key, item in value.items() if key != "$ref"}, document)
        assert not (result.keys() & siblings.keys()), "Overlapping ref siblings need review"
        return {**result, **siblings}
    result = {
        key: _resolved(item, document, trail)
        for key, item in value.items()
        if not (key in ANNOTATIONS and isinstance(item, str))
    }
    for key in ("required", "enum", "anyOf", "oneOf", "allOf", "security"):
        if isinstance(result.get(key), list):
            result[key] = sorted(result[key], key=_canonical)
    return result


def _operation(document, path, method):
    assert path in document["paths"], f"Missing frozen path: {path}"
    path_item = document["paths"][path]
    assert method in path_item, f"Missing frozen operation: {method.upper()} {path}"
    operation = deepcopy(path_item[method])
    parameters = [*path_item.get("parameters", []), *operation.pop("parameters", [])]
    normalized = {}
    for raw in parameters:
        item = _resolved(raw, document)
        identity = (item["in"], item["name"].lower() if item["in"] == "header" else item["name"])
        assert identity not in normalized, f"Duplicate parameter: {identity}"
        item["required"] = item.get("required", False)
        item["name"] = identity[1]
        normalized[identity] = item
    operation["parameters"] = [normalized[key] for key in sorted(normalized)]
    # Security alternatives can be declared globally in the frozen document.
    # Their effective meaning must be explicit on each newly generated route.
    operation["security"] = operation.get("security", document.get("security", []))
    return _resolved(operation, document)


@pytest.mark.parametrize(("path", "method"), OPERATIONS)
def test_operation_matches_complete_frozen_contract(documents, path, method):
    actual, frozen = documents
    expected = _operation(frozen, path, method)
    observed = _operation(actual, path, method)
    assert "security" in actual["paths"][path][method]
    # Includes operationId, body/media type, every status/header/error schema,
    # role/CSRF extensions, exact parameters, nullable/required fields, strict
    # integer bounds and additionalProperties. Only prose annotations are ignored.
    assert observed == expected


def test_operation_security_schemes_match_frozen_contract(documents):
    actual, frozen = documents
    assert _resolved(actual["components"].get("securitySchemes", {}), actual) == _resolved(
        frozen["components"]["securitySchemes"], frozen
    )


def test_existing_openapi_metadata_is_preserved_exactly(documents):
    actual, _ = documents
    preserved = deepcopy(actual)
    for path, method in OPERATIONS:
        if path in preserved["paths"]:
            preserved["paths"][path].pop(method, None)
            if not preserved["paths"][path]:
                del preserved["paths"][path]
    components = preserved["components"]
    assert set(components) <= {"schemas", "securitySchemes"}
    assert BASELINE_SCHEMA_DIGESTS.keys() <= components["schemas"].keys(), BASELINE_SOURCE
    assert preserved["paths"].keys() == BASELINE_PATH_DIGESTS.keys(), BASELINE_SOURCE
    for path, digest in BASELINE_PATH_DIGESTS.items():
        assert (
            hashlib.sha256(_canonical(preserved["paths"][path]).encode()).hexdigest() == digest
        ), f"Accepted {BASELINE_SOURCE} metadata changed at paths[{path!r}]"
    for name, digest in BASELINE_SCHEMA_DIGESTS.items():
        assert (
            hashlib.sha256(_canonical(components["schemas"][name]).encode()).hexdigest() == digest
        ), f"Accepted {BASELINE_SOURCE} metadata changed at components.schemas[{name!r}]"
    # Preserve global metadata too: adding global security would alter accepted
    # legacy/list/detail meaning despite correct security on the three new routes.
    assert {
        key: value for key, value in preserved.items() if key not in {"paths", "components"}
    } == {
        "openapi": "3.1.0",
        "info": {"title": "Agent Rewind", "version": "0.1.0"},
    }, BASELINE_SOURCE
