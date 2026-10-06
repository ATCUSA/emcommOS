import pytest
from sysfs import add_sound, add_tty, make_usb

from emcomm.detect import candidates, find_node, hint_matches, scan, to_match
from emcomm.models import UsbHint
from emcomm.validation import ProfileError


@pytest.fixture
def ic7300_and_ft991a(tmp_path):
    sysfs = tmp_path / "sys"
    add_tty(sysfs, make_usb(sysfs, "1-1", "10c4", "ea60", "IC-7300 03001234 A", "IC-7300"), "ttyUSB0")
    add_sound(sysfs, make_usb(sysfs, "1-2", "08bb", "2901", product="USB Audio CODEC"), "card1")
    add_tty(sysfs, make_usb(sysfs, "1-3", "10c4", "ea70", "00A5B1C2", "CP2105", iface="00"), "ttyUSB1")
    add_tty(sysfs, make_usb(sysfs, "1-3", "10c4", "ea70", "00A5B1C2", "CP2105", iface="01"), "ttyUSB2")
    return sysfs


def test_scan(ic7300_and_ft991a):
    found = {d.node: d for d in scan(ic7300_and_ft991a)}
    assert set(found) == {"ttyUSB0", "ttyUSB1", "ttyUSB2", "card1"}
    assert found["ttyUSB0"].serial == "IC-7300 03001234 A"
    assert found["ttyUSB2"].interface == "01"
    assert found["card1"].kind == "sound"
    assert found["card1"].vendor_id == "08bb"


def test_scan_empty(tmp_path):
    assert scan(tmp_path / "nothing") == []


def test_hints(ic7300_and_ft991a):
    devices = scan(ic7300_and_ft991a)
    ic = [UsbHint(vendor_id="10c4", product_id="ea60", serial_prefix="IC-7300")]
    assert [d.node for d in candidates(ic, devices, "tty")] == ["ttyUSB0"]
    ft = [UsbHint(vendor_id="10c4", product_id="ea70", interface="00")]
    assert [d.node for d in candidates(ft, devices, "tty")] == ["ttyUSB1"]
    by_name = [UsbHint(product_contains="IC-7300")]
    assert hint_matches(by_name[0], find_node(devices, "tty", "ttyUSB0"))


def test_find_node_errors(ic7300_and_ft991a):
    with pytest.raises(ProfileError, match="ttyUSB9"):
        find_node(scan(ic7300_and_ft991a), "tty", "ttyUSB9")


def test_to_match(ic7300_and_ft991a):
    devices = scan(ic7300_and_ft991a)
    tty = to_match(find_node(devices, "tty", "ttyUSB1"))
    assert (tty.vendor_id, tty.product_id, tty.interface) == ("10c4", "ea70", "00")
    snd = to_match(find_node(devices, "sound", "card1"))
    assert snd.interface == ""
