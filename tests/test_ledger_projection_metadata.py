"""Contract controls for bounded native projection receipts and row validation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agent_rewind.migrations import ledger_compatibility as compatibility
from agent_rewind.migrations.schema import MigrationRefused

ACCOUNT_FIELDS = (
    "id",
    "organization_id",
    "scope",
    "scope_id",
    "project_id",
    "job_id",
    "period_start",
    "period_end",
    "limit_microusd",
    "opening_held_microusd",
)
JOB_FIELDS = ("job_id", "project_id", "organization_id", "legacy_reserved_microusd")
FAMILIES = ("immutable_accounts", "original_jobs")
FIELDS = [
    (family, field)
    for family, fields in zip(FAMILIES, (ACCOUNT_FIELDS, JOB_FIELDS), strict=True)
    for field in fields
]
MONEY_FIELDS = [
    ("immutable_accounts", "limit_microusd"),
    ("immutable_accounts", "opening_held_microusd"),
    ("original_jobs", "legacy_reserved_microusd"),
]
MAX_MONEY = 2**63 - 1
PARAMETERS = {"organization_id": "a" * 32}


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


class Checks:
    def __init__(self, stop=None, error=None):
        self.calls = 0
        self.stop = stop
        self.error = error if error is not None else RuntimeError("inspection expired")

    def check(self):
        self.calls += 1
        if self.calls == self.stop:
            raise self.error


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


def account(index):
    return {
        "id": f"{index:032x}",
        "organization_id": "a" * 32,
        "scope": "organization",
        "scope_id": "a" * 32,
        "project_id": None,
        "job_id": None,
        "period_start": "2030-01-01T00:00:00.000000Z",
        "period_end": "2030-01-02T00:00:00.000000Z",
        "limit_microusd": MAX_MONEY,
        "opening_held_microusd": 0,
    }


def job(index):
    return {
        "job_id": f"{index:032x}",
        "project_id": "b" * 32,
        "organization_id": "a" * 32,
        "legacy_reserved_microusd": 1,
    }


class Projection:
    """An in-memory execute boundary; the actual query and reader functions run."""

    def __init__(self, family, count=2):
        self.family = family
        self.dialect = SimpleNamespace(name="sqlite")
        factory = account if family == "immutable_accounts" else job
        self.rows = [factory(index) for index in range(count)]
        self.queries = []
        self.refresh_gate()

    def refresh_gate(self):
        size = sum(
            0 if value is None else len(str(value).encode("utf-8"))
            for row in self.rows
            for value in row.values()
        )
        self.gate = {
            "candidate_rows": len(self.rows),
            "invalid_rows": 0,
            "native_bytes": size,
            "utf8_bytes": size,
        }
        self.gates = [self.gate]

    def execute(self, statement, parameters):
        statements = {
            compatibility.SQL["sqlite_" + self.family + "_" + phase]: phase
            for phase in ("gate", "body")
        }
        phase = statements[str(statement)]
        self.queries.append((phase, deepcopy(parameters)))
        return Result(self.gates if phase == "gate" else self.rows)


@pytest.fixture
def read_projection():
    return compatibility._read


def read(reader, projection, checks=None, expected=None):
    return reader(
        projection,
        projection.family,
        PARAMETERS,
        checks if checks is not None else Checks(),
        expected_count=len(projection.rows) if expected is None else expected,
    )


def assert_queries(projection, phases):
    expected = [("gate", PARAMETERS)]
    if "body" in phases:
        expected.append(
            (
                "body",
                {
                    **PARAMETERS,
                    "expected_rows": projection.gate["candidate_rows"],
                    "expected_native_bytes": projection.gate["native_bytes"],
                    "expected_utf8_bytes": projection.gate["utf8_bytes"],
                },
            )
        )
    assert projection.queries == expected[: len(phases)]


@pytest.mark.parametrize(
    ("family", "count"),
    [("immutable_accounts", n) for n in (0, 1, 4096)] + [("original_jobs", n) for n in (0, 1, 12)],
)
def test_projection_preserves_rows_queries_and_check_positions(read_projection, family, count):
    projection = Projection(family, count)
    before = deepcopy(projection.rows)
    checks = Checks()
    assert read(read_projection, projection, checks) == before
    assert projection.rows == before
    assert checks.calls == (3 if count == 0 else 6 + count * 2)
    assert_queries(projection, ["gate"] if count == 0 else ["gate", "body"])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize(
    "shape",
    [
        "absent",
        "duplicate",
        "extra",
        "candidate_rows",
        "invalid_rows",
        "native_bytes",
        "utf8_bytes",
    ],
)
def test_invalid_gate_shape_never_fetches_body(read_projection, family, shape):
    projection = Projection(family)
    if shape == "absent":
        projection.gates = []
    elif shape == "duplicate":
        projection.gates.append(dict(projection.gate))
    elif shape == "extra":
        projection.gate["extra"] = 0
    else:
        del projection.gate[shape]
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        read(read_projection, projection)
    assert_queries(projection, ["gate"])


@pytest.mark.parametrize("field", ["candidate_rows", "invalid_rows", "native_bytes", "utf8_bytes"])
@pytest.mark.parametrize("value", [True, IntegerSubclass(1), -1, "1", 1.5, None])
def test_gate_counters_require_exact_nonnegative_integers(read_projection, field, value):
    projection = Projection("immutable_accounts")
    projection.gate[field] = value
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        read(read_projection, projection)
    assert_queries(projection, ["gate"])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize(
    "kind", ["count", "invalid", "native", "utf8", "empty-native", "empty-utf8"]
)
def test_gate_count_and_byte_bounds_refuse_before_body(read_projection, family, kind):
    projection = Projection(family, 0 if kind.startswith("empty") else 2)
    expected = len(projection.rows)
    if kind == "count":
        expected = 4097 if family == "immutable_accounts" else 13
        projection.gate["candidate_rows"] = expected
    elif kind == "invalid":
        projection.gate["invalid_rows"] = 1
    elif kind == "native":
        projection.gate["native_bytes"] = (255 if family == "immutable_accounts" else 115) * 2 + 1
    elif kind == "utf8":
        projection.gate["utf8_bytes"] = 4 * projection.gate["native_bytes"] + 1
    elif kind == "empty-native":
        projection.gate["native_bytes"] = 1
    else:
        projection.gate["utf8_bytes"] = 1
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        read(read_projection, projection, expected=expected)
    assert_queries(projection, ["gate"])


@pytest.mark.parametrize(("family", "field"), FIELDS)
@pytest.mark.parametrize(
    "value", [True, 1.5, b"x", [], {}, StringSubclass("x"), IntegerSubclass(1)]
)
def test_every_native_field_rejects_wrong_types_and_subclasses(
    read_projection, family, field, value
):
    projection = Projection(family)
    projection.rows[0][field] = value
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        read(read_projection, projection)
    assert_queries(projection, ["gate", "body"])


@pytest.mark.parametrize(("family", "field"), FIELDS)
def test_only_nullable_account_ids_accept_none(read_projection, family, field):
    projection = Projection(family)
    projection.rows[0][field] = None
    projection.refresh_gate()
    if family == "immutable_accounts" and field in ("project_id", "job_id"):
        assert read(read_projection, projection) == projection.rows
    else:
        with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
            read(read_projection, projection)
    assert_queries(projection, ["gate", "body"])


@pytest.mark.parametrize(("family", "field"), [item for item in FIELDS if item not in MONEY_FIELDS])
def test_all_text_fields_refuse_non_ascii_body_values(read_projection, family, field):
    projection = Projection(family)
    projection.rows[0][field] = "é"
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        read(read_projection, projection)
    assert_queries(projection, ["gate", "body"])


@pytest.mark.parametrize(("family", "field"), MONEY_FIELDS)
@pytest.mark.parametrize("value", [-1, MAX_MONEY + 1, "1"])
def test_money_fields_keep_strict_bounds(read_projection, family, field, value):
    projection = Projection(family)
    projection.rows[0][field] = value
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        read(read_projection, projection)
    assert_queries(projection, ["gate", "body"])


@pytest.mark.parametrize(("family", "field"), MONEY_FIELDS)
@pytest.mark.parametrize("value", [0, MAX_MONEY])
def test_money_boundaries_preserve_exact_bytes(read_projection, family, field, value):
    projection = Projection(family)
    projection.rows[0][field] = value
    projection.refresh_gate()
    assert read(read_projection, projection) == projection.rows
    assert_queries(projection, ["gate", "body"])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize(
    "kind", ["missing", "extra", "fewer", "more", "byte-minus", "byte-plus", "expected-count"]
)
def test_body_shape_counts_and_utf8_receipts_are_checked(read_projection, family, kind):
    projection = Projection(family)
    expected = len(projection.rows)
    if kind == "missing":
        del projection.rows[0][next(iter(projection.rows[0]))]
    elif kind == "extra":
        projection.rows[0]["extra"] = "x"
    elif kind == "fewer":
        projection.rows.pop()
    elif kind == "more":
        projection.rows.append(dict(projection.rows[0]))
    elif kind == "byte-minus":
        projection.gate["utf8_bytes"] -= 1
    elif kind == "byte-plus":
        projection.gate["utf8_bytes"] += 1
    else:
        expected += 1
    with pytest.raises(MigrationRefused, match="ledger_progress_invalid"):
        read(read_projection, projection, expected=expected)
    assert_queries(projection, ["gate"] if kind == "expected-count" else ["gate", "body"])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("stop", range(1, 11))
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_each_query_and_row_interruption_preserves_original_exception(
    read_projection,
    family,
    stop,
    error_type,
):
    projection = Projection(family)
    before = deepcopy(projection.rows)
    error = error_type("inspection expired")
    checks = Checks(stop, error)
    with pytest.raises(error_type) as caught:
        read(read_projection, projection, checks)
    assert caught.value is error
    assert checks.calls == stop
    assert projection.rows == before
    phases = [] if stop == 1 else ["gate"] if stop <= 4 else ["gate", "body"]
    assert_queries(projection, phases)


def test_repeated_calls_recompute_family_metadata_without_cross_contamination(read_projection):
    for family in (*FAMILIES, *reversed(FAMILIES)):
        projection = Projection(family)
        assert read(read_projection, projection) == projection.rows
        assert_queries(projection, ["gate", "body"])
