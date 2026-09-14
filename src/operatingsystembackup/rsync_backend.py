"""rsync argv builder and optional execution. Successor of backup.py run_backup."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from operatingsystembackup.errors import OSBackupError, PartialBackupError
from operatingsystembackup.process import run, which
from operatingsystembackup.sources import classify_source

log = logging.getLogger("operatingsystembackup")


@dataclass
class RsyncCapabilities:
    available: bool
    binary: str | None = None
    variant: str = "none"
    acls: bool = False
    xattrs: bool = False
    numeric_ids: bool = False
    link_dest: bool = False
    dry_run: bool = False
    one_file_system: bool = False
    hardlinks: bool = False
    partial: bool = False
    delay_updates: bool = False
    delete: bool = False
    version_text: str = ""


_CACHED: RsyncCapabilities | None = None


def probe(force: bool = False) -> RsyncCapabilities:
    global _CACHED
    if _CACHED is not None and not force:
        return _CACHED
    binary = which("rsync")
    if binary is None:
        _CACHED = RsyncCapabilities(available=False)
        return _CACHED
    version = run([binary, "--version"], timeout=8)
    help_result = run([binary, "--help"], timeout=8)
    text = f"{version.stdout or ''}{version.stderr or ''}{help_result.stdout or ''}{help_result.stderr or ''}"
    lowered = text.lower()
    openrsync = "openrsync" in lowered
    gnu = (not openrsync) and ("rsync  version" in lowered or "samba" in lowered or "protocol version" in lowered)
    variant = "openrsync" if openrsync else ("gnu" if gnu else "unknown")
    caps = RsyncCapabilities(
        available=True,
        binary=binary,
        variant=variant,
        acls="--acls" in lowered or " -A," in text or "\n -A " in text,
        xattrs="--xattrs" in lowered or " -X," in text,
        numeric_ids="--numeric-ids" in lowered,
        link_dest="--link-dest" in lowered,
        dry_run="--dry-run" in lowered,
        one_file_system="--one-file-system" in lowered or " -x," in text,
        hardlinks="--hard-links" in lowered or " -H," in text,
        partial="--partial" in lowered,
        delay_updates="--delay-updates" in lowered,
        delete="--delete" in lowered,
        version_text=(version.stdout or version.stderr or "").splitlines()[0] if (version.stdout or version.stderr) else "",
    )
    if openrsync:
        caps.acls = False
        caps.numeric_ids = "--numeric-ids" in lowered
        caps.xattrs = "--xattrs" in lowered
    _CACHED = caps
    return caps


def gnu_rsync_available() -> bool:
    caps = probe()
    return caps.available and caps.variant == "gnu"


def build_command(
    source: Path,
    dest: Path,
    excludes: list[str],
    *,
    link_dest: Path | None = None,
    dry_run: bool = False,
    caps: RsyncCapabilities | None = None,
    extra_args: list[str] | None = None,
) -> list[str]:
    caps = caps or probe()
    if not caps.available or not caps.binary:
        raise OSBackupError("rsync is not available")
    cmd = [caps.binary, "-a"]
    if caps.hardlinks:
        cmd.append("-H")
    if caps.acls:
        cmd.append("-A")
    if caps.xattrs:
        cmd.append("-X")
    if caps.numeric_ids:
        cmd.append("--numeric-ids")
    if caps.one_file_system:
        cmd.append("-x")
    if caps.partial:
        cmd.append("--partial")
    if caps.delay_updates:
        cmd.append("--delay-updates")
    if caps.delete:
        cmd.append("--delete")
    if dry_run and caps.dry_run:
        cmd.append("--dry-run")
    if link_dest is not None and caps.link_dest:
        cmd.extend(["--link-dest", str(link_dest.resolve())])
    for pattern in excludes:
        cmd.extend(["--exclude", pattern])
    if extra_args:
        cmd.extend(extra_args)
    src = str(source)
    if source.is_dir() and not src.endswith("/"):
        src += "/"
    cmd.extend([src, str(dest)])
    return cmd


def dest_subdir_for_source(snapshot: Path, source: Path, *, home: Path | None = None) -> tuple[str, Path]:
    prefix, _root = classify_source(source, home=home)
    return prefix, snapshot / prefix


def run_rsync(cmd: list[str], *, allow_partial: bool = True) -> None:
    log.info("OperatingSystemBackup: running %s", cmd[0])
    log.info("%s", " ".join(cmd))
    result = run(cmd)
    if result.returncode == 0:
        return
    stderr = (result.stderr or result.stdout or "").strip()
    if allow_partial and result.returncode in {23, 24}:
        log.warning("rsync partial transfer (code %s); unreadable files skipped: %s", result.returncode, stderr)
        return
    if result.returncode in {23, 24}:
        raise PartialBackupError(f"rsync partial transfer (code {result.returncode}): {stderr}")
    raise OSBackupError(f"rsync exited {result.returncode}: {stderr}")


def sync_sources(
    sources: list[Path],
    snapshot: Path,
    excludes: list[str],
    *,
    parent_snapshot: Path | None = None,
    dry_run: bool = False,
    caps: RsyncCapabilities | None = None,
    home: Path | None = None,
) -> list[list[str]]:
    """Rsync each source into snapshot/<prefix>/. Omits --link-dest when parent is missing."""
    caps = caps or probe()
    commands: list[list[str]] = []
    used_xattrs = bool(caps.xattrs)
    for source in sources:
        prefix, dest_dir = dest_subdir_for_source(snapshot, source, home=home)
        dest_dir.mkdir(parents=True, exist_ok=True)
        link = None
        if parent_snapshot is not None:
            candidate = parent_snapshot / prefix
            if candidate.is_dir() and caps.link_dest:
                link = candidate
        cmd = build_command(
            source,
            dest_dir,
            excludes,
            link_dest=link,
            dry_run=dry_run,
            caps=caps,
        )
        commands.append(cmd)
        if dry_run:
            log.info("would run: %s", " ".join(cmd))
            continue
        try:
            run_rsync(cmd, allow_partial=True)
        except OSBackupError:
            if used_xattrs and "-X" in cmd:
                log.warning("rsync -X failed; retrying without xattrs")
                caps_no_x = RsyncCapabilities(**{**caps.__dict__, "xattrs": False})
                cmd = build_command(
                    source,
                    dest_dir,
                    excludes,
                    link_dest=link,
                    dry_run=dry_run,
                    caps=caps_no_x,
                )
                run_rsync(cmd, allow_partial=True)
            else:
                raise
    return commands
