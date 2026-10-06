"""`emcomm status` — show the active operator and station."""

from __future__ import annotations

import argparse

from ..apply import load_active
from ..paths import Paths
from ..profiles import load_station
from ..radios import load_radios


def register(sub: argparse._SubParsersAction) -> None:
    sub.add_parser("status", help="show the active operator and station").set_defaults(
        func=cmd_status)


def cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    active = load_active(paths)
    if not active:
        print("no active operator/station; run `emcomm use CALLSIGN --station NAME`")
        return 0
    station = load_station(paths, active["station"])
    radio = load_radios(paths.radios_dir).get(station.radio)
    label = radio.label if radio else station.radio
    print(f"operator: {active['operator']}")
    print(f"station: {station.name} ({label})")
    if station.cat:
        print(f"cat: {station.cat_link}")
    if station.audio:
        print(f"audio: {station.alsa_id}")
    return 0
