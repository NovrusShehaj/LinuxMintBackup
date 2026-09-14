"""External and internal local-drive destinations (one copy engine, kind flag for UX)."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from operatingsystembackup.errors import ArchiveError, IncompatibleManifestError
from operatingsystembackup.fsutil import (
    dest_inside_source,
    ensure_dir,
    free_bytes,
    is_writable_dir,
    resolve_path,
    same_mount,
)
from operatingsystembackup.manifest import load_manifest, looks_like_legacy_stamp, summarize
from operatingsystembackup.models import Manifest, ManifestSummary, StagingLocation, ValidationReport

log = logging.getLogger("operatingsystembackup")

CONTAINER = "osbackup"
LATEST_LINK = "latest"
LATEST_JSON = "latest.json"


def is_management_entry(path: Path) -> bool:
    """True for dest-root bookkeeping such as latest/, latest.json, and temps."""
    name = path.name
    return name in {LATEST_LINK, LATEST_JSON} or name.startswith("partial-") or name.startswith(".")


def is_snapshot_directory(path: Path) -> bool:
    """Real snapshot dirs only; never follow management symlinks such as latest."""
    if is_management_entry(path) or path.is_symlink():
        return False
    return path.is_dir()


class LocalDriveDestination:
    def __init__(
        self,
        root: Path | str,
        *,
        kind: str = "internal",
        sources: list[Path] | None = None,
        use_symlink: bool | None = None,
    ) -> None:
        self.root = resolve_path(root)
        self.kind = kind
        self.sources = list(sources or [])
        if use_symlink is None:
            use_symlink = os.name != "nt"
        self.use_symlink = use_symlink

    @property
    def container(self) -> Path:
        return self.root / CONTAINER

    def validate(self) -> ValidationReport:
        messages: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []
        path = self.root
        if not path.exists():
            parent = path.parent
            if not parent.exists():
                errors.append(f"destination does not exist and parent is missing: {path}")
            elif not is_writable_dir(parent):
                errors.append(f"cannot create destination {path}: parent is not writable")
            else:
                messages.append(f"{path} does not exist yet and will be created")
        elif not path.is_dir():
            errors.append(f"destination is not a directory: {path}")
        elif not is_writable_dir(path):
            errors.append(f"destination is not writable: {path}")

        if self.sources:
            hit = dest_inside_source(path, self.sources)
            if hit is not None:
                errors.append(
                    f"destination {path} is inside source {resolve_path(hit)}; "
                    "choose a path outside the backup sources"
                )

        leftover = []
        if self.container.is_dir():
            leftover = sorted(p.name for p in self.container.glob("partial-*") if p.is_dir())
            leftover += sorted(p.name for p in self.container.glob("*.partial"))
        if leftover:
            warnings.append("leftover partial snapshots (ignored by history): " + ", ".join(leftover[:8]))

        same_home = bool(same_mount(path, Path.home())) if path.exists() or path.parent.exists() else False
        if self.kind == "external" and same_home:
            warnings.append(
                "this looks like the same disk as $HOME; an external drive is usually a different "
                "mount. Continuing is allowed (pass --yes in interactive mode)."
            )
        free = free_bytes(path if path.exists() else path.parent)
        return ValidationReport(
            ok=not errors,
            messages=messages,
            warnings=warnings,
            errors=errors,
            free_bytes=free,
            same_device_as_home=same_home,
        )

    def prepare_backup(self, backup_id: str, *, stamp: str) -> StagingLocation:
        ensure_dir(self.container)
        partial = self.container / f"partial-{backup_id}"
        if partial.exists():
            shutil.rmtree(partial)
        ensure_dir(partial)
        final = self.container / f"{stamp}-{backup_id}"
        if final.exists():
            raise ArchiveError(f"snapshot path already exists: {final}")
        return StagingLocation(path=partial, backup_id=backup_id, final_path=final, stamp=stamp)

    def commit(self, staging: StagingLocation) -> Path:
        final = staging.final_path
        if final is None:
            raise ArchiveError("staging is missing final_path")
        if final.exists():
            raise ArchiveError(f"refusing to overwrite snapshot {final}")
        os.replace(staging.path, final)
        staging.is_partial = False
        self._update_latest(final, staging.backup_id)
        return final

    def abort(self, staging: StagingLocation) -> None:
        if staging.path.exists() and staging.is_partial:
            shutil.rmtree(staging.path, ignore_errors=True)

    def _update_latest(self, snapshot: Path, backup_id: str) -> None:
        payload = {"backup_id": backup_id, "directory": snapshot.name}
        json_path = self.container / LATEST_JSON
        tmp_json = self.container / f".{LATEST_JSON}.tmp"
        tmp_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_json, json_path)
        if not self.use_symlink:
            return
        latest = self.container / LATEST_LINK
        tmp = self.container / f".latest.{os.getpid()}.tmp"
        try:
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            tmp.symlink_to(snapshot.name)
            os.replace(tmp, latest)
        except OSError as exc:
            log.warning("could not update latest symlink (%s); latest.json is authoritative", exc)
            if tmp.exists() or tmp.is_symlink():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def list_history(self) -> list[ManifestSummary]:
        found: list[ManifestSummary] = []
        if self.container.is_dir():
            for child in sorted(self.container.iterdir()):
                if not is_snapshot_directory(child):
                    continue
                manifest_path = child / "manifest.json"
                if not manifest_path.is_file():
                    continue
                try:
                    manifest = load_manifest(manifest_path)
                except IncompatibleManifestError as exc:
                    log.warning("%s", exc)
                    continue
                found.append(summarize(manifest, child))
        if self.root.is_dir():
            for child in sorted(self.root.iterdir()):
                if child.name == CONTAINER or not child.is_dir():
                    continue
                if looks_like_legacy_stamp(child.name) and not (child / "manifest.json").is_file():
                    found.append(
                        ManifestSummary(
                            backup_id=child.name,
                            timestamp=child.name.replace("_", "T"),
                            kind="full",
                            parent_id=None,
                            state="complete",
                            destination_kind=self.kind,
                            path=str(child),
                            legacy=True,
                        )
                    )
        return found

    def locate(self, backup_id: str) -> Path | None:
        if not self.container.is_dir():
            return None
        for child in self.container.iterdir():
            if not is_snapshot_directory(child):
                continue
            if child.name == backup_id or child.name.endswith(f"-{backup_id}"):
                return child
            manifest_path = child / "manifest.json"
            if manifest_path.is_file():
                try:
                    if load_manifest(manifest_path).backup_id == backup_id:
                        return child
                except IncompatibleManifestError:
                    continue
        return None

    def open_manifest(self, backup_id: str) -> Manifest:
        located = self.locate(backup_id)
        if located is None:
            raise IncompatibleManifestError(f"backup {backup_id} not found under {self.container}")
        return load_manifest(located / "manifest.json")

    def delete_backup(self, backup_id: str) -> None:
        located = self.locate(backup_id)
        if located is None:
            return
        resolved = resolve_path(located)
        container = resolve_path(self.container)
        if resolved == container or resolved == resolve_path(self.root):
            raise ArchiveError("refusing to delete destination root")
        if resolved.parent != container:
            raise ArchiveError(f"refusing to delete unmanaged path {resolved}")
        if not (resolved.name.endswith(f"-{backup_id}") or resolved.name == backup_id):
            try:
                if load_manifest(resolved / "manifest.json").backup_id != backup_id:
                    raise ArchiveError(f"snapshot {resolved} does not match backup id {backup_id}")
            except IncompatibleManifestError as exc:
                raise ArchiveError(str(exc)) from exc
        log.info("retention deleting %s", resolved)
        shutil.rmtree(resolved)
