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


def _change(paths, rel, old, new):
    from emcomm.apply import FileChange
    return FileChange("t", paths.home / rel, old, new)


def test_backup_dir_never_reused(paths):
    from datetime import UTC, datetime

    from emcomm.apply import apply_changes
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    f = paths.home / "a.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("one")
    apply_changes(paths, [_change(paths, "a.txt", "one", "two")], now)
    apply_changes(paths, [_change(paths, "a.txt", "two", "three")], now)
    contents = sorted(p.read_text() for p in (paths.state / "backups").glob("*/a.txt"))
    assert contents == ["one", "two"]


def test_symlink_target_updated_link_kept(paths, ready):
    real = paths.home / "dotfiles/WSJT-X.ini"
    real.parent.mkdir(parents=True)
    real.write_text("[Configuration]\nMyCall=N0CALL\n")
    link = paths.home / ".config/WSJT-X.ini"
    link.symlink_to(real)
    assert main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths) == 0
    assert link.is_symlink()
    assert "MyCall=K7ABC" in real.read_text()
    backup = next((paths.state / "backups").glob("*/.config/WSJT-X.ini"))
    assert "N0CALL" in backup.read_text()


def test_dangling_symlink_errors(paths, ready, capsys):
    link = paths.home / ".config/WSJT-X.ini"
    link.symlink_to(paths.home / "missing.ini")
    assert main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths) == 1
    assert "broken symlink" in capsys.readouterr().err
    assert not (paths.home / ".config/pat/config.json").exists()
    assert not paths.active_file.exists()


def test_partial_failure_reports(paths, monkeypatch):
    import os
    from datetime import UTC, datetime

    from emcomm.apply import apply_changes
    from emcomm.validation import ProfileError
    a, b = paths.home / "a.txt", paths.home / "b.txt"
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text("a0")
    b.write_text("b0")
    real = os.replace
    n = []

    def flaky(src, dst):
        n.append(1)
        if len(n) == 2:
            raise OSError("disk full")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", flaky)
    changes = [_change(paths, "a.txt", "a0", "a1"), _change(paths, "b.txt", "b0", "b1")]
    with pytest.raises(ProfileError) as ei:
        apply_changes(paths, changes, datetime(2026, 1, 1, tzinfo=UTC))
    msg = str(ei.value)
    backup_root = paths.state / "backups"
    assert str(next(backup_root.iterdir())) in msg and "a.txt" in msg
    assert not list(paths.home.glob("*.emcomm-tmp"))
    assert a.read_text() == "a1" and b.read_text() == "b0"
    assert next(backup_root.glob("*/a.txt")).read_text() == "a0"


def test_restart_services():
    from emcomm.apply import SERVICES, restart_services
    seen = []

    class R:
        def __init__(self, rc):
            self.returncode = rc

    def ok(argv, **kw):
        seen.append(argv)
        return R(0)
    assert restart_services(ok) is True
    assert seen[0] == ["systemctl", "--user", "try-restart", *SERVICES]
    assert restart_services(lambda argv, **kw: R(1)) is False

    def missing(argv, **kw):
        raise FileNotFoundError
    assert restart_services(missing) is False


def test_eof_and_empty_input_abort(paths, ready, monkeypatch):
    def eof(_p):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert main(["use", "K7ABC", "--station", "bench"], paths=paths) == 1
    monkeypatch.setattr("builtins.input", lambda _p: "")
    assert main(["use", "K7ABC", "--station", "bench"], paths=paths) == 1
    assert not (paths.home / ".config/WSJT-X.ini").exists()
