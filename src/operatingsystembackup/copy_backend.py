"""Copy/hardlink backend for Windows and when rsync is unusable."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from operatingsystembackup.models import DiffResult, InventoryItem

log = logging.getLogger("operatingsystembackup")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_one(src: Path, dest: Path) -> None:
    _ensure_parent(dest)
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    if src.is_symlink():
        dest.symlink_to(os.readlink(src))
        return
    shutil.copy2(src, dest, follow_symlinks=False)


def hardlink_or_copy(src: Path, dest: Path) -> None:
    _ensure_parent(dest)
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    try:
        os.link(src, dest)
        return
    except OSError:
        copy_one(src, dest)


def materialize(
    items: list[InventoryItem],
    dest_root: Path,
    *,
    diff: DiffResult | None = None,
    parent_root: Path | None = None,
    kind: str = "full",
    dry_run: bool = False,
) -> None:
    """Build a complete snapshot tree at dest_root.

    Full copies every source file. Incremental copies added/changed files and
    hardlinks unchanged files from parent_root when possible.
    """
    if dry_run:
        log.info("copy backend dry-run: %s files", len(items))
        return
    dest_root.mkdir(parents=True, exist_ok=True)
    if kind == "full" or diff is None or parent_root is None:
        for item in items:
            copy_one(item.abs_path, dest_root / item.relpath)
        return
    for item in [*diff.added, *diff.changed]:
        copy_one(item.abs_path, dest_root / item.relpath)
    for item in diff.unchanged:
        parent_file = parent_root / item.relpath
        target = dest_root / item.relpath
        if parent_file.exists() or parent_file.is_symlink():
            hardlink_or_copy(parent_file, target)
        else:
            copy_one(item.abs_path, target)


def copy_tree(src: Path, dest: Path, *, dry_run: bool = False) -> None:
    if dry_run:
        log.info("would copy %s -> %s", src, dest)
        return
    dest.mkdir(parents=True, exist_ok=True)
    # Path.is_dir() follows symlinks, so a `latest` snapshot link copies as a tree
    # instead of restoring a single symlink named "latest".
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True, symlinks=True, ignore_dangling_symlinks=True)
        return
    copy_one(src, dest / src.name)
