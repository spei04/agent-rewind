"""Pure refusal and opaque-token boundaries; no fabricated registration path."""

import pytest

from agent_rewind.failure_evidence import FailureRefusal, _AcknowledgedClaim


@pytest.mark.parametrize("value", ["private secret canary", True, None, [], object()])
def test_unknown_failure_reason_never_becomes_an_error_payload(value):
    with pytest.raises(ValueError, match="^invalid_refusal_reason$"):
        FailureRefusal(value)


def test_acknowledged_claim_cannot_be_constructed_from_caller_values():
    with pytest.raises(FailureRefusal, match="^invalid_request$") as caught:
        _AcknowledgedClaim()
    assert caught.value.reason == "capability_not_issued"
    forged = object.__new__(_AcknowledgedClaim)
    with pytest.raises(AttributeError):
        forged.job_id = "a" * 32
