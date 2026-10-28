"""Fresh PostgreSQL reflection batching and inherited bind-envelope controls."""

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.engine.reflection import ObjectKind, ObjectScope

from agent_rewind.migrations.ledger_reader_catalog import _postgres_constraints
from agent_rewind.migrations.schema import ADMISSION, LEDGER, MigrationRefused, installed_profile


def reflected(kind, names):
    if kind == "pk":
        return {
            ("public", name): {"constrained_columns": ["id"], "name": name + "_pk"}
            for name in names
        }
    return {
        ("public", name): ([] if index % 2 else [{"name": name + "_b"}, {"name": name + "_a"}])
        for index, name in enumerate(names)
    }


def inspector_for(names, calls, transform=lambda kind, rows: rows):
    def read(kind):
        def observe(**kwargs):
            calls.append((kind, kwargs))
            selected = kwargs.get("filter_names", names)
            return transform(kind, reflected(kind, selected))

        return observe

    return SimpleNamespace(
        get_multi_pk_constraint=read("pk"),
        get_multi_unique_constraints=read("uniques"),
        get_multi_foreign_keys=read("foreign_keys"),
        get_multi_check_constraints=read("checks"),
    )


def test_reflection_batch_retains_complete_empty_and_ordered_values_without_cross_call_cache():
    names = sorted(
        name for name in installed_profile("postgresql", LEDGER) if not name.startswith("$")
    )
    calls, checks = [], []
    inspector = inspector_for(names, calls)
    work = SimpleNamespace(check=lambda: checks.append(True))
    first = _postgres_constraints(inspector, names, work)
    assert len(calls) == 6 and len(checks) == 6
    for kind in ("pk", "uniques"):
        batches = [options["filter_names"] for label, options in calls if label == kind]
        assert batches == [names[:10], names[10:]]
        expected = {}
        for batch in batches:
            expected.update({key[1]: value for key, value in reflected(kind, batch).items()})
        assert first[kind] == expected
    for kind in ("foreign_keys", "checks"):
        assert first[kind] == {key[1]: value for key, value in reflected(kind, names).items()}
        assert "filter_names" not in next(options for label, options in calls if label == kind)
    for _, options in calls:
        assert options["schema"] == "public"
        assert options["scope"] is ObjectScope.DEFAULT and options["kind"] is ObjectKind.TABLE
    assert _postgres_constraints(inspector, names, work) == first
    assert len(calls) == len(checks) == 12


@pytest.mark.parametrize("kind", ["pk", "uniques", "foreign_keys", "checks"])
@pytest.mark.parametrize("fault", ["missing", "extra", "wrong-schema", "wrong-container"])
def test_reflection_batch_refuses_incomplete_or_misowned_results(kind, fault):
    names = sorted(
        name for name in installed_profile("postgresql", LEDGER) if not name.startswith("$")
    )

    def corrupt(actual_kind, rows):
        if actual_kind != kind:
            return rows
        key = next(iter(rows))
        if fault == "missing":
            rows.pop(key)
        elif fault == "extra":
            rows[("public", "not_selected")] = rows[key]
        elif fault == "wrong-schema":
            rows[("other", key[1])] = rows.pop(key)
        else:
            rows[key] = [] if kind == "pk" else {}
        return rows

    with pytest.raises(MigrationRefused, match="^schema_incompatible$"):
        _postgres_constraints(
            inspector_for(names, [], corrupt), names, SimpleNamespace(check=lambda: None)
        )


@pytest.mark.parametrize("revision", [ADMISSION, LEDGER], ids=["ar6", "ar7"])
def test_pinned_postgres_compilation_keeps_every_expanded_parameter_set_within_sixteen(revision):
    dialect = PGDialect_psycopg()
    dialect.server_version_info = (16, 15)
    names = sorted(
        name for name in installed_profile("postgresql", revision) if not name.startswith("$")
    )
    counts = {"oid": [], "key": [], "foreign_keys": [], "checks": []}
    for start in range(0, len(names), 10):
        batch = names[start : start + 10]
        queries = [
            (
                "oid",
                dialect._table_oids_query("public", True, ObjectScope.DEFAULT, ObjectKind.TABLE),
                {"filter_names": batch},
            ),
            ("key", dialect._constraint_query, {"oids": list(range(len(batch))), "contype": "p"}),
            ("key", dialect._constraint_query, {"oids": list(range(len(batch))), "contype": "u"}),
        ]
        for label, query, parameters in queries:
            actual = query.compile(dialect=dialect).construct_expanded_state(parameters).parameters
            counts[label].append(len(actual))
            assert len(actual) <= 16
    for label, query in (
        (
            "foreign_keys",
            dialect._foreing_key_query("public", False, ObjectScope.DEFAULT, ObjectKind.TABLE),
        ),
        (
            "checks",
            dialect._check_constraint_query("public", False, ObjectScope.DEFAULT, ObjectKind.TABLE),
        ),
    ):
        actual = query.compile(dialect=dialect).construct_expanded_state().parameters
        counts[label].append(len(actual))
        assert len(actual) <= 16
    assert {key: max(values) for key, values in counts.items()} == {
        "oid": 15,
        "key": 13,
        "foreign_keys": 8,
        "checks": 8,
    }
