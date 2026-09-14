from __future__ import annotations

from pathlib import Path

from operatingsystembackup.platforms.macos import MacOSAdapter


def test_macos_defaults():
    adapter = MacOSAdapter()
    assert adapter.default_sources() == [Path.home()]
    assert Path("/etc") not in adapter.default_sources()
    assert any("Caches" in item or ".Trash" in item for item in adapter.default_excludes())


def test_brew_missing(monkeypatch):
    monkeypatch.setattr("operatingsystembackup.packages.which", lambda _name: None)
    monkeypatch.setattr("operatingsystembackup.platforms.macos.which", lambda _name: None)
    inventory = MacOSAdapter().collect_package_inventory()
    assert inventory.warnings
    assert "metadata/Brewfile" not in inventory.files
