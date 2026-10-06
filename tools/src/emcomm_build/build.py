"""Orchestrate fetch → container build → package → smoke for one target/arch."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .container import Engine, run_build, write_repo_files
from .fetch import fetch_source
from .model import Recipe, Target, load_recipes
from .net import download
from .package import build_package, nfpm_config
from .plan import (
    closure,
    fetch_manifest,
    package_filename,
    plan_builds,
    published_files,
    recipes_for_target,
)


class BuildError(Exception):
    """A build could not be completed."""


PREFIX = "/opt/emcomm"
# The only files a package may place outside /opt/emcomm (global constraints).
ALLOWED_OUTSIDE = frozenset({"/etc/profile.d/emcomm.sh", "/usr/lib/environment.d/50-emcomm.conf"})
ALLOWED_OUTSIDE_BY_RECIPE = {"cli": frozenset({"/usr/bin/emcomm"})}


def check_package_paths(recipe: Recipe, contents: list[dict]) -> None:
    """Refuse to package anything outside /opt/emcomm except the allowed files."""
    allowed = ALLOWED_OUTSIDE | ALLOWED_OUTSIDE_BY_RECIPE.get(recipe.name, frozenset())
    for entry in contents:
        dst = entry["dst"]
        parts = dst.split("/")
        if ".." in parts or "." in parts or "" in parts[1:]:
            raise BuildError(f"{recipe.package}: refusing non-normalized package path {dst}")
        if dst == PREFIX or dst.startswith(PREFIX + "/") or dst in allowed:
            continue
        raise BuildError(
            f"{recipe.package}: refusing to package {dst}: everything must live under {PREFIX} "
            f"(allowed outside: {', '.join(sorted(allowed))})")


@dataclass(frozen=True)
class BuildSettings:
    root: Path
    target: Target
    arch: str
    out: Path
    work: Path
    repo_url: str | None
    channel: str = "testing"
    only: tuple[str, ...] = ()
    force: bool = False
    smoke: bool = True
    engine: Engine = field(default_factory=Engine)


def clean_workdir(workdir: Path) -> None:
    """Remove a previous build directory, explaining how to recover if that is not permitted."""
    if not workdir.exists():
        return
    try:
        shutil.rmtree(workdir)
    except PermissionError as e:
        raise BuildError(
            f"cannot remove {workdir} ({e.filename or e}): it holds files owned by a "
            f"container sub-UID; remove it with `podman unshare rm -rf {workdir}`"
        ) from e


def host_arch() -> str:
    machine = platform.machine()
    try:
        return {"x86_64": "amd64", "aarch64": "arm64"}[machine]
    except KeyError:
        raise BuildError(f"unsupported host architecture {machine}") from None


def stage(
    recipes: dict[str, Recipe],
    names: list[str],
    settings: BuildSettings,
    manifest: dict | None,
    dest: Path,
) -> list[Path]:
    """Put the packages for names (and everything they need) into dest."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    by_name = {p.rsplit("/", 1)[-1]: p for p in (manifest or {}).get("files", [])}
    staged = []
    for name in sorted(closure(recipes, names)):
        filename = package_filename(recipes[name], settings.target, settings.arch)
        local = settings.out / filename
        target_file = dest / filename
        if local.exists():
            shutil.copy2(local, target_file)
        elif filename in by_name and settings.repo_url:
            url = f"{settings.repo_url.rstrip('/')}/{settings.channel}/{by_name[filename]}"
            download(url, target_file)
        else:
            raise BuildError(f"{recipes[name].package}: {filename} is neither built nor published")
        staged.append(target_file)
    return staged


def smoke(
    recipes: dict[str, Recipe], names: list[str], settings: BuildSettings, manifest: dict | None
) -> None:
    workdir = settings.work / settings.target.name / settings.arch / "_smoke"
    staged = stage(recipes, names, settings, manifest, workdir / "pkgs")
    write_repo_files(settings.target, workdir / "repos")
    skip = " ".join(f"/opt/emcomm/{r.bundle_dir}" for r in recipes.values()
                    if r.bundle_dir and any(p.name.startswith(r.package) for p in staged))
    subprocess.run(
        [
            settings.engine.command, "run", "--rm",
            "-v", f"{settings.root}:/emcomm:ro,z",
            "-v", f"{workdir}:/work:z",
            "-e", f"FAMILY={settings.target.family}",
            "-e", f"SMOKE_RECIPES={' '.join(names)}",
            "-e", f"SMOKE_SKIP_PATHS={skip}",
            settings.target.image, "bash", "/emcomm/tools/container/smoke.sh",
        ],
        check=True,
    )


def run(settings: BuildSettings, *, recipes: dict[str, Recipe] | None = None) -> list[Path]:
    target, arch = settings.target, settings.arch
    recipes = recipes_for_target(recipes or load_recipes(settings.root), target)
    manifest = (
        fetch_manifest(settings.repo_url, settings.channel, target.name, arch)
        if settings.repo_url
        else None
    )
    published = published_files(manifest)
    todo = plan_builds(recipes, target, arch, published, settings.only, settings.force)
    if not todo:
        print(f"{target.name}/{arch}: everything is already published")
        return []

    settings.out.mkdir(parents=True, exist_ok=True)
    built: list[Path] = []
    for name in todo:
        r = recipes[name]
        print(f"==> {target.name}/{arch}: {r.package} {r.version}-{r.release}")
        workdir = settings.work / target.name / arch / name
        clean_workdir(workdir)
        workdir.mkdir(parents=True)
        deps = [*r.depends_on, *r.requires]
        if deps:
            stage(recipes, deps, settings, manifest, workdir / "deps")
        else:
            (workdir / "deps").mkdir()

        if r.kind == "app":
            fetch_source(r, workdir, settings.root, settings.work / "cache", arch=arch)
            tree, runtime = run_build(settings.engine, r, target, settings.root, workdir)
        elif r.kind == "files":
            tree, runtime = r.dir / r.files_dir, []
        else:
            tree, runtime = None, []

        cfg = nfpm_config(r, target, arch, recipes, tree, runtime)
        check_package_paths(r, cfg["contents"])
        out = settings.out / package_filename(r, target, arch)
        built.append(build_package(cfg, target.format, out, workdir))

    if settings.smoke:
        smoke(recipes, todo, settings, manifest)
    return built
