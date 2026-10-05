"""Fetch recipe sources into a work directory."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

from .model import Recipe
from .net import asset_url, download, sha256_file

IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".venv", ".pytest_cache",
                                ".ruff_cache", "dist", "build")


class FetchError(Exception):
    """Source could not be fetched or failed verification."""


def extract_tarball(archive: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        with tarfile.open(archive) as tf:
            tf.extractall(tmp, filter="data")
        entries = list(Path(tmp).iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            shutil.move(str(entries[0]), dest)
        else:
            dest.mkdir()
            for entry in entries:
                shutil.move(str(entry), dest / entry.name)


def _sidecar_sums(recipe_dir: Path) -> dict[str, str]:
    sums = {}
    for line in (recipe_dir / "SHA256SUMS").read_text().splitlines():
        if line.strip():
            sha, name = line.split(maxsplit=1)
            sums[name.strip()] = sha
    return sums


def fetch_source(
    recipe: Recipe,
    workdir: Path,
    root: Path,
    cache: Path,
    *,
    arch: str | None = None,
    download_fn: Callable[[str, Path], str] = download,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    src = workdir / "src"
    if src.exists():
        shutil.rmtree(src)
    workdir.mkdir(parents=True, exist_ok=True)
    s = recipe.source

    if s.type == "none":
        src.mkdir()
    elif s.type == "local":
        src.mkdir()
        for p in s.paths:
            if (root / p).is_dir():
                shutil.copytree(root / p, src / Path(p).name, ignore=IGNORE)
            else:
                shutil.copy2(root / p, src / Path(p).name)
    elif s.type == "arch-url":
        if arch is None:
            raise FetchError(f"{recipe.name}: arch-url sources need the target architecture")
        url = s.url_for(arch, recipe.version)
        name = url.rsplit("/", 1)[-1]
        expected = _sidecar_sums(recipe.dir).get(name)
        if expected is None:
            raise FetchError(f"{recipe.name}: {name} missing from SHA256SUMS; run emcomm-build bump")
        cache.mkdir(parents=True, exist_ok=True)
        cached = cache / f"{recipe.name}-{name}"
        got = sha256_file(cached) if cached.exists() else None
        if got != expected:
            got = download_fn(url, cached)
        if got != expected:
            cached.unlink(missing_ok=True)
            raise FetchError(f"{recipe.name}: sha256 mismatch for {url}: expected {expected}, got {got}")
        src.mkdir()
        shutil.copy2(cached, src / name)  # build.sh unpacks/installs the upstream artifact
    elif s.type == "git":
        run(["git", "clone", "--quiet", "--depth", "1", "--branch",
             s.resolved_ref(recipe.version), s.url, str(src)], check=True)
    elif s.type == "github-release-asset":
        url = asset_url(s.repo, s.ref or "{version}", s.asset, recipe.version)
        cache.mkdir(parents=True, exist_ok=True)
        archive = cache / f"{recipe.name}-{recipe.version}-{url.rsplit('/', 1)[-1]}"
        got = sha256_file(archive) if archive.exists() else None
        if got != s.sha256:
            got = download_fn(url, archive)
        if got != s.sha256:
            archive.unlink(missing_ok=True)
            raise FetchError(
                f"{recipe.name}: sha256 mismatch for {url}: expected {s.sha256}, got {got}"
            )
        extract_tarball(archive, src)
    else:
        raise FetchError(f"{recipe.name}: unknown source type {s.type!r}")
    return src
