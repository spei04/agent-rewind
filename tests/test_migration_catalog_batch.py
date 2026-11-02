"""Native catalog boundaries for fresh PostgreSQL reflection batches."""

import pytest
import test_migrations_postgres as migration_tests
from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.engine.reflection import Inspector, ObjectKind, ObjectScope
from sqlalchemy.exc import NoSuchTableError

from agent_rewind.migrations.schema import MigrationRefused, catalog

pg = migration_tests.pg
pytestmark = pytest.mark.skipif(
    not migration_tests.POSTGRES, reason="Opt-in synthetic PostgreSQL catalog reflection"
)
MULTI = (
    "get_multi_indexes",
    "get_multi_unique_constraints",
    "get_multi_pk_constraint",
    "get_multi_foreign_keys",
    "get_multi_check_constraints",
)


def observe_bulk(monkeypatch, events):
    for method in MULTI:
        original = getattr(Inspector, method)

        def observe(inspector, *args, _method=method, _original=original, **kwargs):
            events.append(
                (
                    _method,
                    kwargs["schema"],
                    tuple(kwargs["filter_names"]),
                    kwargs["kind"],
                    kwargs["scope"],
                )
            )
            return _original(inspector, *args, **kwargs)

        monkeypatch.setattr(Inspector, method, observe)


@pytest.mark.parametrize(
    ("wide_table", "width"),
    [("a_first", 32), ("a_first", 33), ("z_later", 33)],
    ids=["32-columns", "33-first", "33-later"],
)
def test_native_column_bound_precedes_every_bulk_family(pg, monkeypatch, wide_table, width):
    metadata = MetaData()
    for name in ("a_first", "z_later"):
        count = width if name == wide_table else 1
        Table(name, metadata, *(Column(f"c{number}", Integer) for number in range(count)))
    with pg["owner"].begin() as connection:
        metadata.create_all(connection)
        events = []
        original_columns = Inspector.get_columns

        def columns(inspector, table_name, **kwargs):
            assert inspector.bind is connection
            events.append(("columns", table_name, kwargs["schema"]))
            return original_columns(inspector, table_name, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Inspector, "get_columns", columns)
            observe_bulk(patch, events)
            if width == 33:
                with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
                    catalog(connection)
            else:
                shape = catalog(connection)
                assert len(shape["a_first"]["columns"]) == 32
                assert len(shape["z_later"]["columns"]) == 1
        names = ["a_first"] if width == 33 and wide_table == "a_first" else ["a_first", "z_later"]
        assert events[: len(names)] == [("columns", name, "public") for name in names]
        remaining = events[len(names) :]
        if width == 32:
            expected = [
                (method, "public", tuple(names), ObjectKind.TABLE, ObjectScope.DEFAULT)
                for method in MULTI
            ]
            assert sorted(remaining, key=lambda row: row[0]) == sorted(
                expected, key=lambda row: row[0]
            )
        else:
            assert remaining == []


def test_native_empty_catalog_never_uses_an_unfiltered_bulk_read(pg, monkeypatch):
    with pg["owner"].connect() as connection:
        events = []
        with monkeypatch.context() as patch:
            observe_bulk(patch, events)
            shape = catalog(connection)
        assert events == []
        assert shape == {"$postgres": {"columns": [], "constraints": [], "indexes": []}}
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            ).scalar_one()
            == 0
        )
        connection.rollback()


@pytest.mark.parametrize(
    ("method", "fault"),
    [(method, "missing") for method in MULTI]
    + [("get_multi_indexes", "extra"), ("get_multi_indexes", "wrong-schema")],
    ids=[
        "missing-indexes",
        "missing-unique",
        "missing-primary-key",
        "missing-foreign-keys",
        "missing-checks",
        "extra-key",
        "wrong-schema-key",
    ],
)
def test_returned_map_refusal_preserves_the_real_native_catalog(pg, monkeypatch, method, fault):
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql("CREATE TABLE probe (id INTEGER PRIMARY KEY, value INTEGER)")
        connection.exec_driver_sql("INSERT INTO probe VALUES (1, 2)")
    with pg["owner"].connect() as connection:
        before = catalog(connection)
        original = getattr(Inspector, method)
        observations = []

        def corrupt(inspector, *args, **kwargs):
            assert inspector.bind is connection
            rows = dict(original(inspector, *args, **kwargs))
            assert set(rows) == {("public", "probe")}
            observations.append((method, fault))
            # This is a returned-map boundary fault, not a native table disappearance.
            if fault == "missing":
                rows.pop(("public", "probe"))
            elif fault == "extra":
                rows[("public", "unexpected")] = rows["public", "probe"]
            else:
                rows[("foreign", "probe")] = rows.pop(("public", "probe"))
            return rows

        with monkeypatch.context() as patch:
            patch.setattr(Inspector, method, corrupt)
            if fault == "missing":
                with pytest.raises(NoSuchTableError, match=r"^public\.probe$") as refused:
                    catalog(connection)
                assert type(refused.value) is NoSuchTableError
                assert refused.value.__cause__ is None
                assert refused.value.__suppress_context__ is True
            else:
                with pytest.raises(MigrationRefused, match="^schema_incompatible$") as refused:
                    catalog(connection)
                assert type(refused.value) is MigrationRefused
        assert observations == [(method, fault)]
        assert catalog(connection) == before
        assert connection.exec_driver_sql("SELECT id, value FROM probe").all() == [(1, 2)]
        connection.rollback()


def test_native_table_disappearance_after_columns_keeps_missing_table_error(pg, monkeypatch):
    with pg["owner"].begin() as connection:
        connection.exec_driver_sql("CREATE TABLE probe (id INTEGER PRIMARY KEY, value INTEGER)")
        connection.exec_driver_sql("INSERT INTO probe VALUES (1, 2)")
    with pg["owner"].connect() as connection:
        before = catalog(connection)
        original_columns = Inspector.get_columns
        original_indexes = Inspector.get_multi_indexes
        columns_seen, native_drops = [], []

        def columns(inspector, table_name, **kwargs):
            assert inspector.bind is connection
            result = original_columns(inspector, table_name, **kwargs)
            columns_seen.append(table_name)
            return result

        def drop_then_forward(inspector, *args, **kwargs):
            assert inspector.bind is connection
            assert columns_seen == ["probe"] and not native_drops
            connection.exec_driver_sql("DROP TABLE probe")
            absent = connection.exec_driver_sql("SELECT to_regclass('public.probe')").scalar_one()
            assert absent is None
            native_drops.append(absent)
            # Forward the genuine reflection result or error; do not manufacture a map.
            return original_indexes(inspector, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Inspector, "get_columns", columns)
            patch.setattr(Inspector, "get_multi_indexes", drop_then_forward)
            with pytest.raises(NoSuchTableError, match=r"^public\.probe$") as refused:
                catalog(connection)
            assert type(refused.value) is NoSuchTableError
            assert refused.value.__cause__ is None
            assert refused.value.__suppress_context__ is True
        assert columns_seen == ["probe"] and native_drops == [None]
        assert connection.exec_driver_sql("SELECT to_regclass('public.probe')").scalar_one() is None
        connection.rollback()
        assert catalog(connection) == before
        assert connection.exec_driver_sql("SELECT id, value FROM probe").all() == [(1, 2)]
        connection.rollback()


def test_same_connection_observes_native_catalog_changes_and_their_rollback(pg):
    with pg["owner"].connect() as connection:
        with connection.begin():
            connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(
                "CREATE TABLE probe (id INTEGER PRIMARY KEY, parent_id INTEGER, value INTEGER)"
            )
        before = catalog(connection)
        connection.exec_driver_sql("ALTER TABLE probe ADD COLUMN added INTEGER")
        connection.exec_driver_sql("ALTER TABLE probe DROP CONSTRAINT probe_pkey")
        connection.exec_driver_sql("ALTER TABLE probe ADD PRIMARY KEY (id, value)")
        connection.exec_driver_sql(
            "ALTER TABLE probe ADD CONSTRAINT probe_unique UNIQUE (parent_id)"
        )
        connection.exec_driver_sql(
            "ALTER TABLE probe ADD CONSTRAINT probe_parent "
            "FOREIGN KEY (parent_id) REFERENCES parent(id)"
        )
        connection.exec_driver_sql(
            "ALTER TABLE probe ADD CONSTRAINT probe_value CHECK (value >= 0)"
        )
        connection.exec_driver_sql("CREATE INDEX probe_value_idx ON probe(value)")
        changed = catalog(connection)
        assert changed["probe"]["columns"][-1][:2] == ["added", "INTEGER"]
        assert changed["probe"]["pk"] == ["id", "value"]
        assert changed["probe"]["uniques"] == [["parent_id"]]
        assert [
            (
                row["name"],
                row["constrained_columns"],
                row["referred_table"],
                row["referred_columns"],
            )
            for row in changed["probe"]["foreign_keys"]
        ] == [("probe_parent", ["parent_id"], "parent", ["id"])]
        assert [(row["name"], row["sqltext"]) for row in changed["probe"]["checks"]] == [
            ("probe_value", "value >= 0")
        ]
        assert [(row["name"], row["column_names"]) for row in changed["probe"]["indexes"]] == [
            ("probe_value_idx", ["value"])
        ]
        assert changed["probe"] != before["probe"]
        connection.rollback()
        assert catalog(connection) == before
        assert connection.exec_driver_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='probe' ORDER BY ordinal_position"
        ).scalars().all() == ["id", "parent_id", "value"]
        connection.rollback()
