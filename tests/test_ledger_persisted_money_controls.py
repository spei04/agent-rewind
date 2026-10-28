"""Database-free controls for the persisted-money witnesses and direct reader path."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ledger_persisted_money import (
    assert_financial_refusal,
    assert_money_delta,
    observe_financial,
    reader_identity,
)
from ledger_provisioning_fixture import SOURCE_FIELDS
from sqlalchemy.engine import Connection
from sqlalchemy.engine.cursor import CursorFetchStrategy

from agent_rewind.migrations import ledger_inspection
from agent_rewind.migrations.schema import ADMISSION, MigrationRefused


class SyntheticConnection:
    def __init__(self, dialect):
        self.dialect = SimpleNamespace(name=dialect, server_version_info=(16,))
        self.engine = SimpleNamespace(dialect=self.dialect)

    def execute(self, statement, *args, **kwargs):
        return Connection.execute(self, statement, *args, **kwargs)

    def exec_driver_sql(self, statement):
        assert statement == "SELECT 1 FROM sqlite_temp_master LIMIT 1"
        return SimpleNamespace(first=lambda: None)


def run_original_reader(monkeypatch, dialect, *, gate=None, interruption=None):
    """Replace only prerequisite/SQL boundaries; run the original complete reader."""
    connection = SyntheticConnection(dialect)
    raw = object()
    work = SimpleNamespace(_connection=connection, _raw=raw, check=lambda: None)
    watch = SimpleNamespace(
        engine=connection.engine,
        work=work,
        works=[work],
        trace=SimpleNamespace(raws=[raw], handles=[raw]),
    )
    gate = {"candidate_rows": 3, "invalid_rows": 1, "native_bytes": 160} if gate is None else gate

    class Result:
        def __init__(self, statement):
            self.context = SimpleNamespace(statement=str(statement))

        def mappings(self):
            return CursorFetchStrategy.fetchall(None, self, None)

    def execute(_connection, statement, *args, **kwargs):
        assert _connection is connection
        if interruption is not None:
            raise interruption
        return Result(statement)

    monkeypatch.setattr(Connection, "execute", execute)
    monkeypatch.setattr(CursorFetchStrategy, "fetchall", lambda *args: [deepcopy(gate)])
    monkeypatch.setattr(ledger_inspection, "_require_ledger_body", lambda actual: work)
    monkeypatch.setattr(ledger_inspection, "schema_table_names", lambda actual: None)
    monkeypatch.setattr(ledger_inspection, "read_revision", lambda actual: ADMISSION)
    for name in ("inspect_catalog", "read_history", "source_bounds"):
        monkeypatch.setattr(ledger_inspection, name, lambda *args: None)
    recorded = []
    with (
        observe_financial(watch, monkeypatch, lambda *item: recorded.append(item)) as receipt,
        pytest.raises(BaseException) as caught,
    ):
        ledger_inspection.inspect_ledger_state(connection)
    assert recorded == [("financial_reader", receipt)]
    assert connection not in ledger_inspection._ACTIVE
    return receipt, caught.value, reader_identity(watch, connection, work)


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_original_complete_reader_attributes_invalid_money(monkeypatch, dialect):
    receipt, error, identity = run_original_reader(monkeypatch, dialect)
    assert_financial_refusal(receipt, error, identity)
    query = receipt["queries"][0]["rows"][0]
    frame = receipt["readers"][0]["frames"][0]["receipt"]
    assert query == frame and query is not frame
    assert receipt["fetches"] == [
        {"name": "financial_base_job_gate", "method": "fetchall", "rows": 1}
    ]


@pytest.mark.parametrize(
    "change",
    [
        "query-bool",
        "frame-bool",
        "frame-float",
        "fetch-bool",
        "fetch-float",
        "fetch-negative",
        "fetch-body",
        "statement-body",
        "query-body",
        "wrong-call",
        "wrong-raise",
        "wrong-caller",
        "wrong-raw",
        "wrong-error",
    ],
)
def test_refusal_witness_rejects_independent_corruption(monkeypatch, change):
    original, error, identity = run_original_reader(monkeypatch, "postgresql")
    original_error = error
    receipt = deepcopy(original)
    reader = receipt["readers"][0]
    if change == "query-bool":
        receipt["queries"][0]["rows"][0]["invalid_rows"] = True
    elif change in {"frame-bool", "frame-float"}:
        reader["frames"][0]["receipt"]["invalid_rows"] = True if change == "frame-bool" else 1.0
    elif change in {"fetch-bool", "fetch-float", "fetch-negative"}:
        receipt["fetches"][0]["rows"] = {
            "fetch-bool": True,
            "fetch-float": 1.0,
            "fetch-negative": -1,
        }[change]
    elif change == "fetch-body":
        receipt["fetches"].append(
            {"name": "financial_base_job_body", "method": "fetchall", "rows": 0}
        )
    elif change == "statement-body":
        receipt["statements"].append({"name": "financial_base_job_body", **identity})
    elif change == "query-body":
        receipt["queries"].append(
            {"revision": "ar6", "name": "financial_base_job_body", "rows": []}
        )
    elif change == "wrong-call":
        reader["frames"][0]["line"] = 236
    elif change == "wrong-raise":
        reader["frames"][1]["line"] = 207
    elif change == "wrong-caller":
        reader["original_inspector_caller"] = False
    elif change == "wrong-raw":
        reader["raw_id"] += 1
    else:
        error = MigrationRefused("ledger_history_unsupported")
    with pytest.raises((AssertionError, ValueError)):
        assert_financial_refusal(receipt, error, identity)
    assert_financial_refusal(original, original_error, identity)


@pytest.mark.parametrize(
    "gate",
    [
        {"candidate_rows": 3, "invalid_rows": True, "native_bytes": 160},
        {"candidate_rows": 65537, "invalid_rows": 1, "native_bytes": 160},
    ],
)
def test_earlier_original_refusal_does_not_credit_target_guard(monkeypatch, gate):
    receipt, error, identity = run_original_reader(monkeypatch, "sqlite", gate=gate)
    with pytest.raises(AssertionError):
        assert_financial_refusal(receipt, error, identity)


def test_original_query_interrupt_is_preserved_without_refusal_credit(monkeypatch):
    interrupt = KeyboardInterrupt("synthetic query boundary")
    receipt, error, identity = run_original_reader(
        monkeypatch, "postgresql", interruption=interrupt
    )
    assert error is interrupt and receipt["readers"][0]["error"]["identity"] == id(interrupt)
    assert receipt["readers"][0]["frames"] == [
        {
            "kind": "gate",
            "line": 231,
            "domain": "job",
            "prefix": "financial_base_job",
            "receipt": None,
        }
    ]
    with pytest.raises(AssertionError):
        assert_financial_refusal(receipt, error, identity)


def money_states(dialect):
    fields = (*SOURCE_FIELDS["jobs"], "payload_version")
    job = {field: None for field in fields}
    job.update(id="target", reserved=35000, payload_version=1)
    before = {
        "catalog": ("unchanged catalog",),
        "authority": {"owner": "operator"},
        "tables": {
            "jobs": {"columns": fields, "rows": (tuple(job[field] for field in fields),)},
            "other": {"columns": ("id",), "rows": (("preserved",),)},
        },
    }
    source = {
        "jobs": [tuple(job[field] for field in SOURCE_FIELDS["jobs"])],
        "audit": [("preserved",)],
    }
    value = 0.25 if dialect == "sqlite" else -1
    altered = deepcopy(before)
    row = list(altered["tables"]["jobs"]["rows"][0])
    row[fields.index("reserved")] = value
    altered["tables"]["jobs"]["rows"] = (tuple(row),)
    projected = deepcopy(source)
    projected["jobs"] = [
        tuple(value if field == "reserved" else job[field] for field in SOURCE_FIELDS["jobs"])
    ]
    native = {"value": value, "storage": "real" if dialect == "sqlite" else "bigint"}
    return before, altered, source, projected, "target", dialect, native


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_exact_typed_money_cell_and_source_delta(dialect):
    assert_money_delta(*money_states(dialect))


@pytest.mark.parametrize(
    "change",
    [
        "catalog",
        "authority",
        "other-table",
        "source",
        "native-type",
        "storage",
        "cell-type",
    ],
)
def test_money_delta_rejects_collateral_changes_and_type_aliases(change):
    args = list(money_states("postgresql"))
    if change in {"catalog", "authority"}:
        args[1][change] = ("altered",)
    elif change == "other-table":
        args[1]["tables"]["other"]["rows"] = (("altered",),)
    elif change == "source":
        args[3]["audit"] = [("altered",)]
    elif change == "native-type":
        args[6]["value"] = -1.0
    elif change == "storage":
        args[6]["storage"] = "numeric"
    else:
        table = args[1]["tables"]["jobs"]
        row = list(table["rows"][0])
        row[table["columns"].index("reserved")] = -1.0
        table["rows"] = (tuple(row),)
    with pytest.raises(AssertionError):
        assert_money_delta(*args)
