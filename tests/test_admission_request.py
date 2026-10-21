import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from agent_rewind.admission_request import (
    MAX_BODY_BYTES,
    MAX_TASK_BYTES,
    AdmissionPreparationError,
    bounded_canonical,
    parse_submit,
)
from agent_rewind.models import TaskSpec, canonical


def submission():
    return {
        "client_operation_id": "a" * 32,
        "adapter_config_id": "native-v1",
        "seed": 0,
        "budget_microusd": 1,
        "task": {
            "name": "fixture",
            "instruction": "Fix the fixture.",
            "image": "fixture-image",
            "files": {"main.py": ""},
            "evaluator_files": {"check.py": "assert True\n"},
            "evaluator_command": "python check.py",
        },
    }


def at_task_size(size):
    body = submission()
    task = TaskSpec.model_validate({**body["task"], "seed": 0, "budget_usd": 0.000001})
    padding = size - len(canonical(task.model_dump()))
    body["task"]["files"]["main.py"] = "x" * padding
    return body


def test_materialized_defaults_preserve_existing_canonical_bytes_and_legacy_shape():
    body = submission()
    body["task"]["files"]["main.py"] = "é\n  source = '😀'\n"
    value = parse_submit(canonical(body))
    task = TaskSpec.model_validate({**body["task"], "seed": body["seed"], "budget_usd": 0.000001})
    assert value.task_bytes == canonical(task.model_dump())
    expected = {**body, "task": task.model_dump(exclude={"seed", "budget_usd"})}
    assert value.canonical_bytes == canonical(expected)
    assert value.request_digest == hashlib.sha256(canonical(expected)).hexdigest()
    assert value.task_digest == hashlib.sha256(value.task_bytes).hexdigest()
    assert parse_submit(canonical(expected)) == value
    body["task"]["files"]["main.py"] = "changed after preparation"
    assert json.loads(value.task_bytes)["files"]["main.py"] == "é\n  source = '😀'\n"
    with pytest.raises(FrozenInstanceError):
        value.seed = 4


@pytest.mark.parametrize("change", ["source", "unicode", "list", "seed", "budget", "client"])
def test_meaningful_client_intent_changes_have_distinct_identity(change):
    body = submission()
    body["task"]["files"]["main.py"] = "é"
    body["task"]["redact_patterns"] = ["first", "second"]
    before = parse_submit(canonical(body))
    if change == "source":
        body["task"]["files"]["main.py"] += " "
    elif change == "unicode":
        body["task"]["files"]["main.py"] = "e\u0301"
    elif change == "list":
        body["task"]["redact_patterns"].reverse()
    elif change == "seed":
        body["seed"] = 1
    elif change == "budget":
        body["budget_microusd"] = 2
    else:
        body["client_operation_id"] = "b" * 32
    assert parse_submit(canonical(body)).request_digest != before.request_digest


@pytest.mark.parametrize("amount", [1, 2, 999999, 1000000, 1000001, 199999999, 200000000])
def test_integer_money_survives_legacy_conversion(amount):
    body = submission()
    body["budget_microusd"] = amount
    body["seed"] = 2**31 - 1
    value = parse_submit(canonical(body))
    task = json.loads(value.task_bytes)
    assert value.budget_microusd == amount
    assert round(task["budget_usd"] * 1_000_000) == amount
    assert json.loads(value.canonical_bytes)["budget_microusd"] == amount
    assert task["seed"] == value.seed == 2**31 - 1


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_full_materialized_task_boundary_including_wrapper(delta):
    body = at_task_size(MAX_TASK_BYTES + delta)
    raw = canonical(body)
    assert MAX_TASK_BYTES < len(raw) < MAX_BODY_BYTES
    if delta > 0:
        with pytest.raises(AdmissionPreparationError, match="^admission_task_limit$"):
            parse_submit(raw)
    else:
        result = parse_submit(raw)
        assert len(result.task_bytes) == MAX_TASK_BYTES + delta
        assert len(result.canonical_bytes) > MAX_TASK_BYTES


def test_definition_alone_fits_but_materialized_task_exceeds_limit():
    body = at_task_size(MAX_TASK_BYTES + 1)
    assert len(canonical(body["task"])) <= MAX_TASK_BYTES
    with pytest.raises(AdmissionPreparationError, match="^admission_task_limit$"):
        parse_submit(canonical(body))


def test_raw_transport_boundary_is_separate_from_task_limit(monkeypatch):
    raw = canonical(submission())
    padded = raw + b" " * (MAX_BODY_BYTES - len(raw))
    assert parse_submit(padded) == parse_submit(raw)

    def forbidden(*args, **kwargs):
        pytest.fail("oversized body reached the JSON decoder")

    monkeypatch.setattr("agent_rewind.admission_request.json.loads", forbidden)
    with pytest.raises(AdmissionPreparationError, match="^admission_body_limit$"):
        parse_submit(padded + b" ")


def test_unicode_canonical_expansion_is_measured_before_encoding(monkeypatch):
    body = submission()
    body["task"]["files"]["main.py"] = "é" * (MAX_TASK_BYTES // 6 + 1)
    raw = json.dumps(body, ensure_ascii=False).encode()
    assert len(raw) < MAX_BODY_BYTES

    def forbidden(value):
        if isinstance(value, dict | list):
            pytest.fail("oversized canonical output reached the encoder")
        return canonical(value)

    monkeypatch.setattr("agent_rewind.admission_request.canonical", forbidden)
    with pytest.raises(AdmissionPreparationError, match="^admission_task_limit$"):
        parse_submit(raw)


@pytest.mark.parametrize("value", ["abc", '\\"\b\f\n\r\t\x00\x1f\x7f', "é😀", [], {}, None, True])
def test_size_preflight_matches_existing_canonical_escaping(value):
    fixture = {"v": value}
    expected = canonical(fixture)
    assert (
        bounded_canonical(fixture, limit=len(expected), limit_code="admission_task_limit")
        == expected
    )
    with pytest.raises(AdmissionPreparationError, match="^admission_task_limit$"):
        bounded_canonical(fixture, limit=len(expected) - 1, limit_code="admission_task_limit")


@pytest.mark.parametrize(
    "field,value",
    [
        ("seed", True),
        ("seed", 1.0),
        ("seed", -1),
        ("seed", 2**31),
        ("budget_microusd", True),
        ("budget_microusd", 1.0),
        ("budget_microusd", 0),
        ("budget_microusd", 200000001),
        ("client_operation_id", "A" * 32),
        ("client_operation_id", "a" * 32 + "\x00"),
        ("adapter_config_id", "other"),
        ("task", []),
    ],
)
def test_invalid_top_level_fields_have_fixed_error(field, value):
    body = submission()
    body[field] = value
    with pytest.raises(AdmissionPreparationError, match="^admission_invalid_input$"):
        parse_submit(canonical(body))


@pytest.mark.parametrize("field", ["seed", "budget_microusd", "client_operation_id"])
def test_required_fields_never_use_legacy_defaults(field):
    body = submission()
    del body[field]
    with pytest.raises(AdmissionPreparationError, match="^admission_invalid_input$"):
        parse_submit(canonical(body))


@pytest.mark.parametrize("variant", ["unknown", "mode", "path", "overlap", "bool", "surrogate"])
def test_invalid_task_shapes_and_paths_refuse(variant):
    body = submission()
    if variant == "unknown":
        body["task"]["seed"] = 0
    elif variant == "mode":
        body["task"]["files"]["main.py"] = {"content": "x", "mode": 0o755}
    elif variant == "path":
        body["task"]["files"] = {"./main.py": "x"}
    elif variant == "overlap":
        body["task"]["evaluator_files"] = {"main.py": "x"}
    elif variant == "bool":
        body["task"]["max_steps"] = True
    else:
        body["task"]["files"]["main.py"] = "\ud800"
    with pytest.raises(AdmissionPreparationError, match="^admission_invalid_input$"):
        parse_submit(canonical(body))


@pytest.mark.parametrize("count", [2000, 2001])
def test_initial_file_limit_counts_source_and_evaluator(count):
    body = submission()
    body["task"]["files"] = {f"f{i}": "" for i in range(count - 1)}
    if count > 2000:
        with pytest.raises(AdmissionPreparationError, match="^admission_invalid_input$"):
            parse_submit(canonical(body))
    else:
        assert parse_submit(canonical(body)).task_bytes


@pytest.mark.parametrize(
    "raw",
    [
        b'{"seed":0,"seed":1}',
        b'{"seed":0,"se\\u0065d":1}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e999}',
        b'{"x":123456789012345678901}',
        b"[]",
        b"null",
        b"\xff",
        b'{"x":',
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_malformed_or_ambiguous_json_has_fixed_failure(raw):
    with pytest.raises(AdmissionPreparationError, match="^admission_invalid_input$"):
        parse_submit(raw)
