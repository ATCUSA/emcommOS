from conftest import app, write_recipe

from emcomm_build.bump import bump, bump_order, dependents, set_version
from emcomm_build.model import load_recipes

ASSET_RECIPE = """\
name: hamlib
kind: app
summary: hamlib
license: LGPL-2.1-or-later
# keep this comment
version: "4.7.1"
release: 3
source:
  type: github-release-asset
  repo: Hamlib/Hamlib
  asset: "hamlib-{version}.tar.gz"
"""


def test_set_version_inserts_sha_and_keeps_comments(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(ASSET_RECIPE)
    set_version(path, "4.7.2", "a" * 64)
    text = path.read_text()
    assert 'version: "4.7.2"' in text
    assert "release: 1" in text
    assert '  asset: "hamlib-{version}.tar.gz"\n  sha256: ' + "a" * 64 in text
    assert "# keep this comment" in text


def test_set_version_replaces_existing_sha(tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(ASSET_RECIPE + "  sha256: " + "b" * 64 + "\n")
    set_version(path, "4.7.2", "c" * 64)
    assert path.read_text().count("sha256:") == 1
    assert "c" * 64 in path.read_text()


def test_dependents_are_transitive(fake_repo):
    write_recipe(fake_repo, "hamlib", app("hamlib"))
    write_recipe(fake_repo, "wsjtx", app("wsjtx", depends_on="[hamlib]"))
    write_recipe(fake_repo, "extra", app("extra", depends_on="[wsjtx]"))
    write_recipe(fake_repo, "pat", app("pat"))
    assert dependents(load_recipes(fake_repo), "hamlib") == ["extra", "wsjtx"]


def test_bump_arch_url_writes_sidecar(fake_repo):
    d = fake_repo / "recipes" / "pat"
    d.mkdir(parents=True)
    (d / "build.sh").write_text("")
    (d / "recipe.yaml").write_text(
        'name: pat\nkind: app\nsummary: pat\nlicense: MIT\nversion: "0.9.0"\nrelease: 2\n'
        "source:\n  type: arch-url\n  urls:\n"
        '    amd64: "https://x/pat_{version}_linux_amd64.tar.gz"\n'
        '    arm64: "https://x/pat_{version}_linux_arm64.tar.gz"\n')
    assert bump(fake_repo, "pat", "1.0.0", sha_for=lambda url: ("a" if "amd64" in url else "b") * 64) == ["pat"]
    assert (d / "SHA256SUMS").read_text() == (
        "a" * 64 + "  pat_1.0.0_linux_amd64.tar.gz\n" + "b" * 64 + "  pat_1.0.0_linux_arm64.tar.gz\n")
    assert 'version: "1.0.0"' in (d / "recipe.yaml").read_text()


def test_bump_resets_release_and_increments_dependents(fake_repo):
    (fake_repo / "recipes" / "hamlib").mkdir(parents=True)
    (fake_repo / "recipes" / "hamlib" / "recipe.yaml").write_text(ASSET_RECIPE)
    (fake_repo / "recipes" / "hamlib" / "build.sh").write_text("")
    write_recipe(fake_repo, "wsjtx", app("wsjtx", depends_on="[hamlib]", release=2))
    urls = []

    def fake_sha(url):
        urls.append(url)
        return "d" * 64

    changed = bump(fake_repo, "hamlib", "4.7.2", sha_for=fake_sha)
    assert changed == ["hamlib", "wsjtx"]
    assert urls == ["https://github.com/Hamlib/Hamlib/releases/download/4.7.2/hamlib-4.7.2.tar.gz"]
    recipes = load_recipes(fake_repo)
    assert (recipes["hamlib"].version, recipes["hamlib"].release) == ("4.7.2", 1)
    assert recipes["wsjtx"].release == 3


def test_bump_order_sorts_by_dependency(fake_repo):
    write_recipe(fake_repo, "hamlib", app("hamlib"))
    write_recipe(fake_repo, "wsjtx", app("wsjtx", depends_on="[hamlib]"))
    recipes = load_recipes(fake_repo)
    # wsjtx depends on hamlib, so hamlib should come first
    assert bump_order(recipes, ["wsjtx", "hamlib"]) == ["hamlib", "wsjtx"]


def test_bump_order_end_to_end(fake_repo):
    (fake_repo / "recipes" / "hamlib").mkdir(parents=True)
    (fake_repo / "recipes" / "hamlib" / "recipe.yaml").write_text(ASSET_RECIPE + "  sha256: " + "c" * 64 + "\n")
    (fake_repo / "recipes" / "hamlib" / "build.sh").write_text("")
    write_recipe(fake_repo, "wsjtx", app("wsjtx", depends_on="[hamlib]", version="1.0.0", release=1))

    def fake_sha(url):
        return "e" * 64

    # Bump both in the given order (reversed)
    recipes = load_recipes(fake_repo)
    ordered = bump_order(recipes, ["wsjtx", "hamlib"])
    assert ordered == ["hamlib", "wsjtx"]
    # Bump hamlib first
    bump(fake_repo, "hamlib", "4.7.2", sha_for=fake_sha)
    # Bump wsjtx next
    bump(fake_repo, "wsjtx", "1.1.0", sha_for=fake_sha)
    recipes = load_recipes(fake_repo)
    assert (recipes["wsjtx"].version, recipes["wsjtx"].release) == ("1.1.0", 1)
