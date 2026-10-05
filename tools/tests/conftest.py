import textwrap
from pathlib import Path

import pytest

REAL_ROOT = Path(__file__).resolve().parents[2]

TARGETS = """\
targets:
  debian-13:
    family: debian
    format: deb
    image: docker.io/library/debian:13
    dist_tag: deb13
    base_build_deps: [build-essential, file]
  fedora-44:
    family: fedora
    format: rpm
    image: registry.fedoraproject.org/fedora:44
    dist_tag: fc44
    base_build_deps: [gcc, file, findutils]
"""


def write_recipe(root: Path, name: str, body: str, build_sh: str | None = "") -> Path:
    d = root / "recipes" / name
    d.mkdir(parents=True)
    (d / "recipe.yaml").write_text(textwrap.dedent(body))
    if build_sh is not None:
        (d / "build.sh").write_text("#!/usr/bin/env bash\n" + build_sh)
    return d


def app(name: str, version: str = "1.0", depends_on: str = "[]", release: int = 1) -> str:
    return f"""\
    name: {name}
    kind: app
    summary: {name} test app
    license: MIT
    version: "{version}"
    release: {release}
    source:
      type: none
    depends_on: {depends_on}
"""  # no trailing indent, so callers can append 4-space-indented YAML lines


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / "targets.yaml").write_text(TARGETS)
    (tmp_path / "recipes").mkdir()
    monkeypatch.setenv("EMCOMM_REPO_ROOT", str(tmp_path))
    return tmp_path
