"""Run recipe builds inside pristine distro containers."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .model import ExtraRepo, Recipe, Target


@dataclass(frozen=True)
class Engine:
    command: str = "podman"


def engine_from_env() -> Engine:
    return Engine(os.environ.get("EMCOMM_CONTAINER_ENGINE", "podman"))


def build_deps(recipe: Recipe, target: Target) -> list[str]:
    return [*target.base_build_deps, *recipe.deps_for(target.family).build]


def build_command(
    engine: Engine, recipe: Recipe, target: Target, root: Path, workdir: Path
) -> list[str]:
    return [
        engine.command, "run", "--rm",
        "-v", f"{root}:/emcomm:ro,z",
        "-v", f"{workdir}:/work:z",
        "-e", f"FAMILY={target.family}",
        "-e", f"BUILD_DEPS={' '.join(build_deps(recipe, target))}",
        "-e", f"RECIPE_DIR=/emcomm/recipes/{recipe.name}",
        "-e", f"VERSION={recipe.version}",
        target.image, "bash", "/emcomm/tools/container/build.sh",
    ]


def pin_text(repo: ExtraRepo) -> str:
    suite = next(line.split(":", 1)[1].strip() for line in repo.deb822.splitlines()
                 if line.startswith("Suites:"))
    return (f"Package: {' '.join(repo.pin_packages)}\n"
            f"Pin: release n={suite}\n"
            f"Pin-Priority: {repo.pin_priority}\n")


def write_repo_files(target: Target, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for repo in target.extra_repos:
        (dest / f"{repo.name}.sources").write_text(repo.deb822)
        (dest / f"{repo.name}.pref").write_text(pin_text(repo))


def run_build(
    engine: Engine,
    recipe: Recipe,
    target: Target,
    root: Path,
    workdir: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[Path, list[str]]:
    destdir = workdir / "destdir"
    if destdir.exists():
        shutil.rmtree(destdir)
    destdir.mkdir(parents=True)
    deps_file = workdir / "runtime-deps.txt"
    deps_file.unlink(missing_ok=True)
    write_repo_files(target, workdir / "repos")
    run(build_command(engine, recipe, target, root, workdir), check=True)
    if not deps_file.exists():
        raise RuntimeError(
            f"container build for {recipe.name} on {target.name} did not write {deps_file}"
        )
    runtime = [line.strip() for line in deps_file.read_text().splitlines() if line.strip()]
    return destdir, runtime
