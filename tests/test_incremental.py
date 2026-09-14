from __future__ import annotations

from datetime import datetime, timezone

from operatingsystembackup.incremental import apply_retention, diff_against_parent, select_parent
from operatingsystembackup.models import FileRecord, InventoryItem, ManifestSummary
from operatingsystembackup.backup_engine import run_backup
from operatingsystembackup.models import BackupRequest
from operatingsystembackup.platforms.macos import MacOSAdapter


def test_parent_missing_forces_full():
    assert select_parent([], force_full=False) is None
    assert select_parent(
        [ManifestSummary("a", "2020", "full", None, "partial", "internal", "/x")],
        force_full=False,
    ) is None


def test_diff_added_changed_deleted(tmp_path):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    changed = tmp_path / "changed.txt"
    old.write_text("o", encoding="utf-8")
    new.write_text("n", encoding="utf-8")
    changed.write_text("c2", encoding="utf-8")
    current = [
        InventoryItem("new.txt", new, new.stat().st_size, new.stat().st_mtime_ns, new.stat().st_mode),
        InventoryItem("changed.txt", changed, changed.stat().st_size, changed.stat().st_mtime_ns, changed.stat().st_mode),
    ]
    parent = {
        "old.txt": FileRecord("old.txt", 1, 1, 0o644, status="added"),
        "changed.txt": FileRecord("changed.txt", 99, 1, 0o644, sha256="dead", status="added"),
    }
    diff = diff_against_parent(current, parent)
    assert [i.relpath for i in diff.added] == ["new.txt"]
    assert [i.relpath for i in diff.changed] == ["changed.txt"]
    assert [r.path for r in diff.deleted] == ["old.txt"]


def test_retention_deletes_oldest_chain():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    history = [
        ManifestSummary("old", "2026-01-01T00:00:00+00:00", "full", None, "complete", "internal", "p"),
        ManifestSummary("new", "2026-09-01T00:00:00+00:00", "full", None, "complete", "internal", "p"),
    ]
    doomed = apply_retention(history, max_backups=1, now=now)
    assert len(doomed) == 1
    assert doomed[0][0].backup_id == "old"


def test_two_copy_backups_incremental(tmp_path, force_copy):
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.txt").write_text("keep", encoding="utf-8")
    (src / "gone.txt").write_text("gone", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    cfg = {}
    adapter = MacOSAdapter()
    first = run_backup(
        BackupRequest(
            destination_type="internal",
            destination=dest,
            sources=[src],
            excludes=[],
            incremental=True,
            yes=True,
            platform="macos",
        ),
        cfg,
        adapter=adapter,
    )
    assert first.kind == "full"
    (src / "gone.txt").unlink()
    (src / "keep.txt").write_text("keep2", encoding="utf-8")
    (src / "added.txt").write_text("new", encoding="utf-8")
    second = run_backup(
        BackupRequest(
            destination_type="internal",
            destination=dest,
            sources=[src],
            excludes=[],
            incremental=True,
            yes=True,
            platform="macos",
        ),
        cfg,
        adapter=adapter,
    )
    assert second.kind == "incremental"
    assert second.parent_id == first.backup_id
    assert second.counts["added"] >= 1
    assert second.counts["deleted"] >= 1
    assert second.counts["changed"] >= 1
    snap = dest / "osbackup"
    latest = snap / "latest"
    assert latest.exists() or (snap / "latest.json").exists()
