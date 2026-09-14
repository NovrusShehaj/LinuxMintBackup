from __future__ import annotations

from operatingsystembackup.platforms.redhat import RedHatAdapter


def test_redhat_defaults():
    adapter = RedHatAdapter(distro_id="fedora")
    assert Path_home_in_sources(adapter)
    assert adapter.family_id == "redhat"


def Path_home_in_sources(adapter) -> bool:
    from pathlib import Path

    return Path.home() in adapter.default_sources() and Path("/etc") in adapter.default_sources()


def test_rpm_missing(monkeypatch):
    monkeypatch.setattr("operatingsystembackup.packages.which", lambda _name: None)
    inventory = RedHatAdapter().collect_package_inventory()
    assert "metadata/rpm-qa.txt" not in inventory.files
    assert inventory.warnings
