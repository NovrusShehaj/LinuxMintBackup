from __future__ import annotations

from pathlib import Path

from operatingsystembackup.platforms.windows import WindowsAdapter


def test_windows_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    adapter = WindowsAdapter()
    assert adapter.default_sources() == [tmp_path]
    notes = adapter.privilege_notes()
    assert "USERPROFILE" in notes or "Windows" in notes


def test_winget_missing(monkeypatch):
    monkeypatch.setattr("operatingsystembackup.packages.which", lambda _name: None)
    inventory = WindowsAdapter().collect_package_inventory()
    assert inventory.warnings
