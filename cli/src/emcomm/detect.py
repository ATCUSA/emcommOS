"""Find USB serial ports and sound cards by walking sysfs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import UsbHint, UsbMatch
from .validation import ProfileError

PATTERNS = (("tty", "class/tty/ttyUSB*"), ("tty", "class/tty/ttyACM*"),
            ("sound", "class/sound/card*"))


@dataclass(frozen=True)
class Detected:
    kind: str
    node: str
    vendor_id: str
    product_id: str
    serial: str
    product: str
    interface: str


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _usb_ancestors(device: Path) -> tuple[Path | None, Path | None]:
    iface = None
    for p in (device, *device.parents):
        if iface is None and (p / "bInterfaceNumber").is_file():
            iface = p
        if (p / "idVendor").is_file():
            return iface, p
    return iface, None


def scan(sysfs: Path) -> list[Detected]:
    found = []
    for kind, pattern in PATTERNS:
        for entry in sorted(sysfs.glob(pattern)):
            iface, dev = _usb_ancestors(entry.resolve())
            if dev is None:
                continue
            found.append(Detected(
                kind=kind,
                node=entry.name,
                vendor_id=_read(dev / "idVendor"),
                product_id=_read(dev / "idProduct"),
                serial=_read(dev / "serial"),
                product=_read(dev / "product"),
                interface=_read(iface / "bInterfaceNumber") if iface else "",
            ))
    return found


def hint_matches(hint: UsbHint, d: Detected) -> bool:
    return (
        (not hint.vendor_id or hint.vendor_id == d.vendor_id)
        and (not hint.product_id or hint.product_id == d.product_id)
        and d.serial.startswith(hint.serial_prefix)
        and hint.product_contains in d.product
        and (not hint.interface or hint.interface == d.interface)
    )


def candidates(hints: tuple[UsbHint, ...] | list[UsbHint], devices: list[Detected],
               kind: str) -> list[Detected]:
    return [d for d in devices if d.kind == kind and any(hint_matches(h, d) for h in hints)]


def find_node(devices: list[Detected], kind: str, node: str) -> Detected:
    for d in devices:
        if d.kind == kind and d.node == node:
            return d
    available = ", ".join(d.node for d in devices if d.kind == kind) or "none"
    raise ProfileError(f"no USB {kind} device {node!r} (available: {available})")


def to_match(d: Detected) -> UsbMatch:
    return UsbMatch(vendor_id=d.vendor_id, product_id=d.product_id, serial=d.serial,
                    interface=d.interface if d.kind == "tty" else "")
