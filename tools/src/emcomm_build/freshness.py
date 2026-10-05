"""Compare upstream releases with Debian/Fedora package versions."""

from __future__ import annotations

import json
import re
import subprocess
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
    try:
        data = http_json(url) if http_json else json.loads(_get(url))
    except (LookupError, urllib.error.HTTPError):
        return None
    return data.get("version")


def load_entries(root: Path) -> dict[str, dict]:
    data = yaml.safe_load((root / "freshness.yaml").read_text())
    return {name: {**e, "upstream": Upstream(**e["upstream"])} for name, e in data["apps"].items()}


def report(entries: dict[str, dict], *, tags=list_tags, deb=debian_versions,
           fed=fedora_version) -> list[dict]:
    rows = []
    for name, e in entries.items():
        try:
            latest = pick_latest(tags(e["upstream"]), e["upstream"].tag_pattern) or "?"
        except (urllib.error.URLError, TimeoutError, subprocess.CalledProcessError, OSError):
            latest = "?"
        row = {"app": name, "upstream": latest}
        dv = {}
        if e.get("debian"):
            try:
                dv = deb(e["debian"])
            except (urllib.error.URLError, TimeoutError, OSError):
                dv = {}
        for suite in SUITES:
            row[suite] = dv.get(suite, "-")
        for rel in FEDORA:
            v = None
            if e.get("fedora"):
                try:
                    v = fed(e["fedora"], rel)
                except (urllib.error.URLError, TimeoutError, OSError):
                    v = None
            row[f"f{rel}"] = v or "-"
        for key in (*SUITES, *(f"f{r}" for r in FEDORA)):
            if row[key] == latest:
                row[key] = f"={latest}"
        rows.append(row)
    return rows
