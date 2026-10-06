"""`emcomm bootstrap` — apply the emcomm.station playbook to this machine (with consent)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from ..paths import Paths
from ..validation import ProfileError

PLAYBOOK = "ansible_collections/emcomm/station/playbooks/station.yml"


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("bootstrap", help="set this machine up as an emcomm station (root)")
    p.add_argument("--repo-url", default=os.environ.get("EMCOMM_REPO_URL", ""))
    p.add_argument("--channel", default=os.environ.get("EMCOMM_CHANNEL", "testing"))
    p.add_argument("--toolsets", default=os.environ.get("EMCOMM_TOOLSETS", "standard"),
                   help="comma-separated toolsets (default: standard)")
    p.add_argument("--user", action="append", default=[],
                   help="account to add to radio groups (default: the sudo user)")
    p.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
                   help="extra Ansible variable (advanced / managed installs)")
    p.add_argument("--check", action="store_true", help="dry run (ansible --check)")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_bootstrap)


def parse_overrides(items: list[str]) -> dict:
    out = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise ProfileError(f"--set expects KEY=VALUE, got {item!r}")
        try:
            out[key] = json.loads(value)
        except json.JSONDecodeError:
            out[key] = value
    return out


def bootstrap_vars(repo_url: str, channel: str, toolsets: str, users: list[str],
                   overrides: dict) -> dict:
    data = {
        "emcomm_repo_url": repo_url.rstrip("/"),
        "emcomm_channel": channel,
        "emcomm_toolsets": [t.strip() for t in toolsets.split(",") if t.strip()],
        "emcomm_users": users,
        **overrides,
    }
    url, chan = data["emcomm_repo_url"], data["emcomm_channel"]
    if not isinstance(url, str) or not url.startswith(("https://", "file://")):
        raise ProfileError(f"refusing non-HTTPS repository URL: {url}")
    if not re.fullmatch(r"[A-Za-z0-9._~:/%@+-]+", url):
        raise ProfileError(f"repository URL contains unsupported characters: {url!r}")
    if not isinstance(chan, str) or not re.fullmatch(r"[a-z0-9._-]+", chan) or chan in (".", ".."):
        raise ProfileError(f"invalid channel {chan!r} (allowed: a-z 0-9 . _ -)")
    return data


def playbook_command(paths: Paths, vars_file: Path, check: bool) -> list[str]:
    cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local",
           str(paths.ansible_dir / PLAYBOOK), "-e", f"@{vars_file}"]
    if check:
        cmd.append("--check")
    return cmd


def _summary(data: dict) -> str:
    toolsets = ", ".join(f"emcomm-{t}" for t in data["emcomm_toolsets"]) or "(none)"
    users = ", ".join(data["emcomm_users"]) or "(none)"
    return "\n".join([
        "emcomm bootstrap will:",
        (f"  - configure the emcommOS repository ({data['emcomm_repo_url']}, "
         f"{data['emcomm_channel']})"),
        "  - on Debian: enable trixie-backports, pinned to hamlib/WSJT-X/Direwolf only",
        f"  - install toolsets: {toolsets} (may upgrade those distro packages)",
        "  - install and enable chrony (time sync, needed for FT8/JS8)",
        f"  - add {users} to the radio groups (dialout, audio, ...)",
        "  - install emcomm systemd user units (not enabled)",
        "Undo with: sudo emcomm uninstall",
    ])


def cmd_bootstrap(args: argparse.Namespace, paths: Paths) -> int:
    if not args.repo_url:
        raise ProfileError("set --repo-url or EMCOMM_REPO_URL")
    if os.geteuid() != 0 and not args.check:
        raise ProfileError("bootstrap changes system configuration; run it with sudo")
    users = args.user or [os.environ.get("SUDO_USER") or getpass.getuser()]
    users = [u for u in users if u != "root"]
    data = bootstrap_vars(args.repo_url, args.channel, args.toolsets, users,
                          parse_overrides(args.overrides))
    print(_summary(data))
    if not args.yes and input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
        print("aborted; nothing was changed")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        vars_file = Path(tmp) / "vars.json"
        vars_file.write_text(json.dumps(data))
        env = {**os.environ, "ANSIBLE_COLLECTIONS_PATH": str(paths.ansible_dir)}
        result = subprocess.run(playbook_command(paths, vars_file, args.check), env=env,
                                check=False)
    return result.returncode
