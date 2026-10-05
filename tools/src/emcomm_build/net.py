"""HTTP helpers: GitHub asset URLs and hashed downloads."""

from __future__ import annotations

import hashlib
import tempfile
import urllib.request
from pathlib import Path


def asset_url(repo: str, ref_template: str, asset_template: str, version: str) -> str:
    ref = ref_template.format(version=version)
    asset = asset_template.format(version=version)
    return f"https://github.com/{repo}/releases/download/{ref}/{asset}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> str:
    """Download url to dest atomically; return its sha256."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1 << 20):
            h.update(chunk)
            out.write(chunk)
    tmp.replace(dest)
    return h.hexdigest()


def download_sha256(url: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        return download(url, Path(d) / "asset")
