import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from test_admission_configuration import configuration, configuration_value
from test_admission_request import submission

from agent_rewind.admission_configuration import NativeRegistry
from agent_rewind.admission_envelope import (
    MAX_ENVELOPE_BYTES,
    ArtifactBinding,
    OriginCorrelation,
    prepare_admission,
    restore_admission,
)
from agent_rewind.admission_request import AdmissionPreparationError, parse_submit
from agent_rewind.artifact_metadata import ArtifactObject, object_locator
from agent_rewind.models import canonical

PROJECT = "1" * 32
JOB = "2" * 32


def descriptor(content, *, object_id="3" * 32, project=PROJECT):
    digest = hashlib.sha256(content).hexdigest()
    return ArtifactObject(
        object_id,
        project,
        digest,
        object_locator(project, digest),
        1,
        len(content),
        datetime(2026, 10, 21, tzinfo=UTC),
    )


def binding(content, *, role="task", object_id="3" * 32, project=PROJECT, job=JOB):
    return ArtifactBinding(
        project_id=project,
        job_id=job,
        role=role,
        descriptor=descriptor(content, object_id=object_id, project=project),
        plaintext=content,
    )


def arguments():
    intent = parse_submit(canonical(submission()))
    entry = configuration()
    return {
        "intent": intent,
        "registry": NativeRegistry(entry, ["fixture-image"]),
        "project_id": PROJECT,
        "job_id": JOB,
        "origin": OriginCorrelation("6" * 32),
        "task_binding": binding(intent.task_bytes),
        "configuration_binding": binding(
            entry.canonical_bytes, role="admission_config", object_id="4" * 32
        ),
        "permitted_processor_profile": "fixture-processor",
    }


def test_exact_schema2_fields_bind_content_refs_not_object_ids():
    args = arguments()
    result = prepare_admission(**args)
    body = json.loads(result.envelope_bytes)
    assert body == {
        "schema": 2,
        "kind": "native-run",
        "project_id": PROJECT,
        "client_operation_id": args["intent"].client_operation_id,
        "request_digest": args["intent"].request_digest,
        "task_ref": args["intent"].task_digest,
        "task_digest": args["intent"].task_digest,
        "seed": 0,
        "budget_microusd": 1,
        "execution_config_ref": args["registry"].entry.digest,
        "execution_config_digest": args["registry"].entry.digest,
    }
    assert len(body) == 11
    assert len(body["execution_config_ref"]) == 64
    assert body["execution_config_ref"] != args["configuration_binding"].descriptor.id
    assert "job_id" not in body and "correlation_id" not in body
    assert len(result.envelope_bytes) < MAX_ENVELOPE_BYTES
    assert result.envelope_digest == hashlib.sha256(canonical(body)).hexdigest()
    payload = result.bind_payload(descriptor(result.envelope_bytes, object_id="5" * 32))
    assert (payload.project_id, payload.job_id, payload.role) == (PROJECT, JOB, "payload")
    assert payload.descriptor.digest == result.envelope_digest
    assert payload.plaintext == result.envelope_bytes
    with pytest.raises(FrozenInstanceError):
        result.job_id = "9" * 32
    with pytest.raises(FrozenInstanceError):
        payload.role = "task"


def test_origin_is_separate_from_client_and_payload_identity():
    args = arguments()
    first = prepare_admission(**args)
    args["origin"] = OriginCorrelation("7" * 32)
    second = prepare_admission(**args)
    assert first.origin != second.origin
    assert first.intent == second.intent
    assert first.envelope_bytes == second.envelope_bytes
    # The pure layer does not choose the persisted first origin; P3 owns it.
    raw = submission()
    raw["origin_correlation_id"] = "7" * 32
    with pytest.raises(AdmissionPreparationError, match="^admission_invalid_input$"):
        parse_submit(canonical(raw))


@pytest.mark.parametrize("value", ["", "A" * 32, "a" * 64, "a" * 32 + "\x00", None, {}])
def test_origin_shape_does_not_accept_transport_or_arbitrary_values(value):
    with pytest.raises(AdmissionPreparationError, match="^admission_binding_invalid$"):
        OriginCorrelation(value)


@pytest.mark.parametrize(
    "variant", ["project", "job", "task-role", "config-role", "task", "config", "id"]
)
def test_wrong_scoped_association_or_content_refuses(variant):
    args = arguments()
    if variant == "project":
        args["task_binding"] = binding(args["intent"].task_bytes, project="9" * 32)
    elif variant == "job":
        args["configuration_binding"] = binding(
            args["registry"].entry.canonical_bytes,
            role="admission_config",
            object_id="4" * 32,
            job="9" * 32,
        )
    elif variant == "task-role":
        args["task_binding"] = binding(args["intent"].task_bytes, role="payload")
    elif variant == "config-role":
        args["configuration_binding"] = binding(
            args["registry"].entry.canonical_bytes, role="task", object_id="4" * 32
        )
    elif variant == "task":
        body = submission()
        body["seed"] = 1
        args["task_binding"] = binding(parse_submit(canonical(body)).task_bytes)
    elif variant == "config":
        value = configuration_value()
        value["price_version"] = "new"
        args["configuration_binding"] = binding(
            configuration(value).canonical_bytes, role="admission_config", object_id="4" * 32
        )
    else:
        args["configuration_binding"] = binding(
            args["registry"].entry.canonical_bytes, role="admission_config", object_id="3" * 32
        )
    with pytest.raises(AdmissionPreparationError, match="^admission_binding_invalid$"):
        prepare_admission(**args)


@pytest.mark.parametrize("variant", ["missing", "alias", "permission"])
def test_new_preparation_requires_explicit_registry_resolution(variant):
    args = arguments()
    if variant == "missing":
        args["registry"] = NativeRegistry(None, [])
    elif variant == "alias":
        args["registry"] = NativeRegistry(args["registry"].entry, ["other-image"])
    else:
        args["permitted_processor_profile"] = None
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_unavailable$"):
        prepare_admission(**args)


@pytest.mark.parametrize(
    "variant", ["size", "digest", "project", "legacy", "structural", "bytes", "role"]
)
def test_descriptor_binding_validates_all_supplied_metadata_before_accepting(variant):
    content = b"fixture"
    meta = descriptor(content)
    role = "task"
    if variant == "size":
        meta = replace(meta, byte_count=meta.byte_count + 1)
    elif variant == "digest":
        meta = descriptor(b"other")
    elif variant == "project":
        meta = descriptor(content, project="9" * 32)
    elif variant == "legacy":
        meta = replace(meta, locator=f"objects/{meta.digest}")
    elif variant == "structural":
        meta = SimpleNamespace(**meta.__dict__)
    elif variant == "bytes":
        content = bytearray(content)
    else:
        role = []
    with pytest.raises(AdmissionPreparationError, match="^admission_binding_invalid$"):
        ArtifactBinding(
            project_id=PROJECT,
            job_id=JOB,
            role=role,
            descriptor=meta,
            plaintext=content,
        )


def test_descriptor_copies_seven_immutable_fields():
    content = b"fixture"
    meta = descriptor(content)
    bound = ArtifactBinding(
        project_id=PROJECT,
        job_id=JOB,
        role="task",
        descriptor=meta,
        plaintext=content,
    )
    assert bound.descriptor == meta and bound.descriptor is not meta
    assert bound.descriptor.created_at == meta.created_at
    assert "fixture" not in repr(bound)


@pytest.mark.parametrize("variant", ["changed", "id", "invalid"])
def test_payload_binding_cannot_use_other_bytes_or_colliding_metadata(variant):
    result = prepare_admission(**arguments())
    if variant == "changed":
        meta = descriptor(b"different-envelope", object_id="5" * 32)
    elif variant == "id":
        meta = descriptor(result.envelope_bytes, object_id=result.task_binding.descriptor.id)
    else:
        meta = None
    with pytest.raises(AdmissionPreparationError, match="^admission_binding_invalid$"):
        result.bind_payload(meta)


def test_same_client_content_is_project_scoped_without_changing_request_identity():
    first_args = arguments()
    first = prepare_admission(**first_args)
    other_project = "8" * 32
    second_args = {
        **first_args,
        "project_id": other_project,
        "task_binding": binding(first.intent.task_bytes, project=other_project, object_id="a" * 32),
        "configuration_binding": binding(
            first.configuration.canonical_bytes,
            project=other_project,
            role="admission_config",
            object_id="b" * 32,
        ),
    }
    second = prepare_admission(**second_args)
    assert first.intent.request_digest == second.intent.request_digest
    assert first.intent.task_digest == second.intent.task_digest
    assert first.configuration.digest == second.configuration.digest
    assert first.envelope_digest != second.envelope_digest
    assert first.task_binding.descriptor.id != second.task_binding.descriptor.id
    assert first.task_binding.descriptor.locator != second.task_binding.descriptor.locator


def restoration_arguments(value):
    return dict(
        intent=value.intent,
        frozen_configuration=value.configuration.canonical_bytes,
        expected_configuration_digest=value.configuration.digest,
        expected_envelope_digest=value.envelope_digest,
        project_id=value.project_id,
        job_id=value.job_id,
        origin=value.origin,
        task_binding=value.task_binding,
        configuration_binding=value.configuration_binding,
    )


def test_frozen_restoration_preserves_original_bytes_descriptors_and_origin(monkeypatch):
    original = prepare_admission(**arguments())

    def forbidden(*args, **kwargs):
        pytest.fail("restoration consulted current registry")

    monkeypatch.setattr(NativeRegistry, "resolve_new", forbidden)
    restored = restore_admission(**restoration_arguments(original))
    assert restored == original
    assert restored.configuration is not original.configuration
    assert restored.envelope_bytes == original.envelope_bytes
    assert restored.origin.correlation_id == "6" * 32
    assert restored.job_id == JOB
    for name in ("task_binding", "configuration_binding"):
        assert getattr(restored, name).descriptor == getattr(original, name).descriptor
    assert restored.bind_payload(descriptor(original.envelope_bytes, object_id="5" * 32)) == (
        original.bind_payload(descriptor(original.envelope_bytes, object_id="5" * 32))
    )


@pytest.mark.parametrize(
    "field",
    ["config-bytes", "config-digest", "envelope", "task", "project", "job", "role", "duplicate-id"],
)
def test_restoration_rejects_changed_frozen_associations(field):
    original = prepare_admission(**arguments())
    args = restoration_arguments(original)
    if field == "config-bytes":
        args["frozen_configuration"] = b'{"schema":1,"schema":1}'
    elif field == "config-digest":
        args["expected_configuration_digest"] = "0" * 64
    elif field == "envelope":
        args["expected_envelope_digest"] = "0" * 64
    elif field == "task":
        raw = submission()
        raw["seed"] += 1
        args["intent"] = parse_submit(canonical(raw))
    elif field in {"project", "job"}:
        args[field + "_id"] = "9" * 32
    else:
        args["configuration_binding"] = binding(
            original.configuration.canonical_bytes,
            role="payload" if field == "role" else "admission_config",
            object_id="3" * 32 if field == "duplicate-id" else "4" * 32,
        )
    with pytest.raises(AdmissionPreparationError):
        restore_admission(**args)


def test_restoration_rejects_oversized_configuration_before_parsing():
    args = restoration_arguments(prepare_admission(**arguments()))
    args["frozen_configuration"] = b"x" * (64 * 1024 + 1)
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_limit$"):
        restore_admission(**args)


def test_restoration_does_not_turn_frozen_processor_into_a_new_preparation_grant():
    args = arguments()
    original = prepare_admission(**args)
    assert restore_admission(**restoration_arguments(original)) == original
    args["permitted_processor_profile"] = None
    with pytest.raises(AdmissionPreparationError, match="^admission_configuration_unavailable$"):
        prepare_admission(**args)
