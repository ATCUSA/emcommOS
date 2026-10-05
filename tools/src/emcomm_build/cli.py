"""emcomm-build command line."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

from .build import BuildError, BuildSettings, host_arch
from .build import run as run_builds
from .bump import bump, bump_order
from .container import engine_from_env
from .fetch import FetchError
from .freshness import load_entries, report
from .model import DefinitionError, load_recipes, load_targets, repo_root
from .plan import build_order, recipes_for_target
from .publish import publish
from .upstream import is_newer, list_tags, pick_latest


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    targets = load_targets(root)
    recipes = load_recipes(root)
    build_order(recipes)
    print(f"ok: {len(targets)} targets, {len(recipes)} recipes")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    root = repo_root()
    recipes = load_recipes(root)
    updates = []
    failed = False
    for r in recipes.values():
        if r.upstream is None:
            continue
        try:
            latest = pick_latest(list_tags(r.upstream), r.upstream.tag_pattern)
            if latest and is_newer(latest, r.version):
                updates.append((r.name, r.version, latest))
        except (urllib.error.URLError, TimeoutError, subprocess.CalledProcessError, OSError) as exc:
            print(f"error: {r.name}: {exc}", file=sys.stderr)
            failed = True
    for name, old, new in updates:
        print(f"{name}: {old} -> {new}")
    if args.write and updates:
        # Bump in order so dependencies are processed first
        ordered_names = bump_order(recipes, [name for name, _, _ in updates])
        update_dict = {name: new for name, _, new in updates}
        for name in ordered_names:
            new_version = update_dict[name]
            try:
                print(f"  bumped: {', '.join(bump(root, name, new_version))}")
            except (urllib.error.URLError, TimeoutError, subprocess.CalledProcessError, OSError, DefinitionError) as exc:
                print(f"error: {name}: {exc}", file=sys.stderr)
                failed = True
    if not updates and not failed:
        print("all recipes are current")
    return 1 if failed else 0


def cmd_bump(args: argparse.Namespace) -> int:
    changed = bump(repo_root(), args.name, args.version)
    print(f"bumped: {', '.join(changed)}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    root = repo_root()
    targets = load_targets(root)
    if args.target not in targets:
        raise DefinitionError(f"unknown target {args.target!r}; known: {', '.join(targets)}")
    target = targets[args.target]
    arch = args.arch or host_arch()
    if arch != host_arch():
        raise DefinitionError(f"cannot build {arch} on a {host_arch()} host (no emulation)")
    only = list(args.only)
    if only:
        everything = load_recipes(root)
        applicable = recipes_for_target(everything, target)
        kept = []
        for name in only:
            if name not in everything:
                raise DefinitionError(f"unknown recipe {name!r}; known: {', '.join(everything)}")
            if name not in applicable:
                print(f"skipping {name}: not built for {target.name}")
            else:
                kept.append(name)
        if not kept:
            print(f"nothing to build for {target.name}")
            return 0
        only = kept
    settings = BuildSettings(
        root=root,
        target=target,
        arch=arch,
        out=Path(args.out) if args.out else root / "dist" / args.target / arch,
        work=Path(args.work) if args.work else root / "build",
        repo_url=args.repo_url or os.environ.get("EMCOMM_REPO_URL") or None,
        channel=args.channel,
        only=tuple(only),
        force=args.force,
        smoke=not args.no_smoke,
        engine=engine_from_env(),
    )
    built = run_builds(settings)
    for path in built:
        print(f"built {path}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    root = repo_root()
    publish(root, Path(args.dist), Path(args.repo_dir), load_targets(root),
            Path(args.key_file), Path(args.passphrase_file),
            Path(args.public_key) if args.public_key else root / "keys/emcomm-archive-keyring.asc",
            engine=engine_from_env())
    print(f"published {args.repo_dir}")
    return 0


def cmd_freshness(args: argparse.Namespace) -> int:
    rows = report(load_entries(repo_root()))
    cols = ["app", "upstream", "trixie", "trixie-backports", "f43", "f44"]
    print("  ".join(f"{c:<18}" for c in cols))
    for row in rows:
        print("  ".join(f"{row[c]:<18}" for c in cols))
    print("(= means the distro already ships the latest upstream release)")
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
    b = sub.add_parser("build", help="build packages for one target on this host")
    b.add_argument("--target", required=True)
    b.add_argument("--arch", help="defaults to the host architecture")
    b.add_argument("--out", help="output dir (default dist/<target>/<arch>)")
    b.add_argument("--work", help="scratch dir (default build/)")
    b.add_argument("--repo-url", help="published repo base URL (default $EMCOMM_REPO_URL)")
    b.add_argument("--channel", default="testing")
    b.add_argument("--only", action="append", default=[], help="build only this recipe + deps")
    b.add_argument("--force", action="store_true", help="rebuild even if already published")
    b.add_argument("--no-smoke", action="store_true")
    b.set_defaults(func=cmd_build)
    pub = sub.add_parser("publish", help="add built packages to a channel tree and sign it")
    pub.add_argument("--dist", required=True, help="dir laid out as <target>/<arch>/*.pkg")
    pub.add_argument("--repo-dir", required=True, help="local copy of the channel tree")
    pub.add_argument("--key-file", required=True, help="armored secret signing (sub)key")
    pub.add_argument("--passphrase-file", required=True, help="file with the key passphrase")
    pub.add_argument("--public-key", help="default keys/emcomm-archive-keyring.asc")
    pub.set_defaults(func=cmd_publish)
    sub.add_parser("freshness", help="compare distro package versions with upstream").set_defaults(
        func=cmd_freshness)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (DefinitionError, BuildError, FetchError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
