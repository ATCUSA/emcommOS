"""`emcomm station` — station kits (radio + interface on this machine)."""

from __future__ import annotations

import argparse

from ..detect import candidates, find_node, scan, to_match
from ..models import CONTROL_MODES, PTT_METHODS, RadioDef, Station, UsbHint
from ..paths import Paths
from ..profiles import list_stations, save_station
from ..radios import load_radios
from ..udev import apply_udev
from ..validation import ProfileError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("station", help="manage station kits")
    actions = p.add_subparsers(dest="action", required=True)
    actions.add_parser("detect", help="list USB serial ports and sound cards").set_defaults(
        func=cmd_detect)
    add = actions.add_parser("add", help="create or update a station kit (needs root)")
    add.add_argument("name", help="short kit name: lowercase letters, digits, '-', max 8")
    add.add_argument("--radio", required=True, help="radio definition id (see `emcomm radios`)")
    add.add_argument("--cat", help="serial node for CAT/PTT, e.g. ttyUSB0 (default: auto)")
    add.add_argument("--audio", help="sound card node, e.g. card1 (default: auto)")
    add.add_argument("--ptt", choices=PTT_METHODS, help="override the radio's PTT method")
    add.add_argument("--control", choices=CONTROL_MODES, default="direct",
                     help="direct: rigctld drives the radio; wfview: wfview owns it")
    add.add_argument("--virtual-audio", action="store_true",
                     help="LAN kit: create PipeWire virtual RX/TX devices")
    add.add_argument("--no-udev", action="store_true", help="do not write udev rules")
    add.set_defaults(func=cmd_add)
    actions.add_parser("list", help="list station kits").set_defaults(func=cmd_list)
    actions.add_parser("apply-udev", help="regenerate udev rules (needs root)").set_defaults(
        func=cmd_apply_udev)


def cmd_detect(args: argparse.Namespace, paths: Paths) -> int:
    devices = scan(paths.sysfs)
    if not devices:
        print("no USB serial ports or sound cards found")
    for d in devices:
        iface = f" if{d.interface}" if d.interface else ""
        print(f"{d.kind:<6} {d.node:<8} {d.vendor_id}:{d.product_id}{iface:<5} "
              f"{d.product} [{d.serial}]")
    return 0


def _pick(kind: str, flag: str | None, hints: tuple[UsbHint, ...], devices, option: str):
    if flag:
        return to_match(find_node(devices, kind, flag))
    if not hints:
        return None
    found = candidates(hints, devices, kind)
    if len(found) > 1:
        names = ", ".join(d.node for d in found)
        raise ProfileError(f"several {kind} devices match ({names}); choose one with {option}")
    return to_match(found[0]) if found else None


def cmd_add(args: argparse.Namespace, paths: Paths) -> int:
    radios = load_radios(paths.radios_dir)
    if args.radio not in radios:
        raise ProfileError(f"unknown radio {args.radio!r}; see `emcomm radios`")
    radio: RadioDef = radios[args.radio]
    devices = scan(paths.sysfs)
    station = Station(
        name=args.name,
        radio=radio.id,
        cat=_pick("tty", args.cat, radio.cat_hints, devices, "--cat"),
        audio=_pick("sound", args.audio, radio.audio_hints, devices, "--audio"),
        ptt=args.ptt,
        control=args.control,
        virtual_audio=args.virtual_audio,
    )
    path = save_station(paths, station)
    print(f"saved station {station.name} ({radio.label}) -> {path}")
    if station.cat:
        print(f"  CAT/PTT port: {station.cat_link}")
    elif args.control != "wfview" and (
            station.ptt_method(radio) in ("rts", "dtr") or radio.hamlib_model != 1):
        # (wfview owns the CAT port, or reaches the radio over LAN: nothing to warn about)
        print("  warning: no CAT serial port found; plug in the radio or pass --cat")
    if station.audio:
        print(f"  sound card:   {station.alsa_id} (replug the radio after udev rules change)")
    if not args.no_udev:
        _apply(paths, radios)
    if radio.notes:
        print("  radio settings:")
        for note in radio.notes:
            print(f"    - {note}")
    return 0


def cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    stations = list_stations(paths)
    if not stations:
        print("no station kits yet; add one with `emcomm station add NAME --radio ID`")
    for st in stations:
        cat = st.cat_link if st.cat else "-"
        audio = st.alsa_id if st.audio else "-"
        print(f"{st.name:<9} {st.radio:<18} {cat:<26} {audio}")
    return 0


def _apply(paths: Paths, radios: dict[str, RadioDef]) -> None:
    changed = apply_udev(paths, list_stations(paths), radios)
    print("udev: updated" if changed else "udev: up to date")


def cmd_apply_udev(args: argparse.Namespace, paths: Paths) -> int:
    _apply(paths, load_radios(paths.radios_dir))
    return 0
