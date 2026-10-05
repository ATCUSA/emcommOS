"""emcomm-build command line."""

from __future__ import annotations

import argparse
import sys

from .bump import bump
from .model import DefinitionError, load_recipes, load_targets, repo_root
from .upstream import is_newer, list_tags, pick_latest


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    targets = load_targets(root)
    recipes = load_recipes(root)
    print(f"ok: {len(targets)} targets, {len(recipes)} recipes")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    root = repo_root()
    recipes = load_recipes(root)
    updates = []
    for r in recipes.values():
        if r.upstream is None:
            continue
        latest = pick_latest(list_tags(r.upstream), r.upstream.tag_pattern)
        if latest and is_newer(latest, r.version):
            updates.append((r.name, r.version, latest))
    for name, old, new in updates:
        print(f"{name}: {old} -> {new}")
        if args.write:
            print(f"  bumped: {', '.join(bump(root, name, new))}")
    if not updates:
        print("all recipes are current")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    changed = bump(repo_root(), args.name, args.version)
    print(f"bumped: {', '.join(changed)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="emcomm-build", description="emcommOS package builder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate targets.yaml and all recipes").set_defaults(
        func=cmd_validate
    )
    check = sub.add_parser("check", help="look for newer upstream releases")
    check.add_argument("--write", action="store_true", help="bump recipes that are behind")
    check.set_defaults(func=cmd_check)
    bump_p = sub.add_parser("bump", help="set a recipe version (recomputes sha256)")
    bump_p.add_argument("name")
    bump_p.add_argument("version")
    bump_p.set_defaults(func=cmd_bump)
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
