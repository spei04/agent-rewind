"""Pure controls for the PostgreSQL progress oracle; no database is used."""

import pytest
from ledger_provisioning_postgres_fixture import canonical_cursor


def test_progress_cursor_accepts_jsonb_spacing_and_member_order():
    actual = '{ "nested": {"z": false, "a": [true, 17]}, "label": "receipt" }'
    expected = b'{"label":"receipt","nested":{"a":[true,17],"z":false}}'
    assert canonical_cursor(actual) == expected


@pytest.mark.parametrize(
    "raw",
    [
        '{"value":1,"value":2}',
        '{"nested":{"value":1,"value":1}}',
    ],
)
def test_progress_cursor_refuses_duplicate_members_at_every_depth(raw):
    with pytest.raises(ValueError, match="^duplicate progress cursor member$"):
        canonical_cursor(raw)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_progress_cursor_refuses_nonfinite_numbers(constant):
    with pytest.raises(ValueError, match="^nonfinite progress cursor number$"):
        canonical_cursor('{"nested":[' + constant + "]}")


def test_progress_cursor_keeps_nested_booleans_distinct_from_numeric_values():
    expected = canonical_cursor('{"nested":[true,false,{"amount":17}]}')
    for changed in [
        '{"nested":[1,false,{"amount":17}]}',
        '{"nested":[true,0,{"amount":17}]}',
        '{"nested":[true,false,{"amount":18}]}',
    ]:
        assert canonical_cursor(changed) != expected


def test_progress_cursor_refuses_a_non_object_root():
    with pytest.raises(ValueError, match="^progress cursor must be an object$"):
        canonical_cursor('[{"value":1}]')
