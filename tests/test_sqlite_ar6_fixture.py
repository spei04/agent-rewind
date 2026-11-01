"""Independent native isolation and failure controls for fresh SQLite ar6 copies."""

import hashlib
import os
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

import ledger_provisioning_fixture as provisioning
import ledger_reader_fixture as reader
import pytest
import sqlite_ar6_fixture as template_module
from ledger_reader_fixture import ReaderFixture, sqlite_snapshot
from ledger_restore_authority import typed
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlite_ar6_fixture import FreshSqliteAr6Template

from agent_rewind.migrations.schema import ADMISSION


def _template(tmp_path):
    root = tmp_path / "template"
    root.mkdir(mode=0o700)
    return root, FreshSqliteAr6Template(root)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(case):
    return deepcopy(
        {
            field.name: getattr(case, field.name)
            for field in fields(ReaderFixture)
            if field.name not in {"path", "engine"}
        }
    )


def _witness(path):
    metadata = path.lstat()
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        os.readlink(path) if path.is_symlink() else path.read_bytes(),
    )


def test_copies_have_native_captures_and_detached_receipts(tmp_path, monkeypatch):
    root, template = _template(tmp_path)
    builds, captures, disposed, copies = [], [], [], []
    build = template_module.complete_ar6
    capture = template_module.capture_ar6

    def observe_build(path, *, legacy):
        case = build(path, legacy=legacy)
        builds.append(case)
        event.listen(case.engine, "engine_disposed", lambda engine: disposed.append(engine))
        return case

    def observe_capture(path, engine, *, legacy):
        case = capture(path, engine, legacy=legacy)
        with engine.connect() as connection:
            database = next(
                row[2]
                for row in connection.exec_driver_sql("PRAGMA database_list")
                if row[1] == "main"
            )
        assert Path(database).resolve() == path.resolve()
        captures.append(case)
        return case

    monkeypatch.setattr(template_module, "complete_ar6", observe_build)
    monkeypatch.setattr(template_module, "capture_ar6", observe_capture)
    try:
        assert not builds and not list(root.iterdir())
        first = template.copy_to(tmp_path / "first.sqlite")
        copies.append(first)
        assert len(builds) == 1 and builds[0].path == root / "fresh.sqlite"
        assert disposed == [builds[0].engine]
        expected = _receipt(first)
        assert first.legacy is False and first.revision == ADMISSION
        assert first.manifest is first.cursor is first.opening is None
        source_bytes = _digest(root / "fresh.sqlite")
        source_rows = sqlite_snapshot(root / "fresh.sqlite")

        # Mutating either retained builder metadata or a returned receipt must not
        # change the sealed observations used to validate the next native capture.
        for case in (builds[0], first):
            case.original_rows["test_only"] = [("changed",)]
            case.adoption["test_only"] = "changed"
            case.previous_progress.append(("changed",))
            case.expected["test_only"] = {"nested": ["changed"]}

        for name in ("second.sqlite", "third.sqlite"):
            case = template.copy_to(tmp_path / name)
            copies.append(case)
            assert typed(_receipt(case)) == typed(expected)
            assert sqlite_snapshot(case.path) == source_rows
            assert _digest(case.path) == source_bytes
        assert [case.path for case in captures] == [case.path for case in copies]
        assert all(
            captured.engine is copied.engine
            for captured, copied in zip(captures, copies, strict=True)
        )
        assert len(builds) == 1
        assert len({id(case.engine) for case in [builds[0], *copies]}) == 4
        identities = {
            (path.stat().st_dev, path.stat().st_ino)
            for path in [root / "fresh.sqlite", *(case.path for case in copies)]
        }
        assert len(identities) == 4
        for path in [root / "fresh.sqlite", *(case.path for case in copies)]:
            assert not path.is_symlink()
            assert path.stat().st_nlink == 1
        assert (root / "fresh.sqlite").stat().st_mode & 0o777 == 0o400
        assert all(case.path.stat().st_mode & 0o777 == 0o600 for case in copies)
        assert _digest(root / "fresh.sqlite") == source_bytes
        assert sqlite_snapshot(root / "fresh.sqlite") == source_rows
    finally:
        for case in copies:
            case.dispose()
        template.close()


def test_native_commit_rollback_disposal_and_close_are_isolated(tmp_path):
    root, template = _template(tmp_path)
    copies = []
    try:
        first = template.copy_to(tmp_path / "first.sqlite")
        copies.append(first)
        sibling = template.copy_to(tmp_path / "sibling.sqlite")
        copies.append(sibling)
        source_before = _witness(root / "fresh.sqlite")
        sibling_before = _witness(sibling.path)
        sibling_rows = sqlite_snapshot(sibling.path)
        with first.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE isolation_probe (value INTEGER)")
            connection.exec_driver_sql("INSERT INTO isolation_probe VALUES (7)")
        with first.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT value FROM isolation_probe").scalar_one() == 7
        assert _witness(root / "fresh.sqlite") == source_before
        assert _witness(sibling.path) == sibling_before

        # Explicit native BEGIN makes SQLite DDL rollback observable.
        with sibling.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            connection.exec_driver_sql("CREATE TABLE rollback_probe (value INTEGER)")
            connection.exec_driver_sql("INSERT INTO rollback_probe VALUES (9)")
            assert connection.exec_driver_sql("SELECT value FROM rollback_probe").scalar_one() == 9
            connection.rollback()
        assert sqlite_snapshot(sibling.path) == sibling_rows
        assert _witness(root / "fresh.sqlite") == source_before
        first.dispose()
        with sibling.engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == ADMISSION
            )
        template.close()
        template.close()
        assert not (root / "fresh.sqlite").exists()
        assert first.path.is_file() and sibling.path.is_file()
        assert sqlite_snapshot(sibling.path) == sibling_rows
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_closed$"):
            template.copy_to(tmp_path / "after-close.sqlite")
        assert not (tmp_path / "after-close.sqlite").exists()
    finally:
        for case in copies:
            case.dispose()
        template.close()


def test_occupied_targets_and_sidecars_remain_untouched_without_poison(tmp_path):
    root, template = _template(tmp_path)
    copies = []
    occupied = []
    for index, suffix in enumerate(("", "-wal", "-shm", "-journal")):
        target = tmp_path / f"occupied-{index}.sqlite"
        obstacle = Path(str(target) + suffix)
        obstacle.write_bytes(b"caller-owned content")
        occupied.append((target, obstacle, FileExistsError))
    dangling = tmp_path / "dangling.sqlite"
    dangling.symlink_to(tmp_path / "missing.sqlite")
    occupied.append((dangling, dangling, ValueError))
    before = {obstacle: _witness(obstacle) for _, obstacle, _ in occupied}
    try:
        for target, obstacle, error_type in occupied:
            with pytest.raises(error_type) as refused:
                template.copy_to(target)
            if error_type is ValueError:
                assert str(refused.value) == "fresh_ar6_template_invalid"
            assert _witness(obstacle) == before[obstacle]
            assert not list(root.iterdir())
        copies.append(template.copy_to(tmp_path / "ready.sqlite"))
        source_before = _witness(root / "fresh.sqlite")
        for target, obstacle, error_type in occupied:
            with pytest.raises(error_type) as refused:
                template.copy_to(target)
            if error_type is ValueError:
                assert str(refused.value) == "fresh_ar6_template_invalid"
            assert _witness(obstacle) == before[obstacle]
            assert _witness(root / "fresh.sqlite") == source_before
        copies.append(template.copy_to(tmp_path / "still-usable.sqlite"))
        assert typed(_receipt(copies[0])) == typed(_receipt(copies[1]))
    finally:
        for case in copies:
            case.dispose()
        template.close()
    assert all(_witness(path) == witness for path, witness in before.items())


def test_template_paths_and_source_alias_are_not_copy_destinations(tmp_path):
    root, template = _template(tmp_path)
    copies = []
    alias = tmp_path / "source-alias.sqlite"
    try:
        for target in (root, root / "nested.sqlite"):
            with pytest.raises(ValueError, match="^fresh_ar6_template_invalid$"):
                template.copy_to(target)
            assert not list(root.iterdir())
        copies.append(template.copy_to(tmp_path / "first.sqlite"))
        source = root / "fresh.sqlite"
        os.link(source, alias)
        before = _witness(alias)
        with pytest.raises(ValueError, match="^fresh_ar6_template_invalid$"):
            template.copy_to(alias)
        assert _witness(alias) == before
        alias.unlink()
        copies.append(template.copy_to(tmp_path / "after-refusal.sqlite"))
    finally:
        if alias.exists():
            alias.unlink()
        for case in copies:
            case.dispose()
        template.close()


@pytest.mark.parametrize("tamper", ["bytes", "same-bytes-replacement", "sidecar"])
def test_source_tamper_poison_never_rebuilds(tmp_path, monkeypatch, tamper):
    root, template = _template(tmp_path)
    first = template.copy_to(tmp_path / "first.sqlite")
    source = root / "fresh.sqlite"
    original = source.read_bytes()
    sibling_before = _witness(first.path)
    sidecar = Path(str(source) + "-wal")
    replacement = tmp_path / "replacement.sqlite"

    def no_rebuild(*args, **kwargs):
        pytest.fail("A poisoned template must not bootstrap again")

    monkeypatch.setattr(template_module, "complete_ar6", no_rebuild)
    try:
        if tamper == "bytes":
            source.chmod(0o600)
            source.write_bytes(original + b"tampered")
            source.chmod(0o400)
        elif tamper == "same-bytes-replacement":
            replacement.write_bytes(original)
            replacement.chmod(0o400)
            assert replacement.stat().st_ino != source.stat().st_ino
            replacement.replace(source)
        else:
            sidecar.write_bytes(b"unowned sidecar")
        tampered = _witness(source)
        target = tmp_path / "refused.sqlite"
        with pytest.raises(ValueError, match="^fresh_ar6_template_invalid$"):
            template.copy_to(target)
        assert not target.exists()
        assert _witness(source) == tampered
        assert _witness(first.path) == sibling_before
        if sidecar.exists():
            assert sidecar.read_bytes() == b"unowned sidecar"
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_failed$"):
            template.copy_to(tmp_path / "no-rebuild.sqlite")
        assert not (tmp_path / "no-rebuild.sqlite").exists()
        if tamper == "same-bytes-replacement":
            with pytest.raises(ValueError, match="^fresh_ar6_template_invalid$"):
                template.close()
            assert _witness(source) == tampered
        else:
            # Remove only this test's injected damage before ordinary owned cleanup.
            if tamper == "bytes":
                source.chmod(0o600)
                source.write_bytes(original)
                source.chmod(0o400)
            sidecar.unlink(missing_ok=True)
            template.close()
        template.close()
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_closed$"):
            template.copy_to(tmp_path / "closed.sqlite")
    finally:
        first.dispose()
        template.close()


def test_native_builder_failure_keeps_original_error_and_poisons(tmp_path, monkeypatch):
    root, template = _template(tmp_path)
    failures, disposed, owned_identity, close_calls, injected = [], [], [], [], []
    close_error = OSError("injected source descriptor close")
    real_close = template_module.os.close
    unrelated = tmp_path / "caller-owned"
    unrelated.write_bytes(b"keep")

    def close_then_raise(fd):
        if owned_identity:
            close_calls.append(fd)
        metadata = os.fstat(fd)
        matches = owned_identity and (metadata.st_dev, metadata.st_ino) == owned_identity[0]
        real_close(fd)
        if matches and not injected:
            injected.append(fd)
            raise close_error

    def native_failure(engine):
        event.listen(engine, "engine_disposed", lambda value: disposed.append(value))
        metadata = (root / "fresh.sqlite").stat()
        owned_identity.append((metadata.st_dev, metadata.st_ino))
        with engine.connect() as connection:
            try:
                connection.exec_driver_sql("SELECT * FROM absent_template_test_table")
            except OperationalError as error:
                failures.append(error)
                raise

    monkeypatch.setattr(reader, "initialize_admission", native_failure)
    monkeypatch.setattr(template_module.os, "close", close_then_raise)
    try:
        with pytest.raises(OperationalError) as refused:
            template.copy_to(tmp_path / "target.sqlite")
        assert failures == [refused.value]
        assert len(injected) == 1 and close_calls.count(injected[0]) == 1
        assert getattr(refused.value, "__notes__", [])
        assert len(disposed) == 1
        assert not (tmp_path / "target.sqlite").exists()
        assert not list(root.iterdir())
        assert unrelated.read_bytes() == b"keep"
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_failed$"):
            template.copy_to(tmp_path / "retry.sqlite")
        assert len(failures) == 1 and not (tmp_path / "retry.sqlite").exists()
    finally:
        template.close()


def test_native_capture_failure_cleans_only_its_attempt(tmp_path, monkeypatch):
    root, template = _template(tmp_path)
    first = template.copy_to(tmp_path / "first.sqlite")
    source_before = _witness(root / "fresh.sqlite")
    sibling_before = _witness(first.path)
    target = tmp_path / "failed-capture.sqlite"
    failures, disposed = [], []
    capture = template_module.capture_ar6

    def native_drift(path, engine, *, legacy):
        event.listen(engine, "engine_disposed", lambda value: disposed.append(value))
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN unexpected_template_column INTEGER"
            )
        try:
            return capture(path, engine, legacy=legacy)
        except AssertionError as error:
            failures.append(error)
            raise

    monkeypatch.setattr(template_module, "capture_ar6", native_drift)
    try:
        with pytest.raises(AssertionError) as refused:
            template.copy_to(target)
        assert failures == [refused.value] and len(disposed) == 1
        assert not target.exists()
        assert all(
            not Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
        )
        assert _witness(root / "fresh.sqlite") == source_before
        assert _witness(first.path) == sibling_before
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_failed$"):
            template.copy_to(tmp_path / "retry.sqlite")
        assert len(failures) == 1
    finally:
        first.dispose()
        template.close()


@pytest.mark.parametrize("legacy", [False, True], ids=["default-fresh", "excluded-legacy"])
def test_non_opt_in_provisioning_keeps_original_builder(tmp_path, monkeypatch, legacy):
    """Dispatch control only; it does not claim native legacy or PostgreSQL evidence."""
    marker = RuntimeError("original builder reached")
    calls = []

    def original(path, *, legacy):
        calls.append((path, legacy))
        raise marker

    class ForbiddenTemplate:
        def copy_to(self, path):
            pytest.fail("An excluded caller must not request a template copy")

    monkeypatch.setattr(provisioning, "complete_ar6", original)
    path = tmp_path / "default.sqlite"
    with pytest.raises(RuntimeError) as refused:
        provisioning.build_case(path, legacy=legacy)
    assert refused.value is marker
    assert calls == [(path, legacy)] and not path.exists()
    if legacy:
        with pytest.raises(ValueError, match="^fresh_ar6_requires_fresh$"):
            provisioning.build_case(path, legacy=True, fresh_ar6_template=ForbiddenTemplate())
        assert calls == [(path, legacy)] and not path.exists()


def test_close_before_first_copy_is_lazy_and_final(tmp_path, monkeypatch):
    root, template = _template(tmp_path)

    def no_build(*args, **kwargs):
        pytest.fail("Closing an unused template must not bootstrap")

    monkeypatch.setattr(template_module, "complete_ar6", no_build)
    template.close()
    template.close()
    assert not list(root.iterdir())
    with pytest.raises(RuntimeError, match="^fresh_ar6_template_closed$"):
        template.copy_to(tmp_path / "never.sqlite")
    assert not (tmp_path / "never.sqlite").exists()


def test_builder_failure_does_not_adopt_a_foreign_source_replacement(tmp_path, monkeypatch):
    root, template = _template(tmp_path)
    source = root / "fresh.sqlite"
    replacement = tmp_path / "foreign.sqlite"
    replacement.write_bytes(b"caller-owned replacement")
    replacement.chmod(0o600)
    foreign = _witness(replacement)
    failures, disposed = [], []

    def native_failure(engine):
        event.listen(engine, "engine_disposed", lambda value: disposed.append(value))
        with engine.connect() as connection:
            try:
                connection.exec_driver_sql("SELECT * FROM absent_template_test_table")
            except OperationalError as error:
                assert source.is_file()
                assert source.stat().st_ino != replacement.stat().st_ino
                replacement.replace(source)
                failures.append(error)
                raise

    monkeypatch.setattr(reader, "initialize_admission", native_failure)
    try:
        with pytest.raises(OperationalError) as refused:
            template.copy_to(tmp_path / "target.sqlite")
        assert failures == [refused.value] and len(disposed) == 1
        assert _witness(source) == foreign
        assert not (tmp_path / "target.sqlite").exists()
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_failed$"):
            template.copy_to(tmp_path / "retry.sqlite")
        assert len(failures) == 1
        with pytest.raises(ValueError, match="^fresh_ar6_template_invalid$"):
            template.close()
        assert _witness(source) == foreign
        template.close()
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_closed$"):
            template.copy_to(tmp_path / "closed.sqlite")
        assert not (tmp_path / "retry.sqlite").exists()
        assert not (tmp_path / "closed.sqlite").exists()
    finally:
        template.close()


def test_identical_target_replacement_is_refused_before_native_capture(tmp_path, monkeypatch):
    root, template = _template(tmp_path)
    target = tmp_path / "target.sqlite"
    replacement = tmp_path / "foreign.sqlite"
    digest = template_module._digest
    foreign = []

    def replace_after_digest(path):
        value = digest(path)
        if Path(path) == target and not foreign:
            replacement.write_bytes(target.read_bytes())
            replacement.chmod(0o600)
            assert replacement.stat().st_ino != target.stat().st_ino
            replacement.replace(target)
            foreign.append(_witness(target))
        return value

    def no_capture(*args, **kwargs):
        pytest.fail("A replaced target must be refused before native capture")

    monkeypatch.setattr(template_module, "_digest", replace_after_digest)
    monkeypatch.setattr(template_module, "capture_ar6", no_capture)
    try:
        with pytest.raises(ValueError) as refused:
            template.copy_to(target)
        assert refused.value.args == ("fresh_ar6_template_invalid",)
        assert refused.value.__notes__ == ["Fresh ar6 copy cleanup also failed."]
        assert len(foreign) == 1 and _witness(target) == foreign[0]
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_failed$"):
            template.copy_to(tmp_path / "retry.sqlite")
        assert not (tmp_path / "retry.sqlite").exists()
        template.close()
        assert _witness(target) == foreign[0]
        assert not (root / "fresh.sqlite").exists()
    finally:
        template.close()


def test_close_error_after_native_capture_disposes_unreturned_copy(tmp_path, monkeypatch):
    root, template = _template(tmp_path)
    target = tmp_path / "target.sqlite"
    capture = template_module.capture_ar6
    real_close = template_module.os.close
    close_error = OSError("injected target descriptor close")
    captured, disposed, owned_identity, close_calls, injected, source_before = (
        [],
        [],
        [],
        [],
        [],
        [],
    )

    def observe_capture(path, engine, *, legacy):
        case = capture(path, engine, legacy=legacy)
        assert type(case) is ReaderFixture and case.revision == ADMISSION and not case.legacy
        captured.append(case)
        event.listen(engine, "engine_disposed", lambda value: disposed.append(value))
        metadata = path.stat()
        owned_identity.append((metadata.st_dev, metadata.st_ino))
        source_before.append(_witness(root / "fresh.sqlite"))
        return case

    def close_then_raise(fd):
        if owned_identity:
            close_calls.append(fd)
        metadata = os.fstat(fd)
        matches = owned_identity and (metadata.st_dev, metadata.st_ino) == owned_identity[0]
        real_close(fd)
        if matches and not injected:
            injected.append(fd)
            raise close_error

    monkeypatch.setattr(template_module, "capture_ar6", observe_capture)
    monkeypatch.setattr(template_module.os, "close", close_then_raise)
    try:
        with pytest.raises(OSError) as refused:
            template.copy_to(target)
        assert refused.value is close_error
        assert len(captured) == 1 and disposed == [captured[0].engine]
        assert len(injected) == 1 and close_calls.count(injected[0]) == 1
        assert not target.exists()
        assert all(
            not Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
        )
        assert _witness(root / "fresh.sqlite") == source_before[0]
        with pytest.raises(RuntimeError, match="^fresh_ar6_template_failed$"):
            template.copy_to(tmp_path / "retry.sqlite")
        assert len(captured) == 1 and not (tmp_path / "retry.sqlite").exists()
    finally:
        for case in captured:
            case.dispose()
        template.close()
