import tomllib

from emcomm.apply import plan_changes
from emcomm.cli import main
from emcomm.models import Operator, RadioDef, Station
from emcomm.render.context import RenderContext
from emcomm.render.pipewire import render_pipewire
from emcomm.render.qtini import wsjtx_values

MK2 = RadioDef(id="icom-ic7300mk2", vendor="Icom", model="IC-7300MK2", hamlib_model=3094,
               baud=115200, ptt="cat")
LAN = Station(name="mk2", radio="icom-ic7300mk2", control="wfview", virtual_audio=True)
CTX = RenderContext(Operator("K7ABC", grid="DN16bk"), LAN, MK2)


def test_pipewire_dropin():
    text = render_pipewire(None, CTX)
    assert 'node.name        = "emcomm-mk2-rx"' in text
    assert 'node.name        = "emcomm-mk2-tx"' in text
    assert text.count("support.null-audio-sink") == 2
    usb = RenderContext(CTX.operator, Station(name="b", radio="x"), MK2)
    assert render_pipewire(None, usb) is None


def test_qt_apps_use_virtual_devices():
    v = wsjtx_values(CTX)
    assert v["SoundInName"] == '"emcomm-mk2-rx.monitor"'
    assert v["SoundOutName"] == '"emcomm-mk2-tx"'


def test_plan_writes_per_kit_dropin(paths):
    paths_changes = {c.app: c.path for c in plan_changes(paths, CTX)}
    assert paths_changes["pipewire"] == paths.home / ".config/pipewire/pipewire.conf.d/60-emcomm-mk2.conf"
    assert "direwolf" not in paths_changes  # no ALSA card for LAN kits in M1


def test_add_lan_station(paths, capsys):
    assert main(["station", "add", "mk2", "--radio", "icom-ic7300mk2", "--control", "wfview",
                 "--virtual-audio", "--no-udev"], paths=paths) == 0
    data = tomllib.loads((paths.stations_dir / "mk2.toml").read_text())
    assert data["control"] == "wfview" and data["virtual_audio"] is True
    assert "warning" not in capsys.readouterr().out


def test_pipewire_dropin_is_private(paths):
    import stat
    from datetime import UTC, datetime

    from emcomm.apply import apply_changes
    changes = plan_changes(paths, CTX)
    apply_changes(paths, changes, datetime.now(UTC))
    dropin = paths.home / ".config/pipewire/pipewire.conf.d/60-emcomm-mk2.conf"
    assert stat.S_IMODE(dropin.stat().st_mode) == 0o600


def test_switching_kit_removes_stale_dropin_with_backup(paths, monkeypatch):
    from emcomm.commands import use as use_cmd
    monkeypatch.setattr(use_cmd, "restart_services", lambda: True)
    assert main(["operator", "add", "K7ABC"], paths=paths) == 0
    for name in ("kita", "kitb"):
        assert main(["station", "add", name, "--radio", "icom-ic7300mk2", "--control", "wfview",
                     "--virtual-audio", "--no-udev"], paths=paths) == 0
    d = paths.home / ".config/pipewire/pipewire.conf.d"
    assert main(["use", "K7ABC", "--station", "kita", "--yes"], paths=paths) == 0
    assert (d / "60-emcomm-kita.conf").is_file()
    assert main(["use", "K7ABC", "--station", "kitb", "--yes"], paths=paths) == 0
    assert not (d / "60-emcomm-kita.conf").exists() and (d / "60-emcomm-kitb.conf").is_file()
    backups = list((paths.state / "backups").rglob("60-emcomm-kita.conf"))
    assert len(backups) == 1 and "emcomm-kita-rx" in backups[0].read_text()
