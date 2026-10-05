"""emcomm-build command line."""

from __future__ import annotations

import argparse
import sys

from .model import DefinitionError, load_recipes, load_targets, repo_root


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    targets = load_targets(root)
    recipes = load_recipes(root)
    print(f"ok: {len(targets)} targets, {len(recipes)} recipes")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="emcomm-build", description="emcommOS package builder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate targets.yaml and all recipes").set_defaults(
        func=cmd_validate
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DefinitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
