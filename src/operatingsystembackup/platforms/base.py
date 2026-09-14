"""Platform adapter protocol and shared helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from operatingsystembackup.models import PackageInventory


class PlatformAdapter(Protocol):
    family_id: str
    distro_id: str
    display_name: str

    def default_sources(self) -> list[Path]: ...

    def default_excludes(self) -> list[str]: ...

    def collect_package_inventory(self) -> PackageInventory: ...

    def rsync_supported(self) -> bool: ...

    def privilege_notes(self) -> str: ...


def home_path() -> Path:
    return Path.home()
