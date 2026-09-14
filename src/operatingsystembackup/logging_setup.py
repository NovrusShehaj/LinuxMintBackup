"""Console + optional file logging with secret redaction."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from operatingsystembackup import __app_name__

LOGGER_NAME = "operatingsystembackup"

_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***"),
    (re.compile(r"ASIA[0-9A-Z]{16}"), "ASIA***"),
    (re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*)\S+"), r"\1***"),
    (re.compile(r"(?i)(AWS_SECRET_ACCESS_KEY=)\S+"), r"\1***"),
    (re.compile(r"(?i)(Bearer\s+)\S+"), r"\1***"),
    (re.compile(r"(?i)aws_secret[^\s]*"), "aws_secret***"),
)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            else:
                record.args = tuple(
                    redact(str(a)) if isinstance(a, str) else a for a in record.args
                )
        return True


def redact(text: str) -> str:
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def default_log_dir(*, system: str | None = None) -> Path:
    import platform as plat

    sysname = (system or plat.system()).lower()
    home = Path.home()
    if sysname == "darwin":
        return home / "Library" / "Logs" / "operatingsystembackup"
    if sysname == "windows":
        base = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return base / "operatingsystembackup" / "logs"
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / "operatingsystembackup"
    return home / ".local" / "state" / "operatingsystembackup"


def setup_logging(
    *,
    verbosity: str = "info",
    log_file: Path | str | None = None,
    quiet: bool = False,
    verbose: bool = False,
) -> logging.Logger:
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level_name = (verbosity or "info").upper()
        level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    redactor = RedactingFilter()
    fmt = logging.Formatter(f"{__app_name__}: %(levelname)s: %(message)s")

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(fmt)
    console.addFilter(redactor)
    logger.addHandler(console)

    if log_file:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        file_handler.addFilter(redactor)
        logger.addHandler(file_handler)

    return logger
