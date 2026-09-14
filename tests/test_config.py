from __future__ import annotations

import json
from pathlib import Path

import pytest

from operatingsystembackup.config import (
    ConfigError,
    dump_template,
    load,
    loads,
    user_config_path,
)
from operatingsystembackup.errors import ConfigError as CfgErr


def test_example_config_loads():
    root = Path(__file__).resolve().parents[1]
    data = load(root / "config.example.json")
    assert data["schema_version"] == 1
    assert data["default_distro"] == "linuxmint"
    assert "/home/novrus" not in json.dumps(data)
    assert "/home/ghost" not in json.dumps(data)
    assert "aws_secret" not in json.dumps(data).lower()


def test_legacy_four_key_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "sources": ["/tmp/data"],
                "exclude": ["/tmp/data/.cache"],
                "destination": "/mnt/backup/operatingsystembackup",
                "log_file": "/tmp/osbackup.log",
            }
        ),
        encoding="utf-8",
    )
    data = load(path)
    assert data["sources"] == ["/tmp/data"]
    assert data["exclude"] == ["/tmp/data/.cache"]
    assert data["destination"] == "/mnt/backup/operatingsystembackup"
    assert data["logging"]["file"] == "/tmp/osbackup.log"
    assert data["_legacy"] is True


def test_xdg_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = user_config_path(system="Linux")
    assert path == tmp_path / "operatingsystembackup" / "config.json"


def test_macos_path():
    path = user_config_path(system="Darwin")
    assert "Application Support" in str(path)
    assert path.name == "config.json"


def test_reject_secrets():
    with pytest.raises((ConfigError, CfgErr)):
        loads(json.dumps({"aws_secret_access_key": "wJalc"}), origin="mem")


def test_dump_template_sanitized():
    text = dump_template()
    assert "/home/novrus" not in text
    assert "/home/ghost" not in text
    assert "linux-mint" not in text
    assert "operatingsystembackup" in text
