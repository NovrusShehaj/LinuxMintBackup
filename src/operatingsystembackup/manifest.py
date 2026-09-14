"""JSON manifest + files.jsonl inventory (schema version 1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from operatingsystembackup import __app_name__
from operatingsystembackup.errors import IncompatibleManifestError
from operatingsystembackup.models import FileRecord, Manifest, ManifestSummary

SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.json"
FILES_JSONL_NAME = "files.jsonl"
MANIFEST_INNER_NAME = "OSBACKUP/manifest.json"


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def dump_manifest(manifest: Manifest, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MANIFEST_NAME
    payload = manifest.to_json()
    payload["files"] = []
    write_json(path, payload)
    jsonl = directory / FILES_JSONL_NAME
    with jsonl.open("w", encoding="utf-8") as handle:
        for record in manifest.files:
            handle.write(json.dumps(record.to_json(), separators=(",", ":")) + "\n")
    return path


def load_files_jsonl(path: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    if not path.is_file():
        return records
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(FileRecord.from_json(json.loads(line)))
    return records


def parse_manifest_data(data: dict, *, origin: str = "manifest") -> Manifest:
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise IncompatibleManifestError(
            f"incompatible manifest schema_version {version!r} in {origin}; expected {SCHEMA_VERSION}. Use --full."
        )
    if data.get("app") not in {__app_name__, "OperatingSystemBackup"}:
        raise IncompatibleManifestError(f"manifest {origin} is not an OperatingSystemBackup archive")
    if not data.get("backup_id"):
        raise IncompatibleManifestError(f"manifest {origin} is missing backup_id")
    try:
        return Manifest.from_json(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise IncompatibleManifestError(f"corrupt manifest {origin}: {exc}") from exc


def load_manifest(path: Path) -> Manifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IncompatibleManifestError(f"missing manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise IncompatibleManifestError(f"invalid JSON in {path}: {exc}") from exc
    manifest = parse_manifest_data(data, origin=str(path))
    jsonl = path.parent / FILES_JSONL_NAME
    if not jsonl.is_file() and path.name.endswith(".manifest.json"):
        jsonl = path.with_name(path.name.removesuffix(".manifest.json") + ".files.jsonl")
    if jsonl.is_file() and not manifest.files:
        manifest.files = load_files_jsonl(jsonl)
    elif not manifest.files and data.get("files"):
        manifest.files = [FileRecord.from_json(item) for item in data["files"]]
    return manifest


def inventory_index(records: Iterable[FileRecord]) -> dict[str, FileRecord]:
    return {record.path: record for record in records}


def summarize(manifest: Manifest, path: Path, *, legacy: bool = False) -> ManifestSummary:
    return ManifestSummary(
        backup_id=manifest.backup_id,
        timestamp=manifest.timestamp,
        kind=manifest.kind,
        parent_id=manifest.parent_id,
        state=manifest.state,
        destination_kind=manifest.destination_kind,
        path=str(path),
        counts=dict(manifest.counts),
        legacy=legacy,
    )


def looks_like_legacy_stamp(name: str) -> bool:
    parts = name.split("_")
    if len(parts) < 2:
        return False
    date, rest = parts[0], parts[1]
    if len(date) == 10 and date[4] == "-" and date[7] == "-":
        return rest[:8].count("-") == 2 or len(rest) >= 8
    return False


def chain_root_id(backup_id: str, by_id: dict[str, ManifestSummary]) -> str:
    current = backup_id
    seen: set[str] = set()
    while current in by_id:
        if current in seen:
            break
        seen.add(current)
        parent = by_id[current].parent_id
        if not parent or parent not in by_id:
            return current
        current = parent
    return backup_id
