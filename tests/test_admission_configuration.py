import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from agent_rewind.admission_configuration import (
    MAX_ALIAS_BYTES,
    MAX_IMAGE_ALIASES,
    SEED_STRATEGY,
    NativeConfiguration,
    NativeRegistry,
)
from agent_rewind.admission_request import MAX_CONFIG_BYTES, AdmissionPreparationError
from agent_rewind.models import canonical


def configuration_value():
    return {
        "schema": 1,
        "kind": "native-v1",
        "image_identity": "sha256:" + "a" * 64,
        "endpoint_profile": "fixture-provider",
        "endpoint_revision": "revision-1",
        "model_revision": "model-revision-1",
        "adapter_digest": "b" * 64,
        "prompt_digest": "c" * 64,
        "tool_policy_digest": "d" * 64,
        "configuration_digest": "e" * 64,
        "processor_profile": "fixture-processor",
        "max_input_tokens": 128000,
        "max_output_tokens": 2048,
        "reasoning_effort": "",
        "seed_supported": False,
        "seed_strategy": SEED_STRATEGY,
        "price_version": "fixture-prices-1",
        "input_microusd_per_million_tokens": 1000000,
        "output_microusd_per_million_tokens": 2000000,
    }


def configuration(value=None):
    raw = canonical(configuration_value() if value is None else value)
    return NativeConfiguration(raw, expected_digest=hashlib.sha256(raw).hexdigest())


def test_configuration_is_immutable_external_digest_and_no_settings():
    value = configuration_value()
    entry = configuration(value)
    value["model_revision"] = "changed"
    assert json.loads(entry.canonical_bytes)["model_revision"] == "model-revision-1"
    assert entry.digest == hashlib.sha256(entry.canonical_bytes).hexdigest()
    assert entry.digest != json.loads(entry.canonical_bytes)["configuration_digest"]
    with pytest.raises(FrozenInstanceError):
        entry.processor_profile = "other"


def test_registry_detaches_aliases_and_resolves_only_explicit_permission():
    entry = configuration()
    aliases = ["fixture:approved", "fixture-α"]
    registry = NativeRegistry(entry, aliases)
    aliases[0] = "unapproved"
    assert registry.image_aliases == ("fixture:approved", "fixture-α")
    assert (
        registry.resolve_new(
            "native-v1", "fixture:approved", permitted_processor_profile="fixture-processor"
        )
        is entry
    )
    with pytest.raises(FrozenInstanceError):
        registry.image_aliases = ("new",)
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_unavailable$"):
        registry.resolve_new(
            "native-v1", "unapproved", permitted_processor_profile="fixture-processor"
        )


@pytest.mark.parametrize(
    "adapter,image,permission",
    [
        ("other", "fixture", "fixture-processor"),
        ("native-v1", "missing", "fixture-processor"),
        ("native-v1", "fixture", None),
        ("native-v1", "fixture", "other"),
        ("native-v1", "fixture", ["fixture-processor"]),
        ("native-v1", "fixture", {"fixture-processor": True}),
        ("native-v1", "fixture", "fixture-processor\x00"),
    ],
)
def test_resolution_refuses_without_exact_registered_processor_permission(
    adapter, image, permission
):
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_unavailable$"):
        NativeRegistry(configuration(), ["fixture"]).resolve_new(
            adapter, image, permitted_processor_profile=permission
        )


def test_missing_registry_is_explicitly_unavailable():
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_unavailable$"):
        NativeRegistry(None, []).resolve_new(
            "native-v1", "fixture", permitted_processor_profile="fixture-processor"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", True),
        ("schema", 2),
        ("kind", "legacy"),
        ("image_identity", "latest"),
        ("image_identity", "sha256:" + "A" * 64),
        ("endpoint_profile", "https://user:secret@example.invalid/?token=secret"),
        ("endpoint_profile", "fixture?token=secret"),
        ("endpoint_revision", "r/" + "x" * 128),
        ("model_revision", {"name": "model"}),
        ("processor_profile", ["processor"]),
        ("adapter_digest", "x" * 64),
        ("prompt_digest", "b" * 64 + "\x00"),
        ("tool_policy_digest", None),
        ("configuration_digest", True),
        ("max_input_tokens", True),
        ("max_input_tokens", 1000.0),
        ("max_input_tokens", 999),
        ("max_input_tokens", 1000001),
        ("max_output_tokens", 0),
        ("max_output_tokens", 128001),
        ("seed_supported", 1),
        ("seed_strategy", "guess"),
        ("reasoning_effort", []),
        ("reasoning_effort", "unsupported"),
        ("price_version", ""),
        ("input_microusd_per_million_tokens", 0),
        ("input_microusd_per_million_tokens", 1.5),
        ("output_microusd_per_million_tokens", True),
        ("output_microusd_per_million_tokens", 2**63),
    ],
)
def test_all_config_primitives_are_strictly_validated(field, value):
    body = configuration_value()
    body[field] = value
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_invalid$"):
        configuration(body)


def test_unknown_missing_duplicate_and_noncanonical_config_refuse():
    body = configuration_value()
    for value in (
        {**body, "api_key": "secret"},
        {k: v for k, v in body.items() if k != "price_version"},
    ):
        with pytest.raises(AdmissionPreparationError, match="^admission_configuration_invalid$"):
            configuration(value)
    for raw in (json.dumps(body, indent=2).encode(), b'{"schema":1,"schema":1}'):
        with pytest.raises(AdmissionPreparationError, match="^admission_configuration_invalid$"):
            NativeConfiguration(raw, expected_digest=hashlib.sha256(raw).hexdigest())


def test_configuration_digest_must_bind_exact_bytes():
    first = configuration()
    body = configuration_value()
    body["price_version"] = "fixture-prices-2"
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_invalid$"):
        NativeConfiguration(canonical(body), expected_digest=first.digest)
    second = configuration(body)
    assert first.digest != second.digest
    assert json.loads(first.canonical_bytes)["price_version"] == "fixture-prices-1"


def test_config_over_limit_refuses_before_decoder(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("over-limit config was decoded")

    monkeypatch.setattr("agent_rewind.admission_request.json.loads", forbidden)
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_limit$"):
        NativeConfiguration(b" " * (MAX_CONFIG_BYTES + 1), expected_digest="a" * 64)


@pytest.mark.parametrize(
    "aliases",
    [
        [],
        ["duplicate", "duplicate"],
        ["x" * 301],
        ["x\x00"],
        ["\ud800"],
        [["mutable"]],
        {"fixture": True},
        ["x"] * (MAX_IMAGE_ALIASES + 1),
    ],
)
def test_alias_entry_is_bounded_and_strict(aliases):
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_invalid$"):
        NativeRegistry(configuration(), aliases)


def test_alias_canonical_bytes_are_aggregate_bounded():
    aliases = [str(i) + "é" * 295 for i in range(MAX_IMAGE_ALIASES)]
    assert len(canonical(aliases)) > MAX_ALIAS_BYTES
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_limit$"):
        NativeRegistry(configuration(), aliases)
    aliases = [f"fixture-{i}" for i in range(MAX_IMAGE_ALIASES)]
    assert len(NativeRegistry(configuration(), aliases).image_aliases) == MAX_IMAGE_ALIASES


def test_replacement_is_new_snapshot_and_does_not_mutate_old_resolution():
    old = NativeRegistry(configuration(), ["fixture"])
    value = configuration_value()
    value["endpoint_revision"] = "revision-2"
    new = NativeRegistry(configuration(value), ["fixture"])
    assert old.entry.digest != new.entry.digest
    assert json.loads(old.entry.canonical_bytes)["endpoint_revision"] == "revision-1"
    assert json.loads(new.entry.canonical_bytes)["endpoint_revision"] == "revision-2"
