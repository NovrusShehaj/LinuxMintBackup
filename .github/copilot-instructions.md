# Copilot instructions for OperatingSystemBackup

## Project shape

This is a Python 3.10+ `src/`-layout package. The public application is the
`osbackup` CLI (with `operatingsystembackup` as an alias); `python3 -m
operatingsystembackup` uses the same entry point. `backup.py` is only a
deprecated compatibility shim and should not receive new application logic.

The main runtime flow is:

1. `cli.py` parses commands, loads runtime configuration, configures logging,
   and builds a `BackupRequest`.
2. `detect.py` detects the host, then `platforms/` resolves explicit
   `--platform`, `--family`, and `--distro` overrides before detection-derived
   values. Platform adapters provide default sources/excludes, package
   inventory, and rsync capability.
3. `backup_engine.run_backup()` merges adapter/config/CLI sources and excludes,
   validates the destination, walks the source inventory, computes a diff
   against the newest complete parent, and creates a full or incremental
   manifest.
4. Destination providers in `destinations/` implement the lifecycle
   `validate -> prepare_backup -> write -> commit/abort -> history`. Local
   destinations materialize snapshots (rsync with `--link-dest` when usable,
   otherwise the copy/hardlink backend); ZIP and cloud destinations write full
   or delta packs.
5. `restore.py` restores a local snapshot directly or replays the complete
   parent chain for ZIP/cloud backups. `manifest.py` and `incremental.py`
   define the schema, chain reconstruction, diffing, and retention behavior.

## Install, test, and CI commands

Install the package and development dependencies from the repository root:

```bash
python3 -m pip install -e ".[dev]"
```

Run the complete test suite:

```bash
python3 -m pytest
```

Run one test file or one test by node id:

```bash
python3 -m pytest tests/test_cli.py
python3 -m pytest tests/test_cli.py::test_backup_dry_run
```

The configured pytest options live in `pyproject.toml`: tests are discovered
under `tests/`, `src` is on `pythonpath`, and `-q` is enabled by default.
`tests/test_rsync_backend.py` contains the `gnu_rsync` marker for tests that
need a real GNU rsync binary. The GitHub Actions matrix runs the full suite on
Ubuntu, macOS, and Windows with Python 3.10 and 3.12. The Fedora container job
runs the adapter smoke subset:

```bash
python3 -m pytest tests/test_redhat.py tests/test_detect.py tests/test_platforms.py -q
```

There is no configured formatter, type checker, or standalone lint command in
the project metadata; do not invent one as a required validation step.

## Repository-specific conventions

- Add supported distributions through `platforms.FAMILY_REGISTRY` and its
  `FamilySpec` data, rather than duplicating distro names in CLI code or help
  text. Keep the registry and the README platform table aligned.
- Preserve override precedence: explicit request values win over detection,
  and config defaults are only fallback values when detection cannot resolve
  the host.
- Keep backup writes transactional. Write to `partial-*` or `*.partial`,
  publish with the destination provider's `commit()`, and call `abort()` on
  failure. History must ignore incomplete state and retention must never remove
  a destination root or a middle member of an incremental chain.
- Treat only complete manifests as parents. Incremental restore and retention
  operate on the full chain rooted at a full backup; use `--full` to recover
  from an incompatible or incomplete parent chain.
- Use the existing `InventoryItem`, `FileRecord`, `Manifest`, request/result
  dataclasses and destination protocol rather than introducing parallel
  representations. Keep manifest `schema_version` changes deliberate and
  update parsing/compatibility tests when the schema changes.
- Keep subprocess invocations as argv lists with `shell=False`. Do not add
  credentials to JSON configuration; config loading rejects secret-like keys,
  and cloud credentials come from AWS environment/shared credential mechanisms.
- Protect filesystem boundaries: refuse destinations inside sources, use the
  existing archive path validation for ZIP extraction, and retain the
  destination safety checks in `LocalDriveDestination`.
- Optional package-manager inventories are metadata only. Missing
  `dpkg`/`rpm`/`pacman`/`brew`/`winget` tools should remain warnings and must
  not prevent the file backup from completing.
- Tests intentionally mock host package tools and platform detection. Use
  `tmp_path`, `monkeypatch`, and the existing fixtures in `tests/conftest.py`;
  do not make the normal test suite depend on the developer's OS, installed
  package manager, network, or cloud credentials. Use the `force_copy` fixture
  for tests that should not depend on rsync.
- Keep user-facing behavior documented in `README.md`, especially supported
  platforms, destination formats, configuration paths, CLI flags, and
  security/restore constraints. Update the README when behavior or a
  user-visible command changes.
