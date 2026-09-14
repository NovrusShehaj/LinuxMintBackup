"""Restore from local snapshots, ZIP chains, and cloud packs."""

from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path

from operatingsystembackup.copy_backend import copy_tree
from operatingsystembackup.destinations.zip_home import validate_arcname
from operatingsystembackup.errors import ArchiveError, IncompatibleManifestError
from operatingsystembackup.incremental import load_parent_chain
from operatingsystembackup.models import FileRecord, Manifest
from operatingsystembackup.sources import is_relative_to

log = logging.getLogger("operatingsystembackup")


def safe_extract_path(root: Path, member: str) -> Path:
    name = validate_arcname(member)
    dest = (root / name).resolve()
    if not is_relative_to(dest, root.resolve()):
        raise ArchiveError(f"refusing to extract {member!r} outside {root}")
    return dest


def apply_deletions(root: Path, records: list[FileRecord], *, dry_run: bool = False) -> int:
    count = 0
    for record in records:
        if record.status != "deleted":
            continue
        target = safe_extract_path(root, record.path)
        if dry_run:
            count += 1
            continue
        if target.is_symlink() or target.is_file():
            target.unlink()
            count += 1
        elif target.is_dir():
            shutil.rmtree(target)
            count += 1
    return count


def extract_zip(archive: Path, target: Path, *, dry_run: bool = False) -> None:
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/"):
                    continue
                if name.startswith("OSBACKUP/"):
                    continue
                dest = safe_extract_path(target, name)
                if dry_run:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"corrupt zip {archive}: {exc}") from exc


def restore(
    destination,
    backup_id: str,
    target: Path,
    *,
    dry_run: bool = False,
) -> Manifest:
    manifest = destination.open_manifest(backup_id)
    if manifest.state != "complete":
        raise IncompatibleManifestError(f"backup {backup_id} is not complete (state={manifest.state})")
    target = Path(target)
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)

    kind = getattr(destination, "kind", "")
    if kind in {"internal", "external"}:
        snapshot = destination.locate(backup_id)
        if snapshot is None:
            raise IncompatibleManifestError(f"snapshot directory for {backup_id} is missing")
        log.info("OperatingSystemBackup: restoring local snapshot %s -> %s", snapshot, target)
        copy_tree(snapshot, target, dry_run=dry_run)
        return manifest

    chain = load_parent_chain(backup_id, destination.open_manifest)
    if kind == "zip-home":
        for item in chain:
            archive = destination.locate(item.backup_id)
            if archive is None:
                raise IncompatibleManifestError(f"zip for {item.backup_id} is missing")
            log.info("OperatingSystemBackup: applying zip %s", archive)
            extract_zip(archive, target, dry_run=dry_run)
            apply_deletions(target, item.files, dry_run=dry_run)
        return manifest

    if kind == "cloud":
        import tempfile

        with tempfile.TemporaryDirectory(prefix="osbackup-restore-") as tmp:
            tmp_path = Path(tmp)
            for item in chain:
                prefix = destination.object_prefix(item.backup_id)
                pack_name = "full.zip" if item.kind == "full" else "delta.zip"
                local_pack = tmp_path / f"{item.backup_id}-{pack_name}"
                destination.provider.download(f"{prefix}/{pack_name}", local_pack)
                extract_zip(local_pack, target, dry_run=dry_run)
                apply_deletions(target, item.files, dry_run=dry_run)
        return manifest

    raise ArchiveError(f"cannot restore destination kind {kind!r}")
