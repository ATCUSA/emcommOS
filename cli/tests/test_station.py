import tomllib

from sysfs import add_acm, add_sound, add_tty, make_usb

from emcomm.cli import main


def plug_ic7300(paths):
    add_tty(paths.sysfs, make_usb(paths.sysfs, "1-1", "10c4", "ea60", "IC-7300 0300 A",
                                  "IC-7300"), "ttyUSB0")
    add_sound(paths.sysfs, make_usb(paths.sysfs, "1-2", "08bb", "2901"), "card1")


def test_add_auto_detects(paths, capsys):
    plug_ic7300(paths)
    assert main(["station", "add", "kita", "--radio", "icom-ic7300"], paths=paths) == 0
    data = tomllib.loads((paths.stations_dir / "kita.toml").read_text())
    assert data["cat"] == {"vendor_id": "10c4", "product_id": "ea60",
                           "serial": "IC-7300 0300 A", "interface": "00"}
    assert data["audio"] == {"vendor_id": "08bb", "product_id": "2901"}
    assert (paths.udev_rules / "70-emcomm-kita.rules").is_file()
    out = capsys.readouterr().out
    assert "/dev/emcomm/cat-kita" in out and "CI-V USB Baud Rate" in out


def test_add_explicit_nodes(paths):
    plug_ic7300(paths)
    assert main(["station", "add", "kitb", "--radio", "generic-rts", "--cat", "ttyUSB0",
                 "--audio", "card1", "--no-udev"], paths=paths) == 0
    assert not paths.udev_rules.exists()


def test_add_ambiguous(paths, capsys):
    plug_ic7300(paths)
    add_tty(paths.sysfs, make_usb(paths.sysfs, "1-5", "10c4", "ea60", "IC-7300 0999 A",
                                  "IC-7300"), "ttyUSB3")
    assert main(["station", "add", "kita", "--radio", "icom-ic7300"], paths=paths) == 1
    assert "ttyUSB0, ttyUSB3" in capsys.readouterr().err


def test_add_without_hardware(paths, capsys):
    assert main(["station", "add", "bench", "--radio", "generic-vox", "--no-udev"],
                paths=paths) == 0
    assert "cat" not in tomllib.loads((paths.stations_dir / "bench.toml").read_text())


def test_unknown_radio(paths, capsys):
    assert main(["station", "add", "x", "--radio", "nope"], paths=paths) == 1
    assert "emcomm radios" in capsys.readouterr().err


def test_list_and_detect(paths, capsys):
    plug_ic7300(paths)
    main(["station", "add", "kita", "--radio", "icom-ic7300", "--no-udev"], paths=paths)
    capsys.readouterr()
    assert main(["station", "list"], paths=paths) == 0
    assert "EMCOMM_KITA" in capsys.readouterr().out
    assert main(["station", "detect"], paths=paths) == 0
    assert "10c4:ea60" in capsys.readouterr().out


def test_apply_udev_command(paths, capsys):
    plug_ic7300(paths)
    main(["station", "add", "kita", "--radio", "icom-ic7300", "--no-udev"], paths=paths)
    capsys.readouterr()
    assert main(["station", "apply-udev"], paths=paths) == 0
    assert "udev: updated" in capsys.readouterr().out
    assert main(["station", "apply-udev"], paths=paths) == 0
    assert "udev: up to date" in capsys.readouterr().out


def test_add_cat_ttyacm(paths):
    add_acm(paths.sysfs, make_usb(paths.sysfs, "1-4", "0c26", "0036", "IC7300MK2 01",
                                  "IC-7300MK2"), "ttyACM0")
    assert main(["station", "add", "kitc", "--radio", "generic-rts", "--cat", "ttyACM0",
                 "--no-udev"], paths=paths) == 0
    data = tomllib.loads((paths.stations_dir / "kitc.toml").read_text())
    assert data["cat"]["vendor_id"] == "0c26" and data["cat"]["interface"] == "00"
