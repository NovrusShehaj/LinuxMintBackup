"""Destination provider protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from operatingsystembackup.models import Manifest, ManifestSummary, StagingLocation, ValidationReport


class DestinationProvider(Protocol):
    kind: str

    def validate(self) -> ValidationReport: ...

    def prepare_backup(self, backup_id: str, *, stamp: str) -> StagingLocation: ...

    def commit(self, staging: StagingLocation) -> Path: ...

    def abort(self, staging: StagingLocation) -> None: ...

    def list_history(self) -> list[ManifestSummary]: ...

    def open_manifest(self, backup_id: str) -> Manifest: ...

    def locate(self, backup_id: str) -> Path | None: ...

    def delete_backup(self, backup_id: str) -> None: ...
