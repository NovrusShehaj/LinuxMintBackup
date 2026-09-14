"""Generic cloud destination wrapping a CloudProvider (S3-compatible in v1)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Protocol

from operatingsystembackup.errors import ArchiveError, IncompatibleManifestError
from operatingsystembackup.fsutil import dest_inside_source
from operatingsystembackup.manifest import FILES_JSONL_NAME, MANIFEST_NAME, load_files_jsonl, parse_manifest_data, summarize
from operatingsystembackup.models import Manifest, ManifestSummary, StagingLocation, ValidationReport

log = logging.getLogger("operatingsystembackup")


class CloudProvider(Protocol):
    def probe_auth(self) -> None: ...

    def upload(self, local_path: Path, key: str) -> None: ...

    def download(self, key: str, local_path: Path) -> None: ...

    def list_prefix(self, prefix: str) -> list[str]: ...

    def delete_key(self, key: str) -> None: ...


class MemoryCloudProvider:
    """In-memory provider for tests. Never used for real credentials."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def probe_auth(self) -> None:
        return None

    def upload(self, local_path: Path, key: str) -> None:
        self.objects[key] = Path(local_path).read_bytes()

    def download(self, key: str, local_path: Path) -> None:
        if key not in self.objects:
            raise FileNotFoundError(key)
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.objects[key])

    def list_prefix(self, prefix: str) -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))

    def delete_key(self, key: str) -> None:
        self.objects.pop(key, None)


class CloudDestination:
    kind = "cloud"

    def __init__(
        self,
        provider: CloudProvider,
        *,
        prefix: str = "osbackup",
        sources: list[Path] | None = None,
    ) -> None:
        self.provider = provider
        self.prefix = prefix.strip("/").replace("\\", "/")
        self.sources = list(sources or [])

    def object_prefix(self, backup_id: str) -> str:
        return f"{self.prefix}/osbackup/{backup_id}"

    def validate(self) -> ValidationReport:
        errors: list[str] = []
        warnings: list[str] = []
        messages: list[str] = []
        try:
            self.provider.probe_auth()
            messages.append("cloud credentials probe succeeded")
        except Exception as exc:
            errors.append(str(exc))
        if self.sources:
            tmp = Path(tempfile.gettempdir())
            hit = dest_inside_source(tmp, self.sources)
            if hit is not None:
                warnings.append(
                    f"cloud packs are built in a temp directory; {tmp} is inside a source and will be excluded"
                )
        return ValidationReport(ok=not errors, messages=messages, warnings=warnings, errors=errors)

    def prepare_backup(self, backup_id: str, *, stamp: str) -> StagingLocation:
        staging_root = Path(tempfile.mkdtemp(prefix=f"osbackup-cloud-{backup_id}-"))
        if os.name != "nt":
            try:
                os.chmod(staging_root, 0o700)
            except OSError:
                pass
        return StagingLocation(
            path=staging_root,
            backup_id=backup_id,
            final_path=staging_root,
            stamp=stamp,
            extra={"object_prefix": self.object_prefix(backup_id)},
        )

    def commit(self, staging: StagingLocation) -> Path:
        prefix = self.object_prefix(staging.backup_id)
        manifest_path = staging.path / MANIFEST_NAME
        if not manifest_path.is_file():
            raise ArchiveError("cloud staging is missing manifest.json")
        delayed: list[tuple[Path, str]] = []
        for path in sorted(staging.path.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(staging.path).as_posix()
            key = f"{prefix}/{rel}"
            if path.name == MANIFEST_NAME and rel == MANIFEST_NAME:
                delayed.append((path, key))
                continue
            self.provider.upload(path, key)
        for path, key in delayed:
            self.provider.upload(path, key)
        self.abort(staging)
        return Path(prefix)

    def abort(self, staging: StagingLocation) -> None:
        import shutil

        if staging.path.exists() and staging.is_partial:
            shutil.rmtree(staging.path, ignore_errors=True)

    def list_history(self) -> list[ManifestSummary]:
        found: list[ManifestSummary] = []
        keys = self.provider.list_prefix(f"{self.prefix}/osbackup/")
        manifest_keys = [key for key in keys if key.endswith("/" + MANIFEST_NAME) or key.endswith(MANIFEST_NAME)]
        for key in manifest_keys:
            try:
                manifest = self._load_remote_manifest(key)
            except (IncompatibleManifestError, OSError, FileNotFoundError) as exc:
                log.warning("skipping cloud object %s: %s", key, exc)
                continue
            if manifest.state != "complete":
                continue
            found.append(summarize(manifest, Path(key)))
        return found

    def _load_remote_manifest(self, key: str) -> Manifest:
        with tempfile.TemporaryDirectory(prefix="osbackup-mf-") as tmp:
            local = Path(tmp) / MANIFEST_NAME
            self.provider.download(key, local)
            data = json.loads(local.read_text(encoding="utf-8"))
            manifest = parse_manifest_data(data, origin=key)
            jsonl_key = key[: -len(MANIFEST_NAME)] + FILES_JSONL_NAME
            try:
                jsonl_path = Path(tmp) / FILES_JSONL_NAME
                self.provider.download(jsonl_key, jsonl_path)
                if not manifest.files:
                    manifest.files = load_files_jsonl(jsonl_path)
            except FileNotFoundError:
                pass
            return manifest

    def locate(self, backup_id: str) -> Path | None:
        key = f"{self.object_prefix(backup_id)}/{MANIFEST_NAME}"
        keys = self.provider.list_prefix(self.object_prefix(backup_id) + "/")
        if key in keys or any(item.endswith(MANIFEST_NAME) and backup_id in item for item in keys):
            return Path(key)
        return None

    def open_manifest(self, backup_id: str) -> Manifest:
        key = f"{self.object_prefix(backup_id)}/{MANIFEST_NAME}"
        try:
            return self._load_remote_manifest(key)
        except FileNotFoundError as exc:
            raise IncompatibleManifestError(f"cloud backup {backup_id} not found") from exc

    def delete_backup(self, backup_id: str) -> None:
        prefix = self.object_prefix(backup_id) + "/"
        for key in self.provider.list_prefix(prefix):
            log.info("retention deleting cloud object %s", key)
            self.provider.delete_key(key)
