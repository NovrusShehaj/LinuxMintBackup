from __future__ import annotations

from pathlib import Path

import pytest

from operatingsystembackup.errors import InaccessibleSourceError
from operatingsystembackup.sources import discover_sources, is_excluded, merge_excludes, merge_source_lists


def test_merge_cli_overrides_config():
    merged = merge_source_lists([Path("/etc")], ["/home/a"], [Path("/tmp/src")])
    assert merged == [Path("/tmp/src")]


def test_merge_excludes_unique():
    merged = merge_excludes(["a"], ["a", "b"], ["c"])
    assert merged == ["a", "b", "c"]


def test_missing_sources(tmp_path):
    with pytest.raises(InaccessibleSourceError):
        discover_sources([tmp_path / "nope"])


def test_dest_excluded(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    nested = dest / "file"
    nested.write_text("x", encoding="utf-8")
    assert is_excluded(nested, [], dest=dest)
