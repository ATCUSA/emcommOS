import pytest
from conftest import app, write_recipe

from emcomm_build import build as b
from emcomm_build.model import load_recipes, load_targets


@pytest.fixture
def setup(fake_repo, tmp_path, monkeypatch):
    write_recipe(fake_repo, "base", """\
    name: base
    kind: files
    summary: base
    license: MIT
    version: "1.0"
    release: 1
    files_dir: files
    """, build_sh=None)
    (fake_repo / "recipes/base/files/etc").mkdir(parents=True)
    write_recipe(fake_repo, "hamlib", app("hamlib", "4.7.2"))
    write_recipe(fake_repo, "wsjtx", app("wsjtx", "3.0.2", depends_on="[hamlib]"))
    calls = []

    def fake_fetch(recipe, workdir, root, cache, arch=None):
        calls.append(("fetch", recipe.name))
        (workdir / "src").mkdir(parents=True, exist_ok=True)
        return workdir / "src"

    def fake_run_build(engine, recipe, target, root, workdir):
        calls.append(("build", recipe.name, sorted(p.name for p in (workdir / "deps").glob("*"))))
        (workdir / "destdir").mkdir(exist_ok=True)
        return workdir / "destdir", ["libc6"]

    def fake_package(cfg, fmt, out, workdir):
        calls.append(("package", cfg["name"]))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("pkg")
        return out

    monkeypatch.setattr(b, "fetch_source", fake_fetch)
    monkeypatch.setattr(b, "run_build", fake_run_build)
    monkeypatch.setattr(b, "build_package", fake_package)
    monkeypatch.setattr(b, "smoke", lambda *a, **k: calls.append(("smoke",)))
    settings = b.BuildSettings(root=fake_repo, target=load_targets(fake_repo)["debian-13"],
                               arch="amd64", out=tmp_path / "dist", work=tmp_path / "work",
                               repo_url=None)
    return settings, calls


def test_builds_everything_in_order_and_stages_deps(setup):
    settings, calls = setup
    built = b.run(settings)
    assert [p.name for p in built] == [
        "emcomm-base_1.0-1+deb13_amd64.deb",
        "emcomm-hamlib_4.7.2-1+deb13_amd64.deb",
        "emcomm-wsjtx_3.0.2-1+deb13_amd64.deb",
    ]
    build_calls = [c for c in calls if c[0] == "build"]
    assert build_calls[0] == ("build", "hamlib", [])
    assert build_calls[1] == ("build", "wsjtx", ["emcomm-base_1.0-1+deb13_amd64.deb",
                                                 "emcomm-hamlib_4.7.2-1+deb13_amd64.deb"])
    assert calls[-1] == ("smoke",)


def test_only_builds_the_closure_locally(setup):
    settings, _ = setup
    settings = b.BuildSettings(**{**settings.__dict__, "only": ("hamlib",)})
    built = b.run(settings)
    assert [p.name.split("_")[0] for p in built] == ["emcomm-base", "emcomm-hamlib"]


def test_stage_downloads_from_manifest(setup, monkeypatch, tmp_path):
    settings, _ = setup
    settings = b.BuildSettings(**{**settings.__dict__, "repo_url": "https://repo"})
    recipes = load_recipes(settings.root)
    manifest = {"files": ["deb/pool/debian-13/emcomm-base_1.0-1+deb13_amd64.deb"]}
    urls = []

    def fake_download(url, dest):
        urls.append(url)
        dest.write_text("x")
        return "sha"

    monkeypatch.setattr(b, "download", fake_download)
    staged = b.stage(recipes, ["base"], settings, manifest, tmp_path / "deps")
    assert [p.name for p in staged] == ["emcomm-base_1.0-1+deb13_amd64.deb"]
    assert urls == ["https://repo/testing/deb/pool/debian-13/emcomm-base_1.0-1+deb13_amd64.deb"]


def test_stage_errors_when_unavailable(setup, tmp_path):
    settings, _ = setup
    recipes = load_recipes(settings.root)
    with pytest.raises(b.BuildError, match="neither built nor published"):
        b.stage(recipes, ["hamlib"], settings, None, tmp_path / "deps")


def test_host_arch(monkeypatch):
    monkeypatch.setattr(b.platform, "machine", lambda: "aarch64")
    assert b.host_arch() == "arm64"


class _R:
    def __init__(self, name):
        self.name, self.package = name, f"emcomm-{name}"


def test_package_path_guard():
    ok = [{"dst": "/opt/emcomm/bin/x"}, {"dst": "/etc/profile.d/emcomm.sh"},
          {"dst": "/usr/lib/environment.d/50-emcomm.conf"}]
    b.check_package_paths(_R("hamlib"), ok)
    b.check_package_paths(_R("cli"), [*ok, {"dst": "/usr/bin/emcomm"}])
    with pytest.raises(b.BuildError, match="refusing to package /usr/bin/emcomm"):
        b.check_package_paths(_R("hamlib"), [{"dst": "/usr/bin/emcomm"}])
    with pytest.raises(b.BuildError, match="emcomm-pat: refusing to package /usr/lib/libx.so"):
        b.check_package_paths(_R("pat"), [*ok, {"dst": "/usr/lib/libx.so"}])
    with pytest.raises(b.BuildError, match="/opt/emcommx/y"):
        b.check_package_paths(_R("pat"), [{"dst": "/opt/emcommx/y"}])
    with pytest.raises(b.BuildError, match="non-normalized"):
        b.check_package_paths(_R("pat"), [{"dst": "/opt/emcomm/../etc/passwd"}])


def test_run_refuses_files_outside_prefix(setup, monkeypatch):
    settings, calls = setup

    def stray_build(engine, recipe, target, root, workdir):
        dest = workdir / "destdir"
        (dest / "usr/lib").mkdir(parents=True)
        (dest / "usr/lib/libstray.so").write_text("x")
        return dest, []

    monkeypatch.setattr(b, "run_build", stray_build)
    with pytest.raises(b.BuildError, match="emcomm-hamlib: refusing to package /usr/lib/libstray.so"):
        b.run(settings)
    assert ("package", "emcomm-hamlib") not in calls
