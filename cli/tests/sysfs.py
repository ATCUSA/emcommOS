"""Build a minimal fake /sys tree with the same shape as the real one."""

from pathlib import Path


def make_usb(sysfs: Path, port: str, vid: str, pid: str, serial: str = "", product: str = "",
             iface: str = "00") -> Path:
    dev = sysfs / "devices/pci0000:00/0000:00:14.0/usb1" / port
    dev.mkdir(parents=True, exist_ok=True)
    (dev / "idVendor").write_text(vid + "\n")
    (dev / "idProduct").write_text(pid + "\n")
    if serial:
        (dev / "serial").write_text(serial + "\n")
    if product:
        (dev / "product").write_text(product + "\n")
    iface_dir = dev / f"{port}:1.{int(iface, 16)}"
    iface_dir.mkdir(exist_ok=True)
    (iface_dir / "bInterfaceNumber").write_text(iface + "\n")
    return iface_dir


def add_tty(sysfs: Path, iface_dir: Path, name: str) -> None:
    node = iface_dir / name / "tty" / name
    node.mkdir(parents=True)
    (sysfs / "class/tty").mkdir(parents=True, exist_ok=True)
    (sysfs / "class/tty" / name).symlink_to(node)


def add_sound(sysfs: Path, iface_dir: Path, name: str) -> None:
    node = iface_dir / "sound" / name
    node.mkdir(parents=True)
    (sysfs / "class/sound").mkdir(parents=True, exist_ok=True)
    (sysfs / "class/sound" / name).symlink_to(node)
