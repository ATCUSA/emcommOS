"""Recipe and target definitions loaded from the repository."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ARCHES = ("amd64", "arm64")
RPM_ARCH = {"amd64": "x86_64", "arm64": "aarch64"}


class DefinitionError(Exception):
    """A recipe or target definition is invalid."""


@dataclass(frozen=True)
class ExtraRepo:
    name: str
    deb822: str
    pin_packages: tuple[str, ...]
    pin_priority: int


@dataclass(frozen=True)
class Target:
    name: str
    family: str
    format: str
    image: str
    dist_tag: str
    base_build_deps: tuple[str, ...]
    extra_repos: tuple[ExtraRepo, ...] = ()


@dataclass(frozen=True)
class Source:
    type: str
    repo: str | None = None
    asset: str | None = None
    url: str | None = None
    ref: str | None = None
    paths: tuple[str, ...] = ()
    sha256: str | None = None
    urls: tuple[tuple[str, str], ...] = ()  # (arch, url template) for arch-url sources

    def resolved_ref(self, version: str) -> str:
        return (self.ref or "{version}").format(version=version)

    def url_for(self, arch: str, version: str) -> str:
        return dict(self.urls)[arch].format(version=version)


@dataclass(frozen=True)
class Upstream:
    type: str
    tag_pattern: str
    repo: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class FamilyDeps:
    build: tuple[str, ...] = ()
    run: tuple[str, ...] = ()


@dataclass(frozen=True)
class Recipe:
    name: str
    kind: str
    summary: str
    license: str
    version: str
    release: int
    dir: Path
    description: str = ""
    homepage: str = ""
    source: Source = Source(type="none")
    upstream: Upstream | None = None
    depends_on: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    deps: dict[str, FamilyDeps] = field(default_factory=dict)
    files_dir: str | None = None
    families: tuple[str, ...] = ()  # empty = every family
    bundle_dir: str | None = None   # self-contained tree (e.g. extracted AppImage) under /opt/emcomm

    @property
    def package(self) -> str:
        return f"emcomm-{self.name}"

    def applies_to(self, family: str) -> bool:
        return not self.families or family in self.families

    def deps_for(self, family: str) -> FamilyDeps:
        return self.deps.get(family, FamilyDeps())


def _schema(name: str) -> dict[str, Any]:
    return json.loads(resources.files("emcomm_build.schemas").joinpath(name).read_text())


def _validate(data: Any, schema_name: str, where: Path) -> None:
    try:
        jsonschema.validate(data, _schema(schema_name))
    except jsonschema.ValidationError as exc:
        loc = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise DefinitionError(f"{where}: {loc}: {exc.message}") from None


def repo_root(start: Path | None = None) -> Path:
    env = os.environ.get("EMCOMM_REPO_ROOT")
    if env:
        return Path(env)
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "targets.yaml").is_file():
            return candidate
    raise DefinitionError("could not find targets.yaml in this or any parent directory")


def load_targets(root: Path) -> dict[str, Target]:
    path = root / "targets.yaml"
    data = yaml.safe_load(path.read_text())
    _validate(data, "targets.schema.json", path)
    return {
        name: Target(
            name=name,
            family=t["family"],
            format=t["format"],
            image=t["image"],
            dist_tag=t["dist_tag"],
            base_build_deps=tuple(t["base_build_deps"]),
            extra_repos=tuple(
                ExtraRepo(name=r["name"], deb822=r["deb822"],
                          pin_packages=tuple(r["pin_packages"]), pin_priority=r["pin_priority"])
                for r in t.get("extra_repos", [])
            ),
        )
        for name, t in data["targets"].items()
    }


def load_recipe(recipe_dir: Path) -> Recipe:
    path = recipe_dir / "recipe.yaml"
    data = yaml.safe_load(path.read_text())
    _validate(data, "recipe.schema.json", path)
    if data["name"] != recipe_dir.name:
        raise DefinitionError(
            f"{path}: name {data['name']!r} must match directory {recipe_dir.name!r}"
        )
    src = data.get("source", {"type": "none"})
    up = data.get("upstream")
    recipe = Recipe(
        name=data["name"],
        kind=data["kind"],
        summary=data["summary"],
        description=data.get("description", ""),
        license=data["license"],
        homepage=data.get("homepage", ""),
        version=data["version"],
        release=data["release"],
        dir=recipe_dir,
        source=Source(
            type=src["type"],
            repo=src.get("repo"),
            asset=src.get("asset"),
            url=src.get("url"),
            ref=src.get("ref"),
            paths=tuple(src.get("paths", ())),
            sha256=src.get("sha256"),
            urls=tuple(sorted(src.get("urls", {}).items())),
        ),
        upstream=Upstream(
            type=up["type"], tag_pattern=up["tag_pattern"], repo=up.get("repo"), url=up.get("url")
        )
        if up
        else None,
        depends_on=tuple(data.get("depends_on", ())),
        requires=tuple(data.get("requires", ())),
        deps={
            fam: FamilyDeps(build=tuple(d.get("build", ())), run=tuple(d.get("run", ())))
            for fam, d in data.get("deps", {}).items()
        },
        files_dir=data.get("files_dir"),
        families=tuple(data.get("families", ())),
        bundle_dir=data.get("bundle_dir"),
    )
    if recipe.kind == "app" and not (recipe_dir / "build.sh").is_file():
        raise DefinitionError(f"{path}: app recipes need a build.sh next to recipe.yaml")
    if recipe.source.type == "arch-url" and not (recipe_dir / "SHA256SUMS").is_file():
        raise DefinitionError(
            f"{path}: arch-url sources need SHA256SUMS; run `emcomm-build bump {recipe.name} "
            f"{recipe.version}`"
        )
    return recipe


def load_recipes(root: Path) -> dict[str, Recipe]:
    recipes: dict[str, Recipe] = {}
    for d in sorted((root / "recipes").iterdir()):
        if (d / "recipe.yaml").is_file():
            r = load_recipe(d)
            recipes[r.name] = r
    for r in recipes.values():
        for dep in (*r.depends_on, *r.requires):
            if dep not in recipes:
                raise DefinitionError(f"{r.name}: unknown recipe {dep!r}")
    return recipes
