import platform
import shutil

import pytest
from conftest import REAL_ROOT, TARGETS, write_recipe

from emcomm_build.container import Engine, run_build
from emcomm_build.model import load_recipes, load_targets

pytestmark = pytest.mark.container

HELLO_BUILD = """\
set -euo pipefail
cat > hello.c <<'EOF'
#include <stdio.h>
int main(void) { puts("hello from emcomm"); return 0; }
EOF
mkdir -p "$DESTDIR$PREFIX/bin"
# shellcheck disable=SC2086
cc $LDFLAGS -o "$DESTDIR$PREFIX/bin/hello" hello.c
"""

HELLO_RECIPE = """\
name: hello
kind: app
summary: test program
license: MIT
version: "1.0"
release: 1
source:
  type: none
"""


@pytest.fixture
def hello_repo(tmp_path, monkeypatch):
    if shutil.which("podman") is None:
        pytest.skip("podman not installed")
    (tmp_path / "targets.yaml").write_text(TARGETS)
    shutil.copytree(REAL_ROOT / "tools" / "container", tmp_path / "tools" / "container")
    write_recipe(tmp_path, "hello", HELLO_RECIPE, build_sh=HELLO_BUILD)
    (tmp_path / "recipes" / "hello" / "smoke.sh").write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\n[[ $(hello) == "hello from emcomm" ]]\n'
    )
    monkeypatch.setenv("EMCOMM_REPO_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("target,libc", [("debian-13", "libc6"), ("fedora-44", "glibc")])
def test_build_hello(hello_repo, tmp_path, target, libc):
    if platform.machine() not in ("x86_64", "aarch64"):
        pytest.skip("unsupported host arch")
    recipe = load_recipes(hello_repo)["hello"]
    tgt = load_targets(hello_repo)[target]
    workdir = tmp_path / "work" / target
    (workdir / "src").mkdir(parents=True)
    destdir, deps = run_build(Engine(), recipe, tgt, hello_repo, workdir)
    assert (destdir / "opt/emcomm/bin/hello").is_file()
    assert libc in deps


SCRIPT_BUILD = """\
set -euo pipefail
mkdir -p "$DESTDIR$PREFIX/bin"
printf '#!/bin/sh\\necho hi\\n' > "$DESTDIR$PREFIX/bin/hi"
chmod +x "$DESTDIR$PREFIX/bin/hi"
"""


def test_build_script_only_has_no_runtime_deps(hello_repo, tmp_path):
    write_recipe(hello_repo, "hi", HELLO_RECIPE.replace("name: hello", "name: hi"),
                 build_sh=SCRIPT_BUILD)
    recipe = load_recipes(hello_repo)["hi"]
    tgt = load_targets(hello_repo)["debian-13"]
    workdir = tmp_path / "work" / "hi"
    (workdir / "src").mkdir(parents=True)
    destdir, deps = run_build(Engine(), recipe, tgt, hello_repo, workdir)
    assert (destdir / "opt/emcomm/bin/hi").is_file()
    assert deps == []
