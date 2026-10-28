"""Closed CHECK deparse equivalence; all other raw schema evidence stays exact."""

from copy import deepcopy

import ledger_restore_interruption_raw as raw
import pytest
from test_ledger_restore_interruption_raw_controls import restored_witness, witness

CASES = (
    ("installation_adoptions", "source_kind", ("fresh", "legacy")),
    ("installation_adoptions", "state", ("prepared", "ownership_complete")),
    ("migration_progress", "status", ("pending", "running", "complete", "blocked")),
    ("project_memberships", "role", ("viewer", "operator", "maintainer")),
    ("resource_scopes", "resource_kind", ("run", "study", "job", "key", "provider_call")),
)


def check_pair(case):
    relation, column, literals = case
    source = witness()
    owner = next(row for row in source["inventory"]["relations"] if row["name"] == relation)
    name = relation + "_" + column + "_check"
    elements = ", ".join("'" + value + "'::character varying" for value in literals)
    original = f"CHECK ((({column})::text = ANY ((ARRAY[{elements}])::text[])))"
    elements = ", ".join("('" + value + "'::character varying)::text" for value in literals)
    restored = f"CHECK ((({column})::text = ANY (ARRAY[{elements}])))"
    source["inventory"]["constraints"].append(
        {"oid": 91, "schema": "public", "name": name, "kind": "c"}
    )
    source["inventory"]["constraint_definitions"].append(
        {
            "oid": 91,
            "name": name,
            "kind": "c",
            "relation_oid": owner["oid"],
            "relation": relation,
            "referenced_oid": 0,
            "referenced_relation": None,
            "deferrable": False,
            "deferred": False,
            "valid": True,
            "definition": original,
        }
    )
    target = restored_witness(source)
    target["inventory"]["constraint_definitions"][-1]["definition"] = restored
    return source, target


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("forms", ["distinct", "reversed", "source", "restored"])
def test_only_pinned_cast_forms_compare_without_modifying_raw_witnesses(case, forms):
    source, target = check_pair(case)
    a = source["inventory"]["constraint_definitions"][-1]
    b = target["inventory"]["constraint_definitions"][-1]
    if forms == "reversed":
        a["definition"], b["definition"] = b["definition"], a["definition"]
    elif forms == "source":
        b["definition"] = a["definition"]
    elif forms == "restored":
        a["definition"] = b["definition"]
    before = (raw.encoded(source), raw.encoded(target))
    raw.assert_schema_only(target, source)
    assert (raw.encoded(source), raw.encoded(target)) == before
    if forms in {"distinct", "reversed"}:
        assert a["definition"] != b["definition"]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    "fault",
    [
        "literal",
        "literal-order",
        "column",
        "extra-cast",
        "missing-cast",
        "predicate",
        "whitespace",
        "definition-subclass",
        "name",
        "relation",
        "kind",
        "deferrable",
        "deferred",
        "valid",
        "flag-type",
        "missing",
        "duplicate",
        "inventory",
        "local-oid",
        "other-constraint",
    ],
)
def test_cast_equivalence_rejects_mutated_contract_or_other_evidence(case, fault):
    source, target = check_pair(case)
    rows = target["inventory"]["constraint_definitions"]
    row = rows[-1]
    definition = row["definition"]
    if fault == "literal":
        row["definition"] = definition.replace("'" + case[2][0] + "'", "'unexpected'")
    elif fault == "literal-order":
        first, second = case[2][:2]
        row["definition"] = (
            definition.replace("'" + first + "'", "'TEMP'")
            .replace("'" + second + "'", "'" + first + "'")
            .replace("'TEMP'", "'" + second + "'")
        )
    elif fault == "column":
        row["definition"] = definition.replace("(" + case[1] + ")", "(wrong_column)")
    elif fault == "extra-cast":
        row["definition"] = definition.replace("::text,", "::text::text,", 1)
    elif fault == "missing-cast":
        row["definition"] = definition.replace(")::text,", "),", 1)
    elif fault == "predicate":
        row["definition"] = definition[:-1] + " OR true)"
    elif fault == "whitespace":
        row["definition"] += " "
    elif fault == "definition-subclass":

        class Text(str):
            pass

        row["definition"] = Text(definition)
    elif fault == "name":
        row["name"] += "_other"
    elif fault == "relation":
        other = target["inventory"]["relations"][0]
        row["relation"], row["relation_oid"] = other["name"], other["oid"]
    elif fault == "kind":
        row["kind"] = "f"
    elif fault in {"deferrable", "deferred", "valid"}:
        row[fault] = not row[fault]
    elif fault == "flag-type":
        row["valid"] = 1
    elif fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        copy = deepcopy(row)
        copy["oid"] += 10000
        rows.append(copy)
    elif fault == "inventory":
        target["inventory"]["constraints"][-1]["kind"] = "f"
    elif fault == "local-oid":
        row["relation_oid"] += 10000
    else:
        rows[0]["definition"] = "PRIMARY KEY (wrong_column)"
    before = raw.encoded(target)
    with pytest.raises((AssertionError, KeyError)):
        raw.assert_schema_only(target, source)
    assert raw.encoded(target) == before


def test_comparison_does_not_extend_cast_equivalence_to_another_constraint():
    source, target = check_pair(CASES[0])
    for shape in (source, target):
        shape["inventory"]["constraint_definitions"][-1]["name"] = "unrelated_check"
        shape["inventory"]["constraints"][-1]["name"] = "unrelated_check"
    with pytest.raises(AssertionError):
        raw.assert_schema_only(target, source)


def test_same_target_raw_witness_still_distinguishes_the_two_equivalent_forms():
    source, target = check_pair(CASES[0])
    changed = deepcopy(target)
    changed["inventory"]["constraint_definitions"][-1]["definition"] = source["inventory"][
        "constraint_definitions"
    ][-1]["definition"]
    assert raw.structure(changed["inventory"]) == raw.structure(target["inventory"])
    assert raw.encoded(changed) != raw.encoded(target)
