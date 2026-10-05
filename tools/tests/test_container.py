import subprocess
from pathlib import Path

from emcomm_build.container import Engine, build_command, build_deps, run_build
from emcomm_build.model import FamilyDeps, Recipe, Target

TARGET = Target("debian-13", "debian", "deb", "docker.io/library/debian:13", "deb13",
                ("build-essential",))
RECIPE = Recipe(name="hamlib", kind="app", summary="s", license="MIT", version="4.7.2",
                release=1, dir=Path("."), deps={"debian": FamilyDeps(build=("libusb-1.0-0-dev",))})


def test_build_deps_combines_base_and_recipe():
    assert build_deps(RECIPE, TARGET) == ["build-essential", "libusb-1.0-0-dev"]


def test_build_command(tmp_path):
    cmd = build_command(Engine("podman"), RECIPE, TARGET, Path("/repo"), tmp_path)
    assert cmd[:3] == ["podman", "run", "--rm"]
    assert "/repo:/emcomm:ro,z" in cmd
    assert f"{tmp_path}:/work:z" in cmd
    assert "BUILD_DEPS=build-essential libusb-1.0-0-dev" in cmd
    assert "RECIPE_DIR=/emcomm/recipes/hamlib" in cmd
    assert cmd[-3:] == ["docker.io/library/debian:13", "bash", "/emcomm/tools/container/build.sh"]


def test_pin_and_repo_files(tmp_path):
    from emcomm_build.container import pin_text, write_repo_files
    from emcomm_build.model import ExtraRepo
    repo = ExtraRepo("backports", "Types: deb\nSuites: trixie-backports\n", ("wsjtx*", "direwolf"), 500)
    assert pin_text(repo) == ("Package: wsjtx* direwolf\nPin: release n=trixie-backports\n"
                              "Pin-Priority: 500\n")
    target = Target("debian-13", "debian", "deb", "img", "deb13", (), (repo,))
    write_repo_files(target, tmp_path / "repos")
    assert sorted(p.name for p in (tmp_path / "repos").iterdir()) == ["backports.pref",
                                                                     "backports.sources"]


def test_run_build_reads_runtime_deps(tmp_path):
    def fake_run(cmd, check):
        (tmp_path / "runtime-deps.txt").write_text("libc6\nlibusb-1.0-0\n\n")
        return subprocess.CompletedProcess(cmd, 0)

    destdir, deps = run_build(Engine(), RECIPE, TARGET, Path("/repo"), tmp_path, run=fake_run)
    assert destdir == tmp_path / "destdir"
    assert destdir.is_dir()
    assert deps == ["libc6", "libusb-1.0-0"]
