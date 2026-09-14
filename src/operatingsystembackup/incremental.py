"""Parent selection, change detection, backup ids, and chain retention."""

from __future__ import annotations

import logging
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from operatingsystembackup.errors import IncompatibleManifestError
from operatingsystembackup.manifest import chain_root_id
from operatingsystembackup.models import DiffResult, FileRecord, InventoryItem, Manifest, ManifestSummary
from operatingsystembackup.sources import hash_file

log = logging.getLogger("operatingsystembackup")


def new_backup_id() -> str:
    return secrets.token_hex(4)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp_prefix(moment: datetime | None = None) -> str:
    moment = moment or utc_now()
    return moment.strftime("%Y-%m-%d_%H-%M-%S")


def snapshot_dir_name(backup_id: str, moment: datetime | None = None) -> str:
    return f"{stamp_prefix(moment)}-{backup_id}"


def zip_stem(platform: str, distro: str, backup_id: str, moment: datetime | None = None) -> str:
    moment = moment or utc_now()
    stamp = moment.strftime("%Y%m%dT%H%M%S")
    plat = (platform or "unknown").replace("/", "-")
    dist = (distro or "unknown").replace("/", "-")
    return f"osbackup-{plat}-{dist}-{stamp}-{backup_id}"


def complete_backups(history: list[ManifestSummary]) -> list[ManifestSummary]:
    return [item for item in history if item.state == "complete" and not item.legacy]


def newest_complete(history: list[ManifestSummary]) -> ManifestSummary | None:
    complete = complete_backups(history)
    if not complete:
        return None
    return sorted(complete, key=lambda item: (item.timestamp, item.backup_id))[-1]


def select_parent(history: list[ManifestSummary], *, force_full: bool = False) -> ManifestSummary | None:
    if force_full:
        return None
    return newest_complete(history)


def reconstruct_inventory(chain_oldest_first: list[Manifest]) -> dict[str, FileRecord]:
    index: dict[str, FileRecord] = {}
    for manifest in chain_oldest_first:
        if manifest.kind == "full":
            index = {
                record.path: record
                for record in manifest.files
                if record.status != "deleted"
            }
            continue
        for record in manifest.files:
            if record.status == "deleted":
                index.pop(record.path, None)
            else:
                index[record.path] = record
    return index


def load_parent_chain(parent_id: str, opener) -> list[Manifest]:
    chain: list[Manifest] = []
    current: str | None = parent_id
    seen: set[str] = set()
    while current:
        if current in seen:
            raise IncompatibleManifestError(f"parent chain cycle involving {current}")
        seen.add(current)
        try:
            manifest = opener(current)
        except IncompatibleManifestError:
            raise
        except Exception as exc:
            raise IncompatibleManifestError(f"cannot open parent manifest {current}: {exc}") from exc
        chain.append(manifest)
        current = manifest.parent_id
    chain.reverse()
    if chain and chain[0].kind != "full" and chain[0].parent_id:
        raise IncompatibleManifestError(
            f"incomplete parent chain (oldest {chain[0].backup_id} is incremental); use --full"
        )
    return chain


def parent_file_index(parent: ManifestSummary | None, opener) -> dict[str, FileRecord]:
    if parent is None:
        return {}
    chain = load_parent_chain(parent.backup_id, opener)
    return reconstruct_inventory(chain)


def diff_against_parent(
    current: list[InventoryItem],
    parent_index: dict[str, FileRecord],
    *,
    checksum_always: bool = False,
) -> DiffResult:
    current_map = {item.relpath: item for item in current}
    added: list[InventoryItem] = []
    changed: list[InventoryItem] = []
    unchanged: list[InventoryItem] = []

    for item in current:
        previous = parent_index.get(item.relpath)
        if previous is None:
            item.status = "added"
            if not item.is_symlink:
                try:
                    item.sha256 = hash_file(item.abs_path)
                except OSError:
                    item.sha256 = None
            added.append(item)
            continue

        meta_same = (
            item.size == previous.size
            and item.mtime_ns == previous.mtime_ns
            and item.mode == previous.mode
        )
        if meta_same and not checksum_always:
            item.status = "unchanged"
            item.sha256 = previous.sha256
            unchanged.append(item)
            continue

        sha = previous.sha256
        if not item.is_symlink:
            try:
                sha = hash_file(item.abs_path)
            except OSError:
                sha = None
        item.sha256 = sha
        if sha and previous.sha256 and sha == previous.sha256 and not checksum_always:
            item.status = "unchanged"
            unchanged.append(item)
        elif meta_same and not checksum_always:
            item.status = "unchanged"
            unchanged.append(item)
        elif sha and previous.sha256 and sha == previous.sha256:
            item.status = "unchanged"
            unchanged.append(item)
        else:
            item.status = "changed"
            changed.append(item)

    deleted: list[FileRecord] = []
    for path, record in parent_index.items():
        if path not in current_map:
            deleted.append(
                FileRecord(
                    path=record.path,
                    size=record.size,
                    mtime_ns=record.mtime_ns,
                    mode=record.mode,
                    sha256=record.sha256,
                    status="deleted",
                )
            )
    deleted.sort(key=lambda rec: rec.path)
    return DiffResult(added=added, changed=changed, deleted=deleted, unchanged=unchanged)


def records_for_manifest(diff: DiffResult, *, kind: str) -> list[FileRecord]:
    records: list[FileRecord] = []
    if kind == "full":
        for item in [*diff.added, *diff.changed, *diff.unchanged]:
            records.append(_item_record(item, item.status or "added"))
        return records
    for item in diff.added:
        records.append(_item_record(item, "added"))
    for item in diff.changed:
        records.append(_item_record(item, "changed"))
    records.extend(diff.deleted)
    return records


def _item_record(item: InventoryItem, status: str) -> FileRecord:
    return FileRecord(
        path=item.relpath,
        size=item.size,
        mtime_ns=item.mtime_ns,
        mode=item.mode,
        sha256=item.sha256,
        status=status,  # type: ignore[arg-type]
    )


def apply_retention(
    history: list[ManifestSummary],
    *,
    max_backups: int = 14,
    max_days: int | None = None,
    now: datetime | None = None,
) -> list[list[ManifestSummary]]:
    """Return oldest complete chains that should be deleted.

    v1 deletes whole chains (a full backup plus incrementals that need it), never a
    middle incremental, and never the last remaining chain.
    """
    complete = complete_backups(history)
    if not complete:
        return []
    by_id = {item.backup_id: item for item in complete}
    grouped: dict[str, list[ManifestSummary]] = defaultdict(list)
    for item in complete:
        grouped[chain_root_id(item.backup_id, by_id)].append(item)

    chains: list[tuple[str, str, list[ManifestSummary]]] = []
    for root_id, members in grouped.items():
        latest = max(member.timestamp for member in members)
        chains.append((latest, root_id, members))
    chains.sort(key=lambda row: (row[0], row[1]))

    doomed_roots: set[str] = set()
    if max_days is not None and max_days > 0:
        moment = now or utc_now()
        cutoff = (moment - timedelta(days=max_days)).isoformat()
        for latest, root_id, _members in chains:
            remaining_roots = [row[1] for row in chains if row[1] not in doomed_roots]
            if latest < cutoff and len(remaining_roots) > 1:
                doomed_roots.add(root_id)

    def kept_total() -> int:
        return sum(len(members) for latest, root_id, members in chains if root_id not in doomed_roots)

    def kept_chain_count() -> int:
        return sum(1 for _latest, root_id, _members in chains if root_id not in doomed_roots)

    while max_backups > 0 and kept_total() > max_backups and kept_chain_count() > 1:
        for _latest, root_id, _members in chains:
            if root_id not in doomed_roots:
                doomed_roots.add(root_id)
                break

    to_delete = [members for _latest, root_id, members in chains if root_id in doomed_roots]
    if to_delete:
        log.info("retention will delete %s backup chain(s)", len(to_delete))
    return to_delete


def unique_zip_path(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.zip"
    n = 2
    while candidate.exists() or candidate.with_name(candidate.name + ".partial").exists():
        candidate = directory / f"{stem}-{n}.zip"
        n += 1
    return candidate
