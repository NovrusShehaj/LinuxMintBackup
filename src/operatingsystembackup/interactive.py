"""Interactive numbered menus. Options come from the platform/destination registries."""

from __future__ import annotations

import builtins
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from operatingsystembackup.backup_engine import resolve_adapter
from operatingsystembackup.destinations import list_destination_types
from operatingsystembackup.errors import OSBackupError
from operatingsystembackup.fsutil import list_candidate_mounts
from operatingsystembackup.models import BackupRequest
from operatingsystembackup.platforms import list_distros, list_families
from operatingsystembackup.sources import merge_excludes, merge_source_lists

PrintFn = Callable[[str], None]
InputFn = Callable[[str], str]

# Module-level hook so tests can monkeypatch operatingsystembackup.interactive.input.
# prompt_backup_request must resolve this at call time, not in the function signature.
input = builtins.input


def _println(print_fn: PrintFn, text: str = "") -> None:
    print_fn(text)


def _choose(prompt: str, options: list[str], input_fn: InputFn, print_fn: PrintFn, *, default: int | None = 1) -> str:
    if not options:
        raise OSBackupError("no options available")
    _println(print_fn, prompt)
    for index, option in enumerate(options, start=1):
        marker = " (default)" if default == index else ""
        _println(print_fn, f"  {index}) {option}{marker}")
    while True:
        raw = input_fn(f"Select 1-{len(options)}: ").strip()
        if not raw and default is not None:
            return options[default - 1]
        try:
            number = int(raw)
        except ValueError:
            _println(print_fn, "Enter a number.")
            continue
        if 1 <= number <= len(options):
            return options[number - 1]
        _println(print_fn, "Out of range.")


def _yes(prompt: str, input_fn: InputFn) -> bool:
    answer = input_fn(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def prompt_backup_request(
    cfg: dict[str, Any],
    *,
    input_fn: InputFn | None = None,
    print_fn: PrintFn | None = None,
    stdout: TextIO | None = None,
) -> BackupRequest:
    if input_fn is None:
        input_fn = input
    printer: PrintFn = print_fn or (lambda text: print(text, file=stdout or sys.stdout))
    _println(printer, "OperatingSystemBackup interactive backup")
    probe = BackupRequest(
        destination_type="internal",
        destination=None,
        sources=[],
        excludes=[],
    )
    adapter, detection, warning = resolve_adapter(probe, cfg)
    os_name = detection.os_name if detection else "?"
    _println(
        printer,
        f"Detected: os={os_name} family={adapter.family_id} distro={adapter.distro_id} "
        f"({adapter.display_name})" + (f" — {detection.version}" if detection and detection.version else ""),
    )
    if warning:
        _println(printer, f"Warning: {warning}")
    _println(printer, adapter.privilege_notes())

    family = adapter.family_id
    distro = adapter.distro_id
    platform = detection.os_name if detection and detection.ok else None
    if _yes("Override OS/family/distro?", input_fn):
        families = list_families()
        family = _choose("Family:", families, input_fn, printer, default=families.index(family) + 1 if family in families else 1)
        distros = list_distros(family)
        distro = _choose("Distro:", distros, input_fn, printer, default=distros.index(distro) + 1 if distro in distros else 1)
        if family in {"macos", "windows"}:
            platform = family
        else:
            platform = "linux"
        adapter, detection, warning = resolve_adapter(
            BackupRequest(destination_type="internal", destination=None, sources=[], excludes=[], platform=platform, family=family, distro=distro),
            cfg,
        )
        if warning:
            _println(printer, f"Warning: {warning}")

    dest_types = list_destination_types()
    configured = cfg.get("default_destination_type") or "internal"
    default_idx = dest_types.index(configured) + 1 if configured in dest_types else 1
    dest_type = _choose("Destination type:", dest_types, input_fn, printer, default=default_idx)

    destination: Path | None = None
    zip_dir: Path | None = None
    if dest_type in {"external", "internal"}:
        mounts = list_candidate_mounts()
        if mounts:
            _println(printer, "Candidate mounts:")
            for mount in mounts[:12]:
                _println(printer, f"  {mount}")
        default_dest = cfg.get("destination") or ""
        raw = input_fn(f"Destination path{f' [{default_dest}]' if default_dest else ''}: ").strip()
        if not raw:
            raw = str(default_dest)
        if not raw:
            raise OSBackupError("a destination path is required for local disks")
        destination = Path(raw).expanduser()
    elif dest_type == "zip-home":
        default_zip = (cfg.get("archive") or {}).get("zip_dir") or ""
        raw = input_fn(f"ZIP directory [default under home]{f' [{default_zip}]' if default_zip else ''}: ").strip()
        if raw or default_zip:
            zip_dir = Path(raw or default_zip).expanduser()
    else:
        cloud = cfg.get("cloud") or {}
        _println(printer, "S3-compatible cloud uses config keys bucket/prefix/profile/endpoint_url (no secrets in JSON).")
        bucket = input_fn(f"Bucket [{cloud.get('bucket') or ''}]: ").strip() or cloud.get("bucket")
        prefix = input_fn(f"Prefix [{cloud.get('prefix') or 'osbackup'}]: ").strip() or cloud.get("prefix") or "osbackup"
        profile = input_fn(f"AWS profile [{cloud.get('profile') or ''}]: ").strip() or cloud.get("profile")
        endpoint = input_fn(f"Endpoint URL [{cloud.get('endpoint_url') or ''}]: ").strip() or cloud.get("endpoint_url")
        cfg = {
            **cfg,
            "cloud": {
                **cloud,
                "provider": "s3",
                "bucket": bucket,
                "prefix": prefix,
                "profile": profile or None,
                "endpoint_url": endpoint or None,
            },
        }
        if not bucket:
            raise OSBackupError("cloud.bucket is required")

    sources = merge_source_lists(adapter.default_sources(), cfg.get("sources") or None, None)
    excludes = merge_excludes(adapter.default_excludes(), cfg.get("exclude") or None, None)
    _println(printer, "Sources:")
    for source in sources:
        _println(printer, f"  {source}")
    _println(printer, "Excludes:")
    for exclude in excludes:
        _println(printer, f"  {exclude}")
    extra = input_fn("Extra source path (empty to continue): ").strip()
    extra_sources = list(sources)
    while extra:
        extra_sources.append(Path(extra).expanduser())
        extra = input_fn("Another source (empty to continue): ").strip()
    extra_ex = input_fn("Extra exclude (empty to continue): ").strip()
    extra_excludes = list(excludes)
    while extra_ex:
        extra_excludes.append(extra_ex)
        extra_ex = input_fn("Another exclude (empty to continue): ").strip()

    incremental = _choose("Backup mode:", ["incremental", "full"], input_fn, printer, default=1) == "incremental"
    _println(printer, "")
    _println(printer, "Summary:")
    _println(printer, f"  platform={platform} family={adapter.family_id} distro={adapter.distro_id}")
    _println(printer, f"  destination-type={dest_type} destination={destination or zip_dir or '(cloud/zip default)'}")
    _println(printer, f"  mode={'incremental' if incremental else 'full'}")
    _println(printer, f"  sources={', '.join(str(s) for s in extra_sources)}")
    if not _yes("Proceed with backup?", input_fn):
        raise OSBackupError("aborted")

    request = BackupRequest(
        destination_type=dest_type,  # type: ignore[arg-type]
        destination=destination,
        sources=extra_sources,
        excludes=extra_excludes,
        incremental=incremental,
        platform=platform,
        family=adapter.family_id,
        distro=adapter.distro_id,
        yes=True,
        zip_dir=zip_dir,
    )
    request._runtime_config = cfg  # type: ignore[attr-defined]
    return request
