from __future__ import annotations

from pathlib import Path

import pytest

from operatingsystembackup.cli import main
from operatingsystembackup.platforms import DISTRO_REGISTRY, list_platforms_text


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "OperatingSystemBackup" in out
    for command in ("detect", "platforms", "backup", "interactive", "config", "dest", "history", "restore"):
        assert command in out


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "OperatingSystemBackup 0.1.0" in capsys.readouterr().out


def test_platforms_includes_linuxmint(capsys):
    assert main(["platforms"]) == 0
    out = capsys.readouterr().out
    assert "linuxmint" in out
    assert "debian" in out
    assert "fedora" in out
    assert "arch" in out
    assert "macos" in out
    assert "windows" in out
    assert "linuxmint" in DISTRO_REGISTRY
    assert DISTRO_REGISTRY["linuxmint"] == "debian"
    assert "linuxmint" in list_platforms_text()


def test_detect_on_this_host(capsys):
    code = main(["detect"])
    out = capsys.readouterr().out
    assert "OperatingSystemBackup detection:" in out
    assert "os:" in out
    assert code in {0, 3}


def test_bad_distro_exit_code(capsys):
    code = main(
        [
            "backup",
            "--distro",
            "not-a-real-distro",
            "--destination-type",
            "internal",
            "--destination",
            "/tmp/osbackup-nope",
            "--source",
            "/tmp/osbackup-nope-src",
            "--dry-run",
            "--yes",
        ]
    )
    err = capsys.readouterr().err
    assert code == 4
    assert "unsupported distribution" in err


def test_backup_dry_run(tmp_path, capsys, force_copy):
    src = tmp_path / "src"
    src.mkdir()
    (src / "file.txt").write_text("hello", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    code = main(
        [
            "backup",
            "--destination-type",
            "internal",
            "--destination",
            str(dest),
            "--source",
            str(src),
            "--dry-run",
            "--yes",
            "--platform",
            "macos",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert not (dest / "osbackup").exists()


def test_config_validate_example(capsys):
    root = Path(__file__).resolve().parents[1]
    code = main(["--config", str(root / "config.example.json"), "config", "validate"])
    assert code == 0
    assert "ok:" in capsys.readouterr().out


def test_dest_validate_ok(tmp_path, capsys):
    dest = tmp_path / "backup"
    dest.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    code = main(["dest", "validate", str(dest), "--source", str(src)])
    assert code == 0
    assert "ok" in capsys.readouterr().out


def test_interactive_stdin(tmp_path, monkeypatch, capsys, force_copy):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a").write_text("x", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    answers = iter(
        [
            "n",  # override os
            "2",  # internal (1 external 2 internal)
            str(dest),
            "",  # extra source
            "",  # extra exclude
            "2",  # full
            "y",  # proceed
        ]
    )
    monkeypatch.setattr("operatingsystembackup.interactive.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    from operatingsystembackup.backup_engine import run_backup
    from operatingsystembackup.interactive import prompt_backup_request

    request = prompt_backup_request(
        {
            "default_destination_type": "internal",
            "sources": [str(src)],
            "exclude": [],
        }
    )
    request.sources = [src]
    request.dry_run = True
    result = run_backup(request, {"sources": [str(src)]}, adapter=None)
    assert result.dry_run
