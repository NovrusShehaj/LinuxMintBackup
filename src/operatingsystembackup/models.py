"""Dataclasses shared across the CLI, adapters, destinations, and engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ChecksumMode = Literal["mtime-size", "always"]
BackupKind = Literal["full", "incremental"]
FileStatus = Literal["added", "changed", "deleted", "unchanged"]
DestinationKind = Literal["external", "internal", "zip-home", "cloud"]


@dataclass
class DetectionResult:
    ok: bool
    os_name: str | None = None
    family: str | None = None
    distro_id: str | None = None
    distro_name: str | None = None
    version: str | None = None
    reason: str | None = None
    id_like: list[str] = field(default_factory=list)
    warning: str | None = None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class PackageInventory:
    files: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    ok: bool
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    free_bytes: int | None = None
    same_device_as_home: bool = False

    def raise_if_failed(self) -> None:
        from operatingsystembackup.errors import (
            DisconnectedDestinationError,
            UnwritableDestinationError,
        )

        if self.ok:
            return
        text = "; ".join(self.errors) or "destination validation failed"
        lowered = text.lower()
        if "not exist" in lowered or "not mounted" in lowered or "disconnected" in lowered:
            raise DisconnectedDestinationError(text)
        raise UnwritableDestinationError(text)


@dataclass
class BackupRequest:
    destination_type: DestinationKind
    destination: Path | None
    sources: list[Path]
    excludes: list[str]
    incremental: bool = True
    dry_run: bool = False
    platform: str | None = None
    family: str | None = None
    distro: str | None = None
    yes: bool = False
    config_path: Path | None = None
    checksum_always: bool = False
    strict_sources: bool = False
    verbose: bool = False
    quiet: bool = False
    zip_dir: Path | None = None


@dataclass
class InventoryItem:
    relpath: str
    abs_path: Path
    size: int
    mtime_ns: int
    mode: int
    is_symlink: bool = False
    sha256: str | None = None
    status: FileStatus | None = None


@dataclass
class FileRecord:
    path: str
    size: int
    mtime_ns: int
    mode: int
    sha256: str | None = None
    status: FileStatus | None = None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "mode": self.mode,
            "status": self.status,
        }
        if self.sha256 is not None:
            data["sha256"] = self.sha256
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FileRecord:
        return cls(
            path=str(data["path"]),
            size=int(data.get("size", 0)),
            mtime_ns=int(data.get("mtime_ns", 0)),
            mode=int(data.get("mode", 0)),
            sha256=data.get("sha256"),
            status=data.get("status"),
        )


@dataclass
class Manifest:
    schema_version: int
    app: str
    backup_id: str
    parent_id: str | None
    kind: BackupKind
    timestamp: str
    platform: dict[str, str]
    hostname: str
    sources: list[str]
    excludes: list[str]
    destination_kind: str
    counts: dict[str, int]
    state: str
    directory: str | None = None
    files: list[FileRecord] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app": self.app,
            "backup_id": self.backup_id,
            "parent_id": self.parent_id,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "hostname": self.hostname,
            "sources": self.sources,
            "excludes": self.excludes,
            "destination_kind": self.destination_kind,
            "counts": self.counts,
            "state": self.state,
            "directory": self.directory,
            "files": [f.to_json() for f in self.files],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Manifest:
        files = [FileRecord.from_json(item) for item in data.get("files") or []]
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            app=str(data.get("app", "")),
            backup_id=str(data.get("backup_id", "")),
            parent_id=data.get("parent_id"),
            kind=data.get("kind") or "full",
            timestamp=str(data.get("timestamp", "")),
            platform=dict(data.get("platform") or {}),
            hostname=str(data.get("hostname", "")),
            sources=list(data.get("sources") or []),
            excludes=list(data.get("excludes") or []),
            destination_kind=str(data.get("destination_kind", "")),
            counts=dict(data.get("counts") or {}),
            state=str(data.get("state", "")),
            directory=data.get("directory"),
            files=files,
        )


@dataclass
class ManifestSummary:
    backup_id: str
    timestamp: str
    kind: str
    parent_id: str | None
    state: str
    destination_kind: str
    path: str
    counts: dict[str, int] = field(default_factory=dict)
    legacy: bool = False


@dataclass
class StagingLocation:
    path: Path
    backup_id: str
    final_path: Path | None = None
    is_partial: bool = True
    stamp: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiffResult:
    added: list[InventoryItem]
    changed: list[InventoryItem]
    deleted: list[FileRecord]
    unchanged: list[InventoryItem]
    skipped: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "changed": len(self.changed),
            "deleted": len(self.deleted),
            "unchanged": len(self.unchanged),
            "skipped": self.skipped,
        }


@dataclass
class BackupResult:
    backup_id: str
    kind: BackupKind
    destination: Path | None
    dry_run: bool
    counts: dict[str, int]
    parent_id: str | None = None
    warnings: list[str] = field(default_factory=list)
    skipped_sources: list[str] = field(default_factory=list)
    package_warnings: list[str] = field(default_factory=list)
