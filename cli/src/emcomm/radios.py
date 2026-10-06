"""Radio definitions shipped in /opt/emcomm/share/emcomm/radios."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import RadioDef, UsbHint
from .validation import ProfileError, validate


def radio_from_dict(data: dict) -> RadioDef:
    hints = data.get("usb_hints", {})
    return RadioDef(
        id=data["id"],
        vendor=data["vendor"],
        model=data["model"],
        hamlib_model=data["hamlib_model"],
        baud=data["baud"],
        ptt=data["ptt"],
        set_conf=tuple(sorted((k, str(v)) for k, v in data.get("set_conf", {}).items())),
        cat_hints=tuple(UsbHint(**h) for h in hints.get("cat", [])),
        audio_hints=tuple(UsbHint(**h) for h in hints.get("audio", [])),
        notes=tuple(data.get("notes", [])),
    )


def load_radios(directory: Path) -> dict[str, RadioDef]:
    if not directory.is_dir():
        raise ProfileError(f"radio definitions not found in {directory}")
    radios: dict[str, RadioDef] = {}
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        validate("radio", data, path)
        if data["id"] != path.stem:
            raise ProfileError(f"{path}: id {data['id']!r} must match the file name")
        radios[data["id"]] = radio_from_dict(data)
    return radios
