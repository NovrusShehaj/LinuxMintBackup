"""Configuration loading, platform paths, and legacy LinuxMintBackup keys."""

from __future__ import annotations

import json
import logging
import os
import platform
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any

from operatingsystembackup.errors import ConfigError

log = logging.getLogger("operatingsystembackup")

SCHEMA_VERSION = 1
LEGACY_HOME_CONFIG = Path.home() / "backup" / "config.json"
APP_DIRNAME = "operatingsystembackup"

FORBIDDEN_KEYS = frozenset(
    {
        "aws_secret_access_key",
        "secret_access_key",
        "aws_access_key_id",
        "password",
        "secret",
        "token",
        "private_key",
        "access_key",
        "secret_key",
    }
)

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "default_platform": None,
    "default_family": "debian",
    "default_distro": "linuxmint",
    "default_destination_type": "internal",
    "destination": None,
    "sources": [],
    "exclude": [],
    "archive": {"zip_dir": None, "compression": "deflate"},
    "incremental": {
        "enabled": True,
        "checksum": "mtime-size",
        "retention_max_backups": 14,
        "retention_max_days": None,
    },
    "cloud": {
        "provider": "s3",
        "bucket": None,
        "prefix": "osbackup",
        "profile": None,
        "endpoint_url": None,
    },
    "logging": {"file": None, "verbosity": "info"},
}

_LEGACY_KEYS = frozenset({"sources", "exclude", "destination", "log_file"})


def user_config_path(*, system: str | None = None) -> Path:
    sysname = (system or platform.system()).lower()
    home = Path.home()
    if sysname == "darwin":
        return home / "Library" / "Application Support" / APP_DIRNAME / "config.json"
    if sysname == "windows":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        return base / APP_DIRNAME / "config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_DIRNAME / "config.json"
    return home / ".config" / APP_DIRNAME / "config.json"


def legacy_config_candidates() -> list[Path]:
    return [LEGACY_HOME_CONFIG, Path.cwd() / "config.json"]


def find_config_path(
    explicit: Path | str | None = None,
    *,
    system: str | None = None,
) -> tuple[Path | None, str | None]:
    """Return (path, warning). Prefer --config, then platform path, then legacy files."""
    if explicit is not None:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
        return path, None

    preferred = user_config_path(system=system)
    if preferred.is_file():
        leftover = [p for p in (LEGACY_HOME_CONFIG,) if p.is_file() and p != preferred]
        warning = None
        if leftover:
            warning = (
                f"using {preferred}; leftover legacy config still exists at "
                f"{leftover[0]} — migrate with osbackup config init and remove the old file"
            )
        return preferred, warning

    for legacy in legacy_config_candidates():
        if legacy.is_file():
            warning = None
            if legacy == LEGACY_HOME_CONFIG:
                warning = f"legacy config; migrate with osbackup config init ({legacy})"
            return legacy, warning
    return None, None


def _reject_secrets(obj: Any, *, prefix: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            path = f"{prefix}.{key}" if prefix else str(key)
            if lowered in FORBIDDEN_KEYS:
                raise ConfigError(
                    f"refusing to load config key {path}: credentials must not be stored in JSON; "
                    "use AWS_PROFILE / AWS_ACCESS_KEY_ID environment variables or a shared credentials file"
                )
            _reject_secrets(value, prefix=path)


def _is_legacy(data: dict[str, Any]) -> bool:
    if "schema_version" in data:
        return False
    return bool(_LEGACY_KEYS & set(data.keys()))


def _merge_defaults(data: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(DEFAULT_CONFIG)
    for key, value in data.items():
        if key in {"archive", "incremental", "cloud", "logging"} and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    version = data.get("schema_version", SCHEMA_VERSION)
    if not isinstance(version, int) or version != SCHEMA_VERSION:
        raise ConfigError(f"unsupported config schema_version {version!r}; expected {SCHEMA_VERSION}")

    dest_type = data.get("default_destination_type")
    if dest_type not in {None, "external", "internal", "zip-home", "cloud"}:
        raise ConfigError(f"invalid default_destination_type: {dest_type!r}")

    if data.get("sources") is None:
        data["sources"] = []
    if not isinstance(data["sources"], list):
        raise ConfigError("sources must be a list")
    if not isinstance(data.get("exclude", []), list):
        raise ConfigError("exclude must be a list")

    inc = data.get("incremental") or {}
    checksum = inc.get("checksum", "mtime-size")
    if checksum not in {"mtime-size", "always"}:
        raise ConfigError("incremental.checksum must be 'mtime-size' or 'always'")
    retention = inc.get("retention_max_backups", 14)
    if not isinstance(retention, int) or retention < 1:
        raise ConfigError("incremental.retention_max_backups must be a positive integer")

    archive = data.get("archive") or {}
    compression = archive.get("compression", "deflate")
    if compression not in {"deflate", "stored"}:
        raise ConfigError("archive.compression must be 'deflate' or 'stored'")

    cloud = data.get("cloud") or {}
    if cloud.get("provider") not in {None, "s3"}:
        raise ConfigError("cloud.provider must be 's3' in v1")

    verbosity = (data.get("logging") or {}).get("verbosity", "info")
    if str(verbosity).lower() not in {"debug", "info", "warning", "error"}:
        raise ConfigError("logging.verbosity must be debug, info, warning, or error")
    return data


def loads(text: str, *, origin: str = "<string>") -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {origin}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{origin} must contain a JSON object")
    _reject_secrets(data)
    if _is_legacy(data):
        mapped = _merge_defaults(
            {
                "sources": data.get("sources") or [],
                "exclude": data.get("exclude") or [],
                "destination": data.get("destination"),
                "logging": {"file": data.get("log_file"), "verbosity": "info"},
            }
        )
        mapped["_legacy"] = True
        return _validate(mapped)
    unknown = [k for k in data if k not in DEFAULT_CONFIG and not str(k).startswith("_")]
    if unknown:
        log.warning("ignoring unknown config keys in %s: %s", origin, ", ".join(unknown))
    return _validate(_merge_defaults(data))


def load(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    return loads(text, origin=str(path))


def load_runtime(
    explicit: Path | str | None = None,
    *,
    system: str | None = None,
    required: bool = False,
) -> tuple[dict[str, Any], Path | None]:
    path, warning = find_config_path(explicit, system=system)
    if path is None:
        if required:
            raise ConfigError(
                f"no config file found (looked at {user_config_path(system=system)} "
                f"and legacy ~/backup/config.json). Run: osbackup config init"
            )
        return deepcopy(DEFAULT_CONFIG), None
    data = load(path)
    if data.get("_legacy") and not warning:
        warning = f"legacy config; migrate with osbackup config init ({path})"
    if warning:
        log.warning("%s", warning)
        warnings.warn(warning, UserWarning, stacklevel=2)
    return data, path


def dump_template() -> str:
    payload = deepcopy(DEFAULT_CONFIG)
    payload["destination"] = "/mnt/backup/operatingsystembackup"
    payload["default_family"] = "debian"
    payload["default_distro"] = "linuxmint"
    payload["default_destination_type"] = "internal"
    return json.dumps(payload, indent=2) + "\n"


def write_init(path: Path | None = None, *, overwrite: bool = False, system: str | None = None) -> Path:
    target = path or user_config_path(system=system)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise ConfigError(f"config already exists: {target} (pass --yes to overwrite)")
    target.write_text(dump_template(), encoding="utf-8")
    if hasattr(os, "chmod"):
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    return target
