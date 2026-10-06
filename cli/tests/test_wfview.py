import tomllib

from sysfs import add_sound, add_tty, make_usb

from emcomm.cli import main
from emcomm.models import Operator, RadioDef, Station, UsbMatch
from emcomm.profiles import station_from_dict, station_to_dict
from emcomm.radios import load_radios
from emcomm.render.context import RenderContext
from emcomm.render.rigctld import rigctld_args
from emcomm.render.wfview import render_wfview

MK2 = RadioDef(id="icom-ic7300mk2", vendor="Icom", model="IC-7300MK2", hamlib_model=3094,
               baud=115200, ptt="cat")
OP = Operator(callsign="K7ABC", grid="DN16bk")


def kit(control):
    return Station(name="mk2", radio="icom-ic7300mk2", cat=UsbMatch("0c26", "0000"),
                   audio=UsbMatch("08bb", "2901"), control=control)


def test_mk2_definition(paths):
    r = load_radios(paths.radios_dir)["icom-ic7300mk2"]
    assert (r.hamlib_model, r.baud, r.ptt) == (3094, 115200, "cat")


def test_direct_control_drives_radio():
    args = rigctld_args(RenderContext(OP, kit("direct"), MK2))
    assert args[:2] == ["-m", "3094"] and "/dev/emcomm/cat-mk2" in args


def test_wfview_control_proxies_hub():
    assert rigctld_args(RenderContext(OP, kit("wfview"), MK2)) == [
        "-m", "2", "-r", "127.0.0.1:4533", "-T", "127.0.0.1", "-t", "4532"]


def test_render_wfview_only_for_wfview_stations():
    assert render_wfview(None, RenderContext(OP, kit("direct"), MK2)) is None
    out = render_wfview("[General]\nTheme=dark\n", RenderContext(OP, kit("wfview"), MK2))
    assert out == "[General]\nTheme=dark\n\n[LAN]\nEnableRigCtlD=true\nRigCtlPort=4533\n"


def test_control_round_trip():
    st = kit("wfview")
    assert station_from_dict(station_to_dict(st), "t").control == "wfview"
    assert "control" not in station_to_dict(kit("direct"))


def test_station_add_and_use_with_wfview(paths, monkeypatch, capsys):
    from emcomm.commands import use as use_cmd
    monkeypatch.setattr(use_cmd, "restart_services", lambda: True)
    add_tty(paths.sysfs, make_usb(paths.sysfs, "1-1", "0c26", "0000", product="IC-7300MK2"),
            "ttyACM0")
    add_sound(paths.sysfs, make_usb(paths.sysfs, "1-2", "08bb", "2901"), "card1")
    assert main(["operator", "add", "K7ABC"], paths=paths) == 0
    assert main(["station", "add", "mk2", "--radio", "icom-ic7300mk2", "--cat", "ttyACM0",
                 "--audio", "card1", "--control", "wfview", "--no-udev"], paths=paths) == 0
    assert tomllib.loads((paths.stations_dir / "mk2.toml").read_text())["control"] == "wfview"
    capsys.readouterr()
    assert main(["use", "K7ABC", "--station", "mk2", "--yes"], paths=paths) == 0
    assert "EnableRigCtlD=true" in (paths.home / ".config/wfview/wfview.conf").read_text()
    assert "-r 127.0.0.1:4533" in (paths.home / ".config/emcomm/rigctld.env").read_text()
    assert "TCP 4533" in capsys.readouterr().err
