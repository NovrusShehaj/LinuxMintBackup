from __future__ import annotations

from pathlib import Path

import pytest

from operatingsystembackup.rsync_backend import RsyncCapabilities, build_command, gnu_rsync_available, probe


def _gnu_caps() -> RsyncCapabilities:
    return RsyncCapabilities(
        available=True,
        binary="/usr/bin/rsync",
        variant="gnu",
        acls=True,
        xattrs=True,
        numeric_ids=True,
        link_dest=True,
        dry_run=True,
        one_file_system=True,
        hardlinks=True,
        partial=True,
        delay_updates=True,
        delete=True,
    )


def test_omits_link_dest_without_parent():
    cmd = build_command(Path("/tmp/src"), Path("/tmp/dest"), ["*.cache"], link_dest=None, caps=_gnu_caps())
    assert cmd[0] == "/usr/bin/rsync"
    assert "-a" in cmd
    assert "--link-dest" not in cmd
    assert "--exclude" in cmd
    assert "*.cache" in cmd
    joined = " ".join(cmd)
    assert "/tmp/dest" in joined


def test_includes_link_dest_with_parent(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    cmd = build_command(Path("/tmp/src"), Path("/tmp/dest"), [], link_dest=parent, caps=_gnu_caps())
    assert "--link-dest" in cmd
    assert str(parent.resolve()) in cmd


def test_dry_run_flag():
    cmd = build_command(Path("/tmp/src"), Path("/tmp/dest"), [], dry_run=True, caps=_gnu_caps())
    assert "--dry-run" in cmd


@pytest.mark.gnu_rsync
def test_probe_records_variant():
    caps = probe(force=True)
    assert caps.variant in {"gnu", "openrsync", "unknown", "none"}
    assert gnu_rsync_available() is (caps.available and caps.variant == "gnu")
