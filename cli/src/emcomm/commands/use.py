"""`emcomm use` — apply an operator + station to every app's config."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from ..apply import apply_changes, plan_changes, render_diff, restart_services, save_active
from ..paths import Paths
from ..profiles import load_operator, load_station
from ..radios import load_radios
from ..render.context import RenderContext
from ..validation import ProfileError

EMCOMM_WFVIEW = Path("/opt/emcomm/bin/wfview")  # tests monkeypatch this


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("use", help="switch operator/station and update app configs")
    p.add_argument("callsign")
    p.add_argument("--station", required=True)
    p.add_argument("--dry-run", action="store_true", help="show the diff only")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_use)


def _confirm() -> bool:
    try:
        return input("Apply these changes? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def cmd_use(args: argparse.Namespace, paths: Paths) -> int:
    operator = load_operator(paths, args.callsign)
    station = load_station(paths, args.station)
    radios = load_radios(paths.radios_dir)
    if station.radio not in radios:
        raise ProfileError(f"station {station.name} uses unknown radio {station.radio!r}")
    ctx = RenderContext(operator=operator, station=station, radio=radios[station.radio])
    changes = plan_changes(paths, ctx)
    if not changes:
        print("configs already up to date")
        if not args.dry_run:
            save_active(paths, operator.callsign, station.name)
        return 0
    print(render_diff(changes, paths.home), end="")
    if args.dry_run:
        return 0
    if not args.yes and not _confirm():
        print("aborted")
        return 1
    backup = apply_changes(paths, changes, datetime.now())  # noqa: DTZ005
    save_active(paths, operator.callsign, station.name)
    print(f"updated {len(changes)} file(s) for {operator.callsign} on {station.name}")
    if backup:
        print(f"previous files saved in {backup}")
    if not restart_services():
        print("note: could not restart emcomm user services; restart them yourself if running",
              file=sys.stderr)
    if station.control == "wfview":
        print("note: start or restart wfview after `emcomm use` (it overwrites wfview.conf on "
              "exit), and before emcomm-rigctld.", file=sys.stderr)
        if not EMCOMM_WFVIEW.exists():
            print("warning: this wfview is not the emcomm build; its rigctld server listens on "
                  "all interfaces without a password. Block TCP 4533 in the firewall on "
                  "untrusted networks.", file=sys.stderr)
    if station.virtual_audio:
        print("note: restart PipeWire to create the virtual devices "
              "(systemctl --user restart pipewire pipewire-pulse wireplumber). In wfview, set "
              f"audio output to '{station.rx_sink}' and input to 'Monitor of {station.tx_sink}'.",
              file=sys.stderr)
    return 0
