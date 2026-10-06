import stat
import tomllib

import pytest

from emcomm.cli import main
from emcomm.commands import use as use_cmd


@pytest.fixture
def ready(paths, monkeypatch):
    calls = []
    monkeypatch.setattr(use_cmd, "restart_services", lambda: calls.append("restart") or True)
    assert main(["operator", "add", "K7ABC", "--grid", "DN16bk"], paths=paths) == 0
    assert main(["station", "add", "bench", "--radio", "generic-vox", "--no-udev"],
                paths=paths) == 0
    return calls


def test_use_writes_configs_and_active(paths, ready, capsys):
    capsys.readouterr()
    assert main(["use", "k7abc", "--station", "bench", "--yes"], paths=paths) == 0
    ini = (paths.home / ".config/WSJT-X.ini").read_text()
    assert "MyCall=K7ABC" in ini and "CATNetworkPort=127.0.0.1:4532" in ini
    assert (paths.home / ".config/pat/config.json").is_file()
    assert (paths.home / ".fldigi/fldigi_def.xml").is_file()
    env = paths.home / ".config/emcomm/rigctld.env"
    assert 'RIGCTLD_ARGS="-m 1' in env.read_text()
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert not (paths.home / ".config/emcomm/direwolf.conf").exists()  # no sound card
    active = tomllib.loads(paths.active_file.read_text())
    assert active == {"operator": "K7ABC", "station": "bench"}
    assert ready == ["restart"]
    assert "+MyCall=K7ABC" in capsys.readouterr().out


def test_use_backs_up_and_preserves(paths, ready):
    ini = paths.home / ".config/WSJT-X.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text("[Configuration]\nMyCall=N0CALL\nFont=Mono\n")
    ini.chmod(0o640)
    assert main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths) == 0
    assert "Font=Mono" in ini.read_text()
    assert stat.S_IMODE(ini.stat().st_mode) == 0o640
    backups = list((paths.state / "backups").glob("*/.config/WSJT-X.ini"))
    assert len(backups) == 1 and "N0CALL" in backups[0].read_text()
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o640


def test_use_preserves_crlf(paths, ready):
    ini = paths.home / ".config/WSJT-X.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(b"[Configuration]\r\nMyCall=N0CALL\r\nFont=Mono\r\n")
    assert main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths) == 0
    data = ini.read_bytes()
    assert b"MyCall=K7ABC" in data and b"Font=Mono" in data
    assert data.count(b"\r\n") == data.count(b"\n")
    backup = next((paths.state / "backups").glob("*/.config/WSJT-X.ini"))
    assert b"N0CALL\r\n" in backup.read_bytes()


def test_dry_run_changes_nothing(paths, ready, capsys):
    assert main(["use", "K7ABC", "--station", "bench", "--dry-run"], paths=paths) == 0
    assert not (paths.home / ".config/WSJT-X.ini").exists()
    assert not paths.active_file.exists()
    assert "+MyCall=K7ABC" in capsys.readouterr().out


def test_second_run_is_noop(paths, ready, capsys):
    main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths)
    capsys.readouterr()
    assert main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths) == 0
    assert "already up to date" in capsys.readouterr().out


def test_declined_confirmation(paths, ready, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert main(["use", "K7ABC", "--station", "bench"], paths=paths) == 1
    assert not (paths.home / ".config/WSJT-X.ini").exists()


def test_status(paths, ready, capsys):
    assert main(["status"], paths=paths) == 0
    assert "no active operator" in capsys.readouterr().out
    main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths)
    capsys.readouterr()
    assert main(["status"], paths=paths) == 0
    out = capsys.readouterr().out
    assert "operator: K7ABC" in out and "station: bench (Generic VOX (audio only))" in out
