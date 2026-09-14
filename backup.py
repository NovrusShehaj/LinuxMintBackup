#!/usr/bin/env python3
"""Deprecated compatibility shim. Use `osbackup` or `python3 -m operatingsystembackup`."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

print(
    "OperatingSystemBackup: python3 backup.py is deprecated; use osbackup or "
    "python3 -m operatingsystembackup",
    file=sys.stderr,
)

from operatingsystembackup.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
