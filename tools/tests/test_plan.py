import io
import json
import urllib.error

import pytest
from conftest import app, write_recipe

from emcomm_build.model import DefinitionError, load_recipes, load_targets
from emcomm_build.plan import (
    build_order,
    closure,
    fetch_manifest,
    full_release,
    package_filename,
    plan_builds,
    published_files,
    recipes_for_target,
    repo_path,
)


@pytest.fixture
def stack(fake_repo):
    write_recipe(fake_repo, "base", app("base"))
    write_recipe(fake_repo, "hamlib", app("hamlib", "4.7.2"))
    write_recipe(fake_repo, "wsjtx", app("wsjtx", "3.0.2", depends_on="[hamlib]"))
    write_recipe(fake_repo, "pat", app("pat", "1.0.0"))
    return load_recipes(fake_repo), load_targets(fake_repo)


def test_build_order_puts_base_and_deps_first(stack):
    recipes, _ = stack
    order = build_order(recipes)
    assert order[0] == "base"
    assert order.index("hamlib") < order.index("wsjtx")


def test_cycle_is_reported(fake_repo):
    write_recipe(fake_repo, "a", app("a", depends_on="[b]"))
    write_recipe(fake_repo, "b", app("b", depends_on="[a]"))
    with pytest.raises(DefinitionError, match="cycle"):
        build_order(load_recipes(fake_repo))


def test_recipes_for_target_filters_families(fake_repo):
    write_recipe(fake_repo, "hamlib", app("hamlib") + "    families: [fedora]\n")
    write_recipe(fake_repo, "core", app("core", depends_on="[hamlib]"))
    recipes, targets = load_recipes(fake_repo), load_targets(fake_repo)
    deb = recipes_for_target(recipes, targets["debian-13"])
    assert set(deb) == {"core"} and deb["core"].depends_on == ()
    fed = recipes_for_target(recipes, targets["fedora-44"])
    assert fed["core"].depends_on == ("hamlib",)


def test_closure_includes_base(stack):
    recipes, _ = stack
    assert closure(recipes, ["wsjtx"]) == {"wsjtx", "hamlib", "base"}


def test_filenames(stack):
    recipes, targets = stack
    deb, rpm = targets["debian-13"], targets["fedora-44"]
    assert full_release(recipes["hamlib"], deb) == "1+deb13"
    assert package_filename(recipes["hamlib"], deb, "arm64") == "emcomm-hamlib_4.7.2-1+deb13_arm64.deb"
    assert package_filename(recipes["hamlib"], rpm, "amd64") == "emcomm-hamlib-4.7.2-1.fc44.x86_64.rpm"
    assert repo_path(deb, "amd64", "x.deb") == "deb/pool/debian-13/x.deb"
    assert repo_path(rpm, "arm64", "x.rpm") == "rpm/fedora-44/aarch64/x.rpm"


def test_plan_skips_published(stack):
    recipes, targets = stack
    deb = targets["debian-13"]
    published = {package_filename(recipes[n], deb, "amd64") for n in ("base", "hamlib")}
    assert plan_builds(recipes, deb, "amd64", published) == ["pat", "wsjtx"]


def test_plan_only_builds_missing_closure(stack):
    recipes, targets = stack
    deb = targets["debian-13"]
    published = {package_filename(recipes["base"], deb, "amd64")}
    assert plan_builds(recipes, deb, "amd64", published, only=["wsjtx"]) == ["hamlib", "wsjtx"]


def test_plan_force_only_rebuilds_named(stack):
    recipes, targets = stack
    deb = targets["debian-13"]
    published = {package_filename(r, deb, "amd64") for r in recipes.values()}
    assert plan_builds(recipes, deb, "amd64", published, only=["wsjtx"], force=True) == ["wsjtx"]


def test_published_files():
    manifest = {"files": ["deb/pool/debian-13/a.deb", "deb/pool/debian-13/b.deb"]}
    assert published_files(manifest) == {"a.deb", "b.deb"}
    assert published_files(None) == set()


def test_fetch_manifest_404_is_none():
    def opener(url, timeout):
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)

    assert fetch_manifest("https://r", "testing", "debian-13", "amd64", opener=opener) is None


def test_fetch_manifest_reads_json():
    seen = []

    def opener(url, timeout):
        seen.append(url)
        return io.BytesIO(json.dumps({"files": []}).encode())

    assert fetch_manifest("https://r", "testing", "debian-13", "amd64", opener=opener) == {"files": []}
    assert seen == ["https://r/testing/manifest/debian-13-amd64.json"]
