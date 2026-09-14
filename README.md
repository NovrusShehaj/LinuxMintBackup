# OperatingSystemBackup

Cross-platform command-line backup tool for Debian-family Linux (including **Linux Mint**), Red Hat-family Linux, Arch-family Linux, macOS, and Windows. It creates incremental file backups to a local disk, a ZIP archive under your home directory, or an optional S3-compatible bucket.

The GitHub repository may still be named `LinuxMintBackup`; the local project, package, and CLI are **OperatingSystemBackup**.

This is a file-level backup utility, not a full-disk imager, not an encryption product, and not a restic/borg replacement.

## Overview

- CLI `osbackup` (alias `operatingsystembackup`) and `python3 -m operatingsystembackup`
- Interactive menus (`osbackup interactive`) and non-interactive flags for automation
- Genuine incrementals: rsync `--link-dest` on POSIX local disks when rsync is usable; copy + hardlink fallback; JSON manifests with added/changed/deleted files
- Destinations: `external` and `internal` local drives, `zip-home` archives, `cloud` (S3-compatible, optional extra)
- Package inventories as snapshot metadata when `dpkg`/`rpm`/`pacman`/`brew`/`winget` exist; missing tools are warnings
- Linux Mint is distro id `linuxmint` on the Debian-family adapter (home + `/etc`, cache/Trash excludes)

## Supported platforms

Keep this table in sync with `operatingsystembackup.platforms.FAMILY_REGISTRY` (`osbackup platforms` prints the live list).

| Family | OS | Distro ids |
|---|---|---|
| debian | linux | debian, ubuntu, linuxmint, pop, raspbian, neon, elementary, zorin |
| redhat | linux | fedora, rhel, centos, rocky, almalinux, ol |
| arch | linux | arch, manjaro, endeavouros, garuda, cachyos |
| macos | macos | macos, darwin |
| windows | windows | windows |

Unknown Linux `ID` values can still map through `ID_LIKE` (for example Mint’s `ID=linuxmint` `ID_LIKE=ubuntu debian`).

## Installation

Requires **Python 3.10+**. Linux Mint 20 / Python 3.8 is not supported.

```bash
python3 -m pip install -e .
osbackup --help
```

Optional:

```bash
python3 -m pip install -e ".[dev]"     # pytest
python3 -m pip install -e ".[s3]"      # boto3 for S3-compatible cloud
```

External binaries are **not** Python dependencies:

| Binary | Role |
|---|---|
| rsync | Preferred for local POSIX snapshots (GNU rsync on Linux; OpenRsync on macOS is probed and may fall back to copy) |
| dpkg, apt-mark | Debian-family package lists |
| rpm, dnf | Red Hat-family package lists |
| pacman | Arch-family package lists |
| brew | macOS Brewfile metadata |
| winget | Windows package list |

## CLI usage

```bash
osbackup --help
osbackup --version
osbackup detect
osbackup platforms
osbackup interactive
osbackup backup --destination-type internal --destination /mnt/backup/operatingsystembackup --yes
osbackup backup --destination-type zip-home --source /path/to/tree --dry-run --yes
osbackup config path
osbackup config init
osbackup config validate
osbackup dest validate /mnt/backup/operatingsystembackup
osbackup history --destination /mnt/backup/operatingsystembackup
osbackup restore BACKUP_ID --destination /mnt/backup/operatingsystembackup --to /tmp/restore --yes
osbackup history --destination-type zip-home --zip-dir ~/osbackup-archives
osbackup restore BACKUP_ID --destination-type zip-home --zip-dir ~/osbackup-archives --to /tmp/restore --yes
```

`python3 backup.py` still starts the CLI and prints a deprecation warning.

Non-interactive `backup` reads config plus flags. `--source` / `--exclude` are repeatable. `--full` forces a new baseline; otherwise a complete parent is used when one exists. `--yes` skips the TTY confirmation prompt. Without a TTY, backup proceeds without prompting.

If stdin is a TTY and no local destination is configured, `osbackup backup` switches to interactive mode instead of crashing.

### `osbackup backup` flags

| Flag | Role |
|---|---|
| `--platform {linux,macos,windows}` | Manual OS override |
| `--family` | Family override (`debian`, `redhat`, `arch`, `macos`, `windows`) |
| `--distro ID` | Distro id from `osbackup platforms` (for example `linuxmint`) |
| `--destination-type {external,internal,zip-home,cloud}` | Required unless config `default_destination_type` is set |
| `--destination PATH` | Local path for external/internal |
| `--zip-dir PATH` | ZIP archive directory (zip-home) |
| `--incremental` / `--full` | Incremental when a baseline exists (default) or force full |
| `--dry-run` | Report planned id, parent, and added/changed/deleted counts; **does not write**. The rsync argv is logged when rsync would be used; it is not executed |
| `--config PATH` | Config override |
| `--source PATH` | Repeatable source override (replaces adapter/config sources) |
| `--exclude PATH` | Repeatable extra exclude |
| `--yes` | Skip confirmation |
| `--verbose` / `--quiet` | Logging |
| `--strict-sources` | Fail if any requested source is missing |
| `--checksum-always` | Hash every file (slow) |

## Destinations

**External** and **internal** local drives share one implementation. Snapshots live under `PATH/osbackup/<YYYY-MM-DD_HH-MM-SS>-<id>/` with `manifest.json` and `files.jsonl`. On POSIX, `latest` is a relative symlink (plus `latest.json`). On Windows, `latest.json` is the pointer. If the path is on the same device as `$HOME`, external mode warns but still allows the run.

A destination inside a source is refused (`DestinationLoopError`).

**ZIP home** writes `~/osbackup-archives/` (mode `0700` on POSIX) unless `archive.zip_dir` / `--zip-dir` is set. Names look like `osbackup-macos-macos-20260914T160000-ab12cd34.zip`. Files are written as `*.zip.partial` then renamed. Incremental zips contain added/changed files only; deletions are recorded in the manifest. A sidecar `*.manifest.json` sits next to the zip; `OSBACKUP/manifest.json` is also stored inside.

**Cloud** is S3-compatible only in v1 (AWS S3, MinIO, Backblaze B2’s S3 API, and similar). Install `operatingsystembackup[s3]`. Credentials come from the environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`) or the shared AWS credentials file — never from committed JSON. Object layout: `s3://bucket/<prefix>/osbackup/<backup_id>/` with pack zip, `files.jsonl`, and `manifest.json` uploaded last.

Google Drive, OneDrive, and Dropbox are not implemented.

## Incremental backups

- Local POSIX disk: rsync into a new snapshot directory with `--link-dest` pointing at the last **complete** snapshot (not a dangling `latest` on first run). `--link-dest` is omitted when there is no parent. `--delete` applies only inside that snapshot prefix, never to the backup root.
- Local Windows / rsync-unavailable: copy added/changed files; `os.link` unchanged files from the parent snapshot when the volume allows it.
- ZIP and cloud: full pack, then delta packs plus parent ids. Restore replays the chain and honors deletions.
- Manifest schema version `1`. Incremental manifests list added/changed/deleted; unchanged files are counted. Full backups list every file (via `files.jsonl`).
- Retention (`incremental.retention_max_backups`, default 14, optional `retention_max_days`) deletes oldest **chains** (a full backup and the incrementals that need it), never a middle incremental, and never the destination root. Only snapshot directories that match OperatingSystemBackup ids are removed.

Interrupted runs leave `partial-*` directories or `*.zip.partial` files. History lists only `state=complete`. The next run will not use a partial as a parent.

## Configuration

| Platform | User config path |
|---|---|
| Linux | `$XDG_CONFIG_HOME/operatingsystembackup/config.json` (default `~/.config/operatingsystembackup/config.json`) |
| macOS | `~/Library/Application Support/operatingsystembackup/config.json` |
| Windows | `%APPDATA%\operatingsystembackup\config.json` |

`osbackup config path` prints the platform path. `osbackup config init` writes `config.example.json`-style defaults. `--config` overrides.

If `~/backup/config.json` or `./config.json` exists, it is loaded with a warning (legacy keys `sources`, `exclude`, `destination`, `log_file`). Empty `sources` means adapter defaults (home + `/etc` on Linux families; home only on macOS/Windows).

See `config.example.json`. Do not put AWS secret keys in JSON; those keys are rejected on load.

## Detection and overrides

`osbackup detect` reads `platform.system()` and Linux `/etc/os-release`. Flags `--platform` / `--family` / `--distro` always win over detection. Config `default_family` / `default_distro` apply only when detection fails.

## Permissions

The CLI does not `sudo` itself. `/etc` is best-effort: unreadable files are skipped and counted. rsync exit codes 23 and 24 (partial transfer because of permissions) are treated as warnings so a non-root home+`/etc` backup can still complete. Other rsync failures fall back to the copy backend when possible, or abort without updating `latest`.

Windows does not require Developer Mode symlinks.

## Security

- Destinations inside sources are refused
- Subprocess calls use argv lists (`shell=False`)
- ZIP restore rejects `..` and absolute members
- Retention never `rm -rf`s the destination root
- Logs redact `AKIA…` / `ASIA…` keys, `Bearer` tokens, and `aws_secret…`
- A default home backup **includes** `~/.ssh` and browser profiles; add excludes if you do not want that
- Do not commit backup data, zips, or `config.json`

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `unsupported distribution` | Unknown `ID` without a usable `ID_LIKE`; see `osbackup platforms` |
| `rsync is not available` / copy used | Install rsync, or accept the copy backend |
| OpenRsync flag errors | The engine probes flags and retries without `-X`; it may fall back to copy |
| `destination is not writable` / disconnected | Mount the drive; path must exist or have a writable parent |
| `pip install 'operatingsystembackup[s3]'` | Cloud selected without boto3 |
| `cloud.bucket is required` | Set `cloud.bucket` in config |
| `S3 authentication failed` | Fix `AWS_PROFILE` / keys; nothing is read from committed JSON |
| `incompatible manifest` | `schema_version` newer or corrupt JSON; use `--full` |
| `no usable sources remain` | Every `--source` was missing; pass `--strict-sources` to fail earlier |

## Development

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

## Testing / CI

GitHub Actions runs pytest on Ubuntu, macOS, and Windows (Python 3.10 and 3.12). An optional Fedora container job smoke-tests Red Hat adapters and is allowed to fail. This repository’s audit/development host is macOS: it cannot execute real `apt`/`dnf`/`pacman`/`winget` against Mint/Fedora/Arch/Windows. Those paths are mocked in tests.

## Current limitations

- No Google Drive, OneDrive, or Dropbox
- No systemd unit installer
- No backup encryption
- No full-disk image
- Windows incremental without rsync is copy + hardlink
- Restore is file-level into `--to` (snapshot layout `home/…`, `etc/…`, or `extra/…` depending on the source path)
- No AUR helper inventory
- Dry-run does not execute rsync (it reports the file diff and planned path)

## Project structure

```text
LinuxMintBackup/                          # clone directory name may stay
├── .cursor/operating-system-backup-plan.md
├── .github/workflows/ci.yml
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml
├── config.example.json
├── backup.py                             # deprecated shim
├── src/operatingsystembackup/
└── tests/
```

## Roadmap

More cloud providers, AUR helpers, and an example systemd unit are later work — they are not in this release.

## Author

Novrus Shehaj
GitHub: https://github.com/NovrusShehaj
Repository (current GitHub name): https://github.com/NovrusShehaj/LinuxMintBackup

## License

MIT. See [LICENSE](LICENSE).
