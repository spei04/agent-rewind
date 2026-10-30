"""Factory policy checks without opening any PostgreSQL connection."""

import gc
import sqlite3
import weakref

import psycopg
import pytest
from ledger_operator_fixture import assert_pool_released, ledger_case
from sqlalchemy import event
from sqlalchemy.engine import Engine

from agent_rewind.migrations import ledger_engine
from agent_rewind.migrations.ledger_engine import create_ledger_engine
from agent_rewind.migrations.ledger_transaction import LedgerOutcome, ledger_transaction
from agent_rewind.migrations.ledger_work import LedgerWork
from agent_rewind.migrations.schema import MigrationRefused

__all__ = ["ledger_case"]


@pytest.fixture
def no_native_connect(monkeypatch):
    calls = []

    def reject(*args, **kwargs):
        calls.append(True)
        pytest.fail("factory policy reached a native connection")

    monkeypatch.setattr(sqlite3, "connect", reject)
    monkeypatch.setattr(psycopg, "connect", reject)
    yield calls
    assert calls == []


@pytest.fixture
def explicit_pg_environment(monkeypatch):
    # Remove ambient routing by name without reading or exposing its values.
    for name in (
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGTARGETSESSIONATTRS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///file:memory?mode=memory",
        "sqlite:///unused.sqlite?plugin=unreviewed",
        "sqlite+aiosqlite:///unused.sqlite",
    ],
)
def test_unsupported_sqlite_forms_refuse_without_native_acquisition(no_native_connect, url):
    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        create_ledger_engine(url)


def test_factory_is_lazy_and_warm_reuse_has_no_prepayment_discount(ledger_case):
    case = ledger_case
    assert case.trace.raws == []
    for expected_rows in (1, 1):
        work, outcome = LedgerWork(), LedgerOutcome()
        with ledger_transaction(case.engine, outcome, work=work) as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == expected_rows
        assert (work.prepaid_bootstrap, work.prepaid_cleanup) == (12, 8)
        assert outcome.commit_acknowledged
        assert_pool_released(case)
    assert len(case.trace.raws) == 1


@pytest.mark.parametrize("scope", ["class", "instance"])
def test_extra_callbacks_are_refused_before_they_run(ledger_case, scope):
    case = ledger_case
    calls = []

    def callback(*args):
        calls.append(True)

    target = Engine if scope == "class" else case.engine
    event.listen(target, "before_cursor_execute", callback)
    try:
        with (
            pytest.raises(MigrationRefused, match="^schema_incompatible$"),
            ledger_transaction(case.engine, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("unreviewed callback was accepted")
        assert calls == [] and case.trace.raws == []
    finally:
        event.remove(target, "before_cursor_execute", callback)


@pytest.mark.parametrize("mutation", ["pre_ping", "execution_options", "dialect"])
def test_changed_engine_configuration_refuses_before_checkout(ledger_case, monkeypatch, mutation):
    case = ledger_case
    if mutation == "pre_ping":
        monkeypatch.setattr(case.engine.pool, "_pre_ping", True)
    elif mutation == "execution_options":
        monkeypatch.setattr(case.engine, "_execution_options", {"stream_results": True})
    else:
        monkeypatch.setattr(case.engine, "dialect", type(case.engine.dialect)())
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, LedgerOutcome(), work=LedgerWork()),
    ):
        pytest.fail("altered factory engine was accepted")
    assert case.trace.raws == []


def test_dependency_identity_is_revalidated_before_checkout(ledger_case, monkeypatch):
    case = ledger_case
    original = ledger_engine.version
    monkeypatch.setattr(
        ledger_engine, "version", lambda name: "0.0.0" if name == "sqlalchemy" else original(name)
    )
    with (
        pytest.raises(MigrationRefused, match="^schema_incompatible$"),
        ledger_transaction(case.engine, LedgerOutcome(), work=LedgerWork()),
    ):
        pytest.fail("dependency mismatch entered")
    assert case.trace.raws == []


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://127.0.0.1/example",
        "postgresql+psycopg:///example?host=/tmp",
        "postgresql+psycopg://db.example/example?hostaddr=127.0.0.1&sslmode=verify-full",
        "postgresql+psycopg://127.0.0.1/example?target_session_attrs=any",
    ],
)
def test_explicit_single_endpoint_construction_is_lazy(
    no_native_connect, explicit_pg_environment, url
):
    engine = create_ledger_engine(url)
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "suffix,code",
    [
        ("db.example/example", "numeric_runtime_endpoint_required"),
        ("127.0.0.1/example?host=127.0.0.1,127.0.0.2", "unsupported_runtime_endpoint"),
        ("127.0.0.1/example?target_session_attrs=prefer-standby", "unsupported_runtime_endpoint"),
        ("127.0.0.1/example?port=0", "unsupported_runtime_endpoint"),
    ],
)
def test_unsupported_endpoint_policy_cannot_reach_native_connect(
    no_native_connect, explicit_pg_environment, suffix, code
):
    with pytest.raises(MigrationRefused, match=f"^{code}$"):
        create_ledger_engine("postgresql+psycopg://" + suffix)


@pytest.mark.parametrize(
    "name,value,code",
    [
        ("PGSERVICE", "unreviewed", "explicit_runtime_endpoint_required"),
        ("PGSERVICEFILE", "/unreviewed/service.conf", "explicit_runtime_endpoint_required"),
        ("PGTARGETSESSIONATTRS", "prefer-standby", "unsupported_runtime_endpoint"),
    ],
)
def test_inherited_routing_is_checked_without_disclosing_values(
    no_native_connect, explicit_pg_environment, monkeypatch, name, value, code
):
    monkeypatch.setenv(name, value)
    with pytest.raises(MigrationRefused, match=f"^{code}$") as caught:
        create_ledger_engine("postgresql+psycopg://127.0.0.1/example")
    assert value not in str(caught.value)


@pytest.mark.parametrize(
    "query",
    [
        "plugin=unreviewed",
        "context=unreviewed",
        "cursor_factory=unreviewed",
        "host=127.0.0.1&host=127.0.0.2",
        "prepare_threshold=0",
    ],
)
def test_unreviewed_constructor_parameters_fail_before_sqlalchemy_dispatch(
    no_native_connect, explicit_pg_environment, monkeypatch, query
):
    calls = []

    def constructor(*args, **kwargs):
        calls.append(True)
        pytest.fail("unsupported input reached SQLAlchemy construction")

    monkeypatch.setattr(ledger_engine, "create_engine", constructor)
    with pytest.raises(MigrationRefused, match="^unsupported_runtime_endpoint$"):
        create_ledger_engine("postgresql+psycopg://127.0.0.1/example?" + query)
    assert calls == []


@pytest.mark.parametrize("kind", ["sqlite", "postgresql"])
def test_disposed_factory_engine_and_witnesses_are_collectable(
    tmp_path, no_native_connect, explicit_pg_environment, kind
):
    url = (
        f"sqlite:///{tmp_path / 'unused.sqlite'}"
        if kind == "sqlite"
        else "postgresql+psycopg://127.0.0.1/example"
    )

    def disposed_references():
        engine = create_ledger_engine(url)
        try:
            return weakref.ref(engine), weakref.ref(engine.pool), weakref.ref(engine.dialect)
        finally:
            engine.dispose()

    references = disposed_references()
    gc.collect()
    assert all(reference() is None for reference in references)
    assert not (tmp_path / "unused.sqlite").exists()


@pytest.mark.parametrize("kind", ["sqlite", "postgresql"])
def test_active_claim_keeps_engine_alive_until_explicit_release(
    tmp_path, no_native_connect, explicit_pg_environment, kind
):
    url = (
        f"sqlite:///{tmp_path / 'unused.sqlite'}"
        if kind == "sqlite"
        else "postgresql+psycopg://127.0.0.1/example"
    )

    def claimed_reference():
        engine = create_ledger_engine(url)
        work = LedgerWork()
        work._consume()
        return weakref.ref(engine), ledger_engine.claim_ledger_engine(engine, work)

    reference, claim = claimed_reference()
    try:
        gc.collect()
        assert reference() is claim.engine
        assert ledger_engine._REGISTRY[claim.engine].claim is claim
    finally:
        ledger_engine.release_ledger_engine(claim, clean=True)
        claim.engine.dispose()
    del claim
    gc.collect()
    assert reference() is None
    assert not (tmp_path / "unused.sqlite").exists()


def test_disposed_factory_pool_cannot_be_readmitted(tmp_path, no_native_connect):
    engine = create_ledger_engine(f"sqlite:///{tmp_path / 'unused.sqlite'}")
    try:
        engine.dispose()
        gc.collect()
        with (
            pytest.raises(MigrationRefused, match="^schema_incompatible$"),
            ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("replacement pool was admitted")
        assert not (tmp_path / "unused.sqlite").exists()
    finally:
        engine.dispose()


@pytest.mark.parametrize("mutation", ["removed", "replaced"])
def test_removed_or_replaced_factory_callback_refuses_before_connect(
    tmp_path, no_native_connect, mutation
):
    engine = create_ledger_engine(f"sqlite:///{tmp_path / 'unused.sqlite'}")
    calls = []

    def foreign(*args):
        calls.append(True)

    def mutate():
        original = tuple(engine.dialect.dispatch.do_connect)[0]
        assert original.__name__ == "do_connect"
        event.remove(engine, "do_connect", original)
        if mutation == "replaced":
            event.listen(engine, "do_connect", foreign, insert=True)

    try:
        mutate()
        gc.collect()
        with (
            pytest.raises(MigrationRefused, match="^schema_incompatible$"),
            ledger_transaction(engine, LedgerOutcome(), work=LedgerWork()),
        ):
            pytest.fail("changed callback witness was admitted")
        assert calls == []
        assert not (tmp_path / "unused.sqlite").exists()
    finally:
        if event.contains(engine, "do_connect", foreign):
            event.remove(engine, "do_connect", foreign)
        engine.dispose()
