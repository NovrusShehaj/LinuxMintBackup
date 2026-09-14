"""Shared fixtures for OperatingSystemBackup tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from operatingsystembackup.rsync_backend import RsyncCapabilities

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "os-release"


@pytest.fixture
def os_release_dir() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def no_package_tools(monkeypatch):
    monkeypatch.setattr("operatingsystembackup.packages.which", lambda _name: None)
    monkeypatch.setattr("operatingsystembackup.platforms.macos.which", lambda _name: None)
    monkeypatch.setattr("operatingsystembackup.platforms.windows.which", lambda _name: None)


@pytest.fixture
def force_copy(monkeypatch):
    monkeypatch.setattr(
        "operatingsystembackup.backup_engine._use_rsync",
        lambda adapter: False,
    )
    monkeypatch.setattr(
        "operatingsystembackup.rsync_backend.probe",
        lambda force=False: RsyncCapabilities(available=False),
    )
