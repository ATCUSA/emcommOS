"""`emcomm radios` — list supported radio definitions."""

from __future__ import annotations

import argparse

from ..paths import Paths
from ..radios import load_radios
from ..validation import ProfileError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("radios", help="list radio definitions, or show one")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=cmd_radios)


def cmd_radios(args: argparse.Namespace, paths: Paths) -> int:
    radios = load_radios(paths.radios_dir)
    if args.id is None:
        for r in radios.values():
            print(f"{r.id:<18} {r.label:<40} hamlib {r.hamlib_model:<5} ptt {r.ptt}")
        return 0
    if args.id not in radios:
        raise ProfileError(f"unknown radio {args.id!r}; see `emcomm radios`")
    r = radios[args.id]
    print(f"{r.label}\n  hamlib model: {r.hamlib_model}\n  baud: {r.baud}\n  ptt: {r.ptt}")
    if r.notes:
        print("  radio settings:")
        for note in r.notes:
            print(f"    - {note}")
    return 0
