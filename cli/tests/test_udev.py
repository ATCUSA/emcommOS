from emcomm.models import RadioDef, Station, UsbMatch
from emcomm.udev import apply_udev, render_rules, udev_env_value

IC7300 = RadioDef(id="icom-ic7300", vendor="Icom", model="IC-7300", hamlib_model=3073,
                  baud=19200, ptt="cat")
KIT = Station(name="kita", radio="icom-ic7300",
              cat=UsbMatch("10c4", "ea60", "IC-7300 03001234 A", "00"),
              audio=UsbMatch("08bb", "2901"))


def test_env_value_matches_udev_escaping():
    assert udev_env_value("IC-7300 03001234 A") == "IC-7300_03001234_A"
    assert udev_env_value("a/b") == "a_b"


def test_render_rules():
    text = render_rules(KIT, IC7300)
    lines = text.splitlines()
    assert lines[0].startswith("# Managed by emcomm")
    assert lines[1] == (
        'SUBSYSTEM=="tty", ENV{ID_VENDOR_ID}=="10c4", ENV{ID_MODEL_ID}=="ea60", '
        'ENV{ID_SERIAL_SHORT}=="IC-7300_03001234_A", ENV{ID_USB_INTERFACE_NUM}=="00", '
        'SYMLINK+="emcomm/cat-kita", ENV{ID_MM_DEVICE_IGNORE}="1"'
    )
    assert lines[2] == (
        'ACTION=="add", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="10c4", '
        'ATTR{idProduct}=="ea60", ATTR{serial}=="IC-7300 03001234 A", TEST=="power/control", '
        'ATTR{power/control}="on"'
    )
    assert lines[3] == (
        'SUBSYSTEM=="sound", KERNEL=="card*", ATTRS{idVendor}=="08bb", '
        'ATTRS{idProduct}=="2901", ATTR{id}="EMCOMM_KITA"'
    )
    assert lines[4].endswith('ATTR{idProduct}=="2901", TEST=="power/control", ATTR{power/control}="on"')


def test_render_without_devices():
    assert len(render_rules(Station(name="bench", radio="generic-vox"), IC7300).splitlines()) == 1


def test_apply_writes_and_prunes(paths):
    paths.udev_rules.mkdir(parents=True)
    stale = paths.udev_rules / "70-emcomm-old.rules"
    stale.write_text("x")
    other = paths.udev_rules / "99-local.rules"
    other.write_text("keep")
    calls = []
    assert apply_udev(paths, [KIT], {"icom-ic7300": IC7300}, run=calls.append) is True
    assert (paths.udev_rules / "70-emcomm-kita.rules").is_file()
    assert not stale.exists() and other.exists()
    assert calls == []  # not the real /etc/udev/rules.d, so no udevadm
    assert apply_udev(paths, [KIT], {"icom-ic7300": IC7300}, run=calls.append) is False
