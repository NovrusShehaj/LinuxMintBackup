from __future__ import annotations

import pytest

from operatingsystembackup.errors import UnsupportedDistributionError, UnsupportedPlatformError
from operatingsystembackup.platforms import DISTRO_REGISTRY, FAMILY_REGISTRY, get_adapter, list_distros, list_families


def test_registries():
    assert "debian" in FAMILY_REGISTRY
    assert DISTRO_REGISTRY["linuxmint"] == "debian"
    assert "linuxmint" in list_distros("debian")
    assert list_families() == ["debian", "redhat", "arch", "macos", "windows"]


def test_manual_override_wins():
    adapter, _warning = get_adapter(distro_id="fedora", platform="linux")
    assert adapter.family_id == "redhat"
    assert adapter.distro_id == "fedora"


def test_unknown_family():
    with pytest.raises(UnsupportedPlatformError):
        list_distros("solaris")


def test_unknown_distro():
    with pytest.raises(UnsupportedDistributionError) as exc:
        get_adapter(distro_id="plan9")
    assert "linuxmint" in str(exc.value)
