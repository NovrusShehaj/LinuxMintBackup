"""Debian-family adapter, including Linux Mint (distro id linuxmint)."""

from __future__ import annotations

from pathlib import Path

from operatingsystembackup.models import PackageInventory
from operatingsystembackup.packages import capture


class DebianAdapter:
    family_id = "debian"

    def __init__(self, distro_id: str = "debian", display_name: str | None = None) -> None:
        self.distro_id = distro_id
        self.display_name = display_name or distro_id

    def default_sources(self) -> list[Path]:
        return [Path.home(), Path("/etc")]

    def default_excludes(self) -> list[str]:
        home = Path.home()
        return [
            str(home / ".cache"),
            str(home / ".local" / "share" / "Trash"),
            str(home / ".Trash"),
            str(home / ".thumbnails"),
            str(home / ".cache" / "thumbnails"),
        ]

    def rsync_supported(self) -> bool:
        return True

    def privilege_notes(self) -> str:
        return (
            "Default sources include $HOME and /etc. Unreadable files (typical without root) "
            "are skipped and counted; do not run the whole CLI via sudo."
        )

    def collect_package_inventory(self) -> PackageInventory:
        files: dict[str, str] = {}
        warnings: list[str] = []
        selections, err = capture("dpkg", ["--get-selections"])
        if selections is None:
            warnings.append(err or "dpkg unavailable")
        else:
            files["metadata/dpkg-selections.txt"] = selections
        manual, err = capture("apt-mark", ["showmanual"])
        if manual is None:
            if err:
                warnings.append(err)
        else:
            files["metadata/apt-manual.txt"] = manual
        return PackageInventory(files=files, warnings=warnings)
