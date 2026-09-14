"""OperatingSystemBackup command-line interface (stdlib argparse)."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from operatingsystembackup import __app_name__, __version__
from operatingsystembackup.backup_engine import resolve_adapter, run_backup
from operatingsystembackup.config import find_config_path, load, load_runtime, user_config_path, write_init
from operatingsystembackup.destinations import get_destination, list_destination_types
from operatingsystembackup.detect import detect
from operatingsystembackup.errors import ConfigError, OSBackupError
from operatingsystembackup.interactive import prompt_backup_request
from operatingsystembackup.logging_setup import setup_logging
from operatingsystembackup.models import BackupRequest
from operatingsystembackup.platforms import list_linux_families, list_platforms_text
from operatingsystembackup.restore import restore
from operatingsystembackup.sources import merge_excludes, merge_source_lists


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osbackup",
        description=(
            f"{__app_name__}: incremental file backups for Debian/Red Hat/Arch-family Linux, "
            "macOS, and Windows. Linux Mint is distro id linuxmint (Debian family)."
        ),
        epilog="Distro ids are listed by `osbackup platforms` (from the platform registry).",
    )
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    parser.add_argument("--config", type=Path, help="config file path")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    parser.add_argument("--quiet", action="store_true", help="warnings only on the console")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("detect", help="detect OS / family / distro")
    sub.add_parser("platforms", help="list supported families and distro ids")
    sub.add_parser("interactive", help="guided backup")

    backup = sub.add_parser("backup", help="run a backup from flags and/or config")
    backup.add_argument("--platform", choices=("linux", "macos", "windows"))
    backup.add_argument("--family", help="linux family override (debian, redhat, arch) or macos/windows")
    backup.add_argument("--distro", help="distro id (see osbackup platforms)")
    backup.add_argument("--destination-type", choices=list_destination_types())
    backup.add_argument("--destination", type=Path, help="local destination path (external/internal)")
    backup.add_argument("--incremental", action="store_true", default=None)
    backup.add_argument("--full", action="store_true")
    backup.add_argument("--dry-run", action="store_true")
    backup.add_argument("--source", action="append", type=Path, default=None, dest="sources")
    backup.add_argument("--exclude", action="append", default=None, dest="excludes")
    backup.add_argument("--yes", action="store_true")
    backup.add_argument("--strict-sources", action="store_true")
    backup.add_argument("--checksum-always", action="store_true")
    backup.add_argument("--zip-dir", type=Path)

    cfg = sub.add_parser("config", help="show, create, or validate configuration")
    cfg_sub = cfg.add_subparsers(dest="config_command")
    cfg_sub.add_parser("show", help="print the loaded config")
    cfg_sub.add_parser("path", help="print the platform config path")
    init = cfg_sub.add_parser("init", help="write a template config")
    init.add_argument("--yes", action="store_true", help="overwrite an existing file")
    val = cfg_sub.add_parser("validate", help="validate a config file")
    val.add_argument("path", nargs="?", type=Path)

    dest = sub.add_parser("dest", help="destination helpers")
    dest_sub = dest.add_subparsers(dest="dest_command")
    dval = dest_sub.add_parser("validate", help="validate a local destination path")
    dval.add_argument("path", type=Path)
    dval.add_argument("--destination-type", choices=("external", "internal"), default="internal")
    dval.add_argument("--source", action="append", type=Path, default=None, dest="sources")

    hist = sub.add_parser("history", help="list complete backups")
    hist.add_argument("--destination", type=Path)
    hist.add_argument("--destination-type", choices=list_destination_types())
    hist.add_argument("--zip-dir", type=Path)

    rest = sub.add_parser("restore", help="restore a complete backup id to a directory")
    rest.add_argument("backup_id")
    rest.add_argument("--to", type=Path, required=True)
    rest.add_argument("--destination", type=Path)
    rest.add_argument("--destination-type", choices=list_destination_types())
    rest.add_argument("--zip-dir", type=Path)
    rest.add_argument("--dry-run", action="store_true")
    rest.add_argument("--yes", action="store_true")
    return parser


def _load_cfg(args: argparse.Namespace, *, required: bool = False) -> tuple[dict[str, Any], Path | None]:
    explicit = getattr(args, "config", None)
    return load_runtime(explicit, required=required)


def _setup_from_args(args: argparse.Namespace, cfg: dict[str, Any]) -> None:
    log_file = (cfg.get("logging") or {}).get("file")
    setup_logging(
        verbosity=(cfg.get("logging") or {}).get("verbosity") or "info",
        log_file=log_file,
        quiet=bool(getattr(args, "quiet", False)),
        verbose=bool(getattr(args, "verbose", False)),
    )


def cmd_detect(args: argparse.Namespace) -> int:
    result = detect()
    print(f"{__app_name__} detection:")
    print(f"  ok: {str(result.ok).lower()}")
    print(f"  os: {result.os_name or '-'}")
    print(f"  family: {result.family or '-'}")
    print(f"  distro: {result.distro_id or '-'}")
    print(f"  name: {result.distro_name or '-'}")
    print(f"  version: {result.version or '-'}")
    if result.id_like:
        print(f"  id_like: {' '.join(result.id_like)}")
    if result.reason:
        print(f"  reason: {result.reason}")
    if result.ok:
        adapter, _detection, warning = resolve_adapter(
            BackupRequest(
                destination_type="internal",
                destination=None,
                sources=[],
                excludes=[],
            ),
            {},
        )
        print(f"  resolved_family: {adapter.family_id}")
        print(f"  resolved_distro: {adapter.distro_id}")
        print(f"  adapter: {adapter.display_name}")
        if warning:
            print(f"  warning: {warning}")
    return 0 if result.ok else 3


def cmd_platforms(_args: argparse.Namespace) -> int:
    print(list_platforms_text())
    print(f"  linux families: {', '.join(list_linux_families())}")
    print("  destinations: " + ", ".join(list_destination_types()))
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    command = args.config_command
    if command in {None, "show"}:
        cfg, path = _load_cfg(args)
        print(f"# {path or '(defaults; no config file)'}")
        printable = {key: value for key, value in cfg.items() if not str(key).startswith("_")}
        print(json.dumps(printable, indent=2))
        return 0
    if command == "path":
        print(user_config_path())
        return 0
    if command == "init":
        target = write_init(getattr(args, "config", None), overwrite=bool(args.yes))
        print(f"wrote {target}")
        return 0
    if command == "validate":
        path = args.path
        if path is None:
            found, _warning = find_config_path(getattr(args, "config", None))
            if found is None:
                raise ConfigError("no config file to validate")
            path = found
        load(path)
        print(f"ok: {path}")
        return 0
    print("usage: osbackup config {show,path,init,validate}", file=sys.stderr)
    return 2


def cmd_dest_validate(args: argparse.Namespace) -> int:
    cfg, _path = _load_cfg(args)
    adapter, _detection, _warning = resolve_adapter(
        BackupRequest(destination_type=args.destination_type, destination=args.path, sources=[], excludes=[]),
        cfg,
    )
    sources = args.sources or merge_source_lists(adapter.default_sources(), cfg.get("sources") or None, None)
    dest = get_destination(args.destination_type, path=args.path, sources=list(sources), config=cfg)
    report = dest.validate()
    for line in report.messages:
        print(line)
    for line in report.warnings:
        print(f"warning: {line}")
    for line in report.errors:
        print(f"error: {line}", file=sys.stderr)
    if report.free_bytes is not None:
        print(f"free_bytes: {report.free_bytes}")
    report.raise_if_failed()
    print("ok")
    return 0


def _destination_for(args: argparse.Namespace, cfg: dict[str, Any], adapter, sources: list[Path]):
    dest_type = getattr(args, "destination_type", None) or cfg.get("default_destination_type") or "internal"
    dest_path = getattr(args, "destination", None)
    if dest_path is None and cfg.get("destination") and dest_type in {"internal", "external"}:
        dest_path = Path(str(cfg["destination"])).expanduser()
    zip_dir = getattr(args, "zip_dir", None)
    return dest_type, get_destination(
        dest_type,
        path=dest_path,
        sources=sources,
        config=cfg,
        zip_dir=zip_dir,
    )


def cmd_history(args: argparse.Namespace) -> int:
    cfg, _path = _load_cfg(args)
    adapter, _detection, warning = resolve_adapter(
        BackupRequest(destination_type="internal", destination=None, sources=[], excludes=[]),
        cfg,
    )
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    sources = merge_source_lists(adapter.default_sources(), cfg.get("sources") or None, None)
    _dest_type, dest = _destination_for(args, cfg, adapter, sources)
    rows = [item for item in dest.list_history() if item.state == "complete"]
    if not rows:
        print("No complete backups found.")
        return 0
    for item in rows:
        legacy = " legacy" if item.legacy else ""
        print(
            f"{item.backup_id}  {item.timestamp}  {item.kind}  parent={item.parent_id or '-'}  "
            f"{item.destination_kind}{legacy}  {item.path}"
        )
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    cfg, _path = _load_cfg(args)
    adapter, _detection, _warning = resolve_adapter(
        BackupRequest(destination_type="internal", destination=None, sources=[], excludes=[]),
        cfg,
    )
    sources = merge_source_lists(adapter.default_sources(), cfg.get("sources") or None, None)
    _dest_type, dest = _destination_for(args, cfg, adapter, sources)
    if not args.yes and not args.dry_run and sys.stdin.isatty():
        answer = input(f"Restore {args.backup_id} to {args.to}? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            raise OSBackupError("aborted")
    restore(dest, args.backup_id, args.to, dry_run=args.dry_run)
    print(f"OperatingSystemBackup: restore {args.backup_id} -> {args.to}" + (" (dry-run)" if args.dry_run else ""))
    return 0


def _confirm_backup(request: BackupRequest) -> None:
    if request.dry_run or request.yes or not sys.stdin.isatty():
        return
    dest = request.destination or request.zip_dir or request.destination_type
    answer = input(
        f"OperatingSystemBackup: {request.destination_type} backup to {dest} "
        f"({len(request.sources)} source(s)). Proceed? [y/N]: "
    ).strip().lower()
    if answer not in {"y", "yes"}:
        raise OSBackupError("aborted")


def cmd_backup(args: argparse.Namespace) -> int:
    cfg, cfg_path = _load_cfg(args)
    dest_type = args.destination_type or cfg.get("default_destination_type")
    dest_path = args.destination
    if dest_type in {"internal", "external"} and dest_path is None and cfg.get("destination"):
        dest_path = Path(str(cfg["destination"])).expanduser()
    if not dest_type:
        dest_type = "internal"
    if dest_type in {"internal", "external"} and dest_path is None:
        if sys.stdin.isatty() and sys.stdout.isatty() and not args.yes:
            print("No destination configured; switching to interactive mode.", file=sys.stderr)
            return cmd_interactive(args)
        raise ConfigError("pass --destination PATH or set destination in config (or run osbackup interactive)")

    adapter, _detection, warning = resolve_adapter(
        BackupRequest(
            destination_type=dest_type,
            destination=dest_path,
            sources=[],
            excludes=[],
            platform=args.platform,
            family=args.family,
            distro=args.distro,
        ),
        cfg,
    )
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    sources = merge_source_lists(adapter.default_sources(), cfg.get("sources") or None, args.sources)
    excludes = merge_excludes(adapter.default_excludes(), cfg.get("exclude") or None, args.excludes)
    incremental = True
    if args.full:
        incremental = False
    elif args.incremental:
        incremental = True
    elif (cfg.get("incremental") or {}).get("enabled") is False:
        incremental = False

    request = BackupRequest(
        destination_type=dest_type,
        destination=dest_path,
        sources=list(sources),
        excludes=list(excludes),
        incremental=incremental,
        dry_run=bool(args.dry_run),
        platform=args.platform,
        family=args.family,
        distro=args.distro,
        yes=bool(args.yes),
        config_path=cfg_path,
        checksum_always=bool(args.checksum_always),
        strict_sources=bool(args.strict_sources),
        verbose=bool(args.verbose),
        quiet=bool(args.quiet),
        zip_dir=args.zip_dir,
    )
    _confirm_backup(request)
    result = run_backup(request, cfg, adapter=adapter)
    suffix = " (dry-run)" if result.dry_run else ""
    print(
        f"OperatingSystemBackup: backup {result.backup_id} {result.kind}{suffix} "
        f"added={result.counts.get('added', 0)} changed={result.counts.get('changed', 0)} "
        f"deleted={result.counts.get('deleted', 0)} unchanged={result.counts.get('unchanged', 0)}"
    )
    if result.destination:
        print(f"destination: {result.destination}")
    return 0


def cmd_interactive(args: argparse.Namespace) -> int:
    cfg, _path = _load_cfg(args)
    request = prompt_backup_request(cfg)
    runtime_cfg = getattr(request, "_runtime_config", cfg)
    result = run_backup(request, runtime_cfg)
    print(
        f"OperatingSystemBackup: backup {result.backup_id} {result.kind} "
        f"added={result.counts.get('added', 0)} changed={result.counts.get('changed', 0)}"
    )
    if result.destination:
        print(f"destination: {result.destination}")
    return 0


def dispatch(args: argparse.Namespace) -> int:
    command = args.command
    if command is None:
        build_parser().print_help()
        return 0
    if command == "detect":
        return cmd_detect(args)
    if command == "platforms":
        return cmd_platforms(args)
    if command == "config":
        return cmd_config(args)
    if command == "dest":
        if args.dest_command == "validate":
            return cmd_dest_validate(args)
        print("usage: osbackup dest validate PATH", file=sys.stderr)
        return 2
    if command == "history":
        return cmd_history(args)
    if command == "restore":
        return cmd_restore(args)
    if command == "backup":
        return cmd_backup(args)
    if command == "interactive":
        return cmd_interactive(args)
    build_parser().print_help()
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg: dict[str, Any] = {}
    try:
        if args.command not in {None, "platforms"}:
            skip_load = args.command == "config" and getattr(args, "config_command", None) == "init"
            if not skip_load:
                cfg, _ignored = _load_cfg(args)
            elif getattr(args, "config", None) is None:
                cfg = {}
        _setup_from_args(args, cfg)
        return dispatch(args)
    except OSBackupError as exc:
        print(f"{__app_name__}: {exc.message}", file=sys.stderr)
        return int(getattr(exc, "exit_code", 2))
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        print(f"{__app_name__}: interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        if getattr(args, "verbose", False):
            traceback.print_exc()
        else:
            print(f"{__app_name__}: unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
