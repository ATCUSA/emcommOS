import hashlib
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from emcomm_build.fetch import FetchError, extract_tarball, fetch_source
from emcomm_build.model import Recipe, Source


def recipe(source: Source, version: str = "1.2.3") -> Recipe:
    return Recipe(name="demo", kind="app", summary="s", license="MIT", version=version,
                  release=1, dir=Path("."), source=source)


def make_tarball(tmp_path: Path) -> Path:
    top = tmp_path / "pkg" / "demo-1.2.3"
    top.mkdir(parents=True)
    (top / "configure").write_text("#!/bin/sh\n")
    archive = tmp_path / "demo-1.2.3.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(top, arcname="demo-1.2.3")
    return archive


def test_extract_strips_top_dir(tmp_path):
    dest = tmp_path / "out"
    extract_tarball(make_tarball(tmp_path), dest)
    assert (dest / "configure").is_file()


def test_asset_download_verifies_sha(tmp_path):
    archive = make_tarball(tmp_path)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    urls = []

    def fake_download(url, dest):
        urls.append(url)
        shutil.copy(archive, dest)
        return sha

    src = Source(type="github-release-asset", repo="o/r", asset="demo-{version}.tar.gz", sha256=sha)
    out = fetch_source(recipe(src), tmp_path / "work", tmp_path, tmp_path / "cache",
                       download_fn=fake_download)
    assert (out / "configure").is_file()
    assert urls == ["https://github.com/o/r/releases/download/1.2.3/demo-1.2.3.tar.gz"]
    # cached: second fetch does not download again
    fetch_source(recipe(src), tmp_path / "work", tmp_path, tmp_path / "cache",
                 download_fn=fake_download)
    assert len(urls) == 1


def test_asset_sha_mismatch(tmp_path):
    archive = make_tarball(tmp_path)

    def fake_download(url, dest):
        shutil.copy(archive, dest)
        return "0" * 64

    src = Source(type="github-release-asset", repo="o/r", asset="a.tgz", sha256="f" * 64)
    with pytest.raises(FetchError, match="sha256 mismatch"):
        fetch_source(recipe(src), tmp_path / "w", tmp_path, tmp_path / "c", download_fn=fake_download)


def test_local_copies_paths(tmp_path):
    (tmp_path / "cli" / "src").mkdir(parents=True)
    (tmp_path / "cli" / "src" / "x.py").write_text("x")
    (tmp_path / "cli" / "__pycache__").mkdir()
    out = fetch_source(recipe(Source(type="local", paths=("cli",))), tmp_path / "w", tmp_path,
                       tmp_path / "c")
    assert (out / "cli" / "src" / "x.py").is_file()
    assert not (out / "cli" / "__pycache__").exists()


def test_arch_url_verifies_sidecar(tmp_path):
    rdir = tmp_path / "recipe"
    rdir.mkdir()
    payload = tmp_path / "payload"
    payload.write_bytes(b"binary")
    sha = hashlib.sha256(b"binary").hexdigest()
    (rdir / "SHA256SUMS").write_text(f"{sha}  pat_1.2.3_arm64.tgz\n")
    src = Source(type="arch-url", urls=(("amd64", "https://x/pat_{version}_amd64.tgz"),
                                         ("arm64", "https://x/pat_{version}_arm64.tgz")))
    r = Recipe(name="pat", kind="app", summary="s", license="MIT", version="1.2.3", release=1,
               dir=rdir, source=src)

    def fake_download(url, dest):
        shutil.copy(payload, dest)
        return sha

    out = fetch_source(r, tmp_path / "w", tmp_path, tmp_path / "c", arch="arm64",
                       download_fn=fake_download)
    assert (out / "pat_1.2.3_arm64.tgz").read_bytes() == b"binary"
    with pytest.raises(FetchError, match="missing from SHA256SUMS"):
        fetch_source(r, tmp_path / "w", tmp_path, tmp_path / "c", arch="amd64",
                     download_fn=fake_download)


def test_git_clone_at_tag(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git = ["git", "-C", str(origin), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(origin)], check=True)
    (origin / "README").write_text("v1")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    subprocess.run([*git, "tag", "v1.2.3"], check=True)
    src = Source(type="git", url=f"file://{origin}", ref="v{version}")
    out = fetch_source(recipe(src), tmp_path / "w", tmp_path, tmp_path / "c")
    assert (out / "README").read_text() == "v1"
