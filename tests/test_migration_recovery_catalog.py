"""Literal PostgreSQL 16 recovery renderings; never accept generic SQL rewrites."""

from copy import deepcopy

import pytest

from agent_rewind.migrations.schema import (
    HEAD,
    OWNERSHIP,
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
    # Both Python jobs in synthetic ownership run39353816614 observed these
    # exact reflected/native forms after pg_dump/pg_restore.
    (
        "project_memberships",
        "project_memberships_role_check",
        "role",
        "role::text = ANY (ARRAY['viewer'::character varying::text, "
        "'operator'::character varying::text, 'maintainer'::character varying::text])",
        "CHECK (((role)::text = ANY (ARRAY[('viewer'::character varying)::text, "
        "('operator'::character varying)::text, ('maintainer'::character varying)::text])))",
    ),
    (
        "resource_scopes",
        "resource_scopes_resource_kind_check",
        "resource_kind",
        "resource_kind::text = ANY (ARRAY['run'::character varying::text, "
        "'study'::character varying::text, 'job'::character varying::text, "
        "'key'::character varying::text, 'provider_call'::character varying::text])",
        "CHECK (((resource_kind)::text = ANY (ARRAY[('run'::character varying)::text, "
        "('study'::character varying)::text, ('job'::character varying)::text, "
        "('key'::character varying)::text, ('provider_call'::character varying)::text])))",
    ),
)


def restored_profile(revision=HEAD):
    shape = installed_profile("postgresql", revision)
    for table, name, column, reflected, native in RESTORED_CHECKS:
        if table not in shape:
            continue
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


@pytest.mark.parametrize("revision", [HEAD, OWNERSHIP])
def test_observed_restore_forms_preserve_original_profile_and_stored_fingerprint(revision):
    original = installed_profile("postgresql", revision)
    shape = restored_profile(revision)
    assert shape != original
    _canonicalize_postgresql_enum_checks(shape)
    assert shape == original
    assert checksum(shape) == checksum(original)
    verify_installed_profile(shape, "postgresql", revision)
    _canonicalize_postgresql_enum_checks(shape)
    assert shape == original  # A repeated inspection has the same identity.


@pytest.mark.parametrize("revision", [HEAD, OWNERSHIP])
def test_original_profile_remains_unchanged_and_partial_catalogs_stay_inspectable(revision):
    original = installed_profile("postgresql", revision)
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


@pytest.mark.parametrize("revision,index", [(HEAD, 0), (OWNERSHIP, 3), (OWNERSHIP, 4)])
@pytest.mark.parametrize("view", ["reflected", "native"])
@pytest.mark.parametrize("mutation", ["member", "operator", "type", "cast", "duplicate", "order"])
def test_nearby_enum_operator_type_or_member_changes_still_refuse(revision, index, view, mutation):
    shape = restored_profile(revision)
    table, name, _, reflected, native = RESTORED_CHECKS[index]
    members = {
        0: ("'fresh'", "'legacy'"),
        3: ("'viewer'", "'operator'"),
        4: ("'run'", "'study'"),
    }
    first, second = members[index]
    expression = reflected if view == "reflected" else native
    substitutions = {
        "member": (first, "'unreviewed'"),
        "operator": (" = ANY", " <> ALL"),
        "type": ("character varying", "character(12)"),
        "cast": ("::text", "::citext"),
        "duplicate": (first, second),
    }
    if mutation == "order":
        changed = expression.replace(first, "'temporary'").replace(second, first)
        changed = changed.replace("'temporary'", second)
    else:
        before, after = substitutions[mutation]
        changed = expression.replace(before, after, 1)
    assert changed != expression
    if view == "reflected":
        item = next(c for c in shape[table]["checks"] if c["name"] == name)
        item["sqltext"] = changed
    else:
        item = next(
            r for r in shape["$postgres"]["constraints"] if r[0] == table and r[5] == native
        )
        item[5] = changed
    _canonicalize_postgresql_enum_checks(shape)
    with pytest.raises(MigrationRefused, match="schema_incompatible"):
        verify_installed_profile(shape, "postgresql", revision)


@pytest.mark.parametrize("revision,index", [(HEAD, 0), (OWNERSHIP, 3), (OWNERSHIP, 4)])
@pytest.mark.parametrize("mutation", ["name", "relation", "extra", "missing", "unvalidated"])
def test_constraint_identity_cardinality_and_validation_still_refuse(revision, index, mutation):
    shape = restored_profile(revision)
    table, name, _, _, native = RESTORED_CHECKS[index]
    checks = shape[table]["checks"]
    check = next(c for c in checks if c["name"] == name)
    row = next(r for r in shape["$postgres"]["constraints"] if r[0] == table and r[5] == native)
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
        verify_installed_profile(shape, "postgresql", revision)
