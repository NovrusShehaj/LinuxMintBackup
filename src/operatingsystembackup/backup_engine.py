"""Backup engine: successor of backup.py run_backup."""

from __future__ import annotations

import logging
import socket
from pathlib import Path
from typing import Any

from operatingsystembackup import __app_name__
from operatingsystembackup.copy_backend import materialize as copy_materialize
from operatingsystembackup.destinations import get_destination
from operatingsystembackup.destinations.zip_home import pack_zip, write_manifest_sidecar
from operatingsystembackup.detect import detect
from operatingsystembackup.errors import (
    ArchiveError,
    IncompatibleManifestError,
    InsufficientSpaceError,
    OSBackupError,
)
from operatingsystembackup.fsutil import free_bytes, refuse_destination_loop
from operatingsystembackup.incremental import (
    apply_retention,
    diff_against_parent,
    new_backup_id,
    parent_file_index,
    records_for_manifest,
    select_parent,
    stamp_prefix,
    utc_now,
)
from operatingsystembackup.manifest import SCHEMA_VERSION, dump_manifest
from operatingsystembackup.models import BackupRequest, BackupResult, Manifest, PackageInventory
from operatingsystembackup.platforms import get_adapter
from operatingsystembackup.rsync_backend import build_command, dest_subdir_for_source, probe, sync_sources
from operatingsystembackup.sources import discover_sources, estimate_bytes, merge_excludes, merge_source_lists, walk_inventory

log = logging.getLogger("operatingsystembackup")


def resolve_adapter(request: BackupRequest, cfg: dict[str, Any]):
    system = None
    if request.platform == "linux":
        system = "Linux"
    elif request.platform in {"macos", "darwin"}:
        system = "Darwin"
    elif request.platform == "windows":
        system = "Windows"
    detection = detect(system=system)
    distro = request.distro
    family = request.family
    platform = request.platform
    if not any((distro, family, platform)) and not detection.ok:
        distro = cfg.get("default_distro")
        family = cfg.get("default_family")
        platform = cfg.get("default_platform")
    adapter, warning = get_adapter(
        distro_id=distro,
        family=family,
        detection=detection,
        platform=platform,
    )
    return adapter, detection, warning


def write_metadata(root: Path, inventory: PackageInventory) -> None:
    for rel, content in inventory.files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _use_rsync(adapter) -> bool:
    if getattr(adapter, "family_id", "") == "windows":
        return False
    if not adapter.rsync_supported():
        return False
    return probe().available


def run_backup(
    request: BackupRequest,
    cfg: dict[str, Any] | None = None,
    *,
    adapter=None,
    cloud_provider=None,
) -> BackupResult:
    cfg = cfg or {}
    warning = None
    detection = None
    if adapter is None:
        adapter, detection, warning = resolve_adapter(request, cfg)
        if warning:
            log.warning("%s", warning)
    else:
        detection = detect()

    requested_sources = merge_source_lists(
        adapter.default_sources(),
        cfg.get("sources") or None,
        request.sources or None,
    )
    excludes = merge_excludes(
        adapter.default_excludes(),
        cfg.get("exclude") or None,
        request.excludes or None,
    )
    dest_path = request.destination
    if dest_path is not None:
        excludes = merge_excludes(excludes, [str(dest_path)], None)
        refuse_destination_loop(dest_path, requested_sources)

    sources, skipped_sources = discover_sources(requested_sources, strict=request.strict_sources)

    zip_dir = request.zip_dir
    dest = get_destination(
        request.destination_type,
        path=dest_path,
        sources=sources,
        config=cfg,
        zip_dir=zip_dir,
        cloud_provider=cloud_provider,
    )
    if request.destination_type == "zip-home":
        dest.platform = getattr(adapter, "family_id", None) or (detection.os_name if detection else "unknown")
        dest.distro = getattr(adapter, "distro_id", None) or "unknown"
        excludes = merge_excludes(excludes, [str(dest.directory)], None)

    report = dest.validate()
    for item in report.warnings:
        log.warning("%s", item)
    for item in report.messages:
        log.info("%s", item)
    report.raise_if_failed()

    items, walk_skipped = walk_inventory(
        sources,
        excludes,
        dest=dest_path if dest_path is not None else getattr(dest, "directory", None),
    )
    estimate = estimate_bytes(items)
    space_path = dest_path
    if request.destination_type == "zip-home":
        space_path = dest.directory
    if space_path is not None:
        free = free_bytes(space_path)
        if free is not None:
            if request.destination_type == "zip-home" and free < max(estimate * 0.5, 1):
                raise InsufficientSpaceError(
                    f"not enough free space at {space_path}: {free} bytes free, uncompressed estimate {estimate}"
                )
            if request.destination_type in {"internal", "external"} and free < 1_000_000:
                raise InsufficientSpaceError(f"destination {space_path} has less than 1 MiB free")
            if request.destination_type in {"internal", "external"} and estimate and free < estimate:
                log.warning(
                    "free space (%s) may be below uncompressed source size (%s); hardlinked incrementals need less",
                    free,
                    estimate,
                )

    force_full = not request.incremental
    history = dest.list_history()
    parent = None
    parent_index = {}
    try:
        parent = select_parent(history, force_full=force_full)
        if parent is not None:
            parent_index = parent_file_index(parent, dest.open_manifest)
    except IncompatibleManifestError as exc:
        log.warning("%s; creating a full backup", exc)
        parent = None
        parent_index = {}
        force_full = True

    kind = "full" if parent is None else "incremental"
    checksum_always = request.checksum_always or (cfg.get("incremental") or {}).get("checksum") == "always"
    diff = diff_against_parent(items, parent_index, checksum_always=checksum_always)
    if kind == "full":
        from operatingsystembackup.models import DiffResult

        for item in items:
            item.status = "added"
        diff = DiffResult(added=list(items), changed=[], deleted=[], unchanged=[], skipped=walk_skipped)
    diff.skipped = walk_skipped

    backup_id = new_backup_id()
    moment = utc_now()
    stamp = stamp_prefix(moment)
    platform_meta = {
        "os": getattr(detection, "os_name", None) or getattr(adapter, "family_id", ""),
        "family": getattr(adapter, "family_id", ""),
        "distro": getattr(adapter, "distro_id", ""),
    }

    packages = PackageInventory()
    if not request.dry_run:
        try:
            packages = adapter.collect_package_inventory()
        except OSBackupError as exc:
            packages.warnings.append(str(exc))
        except Exception as exc:  # optional metadata must not abort the file backup
            packages.warnings.append(f"package inventory failed: {exc}")
        for pkg_warn in packages.warnings:
            log.warning("%s", pkg_warn)

    manifest = Manifest(
        schema_version=SCHEMA_VERSION,
        app=__app_name__,
        backup_id=backup_id,
        parent_id=None if kind == "full" else (parent.backup_id if parent else None),
        kind=kind,
        timestamp=moment.isoformat(),
        platform=platform_meta,
        hostname=socket.gethostname(),
        sources=[str(path) for path in sources],
        excludes=list(excludes),
        destination_kind=request.destination_type,
        counts=diff.counts,
        state="complete" if request.dry_run else "partial",
        directory=None,
        files=records_for_manifest(diff, kind=kind),
    )

    if request.dry_run:
        planned = None
        if request.destination_type == "zip-home":
            planned = dest.directory / dest.planned_name(backup_id, stamp)
        elif request.destination_type in {"internal", "external"}:
            planned = dest.container / f"{stamp}-{backup_id}"
        log.info(
            "OperatingSystemBackup: dry-run backup %s (%s) added=%s changed=%s deleted=%s unchanged=%s dest=%s",
            backup_id,
            kind,
            diff.counts["added"],
            diff.counts["changed"],
            diff.counts["deleted"],
            diff.counts["unchanged"],
            planned,
        )
        if _use_rsync(adapter) and request.destination_type in {"internal", "external"}:
            parent_snap = dest.locate(parent.backup_id) if parent else None
            for source in sources:
                prefix, dest_dir = dest_subdir_for_source(planned or Path("."), source)
                link = (parent_snap / prefix) if parent_snap is not None else None
                cmd = build_command(source, dest_dir, excludes, link_dest=link if link and link.is_dir() else None, dry_run=True)
                log.info("would run: %s", " ".join(cmd))
        return BackupResult(
            backup_id=backup_id,
            kind=kind,
            destination=planned,
            dry_run=True,
            counts=diff.counts,
            parent_id=manifest.parent_id,
            warnings=list(packages.warnings),
            skipped_sources=skipped_sources,
            package_warnings=list(packages.warnings),
        )

    staging = dest.prepare_backup(backup_id, stamp=stamp)
    published: Path | None = None
    try:
        if request.destination_type in {"internal", "external"}:
            parent_snap = dest.locate(parent.backup_id) if parent else None
            if _use_rsync(adapter):
                try:
                    sync_sources(
                        sources,
                        staging.path,
                        excludes,
                        parent_snapshot=parent_snap,
                        dry_run=False,
                    )
                except OSBackupError as exc:
                    log.warning("rsync failed (%s); falling back to copy backend", exc)
                    copy_materialize(
                        items,
                        staging.path,
                        diff=diff,
                        parent_root=parent_snap,
                        kind=kind,
                    )
            else:
                copy_materialize(
                    items,
                    staging.path,
                    diff=diff,
                    parent_root=parent_snap,
                    kind=kind,
                )
            write_metadata(staging.path, packages)
            manifest.state = "complete"
            manifest.directory = str(staging.final_path or staging.path)
            dump_manifest(manifest, staging.path)
            published = dest.commit(staging)
            manifest.directory = str(published)
        elif request.destination_type == "zip-home":
            file_items = items if kind == "full" else [*diff.added, *diff.changed]
            file_map = [(item.relpath, item.abs_path) for item in file_items]
            manifest.state = "complete"
            pack_zip(
                staging.path,
                file_map,
                manifest=manifest,
                metadata=packages.files,
                compression=dest.compression,
            )
            published = dest.commit(staging)
            manifest.directory = str(published)
            write_manifest_sidecar(published, manifest)
        else:
            file_items = items if kind == "full" else [*diff.added, *diff.changed]
            file_map = [(item.relpath, item.abs_path) for item in file_items]
            pack_name = "full.zip" if kind == "full" else "delta.zip"
            manifest.state = "complete"
            pack_zip(
                staging.path / pack_name,
                file_map,
                manifest=manifest,
                metadata=packages.files,
            )
            dump_manifest(manifest, staging.path)
            published = dest.commit(staging)
            manifest.directory = str(published)
    except Exception:
        dest.abort(staging)
        raise

    log.info(
        "OperatingSystemBackup: backup %s succeeded (%s) added=%s changed=%s deleted=%s unchanged=%s",
        backup_id,
        kind,
        diff.counts["added"],
        diff.counts["changed"],
        diff.counts["deleted"],
        diff.counts["unchanged"],
    )

    inc = cfg.get("incremental") or {}
    try:
        doomed = apply_retention(
            dest.list_history(),
            max_backups=int(inc.get("retention_max_backups") or 14),
            max_days=inc.get("retention_max_days"),
            now=moment,
        )
        for chain in doomed:
            for summary in chain:
                if summary.backup_id == backup_id:
                    continue
                dest.delete_backup(summary.backup_id)
    except (OSError, ArchiveError, OSBackupError) as exc:
        log.warning("retention skipped: %s", exc)

    return BackupResult(
        backup_id=backup_id,
        kind=kind,
        destination=published,
        dry_run=False,
        counts=diff.counts,
        parent_id=manifest.parent_id,
        warnings=list(packages.warnings),
        skipped_sources=skipped_sources,
        package_warnings=list(packages.warnings),
    )
