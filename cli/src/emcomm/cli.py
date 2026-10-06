"""emcomm command line entry point."""

from __future__ import annotations

import argparse
import sys

from .commands import operator, radios, station, status, use
from .paths import Paths
from .validation import ProfileError

COMMANDS = [operator, radios, station, use, status]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="emcomm", description="emcommOS station tool")
    sub = parser.add_subparsers(dest="command", required=True)
    for module in COMMANDS:
        module.register(sub)
    return parser


def main(argv: list[str] | None = None, paths: Paths | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = paths or Paths.from_env()
    try:
        return args.func(args, paths)
    except (ProfileError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"error: {exc.filename}: permission denied (try sudo)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
