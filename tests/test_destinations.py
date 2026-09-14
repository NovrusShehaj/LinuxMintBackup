from __future__ import annotations

import pytest

from operatingsystembackup.destinations.local import CONTAINER, LocalDriveDestination
from operatingsystembackup.errors import DestinationLoopError, UnwritableDestinationError
from operatingsystembackup.fsutil import refuse_destination_loop
from operatingsystembackup.manifest import dump_manifest
from operatingsystembackup.models import FileRecord, Manifest


def test_dest_inside_source(tmp_path):
    src = tmp_path / "home"
    src.mkdir()
    dest = src / "backups"
    dest.mkdir()
    with pytest.raises(DestinationLoopError):
        refuse_destination_loop(dest, [src])
    report = LocalDriveDestination(dest, kind="internal", sources=[src]).validate()
    assert not report.ok
    with pytest.raises(UnwritableDestinationError):
        report.raise_if_failed()


def test_internal_writable(tmp_path):
    dest = tmp_path / "backup"
    dest.mkdir()
    report = LocalDriveDestination(dest, kind="internal", sources=[tmp_path / "src"]).validate()
    assert report.ok


def test_external_same_device_warning(tmp_path):
    dest = tmp_path / "disk"
    dest.mkdir()
    report = LocalDriveDestination(dest, kind="external", sources=[]).validate()
    assert report.ok
    if report.same_device_as_home:
        assert report.warnings


def _complete_manifest(backup_id: str) -> Manifest:
    return Manifest(
        schema_version=1,
        app="OperatingSystemBackup",
        backup_id=backup_id,
        parent_id=None,
        kind="full",
        timestamp="2026-09-14T16:00:00+00:00",
        platform={"os": "macos", "family": "macos", "distro": "macos"},
        hostname="test",
        sources=["/tmp/src"],
        excludes=[],
        destination_kind="internal",
        counts={"added": 1, "changed": 0, "deleted": 0, "unchanged": 0},
        state="complete",
        files=[FileRecord("extra/src/keep.txt", 4, 1, 0o644, status="added")],
    )


def test_locate_ignores_latest_symlink_and_latest_json(tmp_path):
    dest = tmp_path / "backup"
    container = dest / CONTAINER
    snapshot = container / "2026-09-14_16-00-00-ab12cd34"
    snapshot.mkdir(parents=True)
    (snapshot / "extra" / "src").mkdir(parents=True)
    (snapshot / "extra" / "src" / "keep.txt").write_text("keep", encoding="utf-8")
    dump_manifest(_complete_manifest("ab12cd34"), snapshot)
    (container / "latest.json").write_text('{"backup_id": "ab12cd34"}\n', encoding="utf-8")
    (container / "latest").symlink_to(snapshot.name)

    local = LocalDriveDestination(dest, kind="internal")
    located = local.locate("ab12cd34")
    assert located is not None
    assert located.resolve() == snapshot.resolve()
    assert located.name != "latest"
    assert not located.is_symlink()
    history_ids = [item.backup_id for item in local.list_history()]
    assert history_ids == ["ab12cd34"]
