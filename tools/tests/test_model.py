import pytest
from conftest import app, write_recipe

from emcomm_build.cli import main
from emcomm_build.model import DefinitionError, load_recipes, load_targets, repo_root


def test_load_targets(fake_repo):
    targets = load_targets(fake_repo)
    assert targets["debian-13"].format == "deb"
    assert targets["fedora-44"].dist_tag == "fc44"
    assert targets["fedora-44"].base_build_deps == ("gcc", "file", "findutils")


def test_load_app_recipe(fake_repo):
    write_recipe(fake_repo, "hamlib", app("hamlib", "4.7.2") + """\
    deps:
      debian:
        build: [libusb-1.0-0-dev]
    """)
    r = load_recipes(fake_repo)["hamlib"]
    assert r.package == "emcomm-hamlib"
    assert r.version == "4.7.2"
    assert r.deps_for("debian").build == ("libusb-1.0-0-dev",)
    assert r.deps_for("fedora").build == ()


def test_unquoted_version_is_rejected(fake_repo):
    write_recipe(fake_repo, "direwolf", app("direwolf").replace('"1.0"', "1.8"))
    with pytest.raises(DefinitionError, match="version"):
        load_recipes(fake_repo)


def test_name_must_match_directory(fake_repo):
    write_recipe(fake_repo, "foo", app("bar"))
    with pytest.raises(DefinitionError, match="must match directory"):
        load_recipes(fake_repo)


def test_unknown_dependency(fake_repo):
    write_recipe(fake_repo, "wsjtx", app("wsjtx", depends_on="[hamlib]"))
    with pytest.raises(DefinitionError, match="unknown recipe 'hamlib'"):
        load_recipes(fake_repo)


def test_app_needs_build_script(fake_repo):
    write_recipe(fake_repo, "pat", app("pat"), build_sh=None)
    with pytest.raises(DefinitionError, match="build.sh"):
        load_recipes(fake_repo)


def test_asset_source_requires_sha256(fake_repo):
    write_recipe(fake_repo, "hamlib", app("hamlib").replace(
        "type: none", "type: github-release-asset\n      repo: Hamlib/Hamlib\n      asset: x.tar.gz"))
    with pytest.raises(DefinitionError, match="sha256"):
        load_recipes(fake_repo)


def test_repo_root_walks_up(tmp_path, monkeypatch):
    monkeypatch.delenv("EMCOMM_REPO_ROOT", raising=False)
    (tmp_path / "targets.yaml").write_text("targets: {}\n")
    nested = tmp_path / "tools" / "src"
    nested.mkdir(parents=True)
    assert repo_root(nested) == tmp_path


def test_families_and_arch_url(fake_repo):
    d = write_recipe(fake_repo, "pat", app("pat").replace(
        "type: none",
        'type: arch-url\n      urls:\n        amd64: "https://x/pat_{version}_amd64.tgz"\n'
        '        arm64: "https://x/pat_{version}_arm64.tgz"') + "    families: [fedora]\n")
    with pytest.raises(DefinitionError, match="SHA256SUMS"):
        load_recipes(fake_repo)
    (d / "SHA256SUMS").write_text("")
    r = load_recipes(fake_repo)["pat"]
    assert r.source.url_for("arm64", "1.0") == "https://x/pat_1.0_arm64.tgz"
    assert r.applies_to("fedora") and not r.applies_to("debian")


def test_target_extra_repos(tmp_path):
    (tmp_path / "targets.yaml").write_text(
        "targets:\n  debian-13:\n    family: debian\n    format: deb\n    image: i\n"
        "    dist_tag: deb13\n    base_build_deps: []\n    extra_repos:\n"
        "      - {name: backports, deb822: 'Types: deb', pin_packages: [wsjtx], pin_priority: 500}\n")
    repo = load_targets(tmp_path)["debian-13"].extra_repos[0]
    assert (repo.name, repo.pin_packages, repo.pin_priority) == ("backports", ("wsjtx",), 500)


def test_validate_command(fake_repo, capsys):
    write_recipe(fake_repo, "hamlib", app("hamlib"))
    assert main(["validate"]) == 0
    assert "2 targets, 1 recipes" in capsys.readouterr().out


def test_validate_command_reports_errors(fake_repo, capsys):
    write_recipe(fake_repo, "foo", app("bar"))
    assert main(["validate"]) == 1
    assert "error:" in capsys.readouterr().err
