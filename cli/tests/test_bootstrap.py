import json
import re
import subprocess
from pathlib import Path

from emcomm.cli import main
from emcomm.commands import bootstrap as bs
from emcomm.commands import uninstall as un

REPO = Path(__file__).resolve().parents[2]


def test_vars_and_overrides():
    overrides = bs.parse_overrides(["emcomm_chrony_enable=false", "note=hello"])
    assert overrides == {"emcomm_chrony_enable": False, "note": "hello"}
    assert bs.bootstrap_vars("https://r/", "testing", "core,digital", ["alice"], overrides) == {
        "emcomm_repo_url": "https://r", "emcomm_channel": "testing",
        "emcomm_toolsets": ["core", "digital"], "emcomm_users": ["alice"],
        "emcomm_chrony_enable": False, "note": "hello"}


def test_playbook_command(paths, tmp_path):
    cmd = bs.playbook_command(paths, tmp_path / "v.json", check=True)
    assert cmd[:4] == ["ansible-playbook", "-i", "localhost,", "-c"]
    assert cmd[5].endswith("ansible_collections/emcomm/station/playbooks/station.yml")
    assert f"@{tmp_path / 'v.json'}" in cmd
    assert cmd[-1] == "--check"


def test_bootstrap_runs_ansible(paths, monkeypatch, capsys):
    seen = {}

    def fake_run(cmd, env, check):
        seen["env"] = env
        seen["vars"] = json.loads(Path(cmd[cmd.index("-e") + 1][1:]).read_text())
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(bs.subprocess, "run", fake_run)
    monkeypatch.setattr(bs.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "alice")
    assert main(["bootstrap", "--repo-url", "https://r", "--toolsets", "core", "--yes"],
                paths=paths) == 0
    assert seen["vars"]["emcomm_users"] == ["alice"]
    assert seen["env"]["ANSIBLE_COLLECTIONS_PATH"] == str(paths.ansible_dir)
    assert "emcomm-core" in capsys.readouterr().out


def test_bootstrap_declined(paths, monkeypatch):
    monkeypatch.setattr(bs.os, "geteuid", lambda: 0)
    monkeypatch.setattr("builtins.input", lambda _p: "n")
    assert main(["bootstrap", "--repo-url", "https://r"], paths=paths) == 1


def test_bootstrap_eof_at_prompt_is_no(paths, monkeypatch, capsys):
    monkeypatch.setattr(bs.os, "geteuid", lambda: 0)

    def eof(_p):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert main(["bootstrap", "--repo-url", "https://r"], paths=paths) == 1
    assert "aborted; nothing was changed" in capsys.readouterr().out


def test_bootstrap_needs_root(paths, monkeypatch, capsys):
    monkeypatch.setattr(bs.os, "geteuid", lambda: 1000)
    assert main(["bootstrap", "--repo-url", "https://r", "--yes"], paths=paths) == 1
    assert "sudo" in capsys.readouterr().err


def test_uninstall_runs_packaged_script(paths, monkeypatch, tmp_path):
    script = paths.share / "bootstrap.sh"
    calls = []
    monkeypatch.setattr(un.os, "geteuid", lambda: 0)
    monkeypatch.setattr(un.subprocess, "run",
                        lambda cmd, check: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    assert script.is_file()  # the repo root doubles as share in tests
    assert main(["uninstall", "--yes"], paths=paths) == 0
    assert calls[0][0] == "sh" and calls[0][1].endswith("bootstrap.sh")
    assert calls[0][2:] == ["--uninstall", "--yes"]
    assert calls[0][1] != str(script)  # runs a temp copy; the package removes the original


def test_bootstrap_sh_pins_project_fingerprint():
    fpr = (REPO / "keys/fingerprint.txt").read_text().strip()
    script = (REPO / "bootstrap.sh").read_text()
    assert re.search(rf'^EMCOMM_KEY_FINGERPRINT="{fpr}"$', script, re.MULTILINE)


def test_bootstrap_vars_reject_insecure_url_and_bad_channel():
    import pytest

    from emcomm.validation import ProfileError
    with pytest.raises(ProfileError, match="non-HTTPS"):
        bs.bootstrap_vars("http://r", "testing", "core", [], {})
    with pytest.raises(ProfileError, match="channel"):
        bs.bootstrap_vars("https://r", "te/st", "core", [], {})


def test_overrides_cannot_bypass_validation():
    import pytest

    from emcomm.validation import ProfileError
    with pytest.raises(ProfileError):
        bs.bootstrap_vars("https://r", "testing", "core", [], {"emcomm_repo_url": "http://evil"})
    with pytest.raises(ProfileError):
        bs.bootstrap_vars("https://r", "testing", "core", [], {"emcomm_channel": ".."})
    with pytest.raises(ProfileError):
        bs.bootstrap_vars("https://r\nx", "testing", "core", [], {})
