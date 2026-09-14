"""Backup source discovery, excludes, and inventory walking."""

from __future__ import annotations

import fnmatch
import hashlib
import logging
import os
from pathlib import Path

from operatingsystembackup.errors import InaccessibleSourceError
from operatingsystembackup.fsutil import expand_path, is_relative_to, resolve_path
from operatingsystembackup.models import InventoryItem

log = logging.getLogger("operatingsystembackup")

HOME_PREFIX = "home"
ETC_PREFIX = "etc"
EXTRA_PREFIX = "extra"
METADATA_PREFIX = "metadata"


def classify_source(path: Path, *, home: Path | None = None) -> tuple[str, Path]:
    home = home or Path.home()
    resolved = resolve_path(path)
    home_r = resolve_path(home)
    etc = Path("/etc")
    try:
        if resolved == home_r or is_relative_to(resolved, home_r):
            return HOME_PREFIX, resolved
    except (OSError, ValueError):
        pass
    try:
        if resolved == resolve_path(etc) or is_relative_to(resolved, etc):
            return ETC_PREFIX, resolved
    except (OSError, ValueError):
        pass
    return f"{EXTRA_PREFIX}/{resolved.name or 'src'}", resolved


def archive_relpath(source_root: Path, file_path: Path, prefix: str, *, home: Path | None = None) -> str:
    home = home or Path.home()
    file_r = Path(file_path)
    root_r = Path(source_root)
    try:
        rel = file_r.relative_to(root_r)
    except ValueError:
        rel = Path(file_r.name)
    rel_s = rel.as_posix()
    if prefix == HOME_PREFIX:
        try:
            rel_home = file_r.resolve(strict=False).relative_to(resolve_path(home))
            return f"{HOME_PREFIX}/{rel_home.as_posix()}"
        except ValueError:
            return f"{HOME_PREFIX}/{rel_s}"
    if prefix == ETC_PREFIX:
        try:
            rel_etc = file_r.resolve(strict=False).relative_to(resolve_path(Path("/etc")))
            return f"{ETC_PREFIX}/{rel_etc.as_posix()}"
        except ValueError:
            return f"{ETC_PREFIX}/{rel_s}"
    return f"{prefix}/{rel_s}".replace("\\", "/")


def expand_excludes(excludes: list[str]) -> list[str]:
    return [str(Path(item).expanduser()) if item.startswith("~") else item for item in excludes]


def is_excluded(path: Path, excludes: list[str], *, dest: Path | None = None) -> bool:
    resolved = resolve_path(path)
    if dest is not None:
        dest_r = resolve_path(dest)
        if resolved == dest_r or is_relative_to(resolved, dest_r):
            return True
    text = str(resolved)
    posix = resolved.as_posix()
    for raw in excludes:
        if not raw:
            continue
        pattern = str(Path(raw).expanduser()) if raw.startswith("~") else raw
        try:
            exp = resolve_path(pattern) if not any(ch in pattern for ch in "*?[]") else None
        except (OSError, ValueError):
            exp = None
        if exp is not None and (resolved == exp or is_relative_to(resolved, exp)):
            return True
        if fnmatch.fnmatch(text, pattern) or fnmatch.fnmatch(posix, pattern.replace("\\", "/")):
            return True
        if fnmatch.fnmatch(path.name, pattern):
            return True
        try:
            if any(fnmatch.fnmatch(part, pattern) for part in resolved.parts):
                return True
        except Exception:
            pass
    return False


def discover_sources(
    requested: list[Path | str],
    *,
    strict: bool = False,
) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    skipped: list[str] = []
    for raw in requested:
        path = expand_path(raw)
        if not path.exists():
            skipped.append(str(path))
            log.warning("skipping missing source %s", path)
            continue
        found.append(path)
    if not found:
        raise InaccessibleSourceError(
            "no usable sources remain "
            + (f"(missing: {', '.join(skipped)})" if skipped else "(empty source list)")
        )
    if strict and skipped:
        raise InaccessibleSourceError(f"strict-sources: missing {', '.join(skipped)}")
    return found, skipped


def merge_source_lists(
    adapter_defaults: list[Path],
    config_sources: list[str] | None,
    cli_sources: list[Path] | None,
) -> list[Path]:
    if cli_sources:
        return [expand_path(p) for p in cli_sources]
    if config_sources:
        return [expand_path(p) for p in config_sources]
    return list(adapter_defaults)


def merge_excludes(
    adapter_defaults: list[str],
    config_excludes: list[str] | None,
    cli_excludes: list[str] | None,
) -> list[str]:
    merged: list[str] = []
    for group in (adapter_defaults, config_excludes or [], cli_excludes or []):
        for item in group:
            if item not in merged:
                merged.append(item)
    return expand_excludes(merged)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def walk_inventory(
    sources: list[Path],
    excludes: list[str],
    *,
    dest: Path | None = None,
    home: Path | None = None,
) -> tuple[list[InventoryItem], int]:
    home = home or Path.home()
    items: list[InventoryItem] = []
    skipped = 0
    for source in sources:
        prefix, root = classify_source(source, home=home)
        try:
            walk_root = root if root.is_dir() else root.parent
        except OSError:
            skipped += 1
            continue
        if root.is_file() or root.is_symlink():
            try:
                items.append(_item_for(root, source, prefix, home))
            except OSError:
                skipped += 1
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            dirnames[:] = [
                name
                for name in dirnames
                if not is_excluded(current / name, excludes, dest=dest)
            ]
            for name in filenames:
                path = current / name
                if is_excluded(path, excludes, dest=dest):
                    continue
                try:
                    items.append(_item_for(path, source, prefix, home))
                except OSError:
                    skipped += 1
                    log.debug("skip unreadable %s", path, exc_info=True)
    items.sort(key=lambda item: item.relpath)
    return items, skipped


def _item_for(path: Path, source_root: Path, prefix: str, home: Path) -> InventoryItem:
    stat = path.lstat()
    rel = archive_relpath(source_root, path, prefix, home=home)
    return InventoryItem(
        relpath=rel,
        abs_path=path,
        size=int(stat.st_size),
        mtime_ns=int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
        mode=int(stat.st_mode),
        is_symlink=path.is_symlink(),
    )


def estimate_bytes(items: list[InventoryItem]) -> int:
    return sum(item.size for item in items if not item.is_symlink)
