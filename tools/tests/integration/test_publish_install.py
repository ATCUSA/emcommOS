import platform
import shutil
import subprocess

import pytest
from conftest import REAL_ROOT

from emcomm_build.build import host_arch
from emcomm_build.model import Recipe, load_targets
from emcomm_build.package import build_package, nfpm_config
from emcomm_build.plan import package_filename
from emcomm_build.publish import publish

pytestmark = [pytest.mark.container, pytest.mark.nfpm]


PASSPHRASE = "correct horse battery"


def gpg(env, *args, **kw):
    return subprocess.run(["gpg", "--batch", "--pinentry-mode", "loopback",
                           "--passphrase", PASSPHRASE, *args], check=True, env=env,
                          capture_output=True, **kw)


def make_key(tmp_path):
    """Mirror CI: certify-only Ed25519 primary + signing subkey, passphrase, stub primary."""
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(home), "PATH": "/usr/bin:/bin"}
    gpg(env, "--quick-gen-key", "emcomm test", "ed25519", "cert", "never")
    fpr = gpg(env, "--list-keys", "--with-colons").stdout.decode()
    fpr = next(ln.split(":")[9] for ln in fpr.splitlines() if ln.startswith("fpr:"))
    gpg(env, "--quick-add-key", fpr, "ed25519", "sign", "never")
    secret = tmp_path / "secret.asc"
    public = tmp_path / "public.asc"
    secret.write_bytes(gpg(env, "--armor", "--export-secret-subkeys").stdout)
    public.write_bytes(gpg(env, "--armor", "--export").stdout)
    passphrase = tmp_path / "pp"
    passphrase.write_text(PASSPHRASE)
    return secret, public, passphrase


def build_demo(targets, arch, dist, tmp_path, name):
    meta = Recipe(name=name, kind="meta", summary="demo meta", license="MIT", version="1.0",
                  release=1, dir=tmp_path, deps={})
    for t in targets.values():
        cfg = nfpm_config(meta, t, arch, {name: meta}, None, [])
        build_package(cfg, t.format, dist / t.name / arch / package_filename(meta, t, arch),
                      tmp_path / "w")


def install_all(repo, names, deb_names=None):
    dpkgs = " ".join(f"emcomm-{n}" for n in (deb_names or names))
    pkgs = " ".join(f"emcomm-{n}" for n in names)
    debian = (
        "cp /repo/emcomm-archive-keyring.asc /usr/share/keyrings/ && "
        "printf 'Types: deb\\nURIs: file:/repo/deb\\nSuites: debian-13\\nComponents: main\\n"
        "Signed-By: /usr/share/keyrings/emcomm-archive-keyring.asc\\n' "
        "> /etc/apt/sources.list.d/emcomm.sources && apt-get update -qq && "
        f"apt-get install -y -qq {dpkgs} && dpkg -s {dpkgs}"
    )
    fedora = (
        "printf '[emcomm]\\nname=emcomm\\nbaseurl=file:///repo/rpm/fedora-44/$basearch\\n"
        "gpgcheck=1\\nrepo_gpgcheck=1\\ngpgkey=file:///repo/emcomm-archive-keyring.asc\\n' "
        f"> /etc/yum.repos.d/emcomm.repo && dnf -y -q install {pkgs} && rpm -q {pkgs}"
    )
    for image, script in (("docker.io/library/debian:13", debian),
                          ("registry.fedoraproject.org/fedora:44", fedora)):
        subprocess.run(["podman", "run", "--rm", "-v", f"{repo}:/repo:ro,z", image,
                        "bash", "-euc", script], check=True)


def test_publish_then_install(fake_repo, tmp_path):
    for tool in ("podman", "nfpm", "gpg"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not installed")
    if platform.machine() not in ("x86_64", "aarch64"):
        pytest.skip("unsupported host")
    arch = host_arch()
    targets = load_targets(fake_repo)
    dist = tmp_path / "dist"
    (tmp_path / "empty-dist").mkdir()
    build_demo(targets, arch, dist, tmp_path, "demo")
    secret, public, passphrase = make_key(tmp_path)
    repo = tmp_path / "public/testing"
    publish(REAL_ROOT, dist, repo, targets, secret, passphrase, public)
    install_all(repo, ["demo"])

    # Incremental republish: demo is rebuilt (different bytes) but must stay untouched.
    rpm1 = next((repo / "rpm/fedora-44").rglob("*.rpm"))
    before = rpm1.read_bytes()
    dist2 = tmp_path / "dist2"
    build_demo(targets, arch, dist2, tmp_path, "demo")
    build_demo(targets, arch, dist2, tmp_path, "demo2")
    publish(REAL_ROOT, dist2, repo, targets, secret, passphrase, public)
    assert rpm1.read_bytes() == before
    release = (repo / "deb/dists/debian-13/Release").read_text()
    assert not any(ln.split()[-1] in ("Release", "InRelease", "Release.gpg")
                   for ln in release.splitlines() if ln.startswith(" ") and ln.split())
    install_all(repo, ["demo", "demo2"])

    # Simulated partial failure: an unsigned RPM already sits in the tree, unknown to publish.
    dist3 = tmp_path / "dist3"
    build_demo(targets, arch, dist3, tmp_path, "demo3")
    unsigned = next(dist3.rglob("*.rpm"))
    placed_rpm = rpm1.parent / unsigned.name
    shutil.copy2(unsigned, placed_rpm)
    before_signed = rpm1.read_bytes()
    publish(REAL_ROOT, tmp_path / "empty-dist", repo, targets, secret, passphrase, public)
    assert placed_rpm.read_bytes() != unsigned.read_bytes()
    assert rpm1.read_bytes() == before_signed
    install_all(repo, ["demo", "demo2", "demo3"], ["demo", "demo2"])
