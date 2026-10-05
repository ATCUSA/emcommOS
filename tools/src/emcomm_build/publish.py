"""Assemble and sign the static package repository tree for one channel."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .container import Engine
from .model import ARCHES, RPM_ARCH, Target
from .plan import repo_path

PUBLISH_IMAGE = "docker.io/library/debian:13"
DEFAULT_ENGINE = Engine()


def place_packages(
    dist: Path, repo: Path, targets: dict[str, Target]
) -> dict[tuple[str, str], list[Path]]:
    placed: dict[tuple[str, str], list[Path]] = {}
    for tdir in sorted(p for p in dist.iterdir() if p.is_dir()):
        target = targets[tdir.name]
        for adir in sorted(p for p in tdir.iterdir() if p.is_dir()):
            for pkg in sorted(adir.glob(f"*.{target.format}")):
                dest = repo / repo_path(target, adir.name, pkg.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pkg, dest)
                placed.setdefault((target.name, adir.name), []).append(dest)
    return placed


def write_manifests(repo: Path, targets: dict[str, Target]) -> None:
    for t in targets.values():
        for arch in ARCHES:
            if t.format == "deb":
                files = sorted(repo.glob(f"deb/pool/{t.name}/*_{arch}.deb"))
            else:
                files = sorted(repo.glob(f"rpm/{t.name}/{RPM_ARCH[arch]}/*.rpm"))
            if not files:
                continue
            manifest = {"target": t.name, "arch": arch,
                        "files": [f.relative_to(repo).as_posix() for f in files]}
            out = repo / "manifest" / f"{t.name}-{arch}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(manifest, indent=2) + "\n")


def publish_command(
    engine: Engine,
    root: Path,
    repo: Path,
    targets: dict[str, Target],
    new_rpms: list[str],
    key_file: Path,
    passphrase_file: Path,
) -> list[str]:
    deb_suites = sorted(
        t.name for t in targets.values()
        if t.format == "deb" and (repo / "deb/pool" / t.name).is_dir()
    )
    rpm_dirs = sorted(p.relative_to(repo).as_posix() for p in repo.glob("rpm/*/*") if p.is_dir())
    return [
        engine.command, "run", "--rm",
        "-v", f"{root}:/emcomm:ro,z",
        "-v", f"{repo}:/repo:z",
        "-v", f"{key_file}:/keys/signing.asc:ro,z",
        "-v", f"{passphrase_file}:/keys/passphrase:ro,z",
        "-e", f"DEB_SUITES={' '.join(deb_suites)}",
        "-e", f"RPM_DIRS={' '.join(rpm_dirs)}",
        "-e", f"NEW_RPMS={' '.join(new_rpms)}",
        PUBLISH_IMAGE, "bash", "/emcomm/tools/container/publish.sh",
    ]


def publish(
    root: Path,
    dist: Path,
    repo: Path,
    targets: dict[str, Target],
    key_file: Path,
    passphrase_file: Path,
    public_key: Path,
    *,
    engine: Engine = DEFAULT_ENGINE,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    placed = place_packages(dist, repo, targets)
    new_rpms = [p.relative_to(repo).as_posix()
                for files in placed.values() for p in files if p.suffix == ".rpm"]
    run(publish_command(engine, root, repo, targets, new_rpms, key_file, passphrase_file),
        check=True)
    shutil.copy2(public_key, repo / "emcomm-archive-keyring.asc")
    write_manifests(repo, targets)
