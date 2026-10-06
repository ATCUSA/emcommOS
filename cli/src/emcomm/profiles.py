"""Load and save operator profiles and station kits as TOML."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import tomli_w

from .models import Operator, Station, UsbMatch, normalize_callsign, normalize_grid
from .paths import Paths
from .validation import ProfileError, validate


def _write_toml(path: Path, data: dict, mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if mode is not None:
        # Write with specific mode for sensitive files
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(tomli_w.dumps(data))
        except Exception:
            fd_close_safe = fd
            try:
                os.close(fd_close_safe)
            except OSError:
                pass
            raise
    else:
        tmp.write_text(tomli_w.dumps(data))
    tmp.replace(path)
    return path


def _read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path}: {exc}") from None


def operator_path(paths: Paths, callsign: str) -> Path:
    return paths.operators_dir / f"{callsign.lower().replace('/', '_')}.toml"


def save_operator(paths: Paths, op: Operator) -> Path:
    data = {"callsign": op.callsign}
    if op.name:
        data["name"] = op.name
    if op.grid:
        data["grid"] = op.grid
    validate("operator", data, "operator")

    # Create user_config and operators_dir with mode 0o700 (private)
    paths.user_config.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths.user_config.chmod(0o700)
    paths.operators_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths.operators_dir.chmod(0o700)

    return _write_toml(operator_path(paths, op.callsign), data, mode=0o600)


def _operator_from(data: dict, where: Path) -> Operator:
    validate("operator", data, where)
    return Operator(callsign=normalize_callsign(data["callsign"]), name=data.get("name", ""),
                    grid=normalize_grid(data.get("grid", "")))


def load_operator(paths: Paths, callsign: str) -> Operator:
    path = operator_path(paths, normalize_callsign(callsign))
    if not path.is_file():
        raise ProfileError(
            f"no operator profile for {callsign}; create one with `emcomm operator add {callsign}`"
        )
    return _operator_from(_read_toml(path), path)


def list_operators(paths: Paths) -> list[Operator]:
    if not paths.operators_dir.is_dir():
        return []
    return [_operator_from(_read_toml(p), p) for p in sorted(paths.operators_dir.glob("*.toml"))]


def station_to_dict(st: Station) -> dict:
    data: dict = {"name": st.name, "radio": st.radio}
    if st.ptt:
        data["ptt"] = st.ptt
    for key, match in (("cat", st.cat), ("audio", st.audio)):
        if match:
            m = {"vendor_id": match.vendor_id, "product_id": match.product_id}
            if match.serial:
                m["serial"] = match.serial
            if match.interface:
                m["interface"] = match.interface
            data[key] = m
    return data


def station_from_dict(data: dict, where: Path | str) -> Station:
    validate("station", data, where)

    def match(key: str) -> UsbMatch | None:
        m = data.get(key)
        return UsbMatch(**m) if m else None

    return Station(name=data["name"], radio=data["radio"], cat=match("cat"),
                   audio=match("audio"), ptt=data.get("ptt"))


def save_station(paths: Paths, st: Station) -> Path:
    data = station_to_dict(st)
    validate("station", data, "station")
    return _write_toml(paths.stations_dir / f"{st.name}.toml", data)


def load_station(paths: Paths, name: str) -> Station:
    path = paths.stations_dir / f"{name}.toml"
    if not path.is_file():
        raise ProfileError(f"no station kit named {name!r}; see `emcomm station list`")
    return station_from_dict(_read_toml(path), path)


def list_stations(paths: Paths) -> list[Station]:
    if not paths.stations_dir.is_dir():
        return []
    return [station_from_dict(_read_toml(p), p) for p in sorted(paths.stations_dir.glob("*.toml"))]
