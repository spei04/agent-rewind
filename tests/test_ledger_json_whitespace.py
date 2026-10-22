"""Raw cursor limits and strict JSON tokens survive outer-whitespace trimming."""

import json

import pytest

from agent_rewind.migrations.ledger_inputs import decode_ledger_json


@pytest.mark.parametrize("maximum", [32768, 65536])
@pytest.mark.parametrize("extra", [0, 1])
def test_raw_size_bound_precedes_trimming(maximum, extra):
    body = b'{"value":1}'
    raw = b" \t\r\n" + body + b" " * (maximum + extra - len(body) - 4)
    assert len(raw) == maximum + extra
    if extra:
        with pytest.raises(ValueError, match="size or BOM"):
            decode_ledger_json(raw, maximum=maximum)
    else:
        assert decode_ledger_json(raw, maximum=maximum) == {"value": 1}


@pytest.mark.parametrize("side", ["before", "after"])
@pytest.mark.parametrize(
    "token",
    [
        b"\v",
        b"\f",
        b"\x1c",
        b"\x00",
        "\u00a0".encode(),
        "\u2003".encode(),
        "\u2028".encode(),
        b"\xef\xbb\xbf",
    ],
)
def test_non_json_outer_whitespace_is_never_discarded(token, side):
    body = b'{"value":1}'
    raw = b" \t\r\n" + (token + body if side == "before" else body + token) + b" \t\r\n"
    with pytest.raises(ValueError):
        decode_ledger_json(raw, maximum=65536)


@pytest.mark.parametrize("prefix", [b"", b" \t\r\n"])
def test_bom_and_invalid_utf8_still_refuse(prefix):
    for raw in [prefix + b"\xef\xbb\xbf{}", prefix + b"\xff{}"]:
        with pytest.raises(ValueError):
            decode_ledger_json(raw, maximum=65536)


def test_outer_trim_preserves_quoted_spaces_escapes_and_internal_layout():
    value = {"text": ' spaces " quoted \\ tail [ { ', "items": [1, 2]}
    wire = b" \t\r\n" + json.dumps(value, indent=2).encode() + b"\r\n\t "
    assert decode_ledger_json(wire, maximum=65536) == value


@pytest.mark.parametrize(
    "body",
    [
        b'{"a":1,"a":1}',
        b'{"a":1,"\\u0061":1}',
        b'{"a":1.0}',
        b'{"a":-0}',
        b'{"a":1e0}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":"\\u0000"}',
        b'{"a":"\\ud800"}',
        b'{"a":"unescaped\nline"}',
        b'{"a":"unterminated}',
        b"[" * 9 + b"0" + b"]" * 9,
        b"{}{}",
    ],
)
def test_padded_invalid_json_does_not_gain_acceptance(body):
    with pytest.raises(ValueError):
        decode_ledger_json(b" \t\r\n" + body + b"\r\n\t ", maximum=65536)


def test_exact_depth_boundary_is_unchanged_by_outer_padding():
    raw = b"\n\t" + b"[" * 8 + b"0" + b"]" * 8 + b"\r "
    assert decode_ledger_json(raw, maximum=65536) == [[[[[[[[0]]]]]]]]


def test_all_legal_whitespace_without_a_value_is_still_invalid():
    with pytest.raises(ValueError):
        decode_ledger_json(b" \t\r\n" * 16384, maximum=65536)
