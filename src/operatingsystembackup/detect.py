"""Graceful OS / distribution detection."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from operatingsystembackup.models import DetectionResult
from operatingsystembackup.process import run, which

OS_RELEASE_PATHS = (Path("/etc/os-release"), Path("/usr/lib/os-release"))


def parse_os_release(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        data[key.strip()] = value
    return data


def read_os_release(path: Path | None = None) -> dict[str, str]:
    paths = [path] if path is not None else list(OS_RELEASE_PATHS)
    for candidate in paths:
        if candidate is None:
            continue
        try:
            if candidate.is_file():
                return parse_os_release(candidate.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return {}


def _id_like_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip().lower() for part in raw.replace(",", " ").split() if part.strip()]


def detect(
    *,
    system: str | None = None,
    os_release_path: Path | None = None,
    os_release_text: str | None = None,
) -> DetectionResult:
    sysname = system if system is not None else platform.system()
    lowered = sysname.lower()

    if lowered == "linux":
        raw = parse_os_release(os_release_text) if os_release_text is not None else read_os_release(os_release_path)
        if not raw:
            return DetectionResult(
                ok=False,
                os_name="linux",
                reason="could not read /etc/os-release or /usr/lib/os-release",
            )
        distro_id = (raw.get("ID") or "").strip().lower()
        name = raw.get("PRETTY_NAME") or raw.get("NAME") or distro_id
        version = raw.get("VERSION_ID") or raw.get("VERSION") or ""
        likes = _id_like_list(raw.get("ID_LIKE"))
        if not distro_id:
            return DetectionResult(
                ok=False,
                os_name="linux",
                distro_name=name,
                version=version,
                id_like=likes,
                raw=raw,
                reason="os-release ID is empty",
            )
        return DetectionResult(
            ok=True,
            os_name="linux",
            distro_id=distro_id,
            distro_name=name,
            version=version,
            id_like=likes,
            raw=raw,
        )

    if lowered in {"darwin", "macos"}:
        version = platform.mac_ver()[0] or ""
        if not version and which("sw_vers"):
            result = run(["sw_vers", "-productVersion"], timeout=5)
            if result.returncode == 0:
                version = (result.stdout or "").strip()
        return DetectionResult(
            ok=True,
            os_name="macos",
            family="macos",
            distro_id="macos",
            distro_name="macOS",
            version=version,
        )

    if lowered == "windows":
        win = platform.win32_ver()
        version = win[1] or win[0] or ""
        try:
            wv = sys.getwindowsversion()
            version = version or f"{wv.major}.{wv.minor}.{wv.build}"
        except AttributeError:
            pass
        return DetectionResult(
            ok=True,
            os_name="windows",
            family="windows",
            distro_id="windows",
            distro_name="Windows",
            version=version,
        )

    return DetectionResult(
        ok=False,
        os_name=lowered or None,
        reason=f"unsupported platform {sysname!r}",
    )
