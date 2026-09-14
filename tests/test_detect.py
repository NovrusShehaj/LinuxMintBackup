from __future__ import annotations

from operatingsystembackup.detect import detect, parse_os_release
from operatingsystembackup.platforms import get_adapter


def test_parse_os_release_quotes():
    data = parse_os_release('ID="linuxmint"\nID_LIKE="ubuntu debian"\n')
    assert data["ID"] == "linuxmint"
    assert data["ID_LIKE"] == "ubuntu debian"


def test_linux_fixtures(os_release_dir):
    cases = {
        "linuxmint": ("linuxmint", "debian"),
        "ubuntu": ("ubuntu", "debian"),
        "debian": ("debian", "debian"),
        "fedora": ("fedora", "redhat"),
        "rocky": ("rocky", "redhat"),
        "arch": ("arch", "arch"),
        "manjaro": ("manjaro", "arch"),
    }
    for name, (distro, family) in cases.items():
        result = detect(system="Linux", os_release_path=os_release_dir / name)
        assert result.ok
        assert result.distro_id == distro
        adapter, warning = get_adapter(detection=result)
        assert adapter.family_id == family
        assert adapter.distro_id == distro


def test_unknown_with_id_like(os_release_dir):
    result = detect(system="Linux", os_release_path=os_release_dir / "unknown-like")
    assert result.ok
    adapter, warning = get_adapter(detection=result)
    assert adapter.family_id == "debian"
    assert warning and "ID_LIKE" in warning


def test_unknown_without_like(os_release_dir):
    from operatingsystembackup.errors import UnsupportedDistributionError

    result = detect(system="Linux", os_release_path=os_release_dir / "unknown")
    assert result.ok
    try:
        get_adapter(detection=result)
        raise AssertionError("expected UnsupportedDistributionError")
    except UnsupportedDistributionError as exc:
        assert "plan9" in str(exc)
        assert "linuxmint" in str(exc)


def test_darwin_detect():
    result = detect(system="Darwin")
    assert result.ok
    assert result.os_name == "macos"
    assert result.distro_id == "macos"


def test_windows_detect():
    result = detect(system="Windows")
    assert result.ok
    assert result.os_name == "windows"
