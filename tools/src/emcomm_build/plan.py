"""Build ordering, package file naming and what-needs-building decisions."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import replace
from graphlib import CycleError, TopologicalSorter

from .model import RPM_ARCH, DefinitionError, Recipe, Target


def _edges(recipes: dict[str, Recipe], name: str) -> set[str]:
    r = recipes[name]
    deps = {*r.depends_on, *r.requires}
    if name != "base" and "base" in recipes:
        deps.add("base")
    return deps


def build_order(recipes: dict[str, Recipe]) -> list[str]:
    ts: TopologicalSorter[str] = TopologicalSorter()
    for name in sorted(recipes):
        ts.add(name, *sorted(_edges(recipes, name)))
    try:
        ts.prepare()
    except CycleError as exc:
        raise DefinitionError(f"dependency cycle: {' -> '.join(exc.args[1])}") from None
    order: list[str] = []
    while ts.is_active():
        ready = sorted(ts.get_ready())
        order.extend(ready)
        ts.done(*ready)
    return order


def recipes_for_target(recipes: dict[str, Recipe], target: Target) -> dict[str, Recipe]:
    keep = {n for n, r in recipes.items() if r.applies_to(target.family)}
    return {
        n: replace(r, depends_on=tuple(d for d in r.depends_on if d in keep),
                   requires=tuple(d for d in r.requires if d in keep))
        for n, r in recipes.items()
        if n in keep
    }


def closure(recipes: dict[str, Recipe], names: Iterable[str]) -> set[str]:
    found: set[str] = set()
    frontier = list(names)
    while frontier:
        n = frontier.pop()
        if n not in found:
            found.add(n)
            frontier.extend(_edges(recipes, n))
    return found


def full_release(recipe: Recipe, target: Target) -> str:
    sep = "+" if target.format == "deb" else "."
    return f"{recipe.release}{sep}{target.dist_tag}"


def package_filename(recipe: Recipe, target: Target, arch: str) -> str:
    rel = full_release(recipe, target)
    if target.format == "deb":
        return f"{recipe.package}_{recipe.version}-{rel}_{arch}.deb"
    if target.format == "rpm":
        return f"{recipe.package}-{recipe.version}-{rel}.{RPM_ARCH[arch]}.rpm"
    raise DefinitionError(f"unsupported package format {target.format!r}")


def repo_path(target: Target, arch: str, filename: str) -> str:
    if target.format == "deb":
        return f"deb/pool/{target.name}/{filename}"
    return f"rpm/{target.name}/{RPM_ARCH[arch]}/{filename}"


def published_files(manifest: dict | None) -> set[str]:
    if not manifest:
        return set()
    return {p.rsplit("/", 1)[-1] for p in manifest.get("files", [])}


def plan_builds(
    recipes: dict[str, Recipe],
    target: Target,
    arch: str,
    published: set[str],
    only: Iterable[str] = (),
    force: bool = False,
) -> list[str]:
    only = list(only)
    selected = closure(recipes, only) if only else set(recipes)
    forced = (set(only) if only else set(recipes)) if force else set()
    return [
        n
        for n in build_order(recipes)
        if n in selected
        and (n in forced or package_filename(recipes[n], target, arch) not in published)
    ]


def fetch_manifest(
    repo_url: str,
    channel: str,
    target: str,
    arch: str,
    *,
    opener: Callable = urllib.request.urlopen,
) -> dict | None:
    url = f"{repo_url.rstrip('/')}/{channel}/manifest/{target}-{arch}.json"
    try:
        with opener(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):  # R2 returns 403/404 for missing public objects
            return None
        raise
