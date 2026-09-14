"""Windows adapter. Copy backend is the default; rsync is optional if present."""

from __future__ import annotations

import os
from pathlib import Path

from operatingsystembackup.models import PackageInventory
from operatingsystembackup.packages import capture
from operatingsystembackup.process import which


class WindowsAdapter:
    family_id = "windows"

    def __init__(self, distro_id: str = "windows", display_name: str | None = None) -> None:
        self.distro_id = distro_id
        self.display_name = display_name or "Windows"

    def default_sources(self) -> list[Path]:
        profile = os.environ.get("USERPROFILE")
        return [Path(profile) if profile else Path.home()]

    def default_excludes(self) -> list[str]:
        home = Path.home()
        local = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
        return [
            str(local / "Temp"),
            str(home / "AppData" / "Local" / "Temp"),
            r"C:\$Recycle.Bin",
            r"C:\Recycle Bin",
        ]

    def rsync_supported(self) -> bool:
        return which("rsync") is not None

    def privilege_notes(self) -> str:
        return (
            "Default source is %USERPROFILE% (not C:\\Windows). "
            "latest is a JSON pointer rather than a symlink. Path length is limited to 260 characters unless long paths are enabled in Windows."
        )

    def collect_package_inventory(self) -> PackageInventory:
        files: dict[str, str] = {}
        warnings: list[str] = []
        listing, err = capture("winget", ["list"])
        if listing is None:
            warnings.append(err or "winget not found")
        else:
            files["metadata/winget.txt"] = listing
        return PackageInventory(files=files, warnings=warnings)
