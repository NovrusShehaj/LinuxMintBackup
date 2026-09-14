"""Subprocess helper. Always uses an argv list (never shell=True)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from operatingsystembackup.errors import OSBackupError

log = logging.getLogger("operatingsystembackup")


def which(binary: str) -> str | None:
    return shutil.which(binary)


def run(
    argv: list[str],
    *,
    timeout: float | None = None,
    cwd: Path | str | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    if not argv or not isinstance(argv, list) or not all(isinstance(part, str) for part in argv):
        raise OSBackupError("internal error: process.run requires a list of strings")
    log.debug("exec %s", argv[0])
    result = subprocess.run(  # noqa: S603 — argv list, no shell
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        cwd=str(cwd) if cwd is not None else None,
        shell=False,
        check=False,
    )
    if check and result.returncode != 0:
        raise OSBackupError(
            f"{argv[0]} exited {result.returncode}: {(result.stderr or result.stdout).strip()}"
        )
    return result
