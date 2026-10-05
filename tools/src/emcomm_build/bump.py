"""Rewrite recipe.yaml version fields in place, keeping comments and layout."""

from __future__ import annotations

import re
import urllib.error
from collections.abc import Callable
from pathlib import Path

import yaml

from .model import DefinitionError, Recipe, load_recipes
from .net import asset_url, download_sha256


def _sub_line(text: str, pattern: str, replacement: str, path: Path) -> str:
    new, n = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise DefinitionError(f"{path}: no line matching {pattern!r}")
    return new


def set_version(path: Path, version: str, sha256: str | None) -> None:
    text = path.read_text()
    text = _sub_line(text, r"^version:.*$", f'version: "{version}"', path)
    text = _sub_line(text, r"^release:.*$", "release: 1", path)
    if sha256 is not None:
        if re.search(r"^  sha256:.*$", text, re.MULTILINE):
            text = _sub_line(text, r"^  sha256:.*$", f"  sha256: {sha256}", path)
        else:
            m = re.search(r"^  asset:.*$", text, re.MULTILINE)
            if not m:
                raise DefinitionError(f"{path}: source.asset line not found")
            text = text[: m.end()] + f"\n  sha256: {sha256}" + text[m.end():]
    path.write_text(text)


def increment_release(path: Path) -> None:
    text = path.read_text()
    m = re.search(r"^release:\s*(\d+)\s*$", text, re.MULTILINE)
    if not m:
        raise DefinitionError(f"{path}: no release line")
    path.write_text(text[: m.start()] + f"release: {int(m.group(1)) + 1}" + text[m.end():])


def dependents(recipes: dict[str, Recipe], name: str) -> list[str]:
    """Recipes that transitively build against `name` (depends_on edges only)."""
    found: set[str] = set()
    frontier = [name]
    while frontier:
        current = frontier.pop()
        for r in recipes.values():
            if current in r.depends_on and r.name not in found:
                found.add(r.name)
                frontier.append(r.name)
    return sorted(found)


def _longest_depends_chain(recipes: dict[str, Recipe], name: str) -> int:
    """Compute the longest chain of depends_on edges from this recipe."""
    r = recipes.get(name)
    if not r or not r.depends_on:
        return 0
    return 1 + max((_longest_depends_chain(recipes, dep) for dep in r.depends_on), default=0)


def bump_order(recipes: dict[str, Recipe], names: list[str]) -> list[str]:
    """Sort names so a recipe precedes recipes that depend_on it.

    Sort by depth (longest depends_on chain) ascending, then name.
    """
    return sorted(names, key=lambda n: (_longest_depends_chain(recipes, n), n))


def bump(
    root: Path, name: str, version: str, *, sha_for: Callable[[str], str] = download_sha256
) -> list[str]:
    path = root / "recipes" / name / "recipe.yaml"
    raw = yaml.safe_load(path.read_text())
    src = raw.get("source", {})
    sha = None
    sums_text = None

    # Compute all checksums BEFORE writing anything
    try:
        if src.get("type") == "github-release-asset":
            url = asset_url(src["repo"], src.get("ref", "{version}"), src["asset"], version)
            sha = sha_for(url)
        elif src.get("type") == "arch-url":
            lines = []
            for arch in sorted(src["urls"]):
                url = src["urls"][arch].format(version=version)
                lines.append(f"{sha_for(url)}  {url.rsplit('/', 1)[-1]}")
            sums_text = "\n".join(lines) + "\n"
    except (urllib.error.URLError, OSError) as exc:
        raise DefinitionError(f"{name}: download failed: {exc}") from exc

    # Now write everything
    set_version(path, version, sha)
    if sums_text is not None:
        (path.parent / "SHA256SUMS").write_text(sums_text)
    deps = dependents(load_recipes(root), name)
    for dep in deps:
        increment_release(root / "recipes" / dep / "recipe.yaml")
    return [name, *deps]
