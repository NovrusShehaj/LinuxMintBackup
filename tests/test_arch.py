from __future__ import annotations

from pathlib import Path

from operatingsystembackup.platforms.arch import ArchAdapter


def test_arch_defaults():
    adapter = ArchAdapter(distro_id="arch")
    assert Path.home() in adapter.default_sources()
    assert Path("/etc") in adapter.default_sources()


def test_pacman_missing(monkeypatch):
    monkeypatch.setattr("operatingsystembackup.packages.which", lambda _name: None)
    inventory = ArchAdapter().collect_package_inventory()
    assert inventory.warnings
    assert "metadata/pacman-explicit.txt" not in inventory.files
