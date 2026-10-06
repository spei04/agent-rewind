from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from agent_rewind.policy import ChatPolicy


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
