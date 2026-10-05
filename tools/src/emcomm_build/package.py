"""Turn a built tree into .deb/.rpm packages with nFPM."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml

from .model import Recipe, Target
from .plan import full_release

MAINTAINER = "emcommOS maintainers <maintainers@emcommos.invalid>"


def depends_list(
    recipe: Recipe, target: Target, recipes: dict[str, Recipe], runtime_deps: list[str]
) -> list[str]:
    deps = set(runtime_deps) | set(recipe.deps_for(target.family).run)
    deps |= {recipes[d].package for d in (*recipe.depends_on, *recipe.requires)}
    if recipe.name != "base" and "base" in recipes:
        deps.add(recipes["base"].package)
    return sorted(deps)


def content_entries(tree: Path) -> list[dict]:
    entries: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(tree):
        here = Path(dirpath)
        names = [d for d in dirnames if (here / d).is_symlink()] + filenames
        for name in sorted(names):
            path = here / name
            dst = "/" + path.relative_to(tree).as_posix()
            if path.is_symlink():
                entries.append({"src": os.readlink(path), "dst": dst, "type": "symlink"})
            else:
                entry = {"src": str(path), "dst": dst,
                         "file_info": {"mode": path.stat().st_mode & 0o7777}}
                if dst.startswith("/etc/"):
                    entry["type"] = "config|noreplace"
                entries.append(entry)
    return sorted(entries, key=lambda e: e["dst"])


def nfpm_config(
    recipe: Recipe,
    target: Target,
    arch: str,
    recipes: dict[str, Recipe],
    tree: Path | None,
    runtime_deps: list[str],
) -> dict:
    cfg: dict = {
        "name": recipe.package,
        "arch": arch,
        "platform": "linux",
        "version": recipe.version,
        "version_schema": "none",
        "release": full_release(recipe, target),
        "maintainer": MAINTAINER,
        "description": recipe.description or recipe.summary,
        "vendor": "emcommOS",
        "license": recipe.license,
        "depends": depends_list(recipe, target, recipes, runtime_deps),
        "contents": content_entries(tree) if tree else [],
    }
    if recipe.homepage:
        cfg["homepage"] = recipe.homepage
    if target.format == "rpm":
        cfg["rpm"] = {"summary": recipe.summary}
    return cfg


def build_package(
    cfg: dict,
    fmt: str,
    out: Path,
    workdir: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    cfg_path = workdir / f"nfpm-{fmt}.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["nfpm", "package", "--config", str(cfg_path), "--packager", fmt, "--target", str(out)],
        check=True)
    return out
