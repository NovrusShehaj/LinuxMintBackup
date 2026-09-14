"""Optional package-inventory helpers. Missing tools are warnings, not hard failures."""

from __future__ import annotations

from operatingsystembackup.process import run, which


def capture(binary: str, args: list[str], *, timeout: float = 120) -> tuple[str | None, str | None]:
    path = which(binary)
    if path is None:
        return None, f"{binary} not found on PATH"
    result = run([path, *args], timeout=timeout)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip() or f"{binary} exited {result.returncode}"
        return None, err
    return result.stdout or "", None
