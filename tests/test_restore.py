from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from operatingsystembackup.destinations.cloud import CloudDestination, MemoryCloudProvider
from operatingsystembackup.destinations.local import LocalDriveDestination
from operatingsystembackup.destinations.zip_home import ZipHomeDestination
from operatingsystembackup.errors import ArchiveError
from operatingsystembackup.restore import extract_zip, restore, safe_extract_path


def test_zip_path_traversal_rejected(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil", "nope")
        zf.writestr("/abs", "nope")
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ArchiveError):
        extract_zip(archive, out)


def test_safe_extract_path(tmp_path):
    with pytest.raises(ArchiveError):
        safe_extract_path(tmp_path, "../evil")
    dest = safe_extract_path(tmp_path, "home/user/file.txt")
    assert dest.is_relative_to(tmp_path.resolve())


def test_zip_restore_applies_delete(tmp_path, force_copy):
    from operatingsystembackup.backup_engine import run_backup
    from operatingsystembackup.models import BackupRequest
    from operatingsystembackup.platforms.macos import MacOSAdapter

    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.txt").write_text("k", encoding="utf-8")
    (src / "drop.txt").write_text("d", encoding="utf-8")
    zdir = tmp_path / "zips"
    adapter = MacOSAdapter()
    first = run_backup(
        BackupRequest(
            destination_type="zip-home",
            destination=None,
            sources=[src],
            excludes=[],
            yes=True,
            zip_dir=zdir,
            platform="macos",
        ),
        {"archive": {"zip_dir": str(zdir)}},
        adapter=adapter,
    )
    (src / "drop.txt").unlink()
    second = run_backup(
        BackupRequest(
            destination_type="zip-home",
            destination=None,
            sources=[src],
            excludes=[],
            yes=True,
            zip_dir=zdir,
            platform="macos",
        ),
        {"archive": {"zip_dir": str(zdir)}},
        adapter=adapter,
    )
    assert second.kind == "incremental"
    dest = ZipHomeDestination(zdir, sources=[src], platform="macos", distro="macos")
    out = tmp_path / "restored"
    restore(dest, second.backup_id, out)
    names = {p.name for p in out.rglob("*.txt")}
    assert "keep.txt" in names
    assert "drop.txt" not in names


def test_local_backup_then_restore_incremental(tmp_path, force_copy):
    from operatingsystembackup.backup_engine import run_backup
    from operatingsystembackup.models import BackupRequest
    from operatingsystembackup.platforms.macos import MacOSAdapter

    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.txt").write_text("keep", encoding="utf-8")
    (src / "gone.txt").write_text("gone", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    adapter = MacOSAdapter()
    request_kw = dict(
        destination_type="internal",
        destination=dest,
        sources=[src],
        excludes=[],
        incremental=True,
        yes=True,
        platform="macos",
    )
    first = run_backup(BackupRequest(**request_kw), {}, adapter=adapter)
    assert first.kind == "full"

    (src / "gone.txt").unlink()
    (src / "keep.txt").write_text("keep2", encoding="utf-8")
    (src / "added.txt").write_text("new", encoding="utf-8")
    second = run_backup(BackupRequest(**request_kw), {}, adapter=adapter)
    assert second.kind == "incremental"
    assert second.parent_id == first.backup_id

    local = LocalDriveDestination(dest, kind="internal", sources=[src])
    latest = dest / "osbackup" / "latest"
    assert latest.is_symlink() or (dest / "osbackup" / "latest.json").is_file()

    for backup_id in (first.backup_id, second.backup_id):
        located = local.locate(backup_id)
        assert located is not None
        assert located.name != "latest"
        assert not located.is_symlink()
        assert located.name.endswith(f"-{backup_id}")

    full_out = tmp_path / "restore-full"
    restore(local, first.backup_id, full_out)
    assert not (full_out / "latest").exists()
    full_names = {p.name for p in full_out.rglob("*.txt")}
    assert full_names >= {"keep.txt", "gone.txt"}
    keep_full = next(full_out.rglob("keep.txt"))
    assert keep_full.read_text(encoding="utf-8") == "keep"

    inc_out = tmp_path / "restore-inc"
    restore(local, second.backup_id, inc_out)
    assert not (inc_out / "latest").exists()
    inc_txt = {p.name: p.read_text(encoding="utf-8") for p in inc_out.rglob("*.txt")}
    assert inc_txt["keep.txt"] == "keep2"
    assert inc_txt["added.txt"] == "new"
    assert "gone.txt" not in inc_txt


def test_cloud_upload_manifest_last(tmp_path, force_copy):
    from operatingsystembackup.backup_engine import run_backup
    from operatingsystembackup.models import BackupRequest
    from operatingsystembackup.platforms.macos import MacOSAdapter

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a", encoding="utf-8")
    provider = MemoryCloudProvider()
    original_upload = provider.upload
    order: list[str] = []

    def tracking(local, key):
        order.append(key)
        original_upload(local, key)

    provider.upload = tracking  # type: ignore[method-assign]
    result = run_backup(
        BackupRequest(
            destination_type="cloud",
            destination=None,
            sources=[src],
            excludes=[],
            yes=True,
            platform="macos",
        ),
        {"cloud": {"provider": "s3", "bucket": "test", "prefix": "osbackup"}},
        adapter=MacOSAdapter(),
        cloud_provider=provider,
    )
    assert result.backup_id
    assert order
    assert order[-1].endswith("manifest.json")
    dest = CloudDestination(provider, prefix="osbackup", sources=[src])
    history = dest.list_history()
    assert any(item.backup_id == result.backup_id for item in history)
    out = tmp_path / "cloud-restore"
    restore(dest, result.backup_id, out)
    assert list(out.rglob("a.txt"))
