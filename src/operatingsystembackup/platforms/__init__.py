"""Central family and distribution registries.

Adding a distro is one row. Distro names are not duplicated in CLI help strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from operatingsystembackup.errors import UnsupportedDistributionError, UnsupportedPlatformError
from operatingsystembackup.models import DetectionResult
from operatingsystembackup.platforms.arch import ArchAdapter
from operatingsystembackup.platforms.debian import DebianAdapter
from operatingsystembackup.platforms.macos import MacOSAdapter
from operatingsystembackup.platforms.redhat import RedHatAdapter
from operatingsystembackup.platforms.windows import WindowsAdapter

AdapterFactory = Callable[[str, str], object]

ID_LIKE_TO_FAMILY = {
    "debian": "debian",
    "ubuntu": "debian",
    "rhel": "redhat",
    "fedora": "redhat",
    "centos": "redhat",
    "rocky": "redhat",
    "arch": "arch",
    "archlinux": "arch",
}


@dataclass(frozen=True)
class FamilySpec:
    family_id: str
    os_name: str
    distros: tuple[str, ...]
    adapter: AdapterFactory
    display_names: dict[str, str]


def _debian(distro_id: str, display_name: str) -> DebianAdapter:
    return DebianAdapter(distro_id=distro_id, display_name=display_name)


def _redhat(distro_id: str, display_name: str) -> RedHatAdapter:
    return RedHatAdapter(distro_id=distro_id, display_name=display_name)


def _arch(distro_id: str, display_name: str) -> ArchAdapter:
    return ArchAdapter(distro_id=distro_id, display_name=display_name)


def _macos(distro_id: str, display_name: str) -> MacOSAdapter:
    return MacOSAdapter(distro_id=distro_id, display_name=display_name)


def _windows(distro_id: str, display_name: str) -> WindowsAdapter:
    return WindowsAdapter(distro_id=distro_id, display_name=display_name)


FAMILY_REGISTRY: dict[str, FamilySpec] = {
    "debian": FamilySpec(
        family_id="debian",
        os_name="linux",
        distros=(
            "debian",
            "ubuntu",
            "linuxmint",
            "pop",
            "raspbian",
            "neon",
            "elementary",
            "zorin",
        ),
        adapter=_debian,
        display_names={
            "debian": "Debian",
            "ubuntu": "Ubuntu",
            "linuxmint": "Linux Mint",
            "pop": "Pop!_OS",
            "raspbian": "Raspberry Pi OS",
            "neon": "KDE neon",
            "elementary": "elementary OS",
            "zorin": "Zorin OS",
        },
    ),
    "redhat": FamilySpec(
        family_id="redhat",
        os_name="linux",
        distros=("fedora", "rhel", "centos", "rocky", "almalinux", "ol"),
        adapter=_redhat,
        display_names={
            "fedora": "Fedora",
            "rhel": "Red Hat Enterprise Linux",
            "centos": "CentOS Stream",
            "rocky": "Rocky Linux",
            "almalinux": "AlmaLinux",
            "ol": "Oracle Linux",
        },
    ),
    "arch": FamilySpec(
        family_id="arch",
        os_name="linux",
        distros=("arch", "manjaro", "endeavouros", "garuda", "cachyos"),
        adapter=_arch,
        display_names={
            "arch": "Arch Linux",
            "manjaro": "Manjaro",
            "endeavouros": "EndeavourOS",
            "garuda": "Garuda Linux",
            "cachyos": "CachyOS",
        },
    ),
    "macos": FamilySpec(
        family_id="macos",
        os_name="macos",
        distros=("macos", "darwin"),
        adapter=_macos,
        display_names={"macos": "macOS", "darwin": "macOS (darwin)"},
    ),
    "windows": FamilySpec(
        family_id="windows",
        os_name="windows",
        distros=("windows",),
        adapter=_windows,
        display_names={"windows": "Windows"},
    ),
}

LINUX_FAMILIES = ("debian", "redhat", "arch")

DISTRO_REGISTRY: dict[str, str] = {}
for _family_id, _spec in FAMILY_REGISTRY.items():
    for _distro in _spec.distros:
        DISTRO_REGISTRY[_distro] = _family_id


def list_families() -> list[str]:
    return list(FAMILY_REGISTRY.keys())


def list_linux_families() -> list[str]:
    return list(LINUX_FAMILIES)


def list_distros(family: str | None = None) -> list[str]:
    if family is None:
        return list(DISTRO_REGISTRY.keys())
    spec = FAMILY_REGISTRY.get(family)
    if spec is None:
        raise UnsupportedPlatformError(
            f"unknown family {family!r}. Supported families: {', '.join(list_families())}"
        )
    return list(spec.distros)


def list_platforms_text() -> str:
    lines = ["OperatingSystemBackup supported platforms:"]
    for family_id, spec in FAMILY_REGISTRY.items():
        names = ", ".join(spec.distros)
        lines.append(f"  {family_id} ({spec.os_name}): {names}")
    return "\n".join(lines)


def display_name_for(distro_id: str) -> str:
    family = DISTRO_REGISTRY.get(distro_id)
    if family:
        return FAMILY_REGISTRY[family].display_names.get(distro_id, distro_id)
    return distro_id


def _family_from_id_like(id_like: list[str]) -> str | None:
    for token in id_like:
        mapped = ID_LIKE_TO_FAMILY.get(token.lower())
        if mapped:
            return mapped
    return None


def supported_distro_list() -> str:
    return ", ".join(list_distros())


def get_adapter(
    *,
    distro_id: str | None = None,
    family: str | None = None,
    detection: DetectionResult | None = None,
    platform: str | None = None,
) -> tuple[object, str | None]:
    """Return (adapter, warning). Manual overrides win over detection."""
    warning: str | None = None
    chosen_distro = (distro_id or "").strip().lower() or None
    chosen_family = (family or "").strip().lower() or None
    chosen_platform = (platform or "").strip().lower() or None

    if chosen_platform == "linux" and not chosen_family and not chosen_distro:
        if detection and detection.os_name == "linux" and detection.ok:
            chosen_distro = detection.distro_id
        else:
            chosen_family = "debian"
            warning = "platform=linux with no family/distro; defaulting to debian family"

    if chosen_platform == "macos":
        chosen_family = chosen_family or "macos"
        chosen_distro = chosen_distro or "macos"
    if chosen_platform == "windows":
        chosen_family = chosen_family or "windows"
        chosen_distro = chosen_distro or "windows"

    if chosen_distro:
        if chosen_distro not in DISTRO_REGISTRY:
            raise UnsupportedDistributionError(
                f"unsupported distribution {chosen_distro!r}. "
                f"Supported ids: {supported_distro_list()}"
            )
        mapped_family = DISTRO_REGISTRY[chosen_distro]
        if chosen_family and chosen_family != mapped_family:
            warning = (
                f"distro {chosen_distro} belongs to family {mapped_family}, "
                f"ignoring requested family {chosen_family}"
            )
        chosen_family = mapped_family

    if not chosen_family and detection and detection.ok:
        if detection.distro_id and detection.distro_id in DISTRO_REGISTRY:
            chosen_distro = detection.distro_id
            chosen_family = DISTRO_REGISTRY[chosen_distro]
        elif detection.family and detection.family in FAMILY_REGISTRY:
            chosen_family = detection.family
            chosen_distro = detection.distro_id or chosen_family
        else:
            like_family = _family_from_id_like(detection.id_like)
            if like_family:
                chosen_family = like_family
                chosen_distro = detection.distro_id or like_family
                warning = (
                    f"unknown distro id {detection.distro_id!r}; "
                    f"using family {like_family} because ID_LIKE={detection.id_like}"
                )
            else:
                raise UnsupportedDistributionError(
                    f"unsupported distribution {detection.distro_id!r}. "
                    f"Supported ids: {supported_distro_list()}"
                )

    if not chosen_family:
        reason = detection.reason if detection and detection.reason else "could not detect OS"
        raise UnsupportedPlatformError(
            f"{reason}. Supported families: {', '.join(list_families())}. "
            "Pass --platform/--family/--distro to override."
        )

    if chosen_family not in FAMILY_REGISTRY:
        raise UnsupportedPlatformError(
            f"unknown family {chosen_family!r}. Supported families: {', '.join(list_families())}"
        )

    spec = FAMILY_REGISTRY[chosen_family]
    distro = chosen_distro or spec.distros[0]
    name = spec.display_names.get(distro, distro)
    adapter = spec.adapter(distro, name)
    return adapter, warning
