from __future__ import annotations

from pathlib import Path

from operatingsystembackup.backup_engine import run_backup
from operatingsystembackup.destinations.zip_home import ZipHomeDestination, read_zip_manifest
from operatingsystembackup.models import BackupRequest
from operatingsystembackup.platforms.macos import MacOSAdapter
from operatingsystembackup.restore import restore


def test_zip_dry_run_names_file(tmp_path, force_copy):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.txt").write_text("hi", encoding="utf-8")
    zdir = tmp_path / "zips"
    request = BackupRequest(
        destination_type="zip-home",
        destination=None,
        sources=[src],
        excludes=[],
        dry_run=True,
        yes=True,
        zip_dir=zdir,
        platform="macos",
    )
    result = run_backup(request, {"archive": {"zip_dir": str(zdir)}}, adapter=MacOSAdapter())
    assert result.dry_run
    assert result.destination is not None
    assert str(result.destination).endswith(".zip")
    assert not zdir.exists() or not list(zdir.glob("*.zip"))


def test_zip_create_and_restore(tmp_path, force_copy):
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.txt").write_text("hello", encoding="utf-8")
    zdir = tmp_path / "zips"
    request = BackupRequest(
        destination_type="zip-home",
        destination=None,
        sources=[src],
        excludes=[],
        incremental=False,
        yes=True,
        zip_dir=zdir,
        platform="macos",
    )
    result = run_backup(request, {"archive": {"zip_dir": str(zdir), "compression": "deflate"}}, adapter=MacOSAdapter())
    assert result.kind == "full"
    archive = Path(result.destination)
    assert archive.is_file()
    manifest = read_zip_manifest(archive)
    assert manifest.state == "complete"
    assert any(rec.path.endswith("hello.txt") for rec in manifest.files)
    dest = ZipHomeDestination(zdir, sources=[src], platform="macos", distro="macos")
    out = tmp_path / "restored"
    restore(dest, result.backup_id, out)
    restored = list(out.rglob("hello.txt"))
    assert restored
    assert restored[0].read_text(encoding="utf-8") == "hello"
