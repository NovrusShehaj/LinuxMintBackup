from __future__ import annotations

from pathlib import Path

from operatingsystembackup.platforms.debian import DebianAdapter


def test_mint_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr("operatingsystembackup.platforms.debian.Path.home", lambda: tmp_path)
    adapter = DebianAdapter(distro_id="linuxmint", display_name="Linux Mint")
    sources = adapter.default_sources()
    assert sources[0] == tmp_path
    assert Path("/etc") in sources
    excludes = adapter.default_excludes()
    assert any(".cache" in item for item in excludes)
    assert any("Trash" in item for item in excludes)
    assert adapter.rsync_supported()
    assert adapter.family_id == "debian"
    assert adapter.distro_id == "linuxmint"


def test_dpkg_missing(monkeypatch):
    monkeypatch.setattr("operatingsystembackup.packages.which", lambda _name: None)
    inventory = DebianAdapter().collect_package_inventory()
    assert "metadata/dpkg-selections.txt" not in inventory.files
    assert inventory.warnings


def test_dpkg_present(monkeypatch):
    monkeypatch.setattr("operatingsystembackup.packages.which", lambda name: "/usr/bin/" + name)

    class Result:
        returncode = 0
        stdout = "bash\tinstall\n"
        stderr = ""

    monkeypatch.setattr("operatingsystembackup.packages.run", lambda argv, timeout=120: Result())
    inventory = DebianAdapter().collect_package_inventory()
    assert "metadata/dpkg-selections.txt" in inventory.files
