"""`emcomm operator` — operator profiles (who is operating)."""

from __future__ import annotations

import argparse

from ..models import Operator, normalize_callsign, normalize_grid
from ..paths import Paths
from ..profiles import list_operators, load_operator, save_operator


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("operator", help="manage operator profiles")
    actions = p.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add", help="create or update an operator profile")
    add.add_argument("callsign")
    add.add_argument("--name", default="")
    add.add_argument("--grid", default="", help="Maidenhead locator, e.g. DN16bk")
    add.set_defaults(func=cmd_add)
    actions.add_parser("list", help="list operator profiles").set_defaults(func=cmd_list)
    show = actions.add_parser("show", help="show one operator profile")
    show.add_argument("callsign")
    show.set_defaults(func=cmd_show)


def cmd_add(args: argparse.Namespace, paths: Paths) -> int:
    op = Operator(callsign=normalize_callsign(args.callsign), name=args.name.strip(),
                  grid=normalize_grid(args.grid))
    print(f"saved {op.callsign} -> {save_operator(paths, op)}")
    return 0


def cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    ops = list_operators(paths)
    if not ops:
        print("no operators yet; add one with `emcomm operator add CALLSIGN`")
    for op in ops:
        print(f"{op.callsign:<12} {op.grid:<8} {op.name}")
    return 0


def cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    op = load_operator(paths, args.callsign)
    print(f"callsign: {op.callsign}\nname: {op.name}\ngrid: {op.grid}")
    return 0
