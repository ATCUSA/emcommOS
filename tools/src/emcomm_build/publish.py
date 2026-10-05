"""Assemble and sign the static package repository tree for one channel."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .container import Engine
from .model import ARCHES, RPM_ARCH, DefinitionError, Target
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
                if dest.exists():
                    continue  # published files are immutable; never re-copy or re-sign
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
        PUBLISH_IMAGE, "bash", "/emcomm/tools/container/publish.sh",
    ]


def primary_fingerprint(key_file: Path) -> str:
    """Fingerprint of the first primary key in an armored key file (public or secret)."""
    with tempfile.TemporaryDirectory() as home:
        out = subprocess.run(
            ["gpg", "--batch", "--homedir", home, "--show-keys", "--with-colons", str(key_file)],
            check=True, capture_output=True, text=True,
        ).stdout
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line.split(":")[0] in ("pub", "sec"):
            for nxt in lines[i + 1:]:
                if nxt.startswith("fpr:"):
                    return nxt.split(":")[9]
    raise DefinitionError(f"no key found in {key_file}")


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
    root, dist, repo = root.resolve(), dist.resolve(), repo.resolve()
    key_file, passphrase_file = key_file.resolve(), passphrase_file.resolve()
    public_key = public_key.resolve()
    if primary_fingerprint(public_key) != primary_fingerprint(key_file):
        raise DefinitionError(
            f"public key {public_key} does not match the signing key {key_file} "
            "(different primary fingerprint)"
        )
    repo.mkdir(parents=True, exist_ok=True)
    place_packages(dist, repo, targets)
    run(publish_command(engine, root, repo, targets, key_file, passphrase_file), check=True)
    shutil.copy2(public_key, repo / "emcomm-archive-keyring.asc")
    write_manifests(repo, targets)
