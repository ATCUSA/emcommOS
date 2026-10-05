import os
import shutil
import subprocess
from pathlib import Path

import pytest

from emcomm_build.model import FamilyDeps, Recipe, Target
from emcomm_build.package import build_package, content_entries, depends_list, nfpm_config

DEB = Target("debian-13", "debian", "deb", "img", "deb13", ())
RPM = Target("fedora-44", "fedora", "rpm", "img", "fc44", ())


def r(name, **kw):
    return Recipe(name=name, kind=kw.pop("kind", "app"), summary=f"{name} summary", license="MIT",
                  version="1.0", release=1, dir=Path("."), **kw)


RECIPES = {
    "base": r("base", kind="files"),
    "hamlib": r("hamlib"),
    "wsjtx": r("wsjtx", depends_on=("hamlib",),
               deps={"debian": FamilyDeps(run=("libqt5sql5-sqlite",))}),
}


def test_depends_list():
    deps = depends_list(RECIPES["wsjtx"], DEB, RECIPES, ["libc6", "libqt5core5t64"])
    assert deps == ["emcomm-base", "emcomm-hamlib", "libc6", "libqt5core5t64", "libqt5sql5-sqlite"]


def test_base_does_not_depend_on_itself():
    assert depends_list(RECIPES["base"], DEB, RECIPES, []) == []


def test_content_entries(tmp_path):
    (tmp_path / "opt/emcomm/bin").mkdir(parents=True)
    exe = tmp_path / "opt/emcomm/bin/rigctl"
    exe.write_text("x")
    exe.chmod(0o755)
    os.symlink("rigctl", tmp_path / "opt/emcomm/bin/rig")
    (tmp_path / "etc/profile.d").mkdir(parents=True)
    (tmp_path / "etc/profile.d/emcomm.sh").write_text("x")
    entries = {e["dst"]: e for e in content_entries(tmp_path)}
    assert entries["/opt/emcomm/bin/rig"] == {"src": "rigctl", "dst": "/opt/emcomm/bin/rig",
                                              "type": "symlink"}
    assert entries["/opt/emcomm/bin/rigctl"]["file_info"]["mode"] == 0o755
    assert entries["/etc/profile.d/emcomm.sh"]["type"] == "config|noreplace"


def test_nfpm_config_deb_and_rpm(tmp_path):
    deb = nfpm_config(RECIPES["hamlib"], DEB, "amd64", RECIPES, None, [])
    assert deb["name"] == "emcomm-hamlib"
    assert deb["release"] == "1+deb13"
    assert deb["version_schema"] == "none"
    assert deb["contents"] == []
    rpm = nfpm_config(RECIPES["hamlib"], RPM, "arm64", RECIPES, None, [])
    assert rpm["release"] == "1.fc44"
    assert rpm["rpm"] == {"summary": "hamlib summary"}


def test_build_package_invokes_nfpm(tmp_path):
    calls = []

    def fake_run(cmd, check):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    out = tmp_path / "out" / "x.deb"
    build_package({"name": "x"}, "deb", out, tmp_path, run=fake_run)
    assert calls == [["nfpm", "package", "--config", str(tmp_path / "nfpm-deb.yaml"),
                      "--packager", "deb", "--target", str(out)]]


@pytest.mark.nfpm
def test_real_nfpm_builds_meta_package(tmp_path):
    if shutil.which("nfpm") is None:
        pytest.skip("nfpm not installed")
    cfg = nfpm_config(RECIPES["hamlib"], DEB, "amd64", RECIPES, None, [])
    out = build_package(cfg, "deb", tmp_path / "emcomm-hamlib_1.0-1+deb13_amd64.deb", tmp_path)
    assert out.stat().st_size > 0
