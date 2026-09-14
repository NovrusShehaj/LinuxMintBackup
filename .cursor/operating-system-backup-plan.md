# OperatingSystemBackup Repository Improvement Plan

Phase 1 audit-and-plan document only. This file is the sole repository artifact created during Phase 1. Do not treat this document as authorization to implement Phase 2.

**Repository path (verified):** `/Users/novrusshehaj/Github/LinuxMintBackup`  
**Required local Git branch:** `dev/repo-improvements`  
**Required new project name:** `OperatingSystemBackup`  
**Audit host:** macOS Tahoe 26.6.2, Darwin 25.6.0, arm64 (Apple M3 Max). This host is not Linux Mint, Fedora, RHEL, Arch, or Windows.

**Audit limitation:** Interactive `Shell` in this Phase 1 session was rejected (including a later explore-subagent retry). Git state below is reconstructed from `.git/HEAD`, `.git/config`, `.git/refs/**`, `.git/logs/**`, `.git/packed-refs`, the conversation-start `git status` snapshot, and the three tracked working-tree files. Do not pretend a live `git status`/`git log` process ran in this session.

---

## 1. Executive Summary

`LinuxMintBackup` is an 80-line Python 3 script (`backup.py`) plus a committed `config.json` and a README that over-claims production readiness. There is no package metadata, no tests, no `.gitignore`, no LICENSE file, no CLI parser, no OS detection, and no Linux Mint-specific logic in code. The useful core is a timestamped `rsync` snapshot with `--link-dest` against a `latest` symlink. That core is currently **non-runnable**: `Path.mkdir(..., exisit_ok=True)` is a typo, and `cmd.extend(source)` references an undefined name.

The evolution to `OperatingSystemBackup` should **extract and repair** that rsync snapshot workflow, then wrap it in a small stdlib-first package with:

- a real CLI (`osbackup`, alias `operatingsystembackup`) plus an interactive mode
- a centralized OS/distribution registry (Debian family including Linux Mint, Red Hat family, Arch family, macOS, Windows)
- four destination classes: external drive, internal drive/volume, home-directory ZIP, cloud (S3-compatible in v1)
- genuine incremental backups (keep `--link-dest` on POSIX local disks; add JSON manifests for history, changed-file lists, ZIP/cloud, and Windows)
- platform-appropriate config paths, logging, and explicit errors
- pytest coverage with mocks so this macOS host can prove most logic without apt/dnf/pacman/Windows

Avoid a green-field rewrite, a plugin framework, extra GUIs, backup encryption, systemd, or implementing every cloud vendor. Preserve Linux Mint behavior by making Mint a first-class Debian-family distro whose default sources remain home + `/etc` with cache/Trash exclusions, rsync snapshots, and a `latest` pointer.

**Local rename** happens in metadata, docs, CLI, and package names inside this clone on `dev/repo-improvements`. **Remote GitHub rename** (`NovrusShehaj/LinuxMintBackup` → `OperatingSystemBackup`) is a separate manual hosting step and is **not** performed by Phase 2.

---

## 2. Current Repository Audit

### 2.1 Path, branch, remotes, status

| Item | Evidence | Observation |
|---|---|---|
| Work tree | Workspace path; `.git` present | `/Users/novrusshehaj/Github/LinuxMintBackup` |
| HEAD | `.git/HEAD` | `ref: refs/heads/dev/repo-improvements` |
| `dev/repo-improvements` exists locally | `.git/refs/heads/dev/repo-improvements` | Yes. Tip `e697fe62c2b2d499f995af2aa41acf0c56f36542` |
| `master` exists locally | `.git/refs/heads/master` | Same tip `e697fe62c2b2d499f995af2aa41acf0c56f36542` |
| Remote `dev/repo-improvements` | `.git/refs/remotes/origin/` and `.git/packed-refs` | **Does not exist.** Only `refs/remotes/origin/HEAD` → `origin/master` |
| `origin` | `.git/config` `[remote "origin"]` | `git@github.com:NovrusShehaj/LinuxMintBackup.git` |
| `master` upstream | `.git/config` `[branch "master"]` | `remote = origin`, `merge = refs/heads/master` |
| `dev/repo-improvements` upstream | `.git/config` `[branch "dev/repo-improvements"]` | **No `remote`/`merge`.** Only `vscode-merge-base = origin/master` |
| Reflog | `.git/logs/HEAD`, `.git/logs/refs/heads/*` | Clone from GitHub onto `e697fe62…`, then `checkout` created `dev/repo-improvements` from that commit. Author in reflog: `Novrus Shehaj <78491450+NovrusShehaj@users.noreply.github.com>` |
| Packed remote tip | `.git/packed-refs` | `e697fe62c2b2d499f995af2aa41acf0c56f36542 refs/remotes/origin/master` |
| Conversation-start `git status` | Cursor snapshot at session start | `## dev/repo-improvements` with **no** staged/unstaged/untracked listing → clean tree, no upstream ahead/behind |
| Working files besides `.git` | Recursive glob of the work tree | `backup.py`, `config.json`, `README.md` only |
| `.cursor/` | Glob before this plan | Did not exist; created solely to hold this plan |

Unexpected: a Cursor terminal prompt still showed `master` at 11:45 local while `.git/HEAD` is `dev/repo-improvements` (stale prompt, not a second work tree). `.git/gk/config` and `.git/kilo` exist (GitKraken/Kilo tooling). Git object packs were not enumerable via workspace glob; commit **subject/body was not readable** without `git show`. Do not invent a commit message.

### 2.2 Tracked vs documented layout

README.md project structure claims:

```text
LinuxMintBackup/
├── backup.py
├── config.json
├── logs/
├── .gitignore
└── README.md
```

**Actually present:** `backup.py`, `config.json`, `README.md`.  
**Absent (confirmed by glob):** `.gitignore`, `logs/`, `LICENSE`, `tests/`, `pyproject.toml`, `setup.py`, `requirements.txt`, `Pipfile`, `poetry.lock`, `uv.lock`, `.github/`, systemd units, shell wrappers, `CONTRIBUTING.md`.

`.git/info/exclude` only ignores Kilo worktree paths. It is not a project `.gitignore`.

### 2.3 Language, dependencies, packaging

- **Language:** Python 3. Shebang `#! /usr/bin/env python3` (space after `#!`) in `backup.py`.
- **README requirement:** Python 3.8+ and `rsync`; install hint is `sudo apt install rsync` (Debian-family only).
- **Imports in `backup.py`:** `subprocess`, `json`, `logging`, `datetime.datetime`, `pathlib.Path`, `sys`, `tarfile`. **Zero third-party libraries.**
- **Package/build system:** none. No installable distribution, no console-script entry point, no version pin.
- **External binary:** `rsync` invoked by `subprocess.run` in `run_backup`.
- **Tests / coverage:** none.
- **Installation process:** undocumented beyond `python3 backup.py`. No `pip install`.

### 2.4 Entry points and CLI

- Sole executable entry: `backup.py` `if __name__ == "__main__": main()`.
- No `argparse`, no subcommands, no `--help`, no `--dry-run` (README claims dry runs).
- No interactive prompts.
- Config path is **not** CLI-overridable.

### 2.5 Configuration, logging, errors, privileges

- Runtime config path is hard-coded: `CONFIG_PATH = Path.home() / "backup/config.json"` in `backup.py`. The **repository** `config.json` is never opened by `load_config()`.
- `load_config()` has no schema validation; missing keys raise `KeyError`.
- `setup_logging(log_file)` uses `logging.basicConfig(filename=log_file, level=INFO)` only — no console handler, no directory creation, no secret redaction.
- Failures: `run_backup` logs `result.stderr` and `sys.exit(1)` if rsync `returncode != 0`. No typed errors, no distinction among missing rsync, unreadable source, unwritable dest, or full disk.
- Privilege: none. Backing up `/etc` as in `config.json` typically needs root; the script neither detects this nor uses a narrow privilege path.

### 2.6 Restore, packages, compression, destinations

| Capability | Present? | Where |
|---|---|---|
| File copy backup | Intended via rsync | `run_backup` |
| Incremental | Intended via `rsync --link-dest …/latest` | `run_backup` |
| Restore command | **No** | README only mentions a `latest` symlink “for easy restores” |
| Package/application inventory | **No** | — |
| Config backup as a first-class feature | Only if `/etc` is listed in `sources` | `config.json` |
| User-data backup | Yes, if home is in `sources` | `config.json` |
| Compression | Dead code `archive_builds` writes `builds_{date}.tar.gz` via `tarfile`; **never called**. No ZIP | `backup.py` |
| Destination handling | Single local directory string | `config["destination"]` |
| Cloud | **No** | — |
| External vs internal drive distinction | **No** | — |

### 2.7 Hard-coded assumptions and portability

- Binary `rsync` with GNU-style `-aAx`, `--numeric-ids`, `--link-dest` (Linux-oriented; macOS OpenRsync/old rsync often lack `-A` / differ).
- `latest` as a symlink (`Path.symlink_to`) — poor on Windows without Developer Mode / privilege.
- `CONFIG_PATH` under `~/backup/config.json`.
- Example paths `/home/novrus`, `/home/ghost`, `/mnt/backup/linux-mint`.
- README: Linux Mint, `apt`, systemd timer (no unit files exist).

### 2.8 Security snapshot

- `subprocess.run(cmd, …)` uses a **list** (no `shell=True`) — keep this.
- No destination-inside-source guard (rsync can copy the backup into itself).
- `--delete` is passed; currently the dest is a new timestamp directory, so risk is low unless that path already exists.
- Committed `config.json` exposes this user’s home layout (not passwords). Still should not be the canonical committed config.
- Entire home backup would include `~/.ssh` and browser profiles; undocumented.
- `latest.unlink()` then `symlink_to` is not atomic.

### 2.9 Documentation vs code

README claims production-ready, systemd automation, dry runs, `.gitignore`, and `logs/`. None of those exist in the tree except the README sentences themselves. License is declared MIT with **no** `LICENSE` file.

---

## 3. Existing Linux Mint Functionality

There is **no** Mint-only branch, menu, or `os-release` check. Mint support is branding + example paths + an `apt` install snippet. The behavior worth preserving is the **generic Linux file-backup workflow** that Mint users would run.

### 3.1 What exists (map to symbols)

| Symbol | File | Behavior |
|---|---|---|
| `CONFIG_PATH` | `backup.py` | `Path.home() / "backup/config.json"` |
| `load_config()` | `backup.py` | `json.load` that file |
| `setup_logging(log_file)` | `backup.py` | File logger INFO |
| `archive_builds(build_dir, output_dir)` | `backup.py` | Unused daily `builds_YYYY-MM-DD.tar.gz` |
| `run_backup(sources, destination, exclude)` | `backup.py` | Timestamp dir `YYYY-MM-DD_HH-MM-SS`, rsync `-aAx --delete --numeric-ids --link-dest <dest>/latest`, excludes, then replace `<dest>/latest` symlink |
| `main()` | `backup.py` | load config → log → `run_backup(sources, destination, exclude)` |

`config.json` intended sources: `/home/novrus`, `/etc`. Excludes: `~/.cache`, `~/.local/share/Trash`. Destination: `/mnt/backup/linux-mint`. Log: `/home/ghost/backup/logs/backup.log` (inconsistent user `ghost` vs `novrus`).

### 3.2 What Linux Mint users actually get today

If the typos were fixed and `~/backup/config.json` existed, a Mint box would get:

1. Hardlink-based incremental snapshots on a local mount (true incremental for unchanged files, not a naive full copy).
2. Timestamped directories for point-in-time trees.
3. A `latest` symlink as the restore handle (manual `rsync`/`cp` back; no app restore).
4. Configurable extra sources and excludes.
5. File logging of the rsync command line and failures.

### 3.3 Preserve vs replace

| Behavior | Decision | Replacement / why |
|---|---|---|
| rsync `-a` snapshot + `--link-dest` on local POSIX disks | **Preserve and fix** | Still the right incremental primitive on Linux Mint and other Unix disks. Adding manifests on top, not instead. |
| Timestamped snapshot directories | **Preserve** | Plus a stable `backup_id` in the manifest |
| `latest` symlink | **Preserve on POSIX** | On Windows use `latest.txt` or a junction; do not pretend `symlink_to` is portable |
| `sources` / `exclude` / `destination` / `log_file` keys | **Preserve as a legacy schema** | Migrated into the new config with extras |
| Back up home + `/etc` by default on Debian-family | **Preserve as adapter defaults** | `/etc` becomes best-effort / privilege-aware |
| Cache and Trash excludes | **Preserve as Debian/Mint defaults** | Extend with other junk caches |
| `python3 backup.py` | **Preserve as shim** | Deprecation warning → same engine |
| `~/backup/config.json` | **Read if present** | Warn; prefer XDG/app config |
| `archive_builds` tar.gz of “builds” | **Do not preserve as a hidden extra** | Dead, undocumented. ZIP home archives cover the compression use-case the product actually asked for |
| systemd timer | **Do not invent in v1** | README-only; not in acceptance criteria. Optional later |
| `--delete` | **Keep only inside the snapshot dir, and not on first-create empty dirs unless rsync needs it** | Document; never `--delete` the backup root |
| Dry run | **Implement for real** | README promised it; `rsync --dry-run` + zip listing |

---

## 4. Problems and Technical Debt

Grounded in `backup.py`, `config.json`, `README.md`:

1. **Script does not run:** `exisit_ok` (`backup.py` `run_backup`) is not a valid `Path.mkdir` keyword → `TypeError`. `cmd.extend(source)` → `NameError` (`source` vs `sources`).
2. **README/code split:** dry-run, systemd, `.gitignore`, `logs/`, “production-ready” are false.
3. **Wrong config file:** repo `config.json` is unused; `CONFIG_PATH` is `~/backup/config.json`.
4. **Inconsistent identities in committed config:** `/home/novrus` vs `/home/ghost/backup/logs/backup.log` vs destination `linux-mint`.
5. **No CLI / no `--help` / no non-interactive flags.**
6. **No OS/distro model** — cannot select Debian/RHEL/Arch/macOS/Windows.
7. **rsync-only destinations** — no ZIP, no cloud, no drive classification, no writable/free-space checks.
8. **Incremental is incomplete:** `--link-dest` to a missing `latest` on first run; no manifest, checksums, backup IDs, retention, or changed-file report. Interrupted runs can still flip `latest` only after success (good) but the snapshot dir is left partial (bad).
9. **`archive_builds` dead code** plus unused `tarfile` import.
10. **Logging:** file-only; command line joined with `" ".join(cmd)` can be huge; no console; typo `sucessfully`.
11. **Error handling:** single `sys.exit(1)`.
12. **Security:** no dest-in-source check; home includes secrets; `--delete`; non-atomic symlink update; personal paths committed.
13. **Windows/macOS:** flags `-A`, `--numeric-ids`, symlink `latest` will fail or no-op wrongly.
14. **Privilege:** `/etc` backup will fail for a normal user with a generic rsync error.
15. **No tests, no CI, no packaging, no version, no LICENSE file.**
16. **No restore implementation** despite README restore language.
17. **Maintainability:** one module, no types, no validation, no layering — but it is small, so the fix is a **thin package**, not a framework.

---

## 5. Target Architecture

Keep Python. Do not add Django/Typer/Celery/databases. Three adapter surfaces are enough:

```text
CLI (argparse) ─┬─ interactive prompts (stdlib input)
                └─ flags/subcommands
                      │
                      ▼
              BackupRequest (models)
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
   PlatformAdapter  Sources     DestinationProvider
   (detect+defaults (paths +    (local disk / zip /
    + package list)  excludes)   S3-compatible)
                      │
                      ▼
              BackupEngine
         (full vs incremental)
         ┌──────────┴──────────┐
         ▼                     ▼
   RsyncBackend            ManifestStore
   (POSIX local)           (JSON per backup)
   CopyBackend
   (Windows / fallback)
```

**Why this fits the current code:** `run_backup` is already a backend. `load_config`/`setup_logging` become modules. There are no classes to preserve; introducing a few Protocols is additive, not a rewrite of a large OO tree.

**Registries (plain dicts, not setuptools plugins in v1):**

- `FAMILY_REGISTRY`: linux-debian, linux-redhat, linux-arch, macos, windows
- `DISTRO_REGISTRY`: maps distro id → family + adapter class
- `DESTINATION_REGISTRY`: external, internal, zip-home, cloud-s3

Adding a distro is one registry row. Adding a cloud vendor is a new `CloudProvider` class plus a registry row — not a change to `BackupEngine`.

**Non-goals for v1 (anti-over-engineering):** plugin entry points, async, SQL history, encryption-at-rest, FUSE mounts, restic/borg replacement, systemd installers, implementing Google Drive / OneDrive / Dropbox, full disk imaging, GUI.

---

## 6. Project Rename Strategy

### 6.1 Local project rename (Phase 2, this clone)

| Location | Current | Planned |
|---|---|---|
| GitHub repo name (remote) | `LinuxMintBackup` | **Unchanged by Phase 2** |
| Local directory name | `LinuxMintBackup` | **Do not `mv` the clone.** Optional later user action |
| README title | `# LinuxMintBackup` | `# OperatingSystemBackup` |
| README body, examples, structure diagram | LinuxMintBackup | OperatingSystemBackup |
| `config.json` destination example | `/mnt/backup/linux-mint` | `/mnt/backup/operatingsystembackup` (example file only) |
| `pyproject.toml` `project.name` | (absent) | `operatingsystembackup` |
| Import package | (absent) | `operatingsystembackup` |
| CLI | `python3 backup.py` | `osbackup` and `operatingsystembackup` |
| Archive/ZIP prefix | `builds_YYYY-MM-DD.tar.gz` (dead) | `osbackup-<platform>-<id>.zip` / snapshot dir `osbackup-<id>` |
| User-facing log messages | “Backup completed sucessfully” | “OperatingSystemBackup: backup … succeeded” |
| Comments | none branded | only where they clarify |
| Tests | none | `tests/` importing `operatingsystembackup` |
| Config app name | `~/backup/` | platform dirs named `operatingsystembackup` |

Do **not** blindly replace the string `linux-mint` inside backup **data** or inside `ID_LIKE` detection (Mint’s `os-release` id must remain `linuxmint`). Do not rename Debian-family default paths `/etc` or `$HOME`.

`backup.py` filename may remain as a compatibility shim so old docs/scripts keep working.

### 6.2 Remote hosting rename (not Phase 2)

See section 36. Phase 2 must not run `gh repo rename`, must not change `origin` URL, must not claim GitHub was renamed.

---

## 7. CLI Design

**Branding:** OperatingSystemBackup.  
**Package:** `operatingsystembackup`.  
**Primary executable:** `osbackup` (short, typable).  
**Alias:** `operatingsystembackup` (matches the prompt’s `operatingsystembackup --help` example). Both are `[project.scripts]` in `pyproject.toml`.  
**Module form:** `python3 -m operatingsystembackup`.  
**Shim:** `python3 backup.py` calls `operatingsystembackup.cli.main` with a one-line stderr deprecation notice.

Implementation: **stdlib `argparse`**, not Typer/Click (keeps zero required third-party deps). Interactive mode: stdlib `input()` with numbered menus (no `questionary` unless we later want it as extra).

### 7.1 Subcommands (only what the architecture needs)

```text
osbackup --help
osbackup --version
osbackup detect
osbackup platforms
osbackup backup [options]
osbackup interactive
osbackup config show | path | init | validate
osbackup dest validate PATH
osbackup history [--destination PATH]
osbackup restore BACKUP_ID [--destination PATH] --to PATH
```

`backup` without flags that require a TTY should work non-interactively from config + flags (automation). `interactive` is the guided path. If stdin is a TTY and no destination/config is found, `backup` may offer to switch to interactive rather than crash.

### 7.2 `osbackup backup` flags

| Flag | Role |
|---|---|
| `--platform {linux,macos,windows}` | Manual OS override |
| `--family {debian,redhat,arch}` | Linux family override |
| `--distro ID` | e.g. `linuxmint`, `ubuntu`, `fedora` |
| `--destination-type {external,internal,zip-home,cloud}` | Required unless config default exists |
| `--destination PATH` | Local path (external/internal) |
| `--incremental / --full` | Incremental option (default incremental when a baseline exists) |
| `--dry-run` | No writes; rsync `--dry-run` or zip inventory |
| `--config PATH` | Config file override |
| `--source PATH` (repeatable) | Override sources |
| `--exclude PATH` (repeatable) | Extra excludes |
| `--yes` | Skip confirmation |
| `--verbose` / `--quiet` | Logging |

### 7.3 Interactive flow

1. Run detection; print OS/family/distro; allow override from `platforms` registry lists (not hard-coded menu copies).
2. Choose destination class; prompt path or cloud bucket/profile.
3. Validate destination.
4. Confirm sources/excludes from adapter defaults + config.
5. Incremental vs full.
6. Summary → confirm → `BackupEngine.run`.

Unsupported OS/distro: `UnsupportedPlatformError` with the registry’s supported list. No crash traceback as the only output.

---

## 8. OS and Distribution Architecture

### 8.1 Detection (graceful)

Module: `operatingsystembackup/detect.py`

- `platform.system()` → `Linux` / `Darwin` / `Windows` / other.
- Linux: read `/etc/os-release` (and `/usr/lib/os-release` fallback). Parse `ID`, `ID_LIKE`, `VERSION_ID`, `NAME`. Never assume Mint.
- macOS: `platform.mac_ver()`; optional `sw_vers` via `process.run` if needed.
- Windows: `platform.win32_ver()`; `sys.getwindowsversion()`.
- Failure: return `DetectionResult(ok=False, reason=...)`. CLI still allows `--platform/--distro`.

### 8.2 Central registry

Module: `operatingsystembackup/platforms/__init__.py`

```text
Linux family → distro IDs → adapter class
debian → debian, ubuntu, linuxmint, pop, raspbian, neon, zorin, elementary  → DebianAdapter
redhat → fedora, rhel, centos, rocky, almalinux, ol  → RedHatAdapter
arch   → arch, manjaro, endeavouros, garuda, extra? → ArchAdapter
macos  → macos, darwin → MacOSAdapter
windows → windows → WindowsAdapter
```

`ID_LIKE` maps unknown but compatible IDs onto a family (e.g. Mint `ID=linuxmint` `ID_LIKE=ubuntu debian`). Unknown ID with known `ID_LIKE` → family adapter + warning. Unknown ID and like → error, list supported IDs.

Do **not** scatter distro names in CLI help strings; help text should call `list_distros(family)`.

### 8.3 Adapter interface

`operatingsystembackup/platforms/base.py` — `PlatformAdapter` Protocol:

- `family_id`, `distro_id`, `display_name`
- `default_sources() -> list[Path]`
- `default_excludes() -> list[str]`
- `collect_package_inventory() -> PackageInventory` (optional; skip if tools missing)
- `rsync_supported() -> bool`
- `privilege_notes() -> str`

Linux Mint is **not** a special adapter class. It is `DebianAdapter` with `distro_id=linuxmint` and Mint-friendly default excludes (Trash path as today).

Manual override always wins over detection.

---

## 9. Debian-Family Support

**Adapter:** `operatingsystembackup/platforms/debian.py` — `DebianAdapter`.  
**Distros (v1, reliable):** `debian`, `ubuntu`, `linuxmint`, `pop` (Pop!_OS). Optional same adapter: `raspbian`, `neon`, `elementary`, `zorin` (same apt/dpkg). Do not add Ubuntu derivatives we cannot describe in README as tested.

**Package inventory (optional tools):**

- Prefer `dpkg --get-selections` for a restore-friendly package list.
- Also capture `apt-mark showmanual` when `apt-mark` exists (manual vs auto).
- Store as backup metadata files: `metadata/dpkg-selections.txt`, `metadata/apt-manual.txt`.
- If `dpkg` missing: warning `OptionalDependencyError` path — file backup still proceeds.

**Default sources (Mint-preserving):** `$HOME`, `/etc`.  
**Default excludes:** `~/.cache`, `~/.local/share/Trash`, plus `~/.Trash`, thumbnail caches.  
**Transfer:** GNU rsync backend (`-aH`, `--numeric-ids`; include `-A`/`-X` only if `rsync` supports them — probe once).  
**Config backup:** `/etc` best-effort; unreadable files skipped with count in the summary (do not require running the whole CLI as root).

**Tests:** parse fixture `os-release` for Mint/Ubuntu/Debian; mock `dpkg` missing vs present.

---

## 10. Red-Hat-Family Support

**Adapter:** `operatingsystembackup/platforms/redhat.py` — `RedHatAdapter`.  
**Distros:** `fedora`, `rhel`, `centos` (CentOS Stream), `rocky`, `almalinux`. Optional: `ol` (Oracle Linux) same RPM API.

**Package inventory:**

- `rpm -qa --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n'` if `rpm` exists.
- If `dnf` exists, also `dnf repoquery --userinstalled` (or equivalent) when available; if not, skip extras.
- Files: `metadata/rpm-qa.txt`, `metadata/dnf-userinstalled.txt` (optional).

**Default sources:** `$HOME`, `/etc`.  
**SELinux:** do not require `rsync -X` success; if xattrs fail, retry without `-X` and warn.  
**Tests:** mocked `/etc/os-release` for Fedora/Rocky; mocked `rpm`/`dnf` absences.

This macOS host **cannot** execute real `dnf`/`rpm`. CI container job later (section 30).

---

## 11. Arch-Family Support

**Adapter:** `operatingsystembackup/platforms/arch.py` — `ArchAdapter`.  
**Distros:** `arch`, `manjaro`, `endeavouros`. Optional same pacman API: `garuda`, `cachyos` only if `ID_LIKE` contains `arch` — still one adapter.

**Package inventory:**

- `pacman -Qqe` (explicit) and `pacman -Qq` (all) when `pacman` exists.
- Files: `metadata/pacman-explicit.txt`, `metadata/pacman-all.txt`.
- AUR helpers (`yay`, `paru`) are **out of v1** (optional later).

**Default sources:** `$HOME`, `/etc`. Note Arch `/etc` is especially important; same privilege model as Debian.  
**Tests:** mocked os-release + missing `pacman`.

---

## 12. macOS Support

**Adapter:** `operatingsystembackup/platforms/macos.py` — `MacOSAdapter`.

**Sources:** `$HOME` by default. Do **not** default-backup `/etc` or `/System`. Optional `--include-system-config` for `/Library` / `/opt/homebrew` etc. is a later flag; v1 can allow extra `--source`.

**Excludes:** `~/Library/Caches`, `.Trash`, Time Machine local snapshots are not walked if `-x` one-file-system is on.

**Packages:** if `brew` exists, `brew bundle dump --file=- --brews --casks --taps --mas` captured to `metadata/Brewfile`. If no Homebrew, skip with a clear optional-dependency message.

**rsync:** macOS Tahoe/OpenRsync may reject `-A`, `--numeric-ids`, GNU `--link-dest` semantics. Probe `rsync --version`. Strategy:

1. GNU rsync (Homebrew) → Linux-like flags minus Linux-only xattrs as needed.
2. OpenRsync → reduced flag set; still try `--link-dest` if advertised.
3. No usable rsync → `CopyBackend` (shutil + hardlink when `os.link` works on APFS).

**ZIP destination** is fully supported on this host (stdlib `zipfile`).

**What this audit host can validate:** detection of Darwin, CLI, config dirs under `~/Library/Application Support/operatingsystembackup`, ZIP, unit tests, maybe local rsync probe. **Cannot validate:** Linux Mint defaults, apt, SELinux, Windows ACLs.

---

## 13. Windows Support

**Adapter:** `operatingsystembackup/platforms/windows.py` — `WindowsAdapter`.

**Sources:** `%USERPROFILE%` default. Do not default `C:\Windows`. Optional extra sources via config.

**Excludes:** `%LOCALAPPDATA%\Temp`, Recycle Bin, `AppData\Local\*.log` caches as a small default list (documented).

**Packages:** if `winget` exists, `winget export -o -` or `winget list` to `metadata/winget.txt`. If missing, skip. Do not require PowerShell Get-WmiObject as a hard dep.

**Transfer:** do **not** require rsync. `CopyBackend` using `shutil.copy2`, optional `os.link` on NTFS for incremental. `latest` is a text file `latest.json` pointing at the backup id (avoid symlink requirement). If the user has rsync (cwRsync/Git Bash) it may be used when `rsync_supported()` is true — optional, not documented as required.

**ZIP:** stdlib `zipfile` works. Path length: use `pathlib`; document 260-char limit; no extra Win32 long-path dependency in v1.

**Tests:** all mocked; this Mac cannot run Windows.

---

## 14. Backup Source Architecture

Module: `operatingsystembackup/sources.py` (keep one file).

**Source kinds:**

1. **User data:** adapter `default_sources()` home directory.
2. **System configuration:** `/etc` on Linux families only, best-effort.
3. **Package inventory:** generated files under the snapshot’s `metadata/` (not a substitute for `/usr` binaries).
4. **Explicit config/CLI paths:** union with defaults.

**Not in v1:** imaging `/`, backing up `/usr`, Docker volumes, databases dump agents. Users can add extra `--source` paths if they insist.

**Discovery:** expand `~`, resolve `Path.expanduser().resolve(strict=False)`, drop missing sources with `InaccessibleSourceError` listed in the summary (fail the run only if **zero** sources remain, or if `--strict-sources`).

**Excludes:** config list + adapter defaults + **automatic dest-path exclude** so the backup never includes its own destination.

**Interaction with current code:** today’s `config["sources"]` and `config["exclude"]` are exactly this layer. `run_backup` already loops excludes into rsync `--exclude`. Keep that mapping in `rsync_backend.build_command(sources, dest, exclude, link_dest, dry_run)`.

---

## 15. Backup Destination Architecture

`DestinationProvider` Protocol (`operatingsystembackup/destinations/base.py`):

- `kind: str`
- `validate() -> ValidationReport` (exists, is dir or creatable, writable, free space if available, not inside a source)
- `prepare_backup(backup_id) -> StagingLocation` (partial dir or temp zip)
- `commit(staging)` atomic publish
- `abort(staging)` cleanup
- `list_history() -> list[ManifestSummary]`
- `open_manifest(backup_id)`

**Four kinds share validation helpers** in `operatingsystembackup/fsutil.py`: `is_writable`, `free_bytes`, `is_relative_to(dest, source)`, `same_mount` (Linux `st_dev`, macOS `st_dev`, Windows volume).

External vs internal local drives share `LocalDriveDestination` (`destinations/local.py`) with a `kind` flag for UX and mount-heuristic messages. They are not two copy engines.

ZIP and cloud do **not** use `--link-dest`. They use the incremental pack + manifest strategy in section 20.

---

## 16. External Drive Backups

User-facing type: `external`. Implementation: `LocalDriveDestination(kind="external")`.

**Selection:** CLI `--destination PATH` or interactive path. v1 does **not** scrape GUI disk lists (overkill / platform-specific). Optional later: list `/Volumes` (macOS), `/media/$USER` and `/mnt` (Linux), `Get-Volume` (Windows) as a helper in interactive mode only — a simple `list_candidate_mounts()` in `fsutil.py` is enough.

**Validation:** path exists, is a directory, writable, free space ≥ estimate (du of sources is expensive; v1 estimates from `shutil.disk_usage` vs a sampled size or warns if unreadable). If path is on the same `st_dev` as `$HOME`, **warn** “this looks like the same disk” but allow `--yes` (the drive might be a second partition mis-detected). Prefer warning over hard-fail for same-device to avoid false positives on bind mounts.

**Loop avoidance:** if dest resolves inside any source, `DestinationLoopError`.

**Engine:** POSIX → rsync snapshots under `PATH/osbackup/<backup_id>/`. Windows → copy backend.

---

## 17. Internal Drive Backups

User-facing type: `internal`. Same class as external with `kind="internal"`.

Same safety and capacity checks. Typical paths: second HDD mount, extra APFS volume, D:, `/data`.

Do not require the path to be a different `st_dev` (users backup to another folder on a large disk). Document that incremental hardlinks require the snapshot tree to live on **one** filesystem as `--link-dest`.

Preserve Mint’s `/mnt/backup/linux-mint` as an **example internal/external mount path** in docs, updated to `/mnt/backup/operatingsystembackup`.

---

## 18. Home ZIP Backups

User-facing type: `zip-home`. Module: `operatingsystembackup/destinations/zip_home.py`.

**Location:** `Path.home() / "osbackup-archives"` (created as 0700 on POSIX). Not the repo directory.

**Naming:** `osbackup-{platform}-{distro}-{YYYYMMDDTHHMMSS}-{backup_id}.zip`  
Example: `osbackup-linux-linuxmint-20260914T160000-ab12cd.zip`  
`backup_id` = 8 hex chars from `secrets.token_hex(4)` (not a secret; collision-resistant enough).

**Collision:** if the path exists, append `-2`, `-3`. Never overwrite.

**Creation:** write to `*.zip.partial` in the same directory, then `os.replace` to the final name (atomic on POSIX; best-effort on Windows). On failure delete the partial. `zipfile.ZipFile` with `ZIP_DEFLATED`.

**Interrupted creation:** leftover `*.zip.partial` is ignored by history listing and can be deleted by `osbackup dest validate` cleanup or next run.

**Disk space:** `shutil.disk_usage(home)` vs uncompressed estimate; fail `InsufficientSpaceError` if free < estimate × 0.5 with a clear message (compression ratio unknown).

**Compression errors:** catch `zipfile.LargeZipFile` (enable ZIP64), `OSError`, map to `ArchiveError`.

**Determinism:** `arcname` relative to source roots (`home/...`, `etc/...`, `metadata/...`). Do not store absolute `/home/novrus` prefixes. Sort names when adding.

**Incremental ZIP:** see section 20 — baseline is a full zip; incrementals are smaller zips of changed files plus a sidecar `*.manifest.json` next to the zip (or stored as `OSBACKUP/manifest.json` inside the zip **and** a copy beside it for listing without extract).

This replaces unused `archive_builds` tar.gz. User asked for ZIP specifically; do not ship tar.gz as the user-facing home archive.

---

## 19. Cloud Provider Architecture

**Generic interface:** `operatingsystembackup/destinations/cloud.py` — `CloudProvider` Protocol: `upload(local_path, key)`, `download`, `list_prefix`, `delete_key` (retention only), `probe_auth`.

**v1 implement one provider:** **S3-compatible** (`destinations/s3.py`) via optional extra `operatingsystembackup[s3]` → `boto3`. Covers AWS S3, Backblaze B2 S3 API, MinIO, many NAS boxes. Endpoint URL + bucket + prefix + region + profile name live in **user** config, not in git.

**v1 do not implement:** Google Drive, Microsoft OneDrive, Dropbox. Document as roadmap. They need OAuth apps and would dominate the project.

**Credentials:** never in committed JSON. Read environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`) or shared AWS credentials file. Config may store `profile`, `bucket`, `endpoint_url`, `prefix` only.

**Object layout:** `s3://bucket/prefix/osbackup/<backup_id>/manifest.json` + pack files (`full.tgz` or `delta.tgz` or the zip). Engine builds packs locally in `tempfile.TemporaryDirectory`, then uploads, then writes manifest last (commit). Interrupted = objects without a valid manifest are ignored by `history`.

If `boto3` is missing and user selects cloud: `OptionalDependencyError` telling them `pip install 'operatingsystembackup[s3]'`.

---

## 20. Incremental Backup Design

Current `run_backup` `--link-dest latest` **is** genuine incremental on a single POSIX filesystem (hardlinks). Keep it for local Linux/macOS disks. It is **not** sufficient alone: no IDs, no change list, no ZIP/cloud/Windows, first-run `latest` missing, no retention, no integrity.

### 20.1 Common manifest (`operatingsystembackup/manifest.py`)

JSON file `manifest.json` per backup (schema version `1`):

```json
{
  "schema_version": 1,
  "app": "OperatingSystemBackup",
  "backup_id": "ab12cd34",
  "parent_id": null,
  "kind": "full",
  "timestamp": "2026-09-14T16:00:00+00:00",
  "platform": {"os": "linux", "family": "debian", "distro": "linuxmint"},
  "hostname": "mint-box",
  "sources": ["/home/novrus", "/etc"],
  "excludes": ["..."],
  "destination_kind": "internal",
  "files": [
    {"path": "home/novrus/.bashrc", "size": 123, "mtime_ns": 1, "mode": 420, "sha256": "...", "status": "added"}
  ],
  "counts": {"added": 10, "changed": 2, "deleted": 1, "unchanged": 5000},
  "state": "complete"
}
```

`status` is `added|changed|deleted|unchanged`. Unchanged files may be omitted from the incremental file list with `counts.unchanged` only, to keep manifests small — but then restore needs the parent chain. **Decision:** incremental manifests list **added/changed/deleted** fully; unchanged counted not listed. Full manifests list every file (or a sidecar `files.jsonl` if huge). Prefer `files.jsonl` next to `manifest.json` for scalability without a database.

**Changed-file detection:** compare `(path, size, mtime_ns, mode)` against parent inventory; if those differ, re-hash; if hash differs → `changed`. Optional `--checksum-always` for paranoia (slow).

**Deleted-file handling:** paths in parent inventory missing now → `deleted`. Local rsync snapshots still contain old files in **previous** timestamp dirs; `--delete` applies only within the new snapshot (so the new snapshot does not keep deleted files). History snapshots retain them until retention removes the snapshot.

### 20.2 Strategies by destination

| Destination | Full | Incremental | Restore implication |
|---|---|---|---|
| Local POSIX disk | rsync into new dir; write inventory | rsync `--link-dest` previous complete snapshot (not only `latest` if `latest` is broken — use last `state=complete` id) | Copy/rsync from snapshot dir; deleted files absent in that id |
| Local Windows | copy all files | copy new/changed; `os.link` unchanged when same volume; else copy | Walk manifest chain or copy the snapshot tree |
| ZIP home | full zip + manifest | zip containing only added/changed files; deleted listed in manifest; `parent_id` required | Restore full = extract baseline then each delta in order; honor deletions |
| Cloud S3 | upload full pack + inventory | upload delta pack of added/changed | Download chain, apply deletions |

### 20.3 IDs, timestamps, atomicity, corruption

- `backup_id` unique; directory name includes id + timestamp.
- Staging: `.../partial-<backup_id>/` or `*.partial`. `latest` and `history` only update after `state=complete` and `os.replace` of manifest.
- If process dies: partial left behind; next run does not use it as `--link-dest`. `osbackup history` hides `state!=complete`.
- Corrupt/incompatible manifest (`schema_version` newer, JSON error, missing sha): `IncompatibleManifestError`; do not use as parent; offer `--full`.
- Checksums: sha256 for changed/added blobs. Do not hash every unchanged file every run by default.

### 20.4 Retention

Config `retention.max_backups` (default 14) and optional `retention.max_days`. Cleanup **only** complete backups older than policy, never the last remaining full baseline if incrementals still need it. If deleting a full would orphan deltas, delete the whole chain or skip (document: v1 deletes oldest **chains**, not middle incrementals). Implemented in `incremental.py` `apply_retention()`. Unsafe deletion protection: never `rm -rf` dest root; only known `osbackup-*` snapshot dirs matching manifest ids.

### 20.5 First run

No parent → force full; create `latest`. Missing `latest` but manifests exist → parent = newest complete, recreate `latest`.

### 20.6 Mapping from current functions

`run_backup` timestamp format `YYYY-MM-DD_HH-MM-SS` can remain as directory prefix for human sorting, with id suffix: `2026-09-14_16-00-00-ab12cd34`. `--link-dest` target becomes `destination/<parent_dir>` not a dangling `latest` on first run (`omit --link-dest` if no parent).

---

## 21. Configuration Design

### 21.1 Files

| Platform | User config path |
|---|---|
| Linux | `$XDG_CONFIG_HOME/operatingsystembackup/config.json` (default `~/.config/operatingsystembackup/config.json`) |
| macOS | `~/Library/Application Support/operatingsystembackup/config.json` |
| Windows | `%APPDATA%\operatingsystembackup\config.json` |

`osbackup config path` prints it. `osbackup config init` writes a template. `--config` overrides.

**Legacy:** if `~/backup/config.json` or `./config.json` exists, load and warn “legacy config; migrate with osbackup config init”. Preserve keys `sources`, `exclude`, `destination`, `log_file`.

**Committed example:** replace personal `config.json` with `config.example.json` (no `/home/novrus`, no `ghost`). Stop tracking machine-specific config (`.gitignore` `config.json` in repo root if users keep a local one).

**Secrets:** never `aws_secret_access_key` in this file. Cloud block: `{ "provider": "s3", "bucket": "...", "prefix": "...", "profile": "default", "endpoint_url": null }`.

### 21.2 Schema (v1)

```json
{
  "schema_version": 1,
  "default_platform": null,
  "default_family": "debian",
  "default_distro": "linuxmint",
  "default_destination_type": "internal",
  "destination": "/mnt/backup/operatingsystembackup",
  "sources": [],
  "exclude": [],
  "archive": { "zip_dir": null, "compression": "deflate" },
  "incremental": { "enabled": true, "checksum": "mtime-size", "retention_max_backups": 14 },
  "cloud": { "provider": "s3", "bucket": null, "prefix": "osbackup", "profile": null, "endpoint_url": null },
  "logging": { "file": null, "verbosity": "info" }
}
```

Empty `sources` → adapter defaults (Mint-like home+`/etc` on Debian).  
`load_config()` today becomes `config.load()` with JSON schema checks (hand-rolled, no extra `jsonschema` dep unless we want it — **hand-rolled** to stay stdlib).

---

## 22. Security and Privilege Model

| Topic | Plan |
|---|---|
| Filesystem | Resolve paths; refuse dest ⊆ source; no `shell=True`; `subprocess` arg lists (`process.py` wrapper around current `subprocess.run`) |
| Privilege | Never `sudo` the whole CLI. `/etc` and other unreadable files: skip + count. Optional later: a documented `sudo osbackup backup --only-system` but not default |
| Symlinks | rsync `-a` preserves symlinks (does not follow). CopyBackend uses `follow_symlinks=False`. Restore zip: reject `..` and absolute members (`zipfile` `ZipInfo.filename` checks) |
| Path traversal | ZIP restore and extract_pack must use `is_relative_to` after join |
| Recursive loops | dest-in-source; rsync `-x` one-file-system **on by default** for local (current `-x` in `-aAx` — keep) |
| Unsafe deletion | Retention only deletes snapshot dirs that match `osbackup` manifests. Never `--delete` on dest root. Interactive confirm unless `--yes` |
| Temp files | `tempfile`; 0700 dirs; delete in `finally` |
| Archive safety | ZIP64, partial+rename, no overwrite |
| Cloud credentials | env/profile only; redact `AKIA…`, `aws_secret`, `Bearer` in logs (`logging_setup.RedactingFilter`) |
| Sensitive files | Default home backup **includes** `~/.ssh` (users expect it). README warning. Optional exclude list in example config |
| Command execution | Only known binaries: `rsync`, `dpkg`, `apt-mark`, `rpm`, `dnf`, `pacman`, `brew`, `winget` — looked up with `shutil.which`, never user-supplied shell strings |
| Interrupted ops | partial dirs; manifest last |
| Destination validation | section 15 |

---

## 23. Logging and Error Handling

Evolve `setup_logging` in `operatingsystembackup/logging_setup.py`:

- Always a console handler (INFO default, `--verbose` DEBUG, `--quiet` WARNING).
- Optional file from config `logging.file` or adapter-appropriate log dir (`$XDG_STATE_HOME/operatingsystembackup/` on Linux). `mkdir` parents.
- Redact secrets.
- Do not log full AWS signing payloads.

**Exception hierarchy** (`errors.py`): `OSBackupError` plus `UnsupportedPlatformError`, `UnsupportedDistributionError`, `InaccessibleSourceError`, `UnwritableDestinationError`, `DisconnectedDestinationError`, `InsufficientSpaceError`, `OptionalDependencyError`, `PackageManagerUnavailableError`, `CloudAuthError`, `NetworkError`, `ArchiveError`, `PermissionError` (wrap), `PartialBackupError`, `IncompatibleManifestError`. CLI maps these to exit codes 2–20 and a one-paragraph stderr message. Unexpected exceptions: traceback only at DEBUG.

`run_backup`’s `sys.exit(1)` on any rsync failure is replaced by mapping rsync codes (e.g. 23 partial transfer → `PartialBackupError`, do not update `latest`).

---

## 24. Proposed Repository/File Structure

```text
LinuxMintBackup/                          # folder name unchanged in Phase 2
├── .cursor/operating-system-backup-plan.md
├── .github/workflows/ci.yml
├── .gitignore
├── LICENSE                               # MIT, matching README claim
├── README.md
├── pyproject.toml
├── config.example.json
├── backup.py                             # shim → cli.main
├── src/operatingsystembackup/
│   ├── __init__.py                       # __version__
│   ├── __main__.py
│   ├── cli.py
│   ├── interactive.py
│   ├── config.py
│   ├── models.py
│   ├── errors.py
│   ├── logging_setup.py
│   ├── detect.py
│   ├── fsutil.py
│   ├── process.py
│   ├── sources.py
│   ├── packages.py
│   ├── manifest.py
│   ├── incremental.py
│   ├── backup_engine.py
│   ├── rsync_backend.py
│   ├── copy_backend.py
│   ├── restore.py
│   ├── platforms/
│   │   ├── __init__.py                   # registries
│   │   ├── base.py
│   │   ├── debian.py
│   │   ├── redhat.py
│   │   ├── arch.py
│   │   ├── macos.py
│   │   └── windows.py
│   └── destinations/
│       ├── __init__.py
│       ├── base.py
│       ├── local.py
│       ├── zip_home.py
│       ├── cloud.py
│       └── s3.py
└── tests/
    ├── conftest.py
    ├── fixtures/os-release/*
    ├── test_cli.py
    ├── test_config.py
    ├── test_detect.py
    ├── test_platforms.py
    ├── test_debian.py
    ├── test_redhat.py
    ├── test_arch.py
    ├── test_macos.py
    ├── test_windows.py
    ├── test_sources.py
    ├── test_destinations.py
    ├── test_zip_home.py
    ├── test_incremental.py
    ├── test_manifest.py
    ├── test_rsync_backend.py
    ├── test_errors.py
    ├── test_restore.py
    └── test_backup_shim.py
```

`logs/` is **not** committed (gitignore). No `requirements.txt` if `pyproject.toml` is complete (optional extra `requirements-dev.txt` is unnecessary).

---

## 25. File-by-File Change Plan

### 25.1 Modify

#### `backup.py`

- **Current:** all application logic (`load_config`, `setup_logging`, `archive_builds`, `run_backup`, `main`).
- **Planned:** ~15-line shim: import `cli.main`, print deprecation to stderr, `sys.exit(main())`. Fixing typos **in place** is not the end state; moving logic is.
- **Depends on:** `operatingsystembackup.cli`.
- **Tests:** `tests/test_backup_shim.py`.

#### `README.md`

- **Current:** Mint-only marketing, inaccurate structure/features.
- **Planned:** full rewrite per section 27. Must match implemented behavior.
- **Tests:** none (human + that examples match `--help` output in `test_cli.py`).

#### `config.json`

- **Current:** personal Mint paths; unused by `load_config()` as written.
- **Planned:** stop committing user-specific config. Replace with `config.example.json` and gitignore root `config.json`. If Phase 2 keeps a tracked example, it must not contain `/home/novrus` or `/home/ghost`.
- **Depends on:** `.gitignore`, `config.py` legacy loader.
- **Tests:** `test_config.py` loads example + legacy four-key file.

### 25.2 Create — packaging / OSS

| Path | Purpose | Tests |
|---|---|---|
| `pyproject.toml` | name `operatingsystembackup`, version `0.1.0`, requires-python `>=3.10`, scripts `osbackup`/`operatingsystembackup`, optional `s3`/`dev` extras, hatchling or setuptools package-dir `src/` | CI install |
| `LICENSE` | MIT text (README already says MIT) | — |
| `.gitignore` | section 28 | — |
| `config.example.json` | documented template | `test_config.py` |
| `.github/workflows/ci.yml` | pytest matrix | CI |

### 25.3 Create — package modules

| Path | Responsibility | Interactions | Tests |
|---|---|---|---|
| `src/operatingsystembackup/__init__.py` | `__version__` | cli `--version` | test_cli |
| `__main__.py` | `cli.main()` | `python -m` | test_cli |
| `cli.py` | argparse; dispatch; exit codes | all | test_cli |
| `interactive.py` | menus from **registries** | detect, platforms, dest | test_cli (stdin mock) |
| `config.py` | evolve `load_config`; paths; migrate legacy keys | models | test_config |
| `models.py` | dataclasses: `DetectionResult`, `BackupRequest`, `PackageInventory`, `ValidationReport` | everywhere | unit |
| `errors.py` | hierarchy in §23 | cli | test_errors |
| `logging_setup.py` | evolve `setup_logging` | cli, engine | test_errors/logging |
| `detect.py` | os-release / platform | platforms | test_detect + fixtures |
| `fsutil.py` | writable, space, loop check, mounts | dest | test_destinations |
| `process.py` | wrap `subprocess.run` (from `run_backup`) | rsync, packages | mocks |
| `sources.py` | merge defaults/config/CLI | adapters, engine | test_sources |
| `packages.py` | inventory helpers | adapters | per-family tests |
| `manifest.py` | read/write schema v1 | engine, restore, history | test_manifest |
| `incremental.py` | parent selection, change detect, retention | manifest, dest | test_incremental |
| `backup_engine.py` | successor of `run_backup` orchestration | backends, dest, incremental | test_incremental |
| `rsync_backend.py` | successor of rsync `cmd` list in `run_backup`; probe flags; `--dry-run`; omit `--link-dest` when no parent; fix `sources` name | engine | test_rsync_backend |
| `copy_backend.py` | Windows/fallback | engine | test_incremental |
| `restore.py` | rsync/copy reverse; zip chain; S3 download | dest, manifest | test_restore |
| `platforms/base.py` | Protocol | adapters | — |
| `platforms/__init__.py` | `FAMILY_REGISTRY`, `DISTRO_REGISTRY`, `get_adapter()` | cli, detect | test_platforms |
| `platforms/debian.py` | `DebianAdapter` including Linux Mint | packages, sources | test_debian |
| `platforms/redhat.py` | `RedHatAdapter` | packages | test_redhat |
| `platforms/arch.py` | `ArchAdapter` | packages | test_arch |
| `platforms/macos.py` | `MacOSAdapter` | brew optional | test_macos |
| `platforms/windows.py` | `WindowsAdapter` | winget optional | test_windows |
| `destinations/base.py` | Protocol | engine | — |
| `destinations/__init__.py` | dest registry | cli | test_destinations |
| `destinations/local.py` | external+internal | rsync/copy | test_destinations |
| `destinations/zip_home.py` | ZIP in home | zipfile, incremental | test_zip_home |
| `destinations/cloud.py` | ABC | s3 | mocks |
| `destinations/s3.py` | boto3 optional | cloud | mocks (no AWS) |

### 25.4 Remove / stop using

| Path | Plan |
|---|---|
| `archive_builds` function | Do not port. ZIP destination supersedes |
| `tarfile` import | Drop unless an internal delta pack uses tar; ZIP is user-facing. Internal cloud packs may use `tarfile` stdlib — acceptable, not user-facing “builds_*.tar.gz” |
| README systemd claims | Remove unless a file exists |

### 25.5 Do not touch in Phase 2

- `.git/**`
- User extra untracked files if any appear later
- Remote GitHub settings
- This plan file may remain

---

## 26. Dependency Changes

**Runtime required:** none beyond Python 3.10+ stdlib (`argparse`, `zipfile`, `json`, `hashlib`, `dataclasses`, `pathlib`, `subprocess`, `logging`, `platform`, `tomllib` not needed if JSON).

**External binaries (optional per platform):** `rsync` (required for GNU-style local Linux backups; optional elsewhere), `dpkg`/`apt-mark`, `rpm`/`dnf`, `pacman`, `brew`, `winget`.

**Optional extra `s3`:** `boto3` with a modest lower bound (e.g. `>=1.34`). Not imported unless cloud destination is selected.

**Dev extra:** `pytest>=8`, `pytest-cov` optional.

**Lockfile:** for an application, committing `uv.lock` is nice but **not required** with zero default deps. Decision: **no lockfile in v1** (nothing to lock except extras). If `boto3` is added as extra, still no app lockfile; document `pip install -e '.[dev,s3]'`.

**Do not add:** `rich`, `typer`, `pydantic`, `jsonschema`, `cryptography`, Google/Dropbox SDKs.

**Python version tradeoff:** README says 3.8. Mint 21 ships 3.10; 3.10 enables `list[str]` builtins. Require **3.10+**. Document Mint 20 (3.8) as unsupported rather than complicating typing.

---

## 27. README.md Improvement Plan

Rewrite (Phase 2), reflecting **only shipped** behavior:

1. Title `OperatingSystemBackup` and one-paragraph purpose (cross-platform CLI backup; Linux families + macOS + Windows).
2. Overview and major features (CLI, interactive, incremental, destinations, package inventories as metadata).
3. Supported OS / Linux families / distro table from the **same registry list** (manual copy must match `DISTRO_REGISTRY`; prefer generating the table from code in a comment “keep in sync” or a tiny `--help` dump).
4. Installation: `pip install .` / `pip install -e .` from clone; `osbackup --help`. Prerequisites: Python 3.10+, optional rsync, optional boto3.
5. CLI usage: interactive and non-interactive examples (`osbackup backup --destination-type internal --destination /mnt/backup --yes`).
6. Destination sections: external, internal, ZIP home naming, cloud S3 extra.
7. Incremental: link-dest on POSIX disks; manifests; ZIP chains.
8. Configuration paths + legacy `~/backup/config.json` + example keys.
9. Platform detection + override flags.
10. Permissions: not running as root; `/etc` best-effort; Windows symlink note.
11. Security: dest loops, secrets in home, cloud env vars, do not commit backups.
12. Troubleshooting: each error class in plain language (rsync missing, OpenRsync flags, disconnected drive, boto3 missing).
13. Development: `pip install -e '.[dev]'`, `pytest`.
14. Testing / CI matrix summary.
15. Current limitations: no Drive/OneDrive/Dropbox; no systemd installer; no encryption; no full-disk image; Windows incremental without rsync is copy+hardlink; restore is file-level.
16. Project structure (new tree).
17. Roadmap: more cloud providers, AUR helpers, systemd unit example.
18. Author / MIT + link to `LICENSE`.

Remove false claims (production-ready, systemd present, dry-run until implemented — then document dry-run for real). Keep `python3 backup.py` as deprecated.

---

## 28. .gitignore Plan

Create root `.gitignore` (currently **missing** despite README):

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.venv/
venv/
.env
.env.*

# Tests / coverage
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/

# Tooling
.idea/
.vscode/
*.swp
.DS_Store
Thumbs.db

# Project outputs
logs/
*.log
*.zip
*.zip.partial
osbackup-archives/
partial-*/

# Local config / secrets
config.json
credentials.json
*.pem
id_rsa
id_ed25519

# Backup data that must never be committed
/backups/
```

Do **not** ignore `src/`, `tests/`, `pyproject.toml`, `config.example.json`, `LICENSE`, this plan.

No lockfile to worry about in v1.

`.env` ignored even though unused — belt and suspenders for cloud keys.

---

## 29. Testing Strategy

There are **zero** tests today. Add pytest under `tests/` with `tmp_path`, `monkeypatch`, and fixture `os-release` files.

| Area | Approach |
|---|---|
| Unit | adapters, manifest round-trip, change detection, dest loop checks, rsync argv builder (do not call real rsync in unit tests) |
| CLI | `argparse` via `cli.main(argv)` capturing stdout; `--help`; bad distro exit code |
| Config | legacy four-key file; XDG path with env monkeypatch; reject secrets keys |
| Detection | Darwin on this host as an integration micro-test; Linux via fixtures |
| Family adapters | mock `shutil.which` and `process.run` |
| Destinations | temp dirs; zip create/abort; refuse dest inside source |
| Incremental | two fake trees; expect added/changed/deleted; parent missing → full |
| Manifest | schema_version too new → error |
| Errors | each subclass message |
| Restore | zip chain apply delete; path traversal zip rejected |
| Shim | `backup.py` import path |

Mark tests that need GNU rsync with `@pytest.mark.skipif(not gnu_rsync)`. Do not require network. S3 tests use `moto` **only if** we add it to dev extras; otherwise mock `CloudProvider`. **Decision:** mock the protocol, **do not** add `moto` in v1 (extra dep).

---

## 30. Cross-Platform Test Matrix

| Target | What to prove | Where |
|---|---|---|
| Debian-family (Ubuntu runner) | detect ubuntu, DebianAdapter defaults, rsync argv, local dest | GitHub Actions `ubuntu-latest` |
| Linux Mint | same adapter as Ubuntu + `ID=linuxmint` fixture | **fixture only** on this Mac; optional later Mint VM — not this host |
| Red Hat family | Fedora `os-release` fixture + rpm mock; optional `fedora:latest` container job | CI container; **not** this Mac |
| Arch family | arch fixture + pacman mock; optional `archlinux` container | CI; **not** this Mac |
| macOS | detect Darwin, zip-home, config path, OpenRsync probe | This host + `macos-latest` CI |
| Windows | adapter mocks on Unix CI; real `windows-latest` for copy_backend smoke | CI; **not** this Mac |

**This macOS host cannot validate:** `apt`/`dpkg`/`dnf`/`rpm`/`pacman` real output, Linux ACL `-A`, `--numeric-ids` against GNU coreutils, Mint Cinnamon paths, NTFS junctions, `winget`, SELinux xattrs, `/mnt` USB udev, systemd.

**CI sketch** (`.github/workflows/ci.yml`): pytest on ubuntu/macOS/windows; second Linux job `container: fedora:40` running adapter smoke if cheap. Do not block merge on Fedora container if GH.org lacks it — keep Ubuntu+macOS+Windows as required.

---

## 31. Migration and Backward Compatibility

| Old | New |
|---|---|
| `python3 backup.py` | Works via shim (deprecation on stderr) |
| `~/backup/config.json` keys `sources`, `exclude`, `destination`, `log_file` | Still loaded; mapped into schema v1 |
| Repo `config.json` | Becomes example; personal paths removed |
| Snapshot dirs `YYYY-MM-DD_HH-MM-SS` | New snapshots add id suffix + `manifest.json`. Old dirs without manifest: `history` can treat them as `legacy-rsync` if they look like timestamps; `--link-dest` may still use `latest` |
| `latest` symlink | Unchanged on POSIX |
| Destination `/mnt/backup/linux-mint` | Still valid if user passes it; examples use new name |
| Incremental without manifests | First new run after upgrade is **full** if inventory missing, then incremental |

Do not migrate remote GitHub. Do not rewrite old snapshot file bytes.

Behavioral compatibility for Mint users: home + `/etc`, cache/Trash excludes, rsync hardlinked snapshots, log file, timestamped dirs.

---

## 32. Implementation Phases

Work stays on `dev/repo-improvements`. Do not commit/push unless the user later asks. Order is dependency-based (config/errors before CLI, platforms before engine, local dest before cloud).

### Phase A — Identity and skeleton

- **Objective:** installable empty package named OperatingSystemBackup with CLI `--help`/`--version`.
- **Files:** `pyproject.toml`, `src/operatingsystembackup/{__init__,__main__,cli,errors}.py`, `LICENSE`, `.gitignore` (minimal), shim `backup.py` stub can wait until engine exists — **keep `backup.py` working-or-broken as today until Phase G** to avoid a half-shim that cannot backup. Alternative: Phase A leaves `backup.py` untouched; add package beside it. **Choose: leave `backup.py` intact until Phase G** so Mint script behavior is not deleted early.
- **Tasks:** package layout; version `0.1.0`; scripts entry points returning “not implemented” only for new subcommands; `--help` lists commands.
- **Depends on:** nothing.
- **Tests:** `test_cli.py` help/version.
- **Done when:** `pip install -e .` and `osbackup --help` work.

### Phase B — Config, logging, errors, models

- **Objective:** replace implicit `load_config`/`setup_logging` with validated config + redacting logs + error types.
- **Files:** `config.py`, `logging_setup.py`, `models.py`, `errors.py`, `config.example.json`, `tests/test_config.py`.
- **Tasks:** XDG/macOS/Windows paths; legacy loader; schema_version.
- **Depends on:** A.
- **Done when:** legacy `sources/exclude/destination/log_file` JSON loads; missing file raises `OSBackupError` not `FileNotFoundError` at CLI boundary.

### Phase C — Detection and platform registry

- **Objective:** centralized family→distro→adapter map; `osbackup detect` and `osbackup platforms`.
- **Files:** `detect.py`, `platforms/*`, fixtures `tests/fixtures/os-release/*`, `test_detect.py`, `test_platforms.py`, family tests with mocked package tools.
- **Depends on:** B.
- **Done when:** Mint/Ubuntu/Debian/Fedora/Arch/Darwin/Windows fixtures resolve; unknown distro errors with a list; menus read the registry.

### Phase D — CLI interactive + non-interactive wiring (no copy yet)

- **Objective:** flags and interactive prompts produce a `BackupRequest`.
- **Files:** `cli.py`, `interactive.py`.
- **Depends on:** C.
- **Done when:** `osbackup backup --dry-run` validates request without copying (engine stub).

### Phase E — Destinations validation (local + zip)

- **Objective:** dest validate, loop detection, zip naming/partial.
- **Files:** `fsutil.py`, `destinations/{base,local,zip_home}.py`, tests.
- **Depends on:** B.
- **Done when:** dest inside source fails; zip dry-run names a file; free-space helper works on this Mac.

### Phase F — Package inventories

- **Objective:** optional metadata collectors.
- **Files:** `packages.py`, adapter methods.
- **Depends on:** C.
- **Done when:** missing tools warn; mocked tools write metadata strings.

### Phase G — Backup engine + incremental + rsync/copy (Linux Mint behavior lives here)

- **Objective:** real backups; fix `run_backup` bugs; preserve `--link-dest`; manifests; dry-run; then point `backup.py` at the engine.
- **Files:** `backup_engine.py`, `rsync_backend.py`, `copy_backend.py`, `manifest.py`, `incremental.py`, `sources.py`, `process.py`, rewrite `backup.py` shim.
- **Depends on:** D–F.
- **Tests:** argv builder; incremental fake trees; shim.
- **Done when:** on POSIX with GNU rsync, two runs hardlink unchanged files; first run omits `--link-dest`; `exisit_ok`/`source` bugs gone; `python3 backup.py` still starts a backup via legacy config.

### Phase H — Cloud S3 optional + restore

- **Objective:** S3 provider behind extra; `osbackup restore` for local and zip chains.
- **Files:** `destinations/cloud.py`, `s3.py`, `restore.py`, tests with mocks.
- **Depends on:** G.
- **Done when:** missing boto3 errors clearly; mocked upload writes manifest last; zip restore rejects `../evil`.

### Phase I — Tests completion and CI

- **Files:** remaining tests, `.github/workflows/ci.yml`.
- **Depends on:** G–H.
- **Done when:** `pytest` green on this Mac for non-Linux-tool tests; CI file present.

### Phase J — Documentation and cleanup

- **Files:** `README.md`, `.gitignore` complete, drop dead `archive_builds`, example config sanitized.
- **Depends on:** I (README last so it matches reality).
- **Done when:** README has no unimplemented features.

### Phase K — Validation

- **Objective:** section 35 checklist on this Mac + document what was not run.
- **Depends on:** J.
- **Done when:** checklist filled; remaining GitHub rename is documented only.

---

## 33. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Green-field rewrite never ships | Phase A–G extract `run_backup`; keep shim |
| OpenRsync vs GNU flags on macOS | Probe flags; fallback copy backend |
| `--delete` wiping data | Only inside snapshot; retention allowlist |
| Dest inside home | Resolve + `is_relative_to` |
| Cloud scope creep | S3 only in v1 |
| Running as root | Never default; `/etc` best-effort |
| Manifest too large | `files.jsonl`; incremental omits unchanged paths |
| Orphan incrementals after retention | Delete whole chains |
| Windows no symlinks | `latest.json` |
| Personal `config.json` committed | example + gitignore |
| Phase 2 accidentally renames GitHub | Section 36; no `gh repo rename` |
| Shell-blocked audit missed dirty files | Conversation-start status was clean; re-run `git status` at Phase 2 start **before** edits |
| Over-packaging 40 modules | Structure in §24 is the ceiling; do not add plugins |

---

## 34. Acceptance Criteria

Phase 2 is complete when all of the following are true (and README does not claim more):

- Branded **OperatingSystemBackup** in README, `--help`, package metadata, log identity.
- Useful Linux Mint behavior preserved: Debian-family defaults (home + `/etc`), cache/Trash excludes, rsync timestamped snapshots, `latest` on POSIX, legacy config keys, `python3 backup.py` shim.
- Architecture not Mint-only: registry includes Debian, Red Hat, Arch families, macOS, Windows.
- CLI: `osbackup --help` and `operatingsystembackup --help`; interactive and non-interactive backup.
- Distro lists come from the registry and are shown (`osbackup platforms`).
- Linux Mint is a Debian-family distro id `linuxmint`.
- Destinations: external, internal, home ZIP, cloud interface + **S3-compatible** implementation behind optional extra.
- Incremental: parent/full, backup ids, manifests, changed/deleted detection, no silent fake incrementals; ZIP/cloud strategies documented and implemented as in §20.
- Config: platform paths, exclusions, incremental, cloud profile **without secrets**, verbosity.
- Logging/errors: classes in §23; no secrets in logs.
- Tests: unit/CLI/config/detect/adapters/dest/zip/incremental/manifest/error paths exist and pass on supported runners.
- `.gitignore` exists and ignores backups/logs/secrets/local `config.json`.
- README matches **actual** behavior.
- Local rename done; **remote GitHub still `LinuxMintBackup` unless the user later renames it**.
- `backup.py` `NameError`/`TypeError` gone.
- No Drive/OneDrive/Dropbox required.
- No claim that this Mac tested apt/dnf/pacman/Windows for real.

---

## 35. Post-Implementation Validation

Run at the end of Phase 2 (and after any user-requested commit, not before):

1. Re-verify `git branch --show-current` is `dev/repo-improvements` and `git status` (live; was blocked in Phase 1).
2. `pip install -e '.[dev]'` then `osbackup --help`, `operatingsystembackup --help`, `osbackup detect` on this Mac.
3. `osbackup platforms` lists Debian (including linuxmint), Red Hat, Arch, macOS, Windows.
4. `pytest` on this Mac — all non-skipped tests pass.
5. ZIP dry-run and a tiny real zip of a temp source under `$HOME` (not the repo).
6. Config init + validate; confirm no secrets in example files; `git grep` for `/home/novrus` and `/home/ghost` is empty except maybe CHANGELOG notes.
7. Shim: `python3 backup.py --help` or equivalent still invokes CLI.
8. Rsync probe: record whether this Mac’s `rsync` is GNU or OpenRsync; run a tiny local incremental **only if** flags work; otherwise rely on copy-backend test.
9. Document skipped: real Mint, Fedora, Arch, Windows, S3 live bucket, USB external drive, `/etc` as root.
10. Confirm origin URL still `git@github.com:NovrusShehaj/LinuxMintBackup.git`.
11. Confirm no `LICENSE` mismatch with README.
12. Confirm `.gitignore` would exclude a dummy `foo.zip` and `config.json`.

---

## 36. Remote Repository Rename Considerations

**Local (Phase 2 may do):** metadata, docs, CLI, package name `operatingsystembackup`. Working directory may remain `.../Github/LinuxMintBackup`. Git remote name `origin` stays.

**Remote (Phase 2 must not do):**

- Current hosting: GitHub `NovrusShehaj/LinuxMintBackup` (`git@github.com:NovrusShehaj/LinuxMintBackup.git` in `.git/config`).
- `dev/repo-improvements` has **no** `origin` tracking branch in `.git/config` and no `refs/remotes/origin/dev/repo-improvements`. First push (only if the user later asks) would be `git push -u origin dev/repo-improvements`.
- Renaming the GitHub repository to `OperatingSystemBackup` requires a logged-in GitHub user with admin on that repo, e.g. GitHub Settings → Rename, or later user-run `gh repo rename OperatingSystemBackup`. That updates the GitHub URL; local clones need `git remote set-url origin git@github.com:NovrusShehaj/OperatingSystemBackup.git`.
- This Cursor session must **not** claim the remote was renamed after Phase 2. README should use the **current** Git URL until the user performs the hosting rename, or should say “repository may still be named LinuxMintBackup on GitHub.”
- Do not force-push, do not delete `LinuxMintBackup`, do not rewrite `e697fe62…`.
- GitHub Pages, clone URLs, and the README badge/GitHub link `https://github.com/NovrusShehaj` must be checked after a **manual** rename; out of scope until then.

---

## Appendix A — Current `run_backup` command (to be preserved in spirit)

From `backup.py`:

```text
rsync -aAx --delete --numeric-ids --link-dest <destination>/latest
  [--exclude <e>]…  <sources…>  <destination>/<YYYY-MM-DD_HH-MM-SS>
```

Planned GNU Linux argv (conceptual):

```text
rsync -aH --numeric-ids [-A] [-X] -x --partial --delay-updates
  [--delete]
  [--link-dest <destination>/<parent_dir>]   # omitted if no parent
  [--dry-run]
  [--exclude dest] [--exclude e]…
  <sources…>  <destination>/<stamp>-<backup_id>/
```

Then write `manifest.json` / `files.jsonl`, `os.replace` `latest` symlink.

---

## Appendix B — Phase 1 inspection inventory

**Read:** `backup.py`, `config.json`, `README.md`, `.git/HEAD`, `.git/config`, `.git/packed-refs`, `.git/logs/HEAD`, `.git/logs/refs/heads/master`, `.git/logs/refs/heads/dev/repo-improvements`, `.git/logs/refs/remotes/origin/HEAD`, `.git/refs/heads/*`, `.git/refs/remotes/origin/HEAD`, `.git/info/exclude`, `.git/description`, `.git/gk/config`, `.git/cursor/crepe/e697fe62…/metadata.json`.  
**Glob:** entire work tree (33 paths, mostly `.git`).  
**Not read:** `.env` (none), SSH keys, GitHub tokens, `auth.json` under Hermes.  
**Requirements source:** user Phase 1 prompt + Hermes orchestration paste (truncated at ZIP acceptance line; remaining criteria reconstructed from the same prompt’s earlier mandatory sections).  
**Not executed:** `git status`, `git log`, `git ls-files`, `gh`, dependency install, any backup.

---

## Appendix C — Explicit non-actions for Phase 2 start

Before editing sources, re-run live git status on `dev/repo-improvements`. If unexpected user files exist, preserve them. Do not implement from this plan until Phase 2 is explicitly authorized.
