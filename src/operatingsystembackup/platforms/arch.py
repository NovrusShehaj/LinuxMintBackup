"""Arch-family adapter (Arch, Manjaro, EndeavourOS, and ID_LIKE=arch)."""

from __future__ import annotations

from pathlib import Path

from operatingsystembackup.models import PackageInventory
from operatingsystembackup.packages import capture


class ArchAdapter:
    family_id = "arch"

    def __init__(self, distro_id: str = "arch", display_name: str | None = None) -> None:
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
        ]

    def rsync_supported(self) -> bool:
        return True

    def privilege_notes(self) -> str:
        return (
            "Default sources include $HOME and /etc (especially important on Arch). "
            "Unreadable files are skipped. AUR helpers are not inventoried in v1."
        )

    def collect_package_inventory(self) -> PackageInventory:
        files: dict[str, str] = {}
        warnings: list[str] = []
        explicit, err = capture("pacman", ["-Qqe"])
        if explicit is None:
            warnings.append(err or "pacman unavailable")
        else:
            files["metadata/pacman-explicit.txt"] = explicit
        all_pkgs, err = capture("pacman", ["-Qq"])
        if all_pkgs is None:
            if err:
                warnings.append(err)
        else:
            files["metadata/pacman-all.txt"] = all_pkgs
        return PackageInventory(files=files, warnings=warnings)
