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


def make_key(tmp_path):
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(home), "PATH": "/usr/bin:/bin"}
    subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key",
                    "emcomm test", "ed25519", "sign", "never"], check=True, env=env)
    secret = tmp_path / "secret.asc"
    public = tmp_path / "public.asc"
    secret.write_bytes(subprocess.run(["gpg", "--armor", "--export-secret-keys"], env=env,
                                      check=True, capture_output=True).stdout)
    public.write_bytes(subprocess.run(["gpg", "--armor", "--export"], env=env,
                                      check=True, capture_output=True).stdout)
    passphrase = tmp_path / "pp"
    passphrase.write_text("")
    return secret, public, passphrase


def test_publish_then_install(fake_repo, tmp_path):
    for tool in ("podman", "nfpm", "gpg"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not installed")
    if platform.machine() not in ("x86_64", "aarch64"):
        pytest.skip("unsupported host")
    arch = host_arch()
    targets = load_targets(fake_repo)
    meta = Recipe(name="demo", kind="meta", summary="demo meta", license="MIT", version="1.0",
                  release=1, dir=tmp_path, deps={})
    dist = tmp_path / "dist"
    for t in targets.values():
        cfg = nfpm_config(meta, t, arch, {"demo": meta}, None, [])
        build_package(cfg, t.format, dist / t.name / arch / package_filename(meta, t, arch),
                      tmp_path / "w")
    secret, public, passphrase = make_key(tmp_path)
    repo = tmp_path / "public/testing"
    publish(REAL_ROOT, dist, repo, targets, secret, passphrase, public)

    debian = (
        "cp /repo/emcomm-archive-keyring.asc /usr/share/keyrings/ && "
        "printf 'Types: deb\\nURIs: file:/repo/deb\\nSuites: debian-13\\nComponents: main\\n"
        "Signed-By: /usr/share/keyrings/emcomm-archive-keyring.asc\\n' "
        "> /etc/apt/sources.list.d/emcomm.sources && apt-get update -qq && "
        "apt-get install -y -qq emcomm-demo && dpkg -s emcomm-demo"
    )
    fedora = (
        "printf '[emcomm]\\nname=emcomm\\nbaseurl=file:///repo/rpm/fedora-44/$basearch\\n"
        "gpgcheck=1\\nrepo_gpgcheck=1\\ngpgkey=file:///repo/emcomm-archive-keyring.asc\\n' "
        "> /etc/yum.repos.d/emcomm.repo && dnf -y -q install emcomm-demo && rpm -q emcomm-demo"
    )
    for image, script in (("docker.io/library/debian:13", debian),
                          ("registry.fedoraproject.org/fedora:44", fedora)):
        subprocess.run(["podman", "run", "--rm", "-v", f"{repo}:/repo:ro,z", image,
                        "bash", "-euc", script], check=True)
