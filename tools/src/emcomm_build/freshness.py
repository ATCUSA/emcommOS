"""Compare upstream releases with Debian/Fedora package versions."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

import yaml

from .model import Upstream
from .upstream import list_tags, pick_latest

SUITES = ("trixie", "trixie-backports")
FEDORA = (43, 44)


def _safe(fn: Callable, default, source: str = "") -> object:
    """Call fn safely, catching errors and returning default. Logs to stderr if source given."""
    try:
        return fn()
    except (OSError, ValueError, KeyError, LookupError, subprocess.CalledProcessError) as exc:
        if source:
            print(f"warning: {source}: {exc}", file=sys.stderr)
        return default


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _upstream_version(raw: str) -> str:
    """Strip Debian/Fedora packaging decorations: epoch, +repack, ~bpo, -revision."""
    v = raw.split(":", 1)[-1]
    v = v.rsplit("-", 1)[0] if "-" in v else v
    return re.split(r"[+~]", v, maxsplit=1)[0]


def debian_versions(pkg: str, *, http_text: Callable[[str], str] | None = None) -> dict[str, str]:
    url = "https://qa.debian.org/madison.php?text=on&package=" + urllib.parse.quote(pkg)
    text = http_text(url) if http_text else _get(url).decode()
    versions: dict[str, str] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            versions.setdefault(parts[2], _upstream_version(parts[1]))
    return versions


def fedora_version(pkg: str, release: int, *,
                   http_json: Callable[[str], dict] | None = None) -> str | None:
    url = f"https://mdapi.fedoraproject.org/f{release}/pkg/{urllib.parse.quote(pkg)}"
    def fetch() -> dict:
        if http_json:
            data = http_json(url)
        else:
            data = json.loads(_get(url))
        return data
    data = _safe(fetch, None)
    if data is None:
        return None
    return data.get("version")


def load_entries(root: Path) -> dict[str, dict]:
    data = yaml.safe_load((root / "freshness.yaml").read_text())
    return {name: {**e, "upstream": Upstream(**e["upstream"])} for name, e in data["apps"].items()}


def report(entries: dict[str, dict], *, tags=list_tags, deb=debian_versions,
           fed=fedora_version) -> list[dict]:
    rows = []
    for name, e in entries.items():
        # Upstream tags lookup
        latest = _safe(
            lambda e=e: pick_latest(tags(e["upstream"]), e["upstream"].tag_pattern) or "?",
            "?",
            source=f"{name} upstream"
        )
        row = {"app": name, "upstream": latest}

        # Debian versions lookup
        dv_result = _safe(
            lambda e=e: deb(e["debian"]) if e.get("debian") else {},
            None,
            source=f"{name} debian" if e.get("debian") else ""
        )
        dv = dv_result if dv_result is not None else {}
        dv_failed = dv_result is None and e.get("debian")
        for suite in SUITES:
            if dv_failed:
                row[suite] = "?"
            else:
                row[suite] = dv.get(suite, "-")

        # Fedora versions lookup
        for rel in FEDORA:
            v = None
            if e.get("fedora"):
                v = _safe(
                    lambda e=e, rel=rel: fed(e["fedora"], rel),
                    "?",
                    source=f"{name} fedora-{rel}"
                )
            row[f"f{rel}"] = v if e.get("fedora") else "-"

        # Mark rows where distro matches upstream
        for key in (*SUITES, *(f"f{r}" for r in FEDORA)):
            if row[key] == latest:
                row[key] = f"={latest}"
        rows.append(row)
    return rows
