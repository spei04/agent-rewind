"""Literal PostgreSQL 16 recovery renderings; never accept generic SQL rewrites."""

from copy import deepcopy

import pytest

from agent_rewind.migrations.schema import (
    MigrationRefused,
    _canonicalize_postgresql_enum_checks,
    checksum,
    installed_profile,
    verify_installed_profile,
)

# Captured from the failing synthetic restore in run39349792047. Expected original
# spellings remain in the separately frozen PostgreSQL profile, unchanged here.
RESTORED_CHECKS = (
    (
        "installation_adoptions",
        "installation_adoptions_source_kind_check",
        "source_kind",
        "source_kind::text = ANY (ARRAY['fresh'::character varying::text, "
        "'legacy'::character varying::text])",
        "CHECK (((source_kind)::text = ANY (ARRAY[('fresh'::character varying)::text, "
        "('legacy'::character varying)::text])))",
    ),
    (
        "installation_adoptions",
        "installation_adoptions_state_check",
        "state",
        "state::text = ANY (ARRAY['prepared'::character varying::text, "
        "'ownership_complete'::character varying::text])",
        "CHECK (((state)::text = ANY (ARRAY[('prepared'::character varying)::text, "
        "('ownership_complete'::character varying)::text])))",
    ),
    (
        "migration_progress",
        "migration_progress_status_check",
        "status",
        "status::text = ANY (ARRAY['pending'::character varying::text, "
        "'running'::character varying::text, 'complete'::character varying::text, "
        "'blocked'::character varying::text])",
        "CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, "
        "('running'::character varying)::text, ('complete'::character varying)::text, "
        "('blocked'::character varying)::text])))",
    ),
)


def restored_profile():
    shape = installed_profile("postgresql")
    for table, name, column, reflected, native in RESTORED_CHECKS:
        check = next(check for check in shape[table]["checks"] if check["name"] == name)
        check["sqltext"] = reflected
        matches = [
            row
            for row in shape["$postgres"]["constraints"]
            if row[0] == table and row[5].startswith(f"CHECK ((({column})::text = ANY")
        ]
        assert len(matches) == 1
        matches[0][5] = native
    return shape


def test_observed_restore_forms_preserve_original_profile_and_stored_fingerprint():
    original = installed_profile("postgresql")
    shape = restored_profile()
    assert shape != original
    _canonicalize_postgresql_enum_checks(shape)
    assert shape == original
    assert checksum(shape) == checksum(original)
    verify_installed_profile(shape, "postgresql")
    _canonicalize_postgresql_enum_checks(shape)
    assert shape == original  # A repeated inspection has the same identity.


def test_original_profile_remains_unchanged_and_partial_catalogs_stay_inspectable():
    original = installed_profile("postgresql")
    before = deepcopy(original)
    _canonicalize_postgresql_enum_checks(original)
    assert original == before
    for shape in [
        {"$postgres": {"constraints": []}},
        {"installation_adoptions": {"checks": []}, "$postgres": {"constraints": []}},
    ]:
        expected = deepcopy(shape)
        _canonicalize_postgresql_enum_checks(shape)
        assert shape == expected


@pytest.mark.parametrize("view", ["reflected", "native"])
@pytest.mark.parametrize(
    "before,after",
    [
        ("'fresh'", "'other'"),
        (" = ANY", " <> ALL"),
        ("character varying", "character(12)"),
        ("::text", "::citext"),
        ("'fresh'", "'legacy'"),
    ],
)
def test_nearby_enum_operator_type_or_member_changes_still_refuse(view, before, after):
    shape = restored_profile()
    if view == "reflected":
        item = next(
            c
            for c in shape["installation_adoptions"]["checks"]
            if c["name"] == "installation_adoptions_source_kind_check"
        )
        item["sqltext"] = item["sqltext"].replace(before, after, 1)
    else:
        item = next(
            r
            for r in shape["$postgres"]["constraints"]
            if r[0] == "installation_adoptions" and r[5] == RESTORED_CHECKS[0][4]
        )
        item[5] = item[5].replace(before, after, 1)
    _canonicalize_postgresql_enum_checks(shape)
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        verify_installed_profile(shape, "postgresql")


@pytest.mark.parametrize("mutation", ["name", "relation", "extra", "missing", "unvalidated"])
def test_constraint_identity_cardinality_and_validation_still_refuse(mutation):
    shape = restored_profile()
    checks = shape["installation_adoptions"]["checks"]
    check = next(c for c in checks if c["name"] == "installation_adoptions_source_kind_check")
    row = next(
        r
        for r in shape["$postgres"]["constraints"]
        if r[0] == "installation_adoptions" and r[5] == RESTORED_CHECKS[0][4]
    )
    if mutation == "name":
        check["name"] = "unreviewed_name"
    elif mutation == "relation":
        checks.remove(check)
        shape["migration_progress"]["checks"].append(check)
        row[0] = "migration_progress"
    elif mutation == "extra":
        checks.append(deepcopy(check))
    elif mutation == "missing":
        checks.remove(check)
    else:
        row[4] = False
    _canonicalize_postgresql_enum_checks(shape)
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        verify_installed_profile(shape, "postgresql")
