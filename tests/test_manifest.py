from __future__ import annotations

from pathlib import Path

import pytest

from operatingsystembackup.errors import IncompatibleManifestError
from operatingsystembackup.manifest import dump_manifest, load_manifest, parse_manifest_data
from operatingsystembackup.models import FileRecord, Manifest


def _manifest(**kwargs) -> Manifest:
    data = dict(
        schema_version=1,
        app="OperatingSystemBackup",
        backup_id="ab12cd34",
        parent_id=None,
        kind="full",
        timestamp="2026-09-14T16:00:00+00:00",
        platform={"os": "linux", "family": "debian", "distro": "linuxmint"},
        hostname="mint-box",
        sources=["/home/user"],
        excludes=[],
        destination_kind="internal",
        counts={"added": 1, "changed": 0, "deleted": 0, "unchanged": 0},
        state="complete",
        files=[FileRecord("home/user/.bashrc", 123, 1, 420, sha256="abc", status="added")],
    )
    data.update(kwargs)
    return Manifest(**data)


def test_round_trip(tmp_path):
    man = _manifest()
    dump_manifest(man, tmp_path)
    loaded = load_manifest(tmp_path / "manifest.json")
    assert loaded.backup_id == "ab12cd34"
    assert loaded.files[0].path.endswith(".bashrc")
    assert (tmp_path / "files.jsonl").is_file()


def test_schema_too_new():
    with pytest.raises(IncompatibleManifestError):
        parse_manifest_data({"schema_version": 99, "app": "OperatingSystemBackup", "backup_id": "x"})
