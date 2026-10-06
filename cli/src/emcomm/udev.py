"""Generate udev rules giving each station kit stable device names.

Rules are numbered 70 so ENV{ID_*} from 60-serial.rules is available and
ID_MM_DEVICE_IGNORE is set before ModemManager's 77/80 rules probe the port.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .models import RadioDef, Station, UsbMatch
from .paths import Paths
from .validation import ProfileError

SYSTEM_RULES = Path("/etc/udev/rules.d")
UDEV_UNSAFE = re.compile(r"[^A-Za-z0-9#+\-.:=@_]")


def udev_env_value(value: str) -> str:
    """Mirror how udev's usb_id sanitizes strings into ID_* properties."""
    return UDEV_UNSAFE.sub("_", re.sub(r"\s+", "_", value.strip()))


def rules_path(paths: Paths, station: Station) -> Path:
    return paths.udev_rules / f"70-emcomm-{station.name}.rules"


def _no_autosuspend(m: UsbMatch) -> str:
    """Laptops autosuspend idle USB devices, which drops CAT/audio mid-QSO; keep kit devices on."""
    keys = ['ACTION=="add"', 'SUBSYSTEM=="usb"', 'ENV{DEVTYPE}=="usb_device"',
            f'ATTR{{idVendor}}=="{m.vendor_id}"', f'ATTR{{idProduct}}=="{m.product_id}"']
    if m.serial:
        keys.append(f'ATTR{{serial}}=="{m.serial}"')
    keys += ['TEST=="power/control"', 'ATTR{power/control}="on"']
    return ", ".join(keys)


def render_rules(station: Station, radio: RadioDef) -> str:
    lines = [
        (f"# Managed by emcomm: station {station.name} ({radio.label}). "
         "Regenerate with `emcomm station apply-udev`.")
    ]
    if station.cat:
        m = station.cat
        keys = ['SUBSYSTEM=="tty"', f'ENV{{ID_VENDOR_ID}}=="{m.vendor_id}"',
                f'ENV{{ID_MODEL_ID}}=="{m.product_id}"']
        if m.serial:
            keys.append(f'ENV{{ID_SERIAL_SHORT}}=="{udev_env_value(m.serial)}"')
        if m.interface:
            keys.append(f'ENV{{ID_USB_INTERFACE_NUM}}=="{m.interface}"')
        keys += [f'SYMLINK+="emcomm/cat-{station.name}"', 'ENV{ID_MM_DEVICE_IGNORE}="1"']
        lines.append(", ".join(keys))
        lines.append(_no_autosuspend(m))
    if station.audio:
        m = station.audio
        keys = ['SUBSYSTEM=="sound"', 'KERNEL=="card*"', f'ATTRS{{idVendor}}=="{m.vendor_id}"',
                f'ATTRS{{idProduct}}=="{m.product_id}"']
        if m.serial:
            keys.append(f'ATTRS{{serial}}=="{m.serial}"')
        keys.append(f'ATTR{{id}}="{station.alsa_id}"')
        lines.append(", ".join(keys))
        lines.append(_no_autosuspend(m))
    return "\n".join(lines) + "\n"


def apply_udev(
    paths: Paths,
    stations: list[Station],
    radios: dict[str, RadioDef],
    *,
    run: Callable = subprocess.run,
) -> bool:
    for st in stations:
        if st.radio not in radios:
            raise ProfileError(f"station {st.name!r} references unknown radio {st.radio!r}")
    paths.udev_rules.mkdir(parents=True, exist_ok=True)
    changed = False
    wanted = set()
    for st in stations:
        path = rules_path(paths, st)
        wanted.add(path)
        text = render_rules(st, radios[st.radio])
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            changed = True
    for path in paths.udev_rules.glob("70-emcomm-*.rules"):
        if path not in wanted:
            path.unlink()
            changed = True
    if changed and paths.udev_rules == SYSTEM_RULES:
        try:
            run(["udevadm", "control", "--reload"], check=True)
            run(["udevadm", "trigger", "--action=add", "--subsystem-match=tty",
                 "--subsystem-match=sound", "--subsystem-match=usb"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise ProfileError(
                f"udevadm failed: {exc}; rules were written to {paths.udev_rules}; run "
                "`sudo udevadm control --reload && sudo udevadm trigger` manually"
            ) from exc
    return changed
