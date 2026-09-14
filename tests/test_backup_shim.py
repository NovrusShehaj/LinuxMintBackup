from __future__ import annotations

from pathlib import Path

import pytest


def test_shim_source_is_cli_wrapper():
    shim = Path(__file__).resolve().parents[1] / "backup.py"
    text = shim.read_text(encoding="utf-8")
    assert "deprecated" in text
    assert "operatingsystembackup.cli" in text
    assert "exisit_ok" not in text
    assert "cmd.extend(source)" not in text
    assert "archive_builds" not in text


def test_shim_invokes_cli(monkeypatch, capsys):
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["backup.py", "--version"])
    shim = Path(__file__).resolve().parents[1] / "backup.py"
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(shim), run_name="__main__")
    assert exc.value.code == 0
    mixed = capsys.readouterr()
    assert "deprecated" in mixed.err
    assert "OperatingSystemBackup 0.1.0" in mixed.out
