"""Exact Unicode character rejection without changing strict JSON semantics."""

import json
import unicodedata

import pytest

from agent_rewind.migrations.ledger_inputs import decode_ledger_json, validate_json_value


def test_every_unicode_character_retains_category_rejection():
    for point in range(0x110000):
        character = chr(point)
        forbidden = unicodedata.category(character) in {"Cc", "Cs"}
        try:
            validate_json_value(character)
        except ValueError as error:
            assert forbidden, f"Unexpected rejection of U+{point:04X}"
            assert str(error) == "control or surrogate"
        else:
            assert not forbidden, f"Accepted forbidden U+{point:04X}"


@pytest.mark.parametrize("point", [0x00, 0x1F, 0x7F, 0x9F, 0xD800, 0xDFFF])
@pytest.mark.parametrize("position", ["{}suffix", "prefix{}", "prefix{}suffix"])
@pytest.mark.parametrize("member", ["key", "value"])
def test_controls_and_surrogates_refuse_in_any_string_position(point, position, member):
    value = position.format(chr(point))
    document = {value: 1} if member == "key" else {"safe": value}
    with pytest.raises(ValueError, match="control or surrogate"):
        validate_json_value(document)
    # Escaped JSON must not hide a forbidden key or value from the same validator.
    raw = json.dumps(document, ensure_ascii=True).encode()
    with pytest.raises(ValueError, match="control or surrogate"):
        decode_ledger_json(raw, maximum=65536)


@pytest.mark.parametrize(
    "point",
    [0x20, 0x7E, 0xA0, 0xD7FF, 0xE000, 0x378, 0x200D, 0x2028, 0xFEFF, 0x1F600, 0x10FFFF],
)
@pytest.mark.parametrize("member", ["key", "value"])
def test_neighboring_and_other_unicode_categories_remain_accepted(point, member):
    value = "prefix" + chr(point) + "suffix"
    document = {value: 1} if member == "key" else {"safe": value}
    validate_json_value(document)
    assert decode_ledger_json(json.dumps(document).encode(), maximum=65536) == document


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 2**63, ""])
def test_native_scalar_types_are_preserved(value):
    document = {"safe": [value]}
    validate_json_value(document)
    decoded = decode_ledger_json(json.dumps(document).encode(), maximum=65536)
    assert decoded == document
    assert type(decoded["safe"][0]) is type(value)


@pytest.mark.parametrize("value", [1.0, (), b"safe", {1: "safe"}])
def test_non_json_native_values_still_refuse(value):
    with pytest.raises(ValueError):
        validate_json_value(value)


def test_depth_boundary_is_unchanged_for_native_values_and_json():
    allowed = 0
    for _ in range(8):
        allowed = [allowed]
    validate_json_value(allowed)
    assert decode_ledger_json(json.dumps(allowed).encode(), maximum=65536) == allowed
    with pytest.raises(ValueError, match="nested value exceeds limit"):
        validate_json_value([allowed])
    with pytest.raises(ValueError, match="nested token limit"):
        decode_ledger_json(json.dumps([allowed]).encode(), maximum=65536)
