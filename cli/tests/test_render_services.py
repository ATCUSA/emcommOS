import json

import pytest

from emcomm.models import Operator, RadioDef, Station, UsbMatch
from emcomm.render.context import RenderContext
from emcomm.render.direwolf import render_direwolf
from emcomm.render.pat import render_pat
from emcomm.render.rigctld import render_rigctld, rigctld_args

IC7300 = RadioDef(id="icom-ic7300", vendor="Icom", model="IC-7300", hamlib_model=3073,
                  baud=19200, ptt="cat", set_conf=(("auto_power_on", "0"),))
RTS = RadioDef(id="generic-rts", vendor="Generic", model="RTS", hamlib_model=1, baud=9600,
               ptt="rts")
VOX = RadioDef(id="generic-vox", vendor="Generic", model="VOX", hamlib_model=1, baud=9600,
               ptt="vox")
OP = Operator(callsign="VE7/K7ABC", grid="DN16bk")
KIT = Station(name="kita", radio="x", cat=UsbMatch("10c4", "ea60"), audio=UsbMatch("08bb", "2901"))


def c(radio, station=KIT):
    return RenderContext(operator=OP, station=station, radio=radio)


def test_pat_new_file_uses_defaults():
    data = json.loads(render_pat(None, c(IC7300)))
    assert data["mycall"] == "VE7/K7ABC"
    assert data["locator"] == "DN16bk"
    assert data["http_addr"] == "localhost:8080"
    assert data["hamlib_rigs"]["emcomm"] == {"network": "tcp", "address": "127.0.0.1:4532",
                                             "VFO": ""}
    assert data["ardop"]["rig"] == "emcomm" and data["ardop"]["ptt_ctrl"] is True
    assert data["varahf"]["ptt_ctrl"] is True


def test_pat_preserves_unmanaged_keys():
    existing = json.dumps({"mycall": "N0CALL", "secure_login_password": "s3cret",
                           "hamlib_rigs": {"ft8": {"address": "x"}}, "ardop": {"addr": "h:1"}})
    data = json.loads(render_pat(existing, c(VOX)))
    assert data["secure_login_password"] == "s3cret"
    assert data["hamlib_rigs"]["ft8"] == {"address": "x"}
    assert data["ardop"] == {"addr": "h:1", "rig": "emcomm", "ptt_ctrl": False}


def test_pat_invalid_json():
    with pytest.raises(ValueError, match="pat"):
        render_pat("{nope", c(IC7300))


def test_direwolf():
    out = render_direwolf(None, c(IC7300))
    assert "ADEVICE plughw:CARD=EMCOMM_KITA,DEV=0" in out
    assert "MYCALL K7ABC\n" in out
    assert "PTT RIG 2 127.0.0.1:4532" in out
    assert "PTT" not in render_direwolf(None, c(VOX))
    assert render_direwolf(None, c(IC7300, Station(name="b", radio="x"))) is None


def test_rigctld_args():
    assert rigctld_args(c(IC7300)) == [
        "-m", "3073", "-T", "127.0.0.1", "-t", "4532", "-r", "/dev/emcomm/cat-kita",
        "-s", "19200", "--set-conf=auto_power_on=0"]
    assert rigctld_args(c(RTS)) == [
        "-m", "1", "-T", "127.0.0.1", "-t", "4532", "-P", "RTS", "-p", "/dev/emcomm/cat-kita"]
    assert rigctld_args(c(VOX, Station(name="b", radio="x"))) == [
        "-m", "1", "-T", "127.0.0.1", "-t", "4532"]
    assert render_rigctld(None, c(VOX, Station(name="b", radio="x"))).endswith(
        'RIGCTLD_ARGS="-m 1 -T 127.0.0.1 -t 4532"\n')


@pytest.mark.parametrize("forbidden_char", ['"', '\\', '$', '\n', '\t', '\r', ' '])
def test_render_rigctld_rejects_forbidden_chars_in_set_conf(forbidden_char):
    """Test that render_rigctld rejects set_conf values with forbidden characters."""
    bad_radio = RadioDef(id="bad", vendor="Bad", model="Radio", hamlib_model=1, baud=9600,
                         ptt="vox", set_conf=(("k", f"a{forbidden_char}b"),))
    with pytest.raises(ValueError, match="forbidden"):
        render_rigctld(None, c(bad_radio))


def test_pat_rejects_non_dict_root():
    """Test that pat rejects JSON that isn't an object at root."""
    with pytest.raises(ValueError, match="must be a JSON object"):
        render_pat("[]", c(IC7300))
    with pytest.raises(ValueError, match="must be a JSON object"):
        render_pat("null", c(IC7300))


def test_pat_rejects_non_dict_managed_section():
    """Test that pat rejects non-dict values in managed sections."""
    # ardop is null instead of dict
    with pytest.raises(ValueError, match="ardop.*must be a JSON object"):
        render_pat(json.dumps({"ardop": None}), c(IC7300))
    # hamlib_rigs is null instead of dict
    with pytest.raises(ValueError, match="hamlib_rigs.*must be a JSON object"):
        render_pat(json.dumps({"hamlib_rigs": None}), c(IC7300))


def test_pat_preserves_non_ascii_and_unknown_keys():
    """Test that pat preserves non-ASCII in motd and unknown keys."""
    existing = json.dumps({"mycall": "N0CALL", "motd": ["Café ☕"], "unknown_key": "preserved"})
    rendered = render_pat(existing, c(IC7300))
    data = json.loads(rendered)
    assert data["motd"] == ["Café ☕"]
    assert data["unknown_key"] == "preserved"
