"""`emcomm uninstall` — remove everything emcommOS added (runs bootstrap.sh --uninstall)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..paths import Paths
from ..validation import ProfileError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("uninstall", help="remove emcommOS packages, repo, pins, units, rules")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_uninstall)


def cmd_uninstall(args: argparse.Namespace, paths: Paths) -> int:
    if os.geteuid() != 0:
        raise ProfileError("uninstall changes system configuration; run it with sudo")
    script = paths.share / "bootstrap.sh"
    if not script.is_file():
        raise ProfileError(f"{script} not found; run bootstrap.sh --uninstall manually")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "bootstrap.sh"
        shutil.copy2(script, copy)  # the package being removed owns the original
        cmd = ["sh", str(copy), "--uninstall"] + (["--yes"] if args.yes else [])
        return subprocess.run(cmd, check=False).returncode
