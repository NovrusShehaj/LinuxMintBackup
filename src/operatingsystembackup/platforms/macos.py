"""macOS adapter."""

from __future__ import annotations

from pathlib import Path

from operatingsystembackup.models import PackageInventory
from operatingsystembackup.packages import capture
from operatingsystembackup.process import which


class MacOSAdapter:
    family_id = "macos"

    def __init__(self, distro_id: str = "macos", display_name: str | None = None) -> None:
        self.distro_id = distro_id
        self.display_name = display_name or "macOS"

    def default_sources(self) -> list[Path]:
        return [Path.home()]

    def default_excludes(self) -> list[str]:
        home = Path.home()
        return [
            str(home / "Library" / "Caches"),
            str(home / ".Trash"),
            str(home / ".cache"),
        ]

    def rsync_supported(self) -> bool:
        return which("rsync") is not None

    def privilege_notes(self) -> str:
        return (
            "Default source is $HOME only (not /System or /etc). "
            "OpenRsync may lack GNU flags; a copy fallback is used when rsync is unusable."
        )

    def collect_package_inventory(self) -> PackageInventory:
        files: dict[str, str] = {}
        warnings: list[str] = []
        brewfile, err = capture(
            "brew",
            ["bundle", "dump", "--file=-", "--brews", "--casks", "--taps", "--mas"],
        )
        if brewfile is None:
            warnings.append(err or "Homebrew not found")
        else:
            files["metadata/Brewfile"] = brewfile
        return PackageInventory(files=files, warnings=warnings)
