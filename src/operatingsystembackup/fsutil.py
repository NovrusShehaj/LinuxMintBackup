"""Filesystem helpers for destination validation and loop detection."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from operatingsystembackup.errors import DestinationLoopError


def expand_path(value: Path | str) -> Path:
    return Path(value).expanduser()


def resolve_path(value: Path | str) -> Path:
    return expand_path(value).resolve(strict=False)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        return resolve_path(path).is_relative_to(resolve_path(parent))
    except (OSError, ValueError):
        return False


def dest_inside_source(dest: Path, sources: list[Path]) -> Path | None:
    dest_r = resolve_path(dest)
    for source in sources:
        try:
            src_r = resolve_path(source)
        except OSError:
            continue
        if dest_r == src_r or is_relative_to(dest_r, src_r):
            return source
    return None


def refuse_destination_loop(dest: Path, sources: list[Path]) -> None:
    hit = dest_inside_source(dest, sources)
    if hit is not None:
        raise DestinationLoopError(
            f"destination {resolve_path(dest)} is inside source {resolve_path(hit)}; "
            "choose a path outside the backup sources"
        )


def is_writable_dir(path: Path) -> bool:
    path = expand_path(path)
    probe_dir = path if path.is_dir() else path.parent
    if not probe_dir.exists():
        return False
    try:
        fd, name = tempfile.mkstemp(prefix=".osbackup-write-test-", dir=str(probe_dir))
        os.close(fd)
        os.unlink(name)
        return True
    except OSError:
        return False


def free_bytes(path: Path) -> int | None:
    path = expand_path(path)
    probe = path if path.exists() else path.parent
    if not probe.exists():
        return None
    try:
        usage = os.statvfs(probe) if hasattr(os, "statvfs") else None
        if usage is not None:
            return int(usage.f_bavail * usage.f_frsize)
    except OSError:
        pass
    try:
        import shutil

        return int(shutil.disk_usage(probe).free)
    except OSError:
        return None


def device_id(path: Path) -> int | None:
    try:
        return resolve_path(path).stat().st_dev
    except OSError:
        try:
            parent = resolve_path(path).parent
            return parent.stat().st_dev if parent.exists() else None
        except OSError:
            return None


def same_mount(a: Path, b: Path) -> bool | None:
    da = device_id(a)
    db = device_id(b)
    if da is None or db is None:
        return None
    return da == db


def list_candidate_mounts() -> list[Path]:
    import platform

    system = platform.system().lower()
    found: list[Path] = []
    if system == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            found.extend(sorted(p for p in volumes.iterdir() if p.is_dir()))
    elif system == "linux":
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
        for base in (Path("/media") / user, Path("/run/media") / user, Path("/mnt")):
            if base.is_dir():
                found.extend(sorted(p for p in base.iterdir() if p.is_dir()))
    return found


def ensure_dir(path: Path, *, mode: int | None = 0o700) -> Path:
    path = expand_path(path)
    path.mkdir(parents=True, exist_ok=True)
    if mode is not None and os.name != "nt":
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    return path


def atomic_replace(src: Path, dest: Path) -> None:
    os.replace(src, dest)
