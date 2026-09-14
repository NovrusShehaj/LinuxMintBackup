"""Home-directory ZIP archives (full and incremental packs)."""

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path

from operatingsystembackup.errors import ArchiveError, IncompatibleManifestError
from operatingsystembackup.fsutil import dest_inside_source, ensure_dir, free_bytes, is_writable_dir, resolve_path
from operatingsystembackup.incremental import unique_zip_path, zip_stem
from operatingsystembackup.manifest import MANIFEST_INNER_NAME, load_manifest, parse_manifest_data, summarize
from operatingsystembackup.models import FileRecord, Manifest, ManifestSummary, StagingLocation, ValidationReport

log = logging.getLogger("operatingsystembackup")

DEFAULT_ZIP_DIRNAME = "osbackup-archives"
INNER_FILES = "OSBACKUP/files.jsonl"


class ZipHomeDestination:
    kind = "zip-home"

    def __init__(
        self,
        directory: Path | str | None = None,
        *,
        sources: list[Path] | None = None,
        compression: str = "deflate",
        platform: str = "unknown",
        distro: str = "unknown",
    ) -> None:
        self.directory = resolve_path(directory) if directory else resolve_path(Path.home() / DEFAULT_ZIP_DIRNAME)
        self.sources = list(sources or [])
        self.compression = zipfile.ZIP_DEFLATED if compression != "stored" else zipfile.ZIP_STORED
        self.platform = platform
        self.distro = distro

    def validate(self) -> ValidationReport:
        messages: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []
        path = self.directory
        if path.exists() and not path.is_dir():
            errors.append(f"zip directory is not a directory: {path}")
        elif path.exists() and not is_writable_dir(path):
            errors.append(f"zip directory is not writable: {path}")
        elif not path.exists():
            parent = path.parent
            if not parent.exists() or not is_writable_dir(parent):
                errors.append(f"cannot create zip directory {path}")
            else:
                messages.append(f"{path} will be created")
        if self.sources:
            hit = dest_inside_source(path, self.sources)
            if hit is not None:
                warnings.append(
                    f"zip directory {path} is inside source {resolve_path(hit)} and will be excluded from the archive"
                )
        leftover = []
        if path.is_dir():
            leftover = sorted(p.name for p in path.glob("*.zip.partial"))
        if leftover:
            warnings.append("leftover partial zip files will be ignored: " + ", ".join(leftover[:8]))
        return ValidationReport(
            ok=not errors,
            messages=messages,
            warnings=warnings,
            errors=errors,
            free_bytes=free_bytes(path if path.exists() else path.parent),
        )

    def planned_name(self, backup_id: str, stamp: str | None = None) -> str:
        from datetime import datetime, timezone

        moment = None
        if stamp:
            try:
                moment = datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
            except ValueError:
                moment = None
        return unique_zip_path(self.directory, zip_stem(self.platform, self.distro, backup_id, moment)).name

    def prepare_backup(self, backup_id: str, *, stamp: str) -> StagingLocation:
        ensure_dir(self.directory, mode=0o700)
        from datetime import datetime, timezone

        try:
            moment = datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
        except ValueError:
            moment = None
        final = unique_zip_path(self.directory, zip_stem(self.platform, self.distro, backup_id, moment))
        partial = final.with_name(final.name + ".partial")
        if partial.exists():
            partial.unlink()
        return StagingLocation(
            path=partial,
            backup_id=backup_id,
            final_path=final,
            stamp=stamp,
            extra={"sidecar": str(final.with_suffix(".manifest.json"))},
        )

    def commit(self, staging: StagingLocation) -> Path:
        final = staging.final_path
        if final is None:
            raise ArchiveError("zip staging is missing final_path")
        if not staging.path.is_file():
            raise ArchiveError(f"partial zip missing: {staging.path}")
        if final.exists():
            raise ArchiveError(f"refusing to overwrite {final}")
        os.replace(staging.path, final)
        staging.is_partial = False
        return final

    def abort(self, staging: StagingLocation) -> None:
        if staging.path.exists() and staging.is_partial:
            try:
                staging.path.unlink()
            except OSError:
                pass

    def list_history(self) -> list[ManifestSummary]:
        found: list[ManifestSummary] = []
        if not self.directory.is_dir():
            return found
        for sidecar in sorted(self.directory.glob("*.manifest.json")):
            try:
                manifest = load_manifest(sidecar)
            except IncompatibleManifestError as exc:
                log.warning("%s", exc)
                continue
            if manifest.state != "complete":
                continue
            zip_guess = sidecar.with_name(sidecar.name.removesuffix(".manifest.json") + ".zip")
            path = zip_guess if zip_guess.is_file() else sidecar
            found.append(summarize(manifest, path))
        known = {item.backup_id for item in found}
        for archive in sorted(self.directory.glob("*.zip")):
            if archive.name.endswith(".partial"):
                continue
            try:
                manifest = read_zip_manifest(archive)
            except (IncompatibleManifestError, ArchiveError):
                continue
            if manifest.backup_id in known or manifest.state != "complete":
                continue
            found.append(summarize(manifest, archive))
        return found

    def locate(self, backup_id: str) -> Path | None:
        for summary in self.list_history():
            if summary.backup_id == backup_id:
                path = Path(summary.path)
                if path.suffix == ".zip" and path.is_file():
                    return path
                candidate = path.with_name(path.name.removesuffix(".manifest.json") + ".zip")
                if candidate.is_file():
                    return candidate
        return None

    def open_manifest(self, backup_id: str) -> Manifest:
        sidecar_matches = []
        if self.directory.is_dir():
            sidecar_matches = list(self.directory.glob("*.manifest.json"))
        for sidecar in sidecar_matches:
            try:
                manifest = load_manifest(sidecar)
            except IncompatibleManifestError:
                continue
            if manifest.backup_id == backup_id:
                archive = self.locate(backup_id)
                if archive is not None:
                    inner = read_zip_files(archive)
                    if inner and not manifest.files:
                        manifest.files = inner
                return manifest
        located = self.locate(backup_id)
        if located is None:
            raise IncompatibleManifestError(f"backup {backup_id} not found in {self.directory}")
        return read_zip_manifest(located)

    def delete_backup(self, backup_id: str) -> None:
        archive = self.locate(backup_id)
        sidecar = None
        if archive is not None:
            jsonl = archive.with_name(archive.stem + ".files.jsonl")
            jsonl.unlink(missing_ok=True)
            sidecar = archive.with_name(archive.stem + ".manifest.json")
            if archive.parent != resolve_path(self.directory):
                raise ArchiveError(f"refusing to delete unmanaged path {archive}")
            log.info("retention deleting %s", archive)
            archive.unlink(missing_ok=True)
        if sidecar is not None and sidecar.is_file():
            sidecar.unlink(missing_ok=True)
        elif self.directory.is_dir():
            for path in self.directory.glob("*.manifest.json"):
                try:
                    if load_manifest(path).backup_id == backup_id:
                        path.unlink(missing_ok=True)
                except IncompatibleManifestError:
                    continue


def write_manifest_sidecar(archive: Path, manifest: Manifest) -> None:
    from operatingsystembackup.manifest import write_json
    import json

    sidecar = archive.with_name(archive.stem + ".manifest.json")
    payload = manifest.to_json()
    payload["files"] = []
    write_json(sidecar, payload)
    jsonl = archive.with_name(archive.stem + ".files.jsonl")
    with jsonl.open("w", encoding="utf-8") as handle:
        for rec in manifest.files:
            handle.write(json.dumps(rec.to_json(), separators=(",", ":")) + "\n")


def read_zip_manifest(archive: Path) -> Manifest:
    try:
        with zipfile.ZipFile(archive) as zf:
            try:
                raw = zf.read(MANIFEST_INNER_NAME)
            except KeyError as exc:
                raise IncompatibleManifestError(f"{archive} has no {MANIFEST_INNER_NAME}") from exc
            import json

            data = json.loads(raw.decode("utf-8"))
            manifest = parse_manifest_data(data, origin=str(archive))
            try:
                jsonl = zf.read(INNER_FILES).decode("utf-8")
            except KeyError:
                jsonl = ""
            if jsonl and not manifest.files:
                from operatingsystembackup.models import FileRecord

                records = []
                for line in jsonl.splitlines():
                    if line.strip():
                        records.append(FileRecord.from_json(json.loads(line)))
                manifest.files = records
            return manifest
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"corrupt zip {archive}: {exc}") from exc


def read_zip_files(archive: Path) -> list[FileRecord]:
    try:
        manifest = read_zip_manifest(archive)
    except (IncompatibleManifestError, ArchiveError):
        return []
    return list(manifest.files)


def validate_arcname(name: str) -> str:
    raw = name.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("\\") or (len(raw) >= 2 and raw[1] == ":"):
        raise ArchiveError(f"refusing absolute archive member {name!r}")
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if ".." in parts:
        raise ArchiveError(f"refusing archive member path traversal {name!r}")
    if not parts:
        raise ArchiveError(f"refusing empty archive member {name!r}")
    return "/".join(parts)


def pack_zip(
    zip_path: Path,
    files: list[tuple[str, Path]],
    *,
    manifest: Manifest,
    metadata: dict[str, str] | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    import json

    slim = manifest.to_json()
    slim["files"] = []
    jsonl = "".join(json.dumps(record.to_json(), separators=(",", ":")) + "\n" for record in manifest.files)
    try:
        with zipfile.ZipFile(zip_path, "w", compression=compression, allowZip64=True) as zf:
            for arcname, source in sorted(files, key=lambda row: row[0]):
                name = validate_arcname(arcname)
                if source.is_symlink() or source.is_file():
                    zf.write(source, arcname=name)
            for name, content in sorted((metadata or {}).items()):
                zf.writestr(validate_arcname(name), content)
            zf.writestr(MANIFEST_INNER_NAME, json.dumps(slim, indent=2) + "\n")
            zf.writestr(INNER_FILES, jsonl)
    except zipfile.LargeZipFile as exc:
        raise ArchiveError(f"zip too large (ZIP64 required): {exc}") from exc
    except OSError as exc:
        raise ArchiveError(f"failed to write zip {zip_path}: {exc}") from exc
