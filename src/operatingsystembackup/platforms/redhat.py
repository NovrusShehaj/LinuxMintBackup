"""Red Hat family adapter (Fedora, RHEL, CentOS Stream, Rocky, AlmaLinux)."""

from __future__ import annotations

from pathlib import Path

from operatingsystembackup.models import PackageInventory
from operatingsystembackup.packages import capture


class RedHatAdapter:
    family_id = "redhat"

    def __init__(self, distro_id: str = "fedora", display_name: str | None = None) -> None:
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
            "Default sources include $HOME and /etc. SELinux xattrs are best-effort "
            "(rsync retries without -X if needed). Unreadable files are skipped."
        )

    def collect_package_inventory(self) -> PackageInventory:
        files: dict[str, str] = {}
        warnings: list[str] = []
        rpm_out, err = capture(
            "rpm",
            ["-qa", "--qf", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\\n"],
        )
        if rpm_out is None:
            warnings.append(err or "rpm unavailable")
        else:
            files["metadata/rpm-qa.txt"] = rpm_out
        dnf_out, err = capture("dnf", ["repoquery", "--userinstalled"])
        if dnf_out is None:
            if err:
                warnings.append(err)
        else:
            files["metadata/dnf-userinstalled.txt"] = dnf_out
        return PackageInventory(files=files, warnings=warnings)
