"""Find the newest upstream release tag for a recipe."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from collections.abc import Callable, Iterable

from .model import Upstream


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version))


def is_newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


def pick_latest(tags: Iterable[str], pattern: str) -> str | None:
    r"""Return the highest version among tags that fully match pattern (group 1 = version).

    Excludes release candidates and pre-release versions that don't match \d+(\.\d+)*.
    """
    rx = re.compile(pattern)
    versions = [
        m.group(1)
        for t in tags
        if (m := rx.fullmatch(t)) and re.fullmatch(r"\d+(\.\d+)*", m.group(1))
    ]
    return max(versions, key=version_key, default=None)


def _http_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def list_tags(
    up: Upstream,
    *,
    http_json: Callable[[str], object] = _http_json,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[str]:
    if up.type == "github-releases":
        releases = http_json(f"https://api.github.com/repos/{up.repo}/releases?per_page=100")
        return [r["tag_name"] for r in releases if not r["draft"] and not r["prerelease"]]
    if up.type == "git-tags":
        out = run(
            ["git", "ls-remote", "--tags", "--refs", up.url],
            check=True, capture_output=True, text=True,
        ).stdout
        return [line.split("refs/tags/", 1)[1] for line in out.splitlines() if "refs/tags/" in line]
    raise ValueError(f"unknown upstream type {up.type!r}")
