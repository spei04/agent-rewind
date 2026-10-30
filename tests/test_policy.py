import json
import traceback
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from agent_rewind.policy import ChatPolicy, ModelCallFailure


def test_model_call_reserves_before_dispatch_and_records_usage(settings, task, monkeypatch):
    settings.model_url = "https://model.example.test/v1/chat/completions"
    settings.model_name = "test-model-version"
    settings.model_api_key = SecretStr("fixture-secret")
    settings.model_input_price = 2
    settings.model_output_price = 8
    settings.model_reasoning_effort = "high"
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json, headers):
            assert calls and calls[0] > 0
            assert json["store"] is False
            assert "seed" not in json
            assert json["reasoning_effort"] == "high"
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "choices": [{"message": {"content": '{"tool":"finish"}'}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                    "model": "test-model-version",
                },
            )

    monkeypatch.setattr("agent_rewind.policy.httpx.Client", FakeClient)
    policy = ChatPolicy(settings, calls.append)
    action, record = policy.propose(policy.initial(task), 1, 0)
    assert action.tool == "finish"
    assert record["reported_micro_usd"] == 100
    assert "fixture-secret" not in str(record)
    assert record["reserved_micro_usd"] > record["reported_micro_usd"]
    identity = policy.identity()
    settings.model_reasoning_effort = "low"
    assert policy.identity() != identity


def test_oversized_input_is_rejected_before_reserving_or_dispatching(settings, task, monkeypatch):
    settings.model_url = "https://model.example.test/v1/chat/completions"
    settings.model_name = "test-model-version"
    settings.model_api_key = SecretStr("fixture-secret")
    settings.model_input_price = 2
    settings.model_output_price = 8
    settings.model_max_input_tokens = 1000

    def forbidden(*args, **kwargs):
        pytest.fail("Oversized input must not reserve budget or contact the provider.")

    monkeypatch.setattr("agent_rewind.policy.httpx.Client", forbidden)
    policy = ChatPolicy(settings, forbidden)
    with pytest.raises(ValueError, match="token bound"):
        policy.propose(policy.initial(task), 1, 0)


def test_missing_key_after_initialization_never_dispatches(settings, task, monkeypatch):
    settings.model_url = "https://model.example.test/v1/chat/completions"
    settings.model_name = "test-model-version"
    settings.model_api_key = SecretStr("fixture-secret")
    settings.model_input_price = 2
    settings.model_output_price = 8
    policy = ChatPolicy(settings, lambda _: None)
    settings.model_api_key = None

    def forbidden(*args, **kwargs):
        pytest.fail("Missing credentials must not contact the provider.")

    monkeypatch.setattr("agent_rewind.policy.httpx.Client", forbidden)
    with pytest.raises(ValueError, match="API key is not configured"):
        policy.propose(policy.initial(task), 1, 0)


def make_response_policy(settings, monkeypatch, response, *, post=None, decode=None):
    settings.model_url = "https://model.example.test/v1/chat/completions"
    settings.model_name = "fixture"
    settings.model_api_key = SecretStr("private-fixture-key")
    settings.model_input_price = 2
    settings.model_output_price = 8
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            assert calls and calls[0][0] == "reserve"
            calls.append(("dispatch", None))
            if post:
                post()
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=decode if decode else lambda: response,
            )

    monkeypatch.setattr("agent_rewind.policy.httpx.Client", Client)
    policy = ChatPolicy(settings, lambda value: calls.append(("reserve", value)))
    return policy, calls


@pytest.mark.parametrize(
    "response,code",
    [
        pytest.param(None, "invalid_response", id="null-response"),
        pytest.param([], "invalid_response", id="list-response"),
        pytest.param("private-response", "invalid_response", id="text-response"),
        pytest.param({}, "invalid_usage", id="missing-usage"),
        pytest.param({"usage": None}, "invalid_usage", id="null-usage"),
        pytest.param({"usage": []}, "invalid_usage", id="list-usage"),
        pytest.param({"usage": {"completion_tokens": 0}}, "invalid_usage", id="missing-input"),
        pytest.param({"usage": {"prompt_tokens": 0}}, "invalid_usage", id="missing-output"),
        pytest.param(
            {"usage": {"prompt_tokens": False, "completion_tokens": 0}},
            "invalid_usage",
            id="bool-input",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": True}},
            "invalid_usage",
            id="bool-output",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": -1, "completion_tokens": 0}},
            "invalid_usage",
            id="negative-input",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": -1}},
            "invalid_usage",
            id="negative-output",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0.5, "completion_tokens": 0}},
            "invalid_usage",
            id="fractional-input",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0.5}},
            "invalid_usage",
            id="fractional-output",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": "0", "completion_tokens": 0}},
            "invalid_usage",
            id="text-input",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": None}},
            "invalid_usage",
            id="null-output",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": False}},
            "invalid_usage",
            id="bool-total",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0.0}},
            "invalid_usage",
            id="fractional-total",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": None}},
            "invalid_usage",
            id="null-total",
        ),
        pytest.param(
            {"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 4}},
            "invalid_usage",
            id="inconsistent-total",
        ),
    ],
)
def test_unknown_usage_never_becomes_zero_or_a_returned_action(
    settings, task, monkeypatch, response, code
):
    policy, calls = make_response_policy(settings, monkeypatch, response)
    with pytest.raises(ModelCallFailure) as caught:
        policy.propose(policy.initial(task), 1, 0)
    error = caught.value
    assert error.code == code
    assert error.usage is None and error.reported_micro_usd is None
    assert calls == [("reserve", error.reserved_micro_usd), ("dispatch", None)]
    assert error.reserved_micro_usd > 0
    assert "private-response" not in str(error.evidence())


@pytest.mark.parametrize(
    "usage,cost",
    [
        pytest.param(
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, 0, id="all-zero"
        ),
        pytest.param({"prompt_tokens": 0, "completion_tokens": 2}, 16, id="zero-input"),
        pytest.param({"prompt_tokens": 3, "completion_tokens": 0}, 6, id="zero-output"),
        pytest.param(
            {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
                "provider_metadata": {"unknown_future_field": "retained"},
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
            22,
            id="unrelated-metadata-no-double-charge",
        ),
    ],
)
def test_complete_usage_preserves_zero_and_unrelated_metadata(
    settings, task, monkeypatch, usage, cost
):
    response = {"choices": [{"message": {"content": '{"tool":"finish"}'}}], "usage": usage}
    policy, calls = make_response_policy(settings, monkeypatch, response)
    action, record = policy.propose(policy.initial(task), 1, 0)
    assert action.tool == "finish"
    assert record["reported_micro_usd"] == cost
    assert record["response"] is response
    assert calls == [("reserve", record["reserved_micro_usd"]), ("dispatch", None)]


@pytest.mark.parametrize(
    "choices",
    [
        pytest.param(None, id="null"),
        pytest.param([], id="empty"),
        pytest.param([{}], id="missing-message"),
        pytest.param([{"message": {}}], id="missing-content"),
        pytest.param([{"message": {"content": None}}], id="null-content"),
        pytest.param([{"message": {"content": "private-not-json"}}], id="malformed-json"),
        pytest.param(
            [{"message": {"content": '{"tool":"private-invalid-tool"}'}}], id="bad-action"
        ),
    ],
)
def test_invalid_action_stops_with_known_usage(settings, task, monkeypatch, choices):
    response = {
        "choices": choices,
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }
    policy, calls = make_response_policy(settings, monkeypatch, response)
    with pytest.raises(ModelCallFailure) as caught:
        policy.propose(policy.initial(task), 1, 0)
    error = caught.value
    assert error.code == "invalid_action"
    assert error.usage == response["usage"] and error.reported_micro_usd == 100
    assert calls == [("reserve", error.reserved_micro_usd), ("dispatch", None)]
    assert error.__cause__ is None and error.__suppress_context__
    assert "private-" not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("variant", ["overflow", "nonfinite", "over-quote"])
def test_invalid_post_dispatch_cost_retains_hold(settings, task, monkeypatch, variant):
    count = 10**400 if variant == "overflow" else 10**308 if variant == "nonfinite" else 10**8
    response = {
        "choices": [{"message": {"content": '{"tool":"finish"}'}}],
        "usage": {"prompt_tokens": count, "completion_tokens": 1},
    }
    policy, calls = make_response_policy(settings, monkeypatch, response)
    with pytest.raises(ModelCallFailure) as caught:
        policy.propose(policy.initial(task), 1, 0)
    error = caught.value
    assert error.code == (
        "usage_exceeds_reservation" if variant == "over-quote" else "invalid_usage_cost"
    )
    assert error.usage == response["usage"]
    assert (error.reported_micro_usd is None) == (variant != "over-quote")
    assert calls == [("reserve", error.reserved_micro_usd), ("dispatch", None)]


@pytest.mark.parametrize("stage", ["post", "decode", "deep-json"])
def test_ambiguous_response_is_terminal_and_secret_safe(settings, task, monkeypatch, stage):
    def failed():
        if stage == "post":
            raise httpx.ReadTimeout("private-provider-payload")
        if stage == "deep-json":
            return json.loads("[" * 10000 + "0" + "]" * 10000)
        raise ValueError("private-provider-payload")

    policy, calls = make_response_policy(
        settings, monkeypatch, {}, **{"post" if stage == "post" else "decode": failed}
    )
    with pytest.raises(ModelCallFailure) as caught:
        policy.propose(policy.initial(task), 1, 0)
    error = caught.value
    assert error.code == "response_unavailable"
    assert error.reported_micro_usd is None and error.usage is None
    assert len(calls) == 2 and calls[0][0] == "reserve"
    assert error.__cause__ is None and error.__suppress_context__
    assert "private-provider-payload" not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("model_input_price", float("nan"), id="input-nan"),
        pytest.param("model_output_price", float("inf"), id="output-inf"),
        pytest.param("model_input_price", float("-inf"), id="input-negative-inf"),
        pytest.param("model_output_price", 0, id="output-zero"),
        pytest.param("model_input_price", -1, id="input-negative"),
    ],
)
def test_price_mutation_refuses_before_reservation(settings, task, monkeypatch, field, value):
    policy, calls = make_response_policy(settings, monkeypatch, {})
    setattr(settings, field, value)
    with pytest.raises(ValueError, match="positive finite"):
        policy.propose(policy.initial(task), 1, 0)
    assert calls == []
    with pytest.raises(ValueError, match="positive finite"):
        ChatPolicy(settings, lambda value: pytest.fail("must not reserve"))


def test_price_snapshot_is_used_after_dispatch(settings, task, monkeypatch):
    def changed():
        settings.model_input_price = float("nan")
        settings.model_output_price = 1000000

    response = {
        "choices": [{"message": {"content": '{"tool":"finish"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }
    policy, calls = make_response_policy(settings, monkeypatch, response, post=changed)
    _, record = policy.propose(policy.initial(task), 1, 0)
    assert record["reported_micro_usd"] == 100
    assert record["reserved_micro_usd"] == calls[0][1]
