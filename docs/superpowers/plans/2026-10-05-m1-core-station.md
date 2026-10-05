# emcommOS M1 "Core Station" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the standalone core station for Debian 13 and Fedora 43/44 (amd64 + arm64). That is a signed package repo combining version-floored distro packages, repackaged upstream binaries (Pat, JS8Call), and our own builds (hamlib on Fedora, fldigi/flrig on Debian, wfview, the `emcomm` CLI, and toolset metapackages). Any machine, including a volunteer's own laptop, can be set up from it (with consent, and fully uninstallable), and each app's config is rendered from operator and station profiles for USB or LAN (wfview) station kits.

**Architecture:** Each package's source is declared per distro family (spec §4.1): distro package (with Debian `trixie-backports` pinned for named packages), upstream prebuilt binary, or source build. A Python build tool (`tools/`, `emcomm-build`) reads one `recipe.yaml` per package that we produce. It builds or unpacks that package in a clean per-distro Podman container into `/opt/emcomm`, packages it with nFPM, smoke-tests it in a fresh container, and publishes a signed static apt/dnf repo to Cloudflare R2. Metapackages tie our packages to version-floored distro packages. A second Python package (`cli/`, `emcomm`) manages operator and station profiles, generates udev rules, and renders managed keys into app configs. An Ansible collection (`emcomm.station`) configures the repo, groups, toolsets, and systemd user units, and `bootstrap.sh` ties it all together.

**Tech Stack:** Python ≥3.12 (pyyaml, jsonschema, tomli-w), uv, pytest, ruff, Podman, nFPM 2.41.1, apt-ftparchive, createrepo_c, rpmsign, GnuPG, Ansible-core ≥2.16 with Molecule (podman driver), GitHub Actions (native `ubuntu-24.04` and `ubuntu-24.04-arm` runners), rclone → Cloudflare R2.

**Spec:** `docs/superpowers/specs/2026-10-05-emcommos-design.md`

## Global Constraints

- License Apache-2.0. Copy no code or data from EmComm Tools or 73Linux; write radio definitions from manufacturer and hamlib facts.
- Sourcing order per family: distro package if current enough → upstream prebuilt binary (sha256-pinned) → source build. Decisions are recorded in recipes/metapackages and reviewed with `emcomm-build freshness`.
- Everything we package installs under `/opt/emcomm` (`libdir=/opt/emcomm/lib`, rpath `/opt/emcomm/lib`). Outside it, packages may only add `/etc/profile.d/emcomm.sh` and `/usr/lib/environment.d/50-emcomm.conf` (from `emcomm-base`).
- BYOD: never change a machine without showing the change and getting confirmation (`--yes` for unattended). Everything must be removable with `bootstrap.sh --uninstall` / `emcomm uninstall`. Standalone installs collect no data.
- Package name is `emcomm-<recipe name>`. Every package except `emcomm-base` depends on `emcomm-base`.
- M1 targets are `debian-13`, `fedora-44`, `fedora-43` × `amd64`, `arm64`. The only channel is `testing`.
- Recipe versions are the latest upstream release *tags*. Release candidates are excluded, and versions in YAML are always quoted strings.
- rigctld from hamlib ≥ 4.7.2 (Debian: backports; Fedora: our build), for the CVE fixes and IC-7300MK2 model 3094. rigctld only ever listens on `127.0.0.1:4532`. Apps reach radios only through this hub, so distro apps may link older hamlib.
- The repository URL comes from configuration (`EMCOMM_REPO_URL` / the `emcomm_repo_url` variable / the GitHub variable `EMCOMM_REPO_URL`). Never hardcode a domain.
- In M1, emcomm never writes operator secrets (Winlink password, APRS-IS passcode).
- App configs get **managed keys only**. `~/.config/emcomm/direwolf.conf` and `~/.config/emcomm/rigctld.env` are fully owned by emcomm.
- Signing uses the dedicated project key (Task 1). Only its signing subkey goes to CI.

**M1 scoping notes:**
1. Containers are used only for clean build/test environments. rigctld, Direwolf, and Pat run as plain systemd *user* units through `emcomm-run`, which uses distro or `/opt/emcomm` binaries.
2. Ubuntu 24.04, EL10, Arch (official repos + AUR), group profiles, and the Nix tier-2 path arrive in M2. The managed level (push, machine roles, quirks, inventory) comes later.

---

## File Structure

```
targets.yaml                         # build targets (containers, dist tags, Debian backports pin)
freshness.yaml                       # distro-vs-upstream report inputs (Task 14)
flake.nix, flake.lock                # pinned dev shell (Task 29)
keys/emcomm-archive-keyring.asc      # project public key (Task 1)
keys/fingerprint.txt
bootstrap.sh                         # repo + CLI install, then `emcomm bootstrap`
docs/maintainer/setup.md             # key, R2, GitHub secrets (Task 1)
docs/testing/m1-manual-checks.md     # hardware checks (Task 27)
tools/                               # emcomm-build (Python)
  pyproject.toml
  src/emcomm_build/{model,net,upstream,bump,plan,fetch,container,package,build,publish,freshness,cli}.py
  src/emcomm_build/schemas/{recipe,targets}.schema.json
  tests/...
tools/container/{build,repos,runtime-deps,smoke,publish}.sh   # run inside distro containers
recipes/<name>/{recipe.yaml,build.sh,smoke.sh[,SHA256SUMS]}
                                     # base, hamlib (fedora), fldigi + flrig (debian), js8call +
                                     # pat (prebuilt), wfview, cli, core, digital, winlink, standard
radios/<id>.yaml                     # radio definitions
cli/                                 # emcomm CLI (Python)
  pyproject.toml
  src/emcomm/{paths,models,validation,profiles,radios,detect,udev,apply,cli}.py
  src/emcomm/render/{context,ini,xml,qtini,fldigi,pat,direwolf,rigctld,wfview,pipewire}.py
  src/emcomm/commands/{operator,radios,station,use,status,bootstrap,uninstall}.py
  src/emcomm/schemas/{operator,station,radio}.schema.json
  tests/...
ansible/ansible_collections/emcomm/station/
  galaxy.yml, meta/runtime.yml, playbooks/station.yml
  roles/{base,toolsets,radio_hw,services}/...
  extensions/molecule/default/...
tests/integration/repo-install.sh    # M1 acceptance against a published repo
.github/actions/setup-build-host/action.yml
.github/workflows/{ci,packages,watch-upstream}.yml
```

---

### Task 1: Maintainer setup — signing key, R2 bucket, GitHub settings (human)

This task needs the maintainer. An agent should write the doc and then stop and ask the maintainer to run the steps and commit `keys/`.

**Files:**
- Create: `docs/maintainer/setup.md`
- Create (by maintainer): `keys/emcomm-archive-keyring.asc`, `keys/fingerprint.txt`

**Interfaces:**
- Produces: `keys/emcomm-archive-keyring.asc` (armored public key) and `keys/fingerprint.txt` (40-hex fingerprint plus newline). Both are used by Tasks 9 (publish), 22 (Ansible key), 24 (bootstrap pin), and 26 (CI).
- Produces GitHub secrets `EMCOMM_SIGNING_KEY`, `EMCOMM_SIGNING_PASSPHRASE`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, and variables `EMCOMM_REPO_URL`, `R2_BUCKET`.

- [ ] **Step 1: Write `docs/maintainer/setup.md`**

````markdown
# Maintainer setup

One-time setup for package signing, hosting, and CI. Use a dedicated project key,
not anyone's personal identity.

## 1. Project signing key

Do this on a trusted machine. The primary key is certify-only and stays offline;
only the signing subkey goes to CI.

```bash
export GNUPGHOME="$HOME/.gnupg-emcomm"   # dedicated keyring
mkdir -m 700 -p "$GNUPGHOME"
gpg --quick-gen-key "emcommOS Package Signing" ed25519 cert 3y
FPR=$(gpg --list-keys --with-colons "emcommOS Package Signing" | awk -F: '/^fpr/ {print $10; exit}')
gpg --quick-add-key "$FPR" ed25519 sign 3y
mkdir -p keys
gpg --armor --export "$FPR" > keys/emcomm-archive-keyring.asc
echo "$FPR" > keys/fingerprint.txt
gpg --armor --export-secret-subkeys "$FPR" > "$GNUPGHOME/ci-signing-subkey.asc"
```

- Store an encrypted offline backup of `gpg --armor --export-secret-keys "$FPR"` and of
  `$GNUPGHOME/openpgp-revocs.d/$FPR.rev` (the revocation certificate).
- Never commit secret material. Commit only `keys/emcomm-archive-keyring.asc` and
  `keys/fingerprint.txt`.
- Renew before expiry with `gpg --quick-set-expire "$FPR" 3y` and `gpg --quick-set-expire "$FPR" 3y '*'`,
  then re-export the public key and commit it.

## 2. Cloudflare R2

1. Create a bucket (for example `emcomm-repo`).
2. Enable public read access through an r2.dev URL or a custom domain. That public base URL,
   with no trailing slash, is `EMCOMM_REPO_URL`.
3. Create an R2 API token with Object Read & Write scoped to the bucket. Note the access key ID,
   the secret, and your account ID.

## 3. GitHub repository settings

Secrets (Settings → Secrets and variables → Actions → Secrets):

| Name | Value |
|---|---|
| `EMCOMM_SIGNING_KEY` | contents of `ci-signing-subkey.asc` (then delete that file) |
| `EMCOMM_SIGNING_PASSPHRASE` | the key passphrase (empty if none) |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | R2 token |
| `R2_ACCOUNT_ID` | Cloudflare account ID |

Variables:

| Name | Value |
|---|---|
| `EMCOMM_REPO_URL` | public bucket URL, e.g. `https://pub-xxxx.r2.dev` |
| `R2_BUCKET` | bucket name |

Also enable Settings → Actions → General → "Allow GitHub Actions to create and approve pull
requests" (used by `watch-upstream`). Arm64 builds use the free `ubuntu-24.04-arm` runners,
which are available to public repositories.
````

- [ ] **Step 2: Maintainer runs section 1 and commits the public files**

Run: `cat keys/fingerprint.txt`
Expected: one line of 40 uppercase hex characters.

- [ ] **Step 3: Commit**

```bash
git add docs/maintainer/setup.md keys/emcomm-archive-keyring.asc keys/fingerprint.txt
git commit -m "docs: maintainer setup; add project signing public key"
```

---

### Task 2: Build-tool scaffolding, targets, and recipe model

**Files:**
- Create: `tools/pyproject.toml`, `tools/src/emcomm_build/__init__.py`, `tools/src/emcomm_build/model.py`, `tools/src/emcomm_build/cli.py`
- Create: `tools/src/emcomm_build/schemas/__init__.py`, `tools/src/emcomm_build/schemas/recipe.schema.json`, `tools/src/emcomm_build/schemas/targets.schema.json`
- Create: `targets.yaml`
- Modify: `.gitignore` (append `public/`)
- Test: `tools/tests/conftest.py`, `tools/tests/test_model.py`

**Interfaces:**
- Produces in `emcomm_build.model`:
  - `DefinitionError(Exception)`, `ARCHES = ("amd64", "arm64")`, `RPM_ARCH = {"amd64": "x86_64", "arm64": "aarch64"}`
  - `ExtraRepo(name, deb822, pin_packages, pin_priority)` and `Target(name, family, format, image, dist_tag, base_build_deps, extra_repos=())`
  - `Source(type, repo=None, asset=None, url=None, ref=None, paths=(), sha256=None, urls=())` with `.resolved_ref(version) -> str` and `.url_for(arch, version) -> str`. An `arch-url` source is an upstream prebuilt artifact per architecture; its checksums live in a `SHA256SUMS` sidecar next to `recipe.yaml`.
  - `Upstream(type, tag_pattern, repo=None, url=None)`
  - `FamilyDeps(build=(), run=())`
  - `Recipe(name, kind, summary, license, version, release, dir, description="", homepage="", source=Source("none"), upstream=None, depends_on=(), requires=(), deps={}, files_dir=None, families=(), bundle_dir=None)` with `.package -> "emcomm-<name>"`, `.deps_for(family) -> FamilyDeps`, and `.applies_to(family) -> bool`. `families` limits where a recipe is built (e.g. hamlib only for fedora, because Debian uses backports).
  - `repo_root(start=None) -> Path`, `load_targets(root) -> dict[str, Target]`, `load_recipe(dir) -> Recipe`, `load_recipes(root) -> dict[str, Recipe]`
- Produces in `emcomm_build.cli`: `main(argv=None) -> int`, `build_parser() -> ArgumentParser`. Commands register through `sub.add_parser(...).set_defaults(func=handler)`, where each handler is `(args) -> int`.

- [ ] **Step 1: Create `tools/pyproject.toml`**

```toml
[project]
name = "emcomm-build"
version = "0.1.0"
description = "emcommOS package build tooling"
requires-python = ">=3.12"
license = "Apache-2.0"
dependencies = ["pyyaml>=6", "jsonschema>=4.17"]

[project.scripts]
emcomm-build = "emcomm_build.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/emcomm_build"]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
  "container: needs podman and network access",
  "nfpm: needs the nfpm binary",
]

[tool.ruff]
line-length = 100
```

Create `tools/src/emcomm_build/__init__.py` and `tools/src/emcomm_build/schemas/__init__.py` as empty files.

- [ ] **Step 2: Create `targets.yaml`**

```yaml
# Build targets. `family` selects package-manager logic, `dist_tag` is appended to the
# package release (1+deb13 / 1.fc44) so identical versions never collide across distros.
targets:
  debian-13:
    family: debian
    format: deb
    image: docker.io/library/debian:13
    dist_tag: deb13
    base_build_deps: [build-essential, ca-certificates, pkg-config, git, file]
    # Official backports carry current hamlib/WSJT-X/Direwolf. The pin limits backports to
    # exactly these packages; keep in sync with roles/base/vars/Debian.yml (tested).
    extra_repos:
      - name: backports
        deb822: |
          Types: deb
          URIs: http://deb.debian.org/debian
          Suites: trixie-backports
          Components: main
          Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
        pin_packages: ["libhamlib*", "wsjtx*", "direwolf"]
        pin_priority: 500
  fedora-44:
    family: fedora
    format: rpm
    image: registry.fedoraproject.org/fedora:44
    dist_tag: fc44
    base_build_deps: [gcc, gcc-c++, make, pkgconf-pkg-config, git, file, findutils, which, tar, gzip]
  fedora-43:
    family: fedora
    format: rpm
    image: registry.fedoraproject.org/fedora:43
    dist_tag: fc43
    base_build_deps: [gcc, gcc-c++, make, pkgconf-pkg-config, git, file, findutils, which, tar, gzip]
```

Append `public/` to `.gitignore`.

- [ ] **Step 3: Create the JSON schemas**

`tools/src/emcomm_build/schemas/targets.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["targets"],
  "properties": {
    "targets": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "object",
        "additionalProperties": false,
        "required": ["family", "format", "image", "dist_tag", "base_build_deps"],
        "properties": {
          "family": {"enum": ["debian", "fedora", "el", "arch"]},
          "format": {"enum": ["deb", "rpm"]},
          "image": {"type": "string"},
          "dist_tag": {"type": "string", "pattern": "^[a-z0-9]+$"},
          "base_build_deps": {"type": "array", "items": {"type": "string"}},
          "extra_repos": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["name", "deb822", "pin_packages", "pin_priority"],
              "properties": {
                "name": {"type": "string", "pattern": "^[a-z0-9-]+$"},
                "deb822": {"type": "string"},
                "pin_packages": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "pin_priority": {"type": "integer"}
              }
            }
          }
        }
      }
    }
  }
}
```

`tools/src/emcomm_build/schemas/recipe.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["name", "kind", "summary", "license", "version", "release"],
  "properties": {
    "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "kind": {"enum": ["app", "meta", "files"]},
    "summary": {"type": "string", "minLength": 1},
    "description": {"type": "string"},
    "license": {"type": "string", "minLength": 1},
    "homepage": {"type": "string"},
    "version": {"type": "string", "pattern": "^[0-9][0-9A-Za-z.]*$"},
    "release": {"type": "integer", "minimum": 1},
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type"],
      "properties": {
        "type": {"enum": ["github-release-asset", "git", "local", "arch-url", "none"]},
        "urls": {
          "type": "object",
          "additionalProperties": false,
          "required": ["amd64", "arm64"],
          "properties": {
            "amd64": {"type": "string", "pattern": "^https://"},
            "arm64": {"type": "string", "pattern": "^https://"}
          }
        },
        "repo": {"type": "string"},
        "asset": {"type": "string"},
        "url": {"type": "string", "pattern": "^https://"},
        "ref": {"type": "string"},
        "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
      },
      "allOf": [
        {"if": {"properties": {"type": {"const": "github-release-asset"}}},
         "then": {"required": ["repo", "asset", "sha256"]}},
        {"if": {"properties": {"type": {"const": "git"}}},
         "then": {"required": ["url", "ref"]}},
        {"if": {"properties": {"type": {"const": "local"}}},
         "then": {"required": ["paths"]}},
        {"if": {"properties": {"type": {"const": "arch-url"}}},
         "then": {"required": ["urls"]}}
      ]
    },
    "upstream": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type", "tag_pattern"],
      "properties": {
        "type": {"enum": ["github-releases", "git-tags"]},
        "repo": {"type": "string"},
        "url": {"type": "string", "pattern": "^https://"},
        "tag_pattern": {"type": "string"}
      }
    },
    "depends_on": {"type": "array", "items": {"type": "string"}},
    "requires": {"type": "array", "items": {"type": "string"}},
    "deps": {
      "type": "object",
      "propertyNames": {"enum": ["debian", "fedora", "el", "arch"]},
      "additionalProperties": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "build": {"type": "array", "items": {"type": "string"}},
          "run": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "files_dir": {"type": "string"},
    "families": {
      "type": "array",
      "items": {"enum": ["debian", "fedora", "el", "arch"]},
      "minItems": 1
    },
    "bundle_dir": {"type": "string", "pattern": "^lib/[a-z0-9-]+$"}
  },
  "allOf": [
    {"if": {"properties": {"kind": {"const": "app"}}}, "then": {"required": ["source"]}},
    {"if": {"properties": {"kind": {"const": "files"}}}, "then": {"required": ["files_dir"]}}
  ]
}
```

- [ ] **Step 4: Write the failing tests**

`tools/tests/conftest.py`:

```python
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
```

`tools/tests/test_model.py`:

```python
import pytest

from emcomm_build.cli import main
from emcomm_build.model import DefinitionError, load_recipes, load_targets, repo_root

from conftest import app, write_recipe


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
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.cli'` (or `.model`).

- [ ] **Step 6: Implement `tools/src/emcomm_build/model.py`**

```python
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
```

- [ ] **Step 7: Implement `tools/src/emcomm_build/cli.py`**

```python
"""emcomm-build command line."""

from __future__ import annotations

import argparse
import sys

from .model import DefinitionError, load_recipes, load_targets, repo_root


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    targets = load_targets(root)
    recipes = load_recipes(root)
    print(f"ok: {len(targets)} targets, {len(recipes)} recipes")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="emcomm-build", description="emcommOS package builder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate targets.yaml and all recipes").set_defaults(
        func=cmd_validate
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DefinitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Run the tests and lint**

Run: `uv run --directory tools pytest -q && uv run --directory tools ruff check .`
Expected: all tests PASS and ruff reports no errors.

- [ ] **Step 9: Commit**

```bash
git add tools targets.yaml .gitignore
git commit -m "feat(build): recipe/target model, schemas and validate command"
```

---

### Task 3: Upstream version checks and recipe bumps

**Files:**
- Create: `tools/src/emcomm_build/net.py`, `tools/src/emcomm_build/upstream.py`, `tools/src/emcomm_build/bump.py`
- Modify: `tools/src/emcomm_build/cli.py` (add `check` and `bump` commands)
- Test: `tools/tests/test_upstream.py`, `tools/tests/test_bump.py`

**Interfaces:**
- Consumes: `model.Upstream`, `model.Recipe`, `model.load_recipes`, `model.repo_root`, `model.DefinitionError`.
- Produces:
  - `net.asset_url(repo, ref_template, asset_template, version) -> str`
  - `net.sha256_file(path) -> str`
  - `net.download(url, dest) -> str` (returns the sha256)
  - `net.download_sha256(url) -> str`
  - `upstream.version_key(v) -> tuple[int, ...]`
  - `upstream.pick_latest(tags, pattern) -> str | None` (the pattern must full-match the tag; group 1 is the version)
  - `upstream.is_newer(a, b) -> bool`
  - `upstream.list_tags(up, *, http_json=..., run=...) -> list[str]`
  - `bump.set_version(path, version, sha256)`, `bump.increment_release(path)`, `bump.dependents(recipes, name) -> list[str]`
  - `bump.bump(root, name, version, *, sha_for=net.download_sha256) -> list[str]` (the bumped name followed by its bumped dependents). For `arch-url` sources it rewrites `recipes/<name>/SHA256SUMS` (`<sha256>  <basename>` per architecture).

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_upstream.py`:

```python
import subprocess

from emcomm_build.model import Upstream
from emcomm_build.upstream import is_newer, list_tags, pick_latest, version_key


def test_version_key_orders_numerically():
    assert version_key("4.10.0") > version_key("4.9.9")


def test_pick_latest_filters_by_pattern():
    tags = ["v3.0.1", "v3.0.2", "v3.2.0-rc1", "wsjtx-2.7.0"]
    assert pick_latest(tags, r"v(\d+\.\d+\.\d+)") == "3.0.2"


def test_pick_latest_bare_versions():
    assert pick_latest(["1.7", "1.8", "1.8.1", "1.8-beta1"], r"(\d+\.\d+(?:\.\d+)?)") == "1.8.1"


def test_pick_latest_none_when_nothing_matches():
    assert pick_latest(["foo"], r"v(\d+)") is None


def test_is_newer():
    assert is_newer("4.7.2", "4.7.1")
    assert not is_newer("4.7.2", "4.7.2")


def test_list_tags_github_skips_prereleases():
    releases = [
        {"tag_name": "v1.0.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.1.0-rc1", "draft": False, "prerelease": True},
        {"tag_name": "v0.9.0", "draft": True, "prerelease": False},
    ]
    up = Upstream(type="github-releases", tag_pattern=r"v(.*)", repo="la5nta/pat")
    seen = []

    def fake_http(url):
        seen.append(url)
        return releases

    assert list_tags(up, http_json=fake_http) == ["v1.0.0"]
    assert seen == ["https://api.github.com/repos/la5nta/pat/releases?per_page=100"]


def test_list_tags_git():
    out = "abc\trefs/tags/v4.2.12\ndef\trefs/tags/v4.2.13\n"

    def fake_run(cmd, **kwargs):
        assert cmd[:4] == ["git", "ls-remote", "--tags", "--refs"]
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    up = Upstream(type="git-tags", tag_pattern=r"v(.*)", url="https://git.code.sf.net/p/fldigi/fldigi")
    assert list_tags(up, run=fake_run) == ["v4.2.12", "v4.2.13"]
```

`tools/tests/test_bump.py`:

```python
from emcomm_build.bump import bump, dependents, set_version
from emcomm_build.model import load_recipes

from conftest import app, write_recipe

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q tests/test_upstream.py tests/test_bump.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.upstream'`.

- [ ] **Step 3: Implement `net.py`**

```python
"""HTTP helpers: GitHub asset URLs and hashed downloads."""

from __future__ import annotations

import hashlib
import tempfile
import urllib.request
from pathlib import Path


def asset_url(repo: str, ref_template: str, asset_template: str, version: str) -> str:
    ref = ref_template.format(version=version)
    asset = asset_template.format(version=version)
    return f"https://github.com/{repo}/releases/download/{ref}/{asset}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> str:
    """Download url to dest atomically; return its sha256."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as out:
        while chunk := resp.read(1 << 20):
            h.update(chunk)
            out.write(chunk)
    tmp.replace(dest)
    return h.hexdigest()


def download_sha256(url: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        return download(url, Path(d) / "asset")
```

- [ ] **Step 4: Implement `upstream.py`**

```python
"""Find the newest upstream release tag for a recipe."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from collections.abc import Callable, Iterable

from .model import Upstream


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version))


def is_newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


def pick_latest(tags: Iterable[str], pattern: str) -> str | None:
    """Return the highest version among tags that fully match pattern (group 1 = version)."""
    rx = re.compile(pattern)
    versions = [m.group(1) for t in tags if (m := rx.fullmatch(t))]
    return max(versions, key=version_key, default=None)


def _http_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def list_tags(
    up: Upstream,
    *,
    http_json: Callable[[str], object] = _http_json,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[str]:
    if up.type == "github-releases":
        releases = http_json(f"https://api.github.com/repos/{up.repo}/releases?per_page=100")
        return [r["tag_name"] for r in releases if not r["draft"] and not r["prerelease"]]
    if up.type == "git-tags":
        out = run(
            ["git", "ls-remote", "--tags", "--refs", up.url],
            check=True, capture_output=True, text=True,
        ).stdout
        return [line.split("refs/tags/", 1)[1] for line in out.splitlines() if "refs/tags/" in line]
    raise ValueError(f"unknown upstream type {up.type!r}")
```

- [ ] **Step 5: Implement `bump.py`**

```python
"""Rewrite recipe.yaml version fields in place, keeping comments and layout."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import yaml

from .model import DefinitionError, Recipe, load_recipes
from .net import asset_url, download_sha256


def _sub_line(text: str, pattern: str, replacement: str, path: Path) -> str:
    new, n = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.M)
    if n != 1:
        raise DefinitionError(f"{path}: no line matching {pattern!r}")
    return new


def set_version(path: Path, version: str, sha256: str | None) -> None:
    text = path.read_text()
    text = _sub_line(text, r"^version:.*$", f'version: "{version}"', path)
    text = _sub_line(text, r"^release:.*$", "release: 1", path)
    if sha256 is not None:
        if re.search(r"^  sha256:.*$", text, re.M):
            text = _sub_line(text, r"^  sha256:.*$", f"  sha256: {sha256}", path)
        else:
            m = re.search(r"^  asset:.*$", text, re.M)
            if not m:
                raise DefinitionError(f"{path}: source.asset line not found")
            text = text[: m.end()] + f"\n  sha256: {sha256}" + text[m.end():]
    path.write_text(text)


def increment_release(path: Path) -> None:
    text = path.read_text()
    m = re.search(r"^release:\s*(\d+)\s*$", text, re.M)
    if not m:
        raise DefinitionError(f"{path}: no release line")
    path.write_text(text[: m.start()] + f"release: {int(m.group(1)) + 1}" + text[m.end():])


def dependents(recipes: dict[str, Recipe], name: str) -> list[str]:
    """Recipes that transitively build against `name` (depends_on edges only)."""
    found: set[str] = set()
    frontier = [name]
    while frontier:
        current = frontier.pop()
        for r in recipes.values():
            if current in r.depends_on and r.name not in found:
                found.add(r.name)
                frontier.append(r.name)
    return sorted(found)


def bump(
    root: Path, name: str, version: str, *, sha_for: Callable[[str], str] = download_sha256
) -> list[str]:
    path = root / "recipes" / name / "recipe.yaml"
    raw = yaml.safe_load(path.read_text())
    src = raw.get("source", {})
    sha = None
    if src.get("type") == "github-release-asset":
        sha = sha_for(asset_url(src["repo"], src.get("ref", "{version}"), src["asset"], version))
    elif src.get("type") == "arch-url":
        lines = []
        for arch in sorted(src["urls"]):
            url = src["urls"][arch].format(version=version)
            lines.append(f"{sha_for(url)}  {url.rsplit('/', 1)[-1]}")
        (path.parent / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    set_version(path, version, sha)
    deps = dependents(load_recipes(root), name)
    for dep in deps:
        increment_release(root / "recipes" / dep / "recipe.yaml")
    return [name, *deps]
```

- [ ] **Step 6: Add the `check` and `bump` commands to `cli.py`**

Add these imports at the top of `cli.py`:

```python
from .bump import bump
from .upstream import is_newer, list_tags, pick_latest
```

Add these handlers above `build_parser`:

```python
def cmd_check(args: argparse.Namespace) -> int:
    root = repo_root()
    recipes = load_recipes(root)
    updates = []
    for r in recipes.values():
        if r.upstream is None:
            continue
        latest = pick_latest(list_tags(r.upstream), r.upstream.tag_pattern)
        if latest and is_newer(latest, r.version):
            updates.append((r.name, r.version, latest))
    for name, old, new in updates:
        print(f"{name}: {old} -> {new}")
        if args.write:
            print(f"  bumped: {', '.join(bump(root, name, new))}")
    if not updates:
        print("all recipes are current")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    changed = bump(repo_root(), args.name, args.version)
    print(f"bumped: {', '.join(changed)}")
    return 0
```

Add this inside `build_parser`, before `return parser`:

```python
    check = sub.add_parser("check", help="look for newer upstream releases")
    check.add_argument("--write", action="store_true", help="bump recipes that are behind")
    check.set_defaults(func=cmd_check)
    bump_p = sub.add_parser("bump", help="set a recipe version (recomputes sha256)")
    bump_p.add_argument("name")
    bump_p.add_argument("version")
    bump_p.set_defaults(func=cmd_bump)
```

- [ ] **Step 7: Run the tests**

Run: `uv run --directory tools pytest -q && uv run --directory tools ruff check .`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tools
git commit -m "feat(build): upstream tag checks and recipe bumping"
```

---

### Task 4: Build ordering, package naming, and build planning

**Files:**
- Create: `tools/src/emcomm_build/plan.py`
- Modify: `tools/src/emcomm_build/cli.py` (`validate` also checks ordering)
- Test: `tools/tests/test_plan.py`

**Interfaces:**
- Consumes: `model.Recipe`, `model.Target`, `model.RPM_ARCH`, `model.DefinitionError`.
- Produces:
  - `build_order(recipes) -> list[str]`. A topological order over `depends_on`, `requires`, and an implicit dependency on `base`; ties break deterministically. A cycle raises `DefinitionError`.
  - `closure(recipes, names) -> set[str]`: the names, everything they transitively depend on or require, and `base` if that recipe exists.
  - `recipes_for_target(recipes, target) -> dict[str, Recipe]`: only the recipes that apply to the target's family. Their `depends_on`/`requires` edges to excluded recipes are dropped; for example, `core` requires `hamlib`, which only exists on Fedora. Every later step works on this filtered dict.
  - `full_release(recipe, target) -> str`: `"1+deb13"` for deb, `"1.fc44"` for rpm.
  - `package_filename(recipe, target, arch) -> str`
  - `repo_path(target, arch, filename) -> str`: `deb/pool/<target>/<file>` or `rpm/<target>/<x86_64|aarch64>/<file>`.
  - `published_files(manifest) -> set[str]`: package basenames.
  - `plan_builds(recipes, target, arch, published, only=(), force=False) -> list[str]`
  - `fetch_manifest(repo_url, channel, target, arch, *, opener=urllib.request.urlopen) -> dict | None`: returns `None` on 404.
- Manifest JSON, at `<channel>/manifest/<target>-<arch>.json`: `{"target": str, "arch": str, "files": [repo-relative paths]}`

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_plan.py`:

```python
import io
import json
import urllib.error

import pytest

from emcomm_build.model import DefinitionError, load_recipes, load_targets
from emcomm_build.plan import (
    build_order, closure, fetch_manifest, full_release, package_filename, plan_builds,
    recipes_for_target,
    published_files, repo_path,
)

from conftest import app, write_recipe


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q tests/test_plan.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.plan'`.

- [ ] **Step 3: Implement `plan.py`**

```python
"""Build ordering, package file naming and what-needs-building decisions."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import replace
from graphlib import CycleError, TopologicalSorter

from .model import RPM_ARCH, DefinitionError, Recipe, Target


def _edges(recipes: dict[str, Recipe], name: str) -> set[str]:
    r = recipes[name]
    deps = {*r.depends_on, *r.requires}
    if name != "base" and "base" in recipes:
        deps.add("base")
    return deps


def build_order(recipes: dict[str, Recipe]) -> list[str]:
    ts: TopologicalSorter[str] = TopologicalSorter()
    for name in sorted(recipes):
        ts.add(name, *sorted(_edges(recipes, name)))
    try:
        ts.prepare()
    except CycleError as exc:
        raise DefinitionError(f"dependency cycle: {' -> '.join(exc.args[1])}") from None
    order: list[str] = []
    while ts.is_active():
        ready = sorted(ts.get_ready())
        order.extend(ready)
        ts.done(*ready)
    return order


def recipes_for_target(recipes: dict[str, Recipe], target: Target) -> dict[str, Recipe]:
    keep = {n for n, r in recipes.items() if r.applies_to(target.family)}
    return {
        n: replace(r, depends_on=tuple(d for d in r.depends_on if d in keep),
                   requires=tuple(d for d in r.requires if d in keep))
        for n, r in recipes.items()
        if n in keep
    }


def closure(recipes: dict[str, Recipe], names: Iterable[str]) -> set[str]:
    found: set[str] = set()
    frontier = list(names)
    while frontier:
        n = frontier.pop()
        if n not in found:
            found.add(n)
            frontier.extend(_edges(recipes, n))
    return found


def full_release(recipe: Recipe, target: Target) -> str:
    sep = "+" if target.format == "deb" else "."
    return f"{recipe.release}{sep}{target.dist_tag}"


def package_filename(recipe: Recipe, target: Target, arch: str) -> str:
    rel = full_release(recipe, target)
    if target.format == "deb":
        return f"{recipe.package}_{recipe.version}-{rel}_{arch}.deb"
    if target.format == "rpm":
        return f"{recipe.package}-{recipe.version}-{rel}.{RPM_ARCH[arch]}.rpm"
    raise DefinitionError(f"unsupported package format {target.format!r}")


def repo_path(target: Target, arch: str, filename: str) -> str:
    if target.format == "deb":
        return f"deb/pool/{target.name}/{filename}"
    return f"rpm/{target.name}/{RPM_ARCH[arch]}/{filename}"


def published_files(manifest: dict | None) -> set[str]:
    if not manifest:
        return set()
    return {p.rsplit("/", 1)[-1] for p in manifest.get("files", [])}


def plan_builds(
    recipes: dict[str, Recipe],
    target: Target,
    arch: str,
    published: set[str],
    only: Iterable[str] = (),
    force: bool = False,
) -> list[str]:
    only = list(only)
    selected = closure(recipes, only) if only else set(recipes)
    forced = (set(only) if only else set(recipes)) if force else set()
    return [
        n
        for n in build_order(recipes)
        if n in selected
        and (n in forced or package_filename(recipes[n], target, arch) not in published)
    ]


def fetch_manifest(
    repo_url: str,
    channel: str,
    target: str,
    arch: str,
    *,
    opener: Callable = urllib.request.urlopen,
) -> dict | None:
    url = f"{repo_url.rstrip('/')}/{channel}/manifest/{target}-{arch}.json"
    try:
        with opener(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):  # R2 returns 403/404 for missing public objects
            return None
        raise
```

`io.BytesIO` works as a context manager, so the test opener can return it directly.

- [ ] **Step 4: Make `validate` check ordering too**

In `cli.py`, add `from .plan import build_order`. In `cmd_validate`, add `build_order(recipes)` after `recipes = load_recipes(root)`.

- [ ] **Step 5: Run the tests**

Run: `uv run --directory tools pytest -q && uv run --directory tools ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools
git commit -m "feat(build): build ordering, package naming and build planning"
```

---

### Task 5: Source fetching

**Files:**
- Create: `tools/src/emcomm_build/fetch.py`
- Test: `tools/tests/test_fetch.py`

**Interfaces:**
- Consumes: `model.Recipe`, `model.Source`, `net.asset_url`, `net.download`, `net.sha256_file`.
- Produces:
  - `FetchError(Exception)`
  - `extract_tarball(archive: Path, dest: Path) -> None`: strips a single top-level directory.
  - `fetch_source(recipe, workdir, root, cache, *, arch=None, download_fn=download, run=subprocess.run) -> Path`: returns `workdir/"src"`.
    - `local` sources copy each path (directory or file) to `src/<basename>`.
    - `arch-url` sources download the artifact for `arch`, verify it against the recipe's `SHA256SUMS` sidecar, and place it unextracted in `src/`, where the recipe's `build.sh` unpacks it.
    - `git` sources do a shallow clone of the resolved ref.
    - `github-release-asset` sources download into `cache`, verify the sha256, and extract.
    - `none` creates an empty `src`.

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_fetch.py`:

```python
import hashlib
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from emcomm_build.fetch import FetchError, extract_tarball, fetch_source
from emcomm_build.model import Recipe, Source


def recipe(source: Source, version: str = "1.2.3") -> Recipe:
    return Recipe(name="demo", kind="app", summary="s", license="MIT", version=version,
                  release=1, dir=Path("."), source=source)


def make_tarball(tmp_path: Path) -> Path:
    top = tmp_path / "pkg" / "demo-1.2.3"
    top.mkdir(parents=True)
    (top / "configure").write_text("#!/bin/sh\n")
    archive = tmp_path / "demo-1.2.3.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(top, arcname="demo-1.2.3")
    return archive


def test_extract_strips_top_dir(tmp_path):
    dest = tmp_path / "out"
    extract_tarball(make_tarball(tmp_path), dest)
    assert (dest / "configure").is_file()


def test_asset_download_verifies_sha(tmp_path):
    archive = make_tarball(tmp_path)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    urls = []

    def fake_download(url, dest):
        urls.append(url)
        shutil.copy(archive, dest)
        return sha

    src = Source(type="github-release-asset", repo="o/r", asset="demo-{version}.tar.gz", sha256=sha)
    out = fetch_source(recipe(src), tmp_path / "work", tmp_path, tmp_path / "cache",
                       download_fn=fake_download)
    assert (out / "configure").is_file()
    assert urls == ["https://github.com/o/r/releases/download/1.2.3/demo-1.2.3.tar.gz"]
    # cached: second fetch does not download again
    fetch_source(recipe(src), tmp_path / "work", tmp_path, tmp_path / "cache",
                 download_fn=fake_download)
    assert len(urls) == 1


def test_asset_sha_mismatch(tmp_path):
    archive = make_tarball(tmp_path)

    def fake_download(url, dest):
        shutil.copy(archive, dest)
        return "0" * 64

    src = Source(type="github-release-asset", repo="o/r", asset="a.tgz", sha256="f" * 64)
    with pytest.raises(FetchError, match="sha256 mismatch"):
        fetch_source(recipe(src), tmp_path / "w", tmp_path, tmp_path / "c", download_fn=fake_download)


def test_local_copies_paths(tmp_path):
    (tmp_path / "cli" / "src").mkdir(parents=True)
    (tmp_path / "cli" / "src" / "x.py").write_text("x")
    (tmp_path / "cli" / "__pycache__").mkdir()
    out = fetch_source(recipe(Source(type="local", paths=("cli",))), tmp_path / "w", tmp_path,
                       tmp_path / "c")
    assert (out / "cli" / "src" / "x.py").is_file()
    assert not (out / "cli" / "__pycache__").exists()


def test_arch_url_verifies_sidecar(tmp_path):
    rdir = tmp_path / "recipe"
    rdir.mkdir()
    payload = tmp_path / "payload"
    payload.write_bytes(b"binary")
    sha = hashlib.sha256(b"binary").hexdigest()
    (rdir / "SHA256SUMS").write_text(f"{sha}  pat_1.2.3_arm64.tgz\n")
    src = Source(type="arch-url", urls=(("amd64", "https://x/pat_{version}_amd64.tgz"),
                                         ("arm64", "https://x/pat_{version}_arm64.tgz")))
    r = Recipe(name="pat", kind="app", summary="s", license="MIT", version="1.2.3", release=1,
               dir=rdir, source=src)

    def fake_download(url, dest):
        shutil.copy(payload, dest)
        return sha

    out = fetch_source(r, tmp_path / "w", tmp_path, tmp_path / "c", arch="arm64",
                       download_fn=fake_download)
    assert (out / "pat_1.2.3_arm64.tgz").read_bytes() == b"binary"
    with pytest.raises(FetchError, match="missing from SHA256SUMS"):
        fetch_source(r, tmp_path / "w", tmp_path, tmp_path / "c", arch="amd64",
                     download_fn=fake_download)


def test_git_clone_at_tag(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git = ["git", "-C", str(origin), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(origin)], check=True)
    (origin / "README").write_text("v1")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    subprocess.run([*git, "tag", "v1.2.3"], check=True)
    src = Source(type="git", url=f"file://{origin}", ref="v{version}")
    out = fetch_source(recipe(src), tmp_path / "w", tmp_path, tmp_path / "c")
    assert (out / "README").read_text() == "v1"
```

The `git` test uses a `file://` URL, but the schema only requires `https://` for recipe files; `fetch_source` doesn't validate the URL scheme.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q tests/test_fetch.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.fetch'`.

- [ ] **Step 3: Implement `fetch.py`**

```python
"""Fetch recipe sources into a work directory."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

from .model import Recipe
from .net import asset_url, download, sha256_file

IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".venv", ".pytest_cache",
                                ".ruff_cache", "dist", "build")


class FetchError(Exception):
    """Source could not be fetched or failed verification."""


def extract_tarball(archive: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        with tarfile.open(archive) as tf:
            tf.extractall(tmp, filter="data")
        entries = list(Path(tmp).iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            shutil.move(str(entries[0]), dest)
        else:
            dest.mkdir()
            for entry in entries:
                shutil.move(str(entry), dest / entry.name)


def _sidecar_sums(recipe_dir: Path) -> dict[str, str]:
    sums = {}
    for line in (recipe_dir / "SHA256SUMS").read_text().splitlines():
        if line.strip():
            sha, name = line.split(maxsplit=1)
            sums[name.strip()] = sha
    return sums


def fetch_source(
    recipe: Recipe,
    workdir: Path,
    root: Path,
    cache: Path,
    *,
    arch: str | None = None,
    download_fn: Callable[[str, Path], str] = download,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    src = workdir / "src"
    if src.exists():
        shutil.rmtree(src)
    workdir.mkdir(parents=True, exist_ok=True)
    s = recipe.source

    if s.type == "none":
        src.mkdir()
    elif s.type == "local":
        src.mkdir()
        for p in s.paths:
            if (root / p).is_dir():
                shutil.copytree(root / p, src / Path(p).name, ignore=IGNORE)
            else:
                shutil.copy2(root / p, src / Path(p).name)
    elif s.type == "arch-url":
        if arch is None:
            raise FetchError(f"{recipe.name}: arch-url sources need the target architecture")
        url = s.url_for(arch, recipe.version)
        name = url.rsplit("/", 1)[-1]
        expected = _sidecar_sums(recipe.dir).get(name)
        if expected is None:
            raise FetchError(f"{recipe.name}: {name} missing from SHA256SUMS; run emcomm-build bump")
        cached = cache / f"{recipe.name}-{name}"
        got = sha256_file(cached) if cached.exists() else None
        if got != expected:
            got = download_fn(url, cached)
        if got != expected:
            cached.unlink(missing_ok=True)
            raise FetchError(f"{recipe.name}: sha256 mismatch for {url}: expected {expected}, got {got}")
        src.mkdir()
        shutil.copy2(cached, src / name)  # build.sh unpacks/installs the upstream artifact
    elif s.type == "git":
        run(["git", "clone", "--quiet", "--depth", "1", "--branch",
             s.resolved_ref(recipe.version), s.url, str(src)], check=True)
    elif s.type == "github-release-asset":
        url = asset_url(s.repo, s.ref or "{version}", s.asset, recipe.version)
        archive = cache / f"{recipe.name}-{recipe.version}-{url.rsplit('/', 1)[-1]}"
        got = sha256_file(archive) if archive.exists() else None
        if got != s.sha256:
            got = download_fn(url, archive)
        if got != s.sha256:
            archive.unlink(missing_ok=True)
            raise FetchError(
                f"{recipe.name}: sha256 mismatch for {url}: expected {s.sha256}, got {got}"
            )
        extract_tarball(archive, src)
    else:
        raise FetchError(f"{recipe.name}: unknown source type {s.type!r}")
    return src
```

- [ ] **Step 4: Run the tests**

Run: `uv run --directory tools pytest -q && uv run --directory tools ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools
git commit -m "feat(build): fetch recipe sources (asset, git, local)"
```

---

### Task 6: Containerized builds

**Files:**
- Create: `tools/src/emcomm_build/container.py`
- Create: `tools/container/build.sh`, `tools/container/runtime-deps.sh`, `tools/container/repos.sh`
- Test: `tools/tests/test_container.py`, `tools/tests/integration/test_container_build.py`, `tools/tests/integration/__init__.py` (empty)

**Interfaces:**
- Consumes: `model.Recipe`, `model.Target`.
- Produces:
  - `Engine(command="podman")`, `engine_from_env() -> Engine` (reads `EMCOMM_CONTAINER_ENGINE`)
  - `build_deps(recipe, target) -> list[str]`
  - `build_command(engine, recipe, target, root, workdir) -> list[str]`
  - `run_build(engine, recipe, target, root, workdir, *, run=subprocess.run) -> tuple[Path, list[str]]`: returns the destdir and the runtime package dependencies that were auto-detected from the ELF files.
  - `pin_text(repo: ExtraRepo) -> str` and `write_repo_files(target, dest: Path) -> None`. For each extra repo these write `<name>.sources` (deb822) and `<name>.pref` (apt pin limited to `pin_packages`). `tools/container/repos.sh` installs them inside build and smoke containers, and the Ansible base role writes the same content on real machines.
- Container contract (used by every recipe `build.sh`):
  - The repo is mounted read-only at `/emcomm`, and `/work` holds `src/`, `deps/`, and `destdir/`.
  - `build.sh` runs with cwd `$SRC` and these variables: `PREFIX=/opt/emcomm`, `DESTDIR=/work/destdir`, `SRC=/work/src`, `JOBS`, `VERSION`, `PKG_CONFIG_PATH=/opt/emcomm/lib/pkgconfig`, `CMAKE_PREFIX_PATH=/opt/emcomm`, and `LDFLAGS` containing `-Wl,-rpath,/opt/emcomm/lib`.
  - Packages in `/work/deps` (our previously built emcomm packages) are installed before the build.
  - `/work/runtime-deps.txt` receives the distro packages that own every shared library the built ELF files link against.

- [ ] **Step 1: Write the failing unit test**

`tools/tests/test_container.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --directory tools pytest -q tests/test_container.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.container'`.

- [ ] **Step 3: Implement `container.py`**

```python
"""Run recipe builds inside pristine distro containers."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .model import ExtraRepo, Recipe, Target


@dataclass(frozen=True)
class Engine:
    command: str = "podman"


def engine_from_env() -> Engine:
    return Engine(os.environ.get("EMCOMM_CONTAINER_ENGINE", "podman"))


def build_deps(recipe: Recipe, target: Target) -> list[str]:
    return [*target.base_build_deps, *recipe.deps_for(target.family).build]


def build_command(
    engine: Engine, recipe: Recipe, target: Target, root: Path, workdir: Path
) -> list[str]:
    return [
        engine.command, "run", "--rm",
        "-v", f"{root}:/emcomm:ro,z",
        "-v", f"{workdir}:/work:z",
        "-e", f"FAMILY={target.family}",
        "-e", f"BUILD_DEPS={' '.join(build_deps(recipe, target))}",
        "-e", f"RECIPE_DIR=/emcomm/recipes/{recipe.name}",
        "-e", f"VERSION={recipe.version}",
        target.image, "bash", "/emcomm/tools/container/build.sh",
    ]


def pin_text(repo: ExtraRepo) -> str:
    suite = next(line.split(":", 1)[1].strip() for line in repo.deb822.splitlines()
                 if line.startswith("Suites:"))
    return (f"Package: {' '.join(repo.pin_packages)}\n"
            f"Pin: release n={suite}\n"
            f"Pin-Priority: {repo.pin_priority}\n")


def write_repo_files(target: Target, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for repo in target.extra_repos:
        (dest / f"{repo.name}.sources").write_text(repo.deb822)
        (dest / f"{repo.name}.pref").write_text(pin_text(repo))


def run_build(
    engine: Engine,
    recipe: Recipe,
    target: Target,
    root: Path,
    workdir: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[Path, list[str]]:
    destdir = workdir / "destdir"
    if destdir.exists():
        shutil.rmtree(destdir)
    destdir.mkdir(parents=True)
    deps_file = workdir / "runtime-deps.txt"
    deps_file.unlink(missing_ok=True)
    write_repo_files(target, workdir / "repos")
    run(build_command(engine, recipe, target, root, workdir), check=True)
    runtime = []
    if deps_file.exists():
        runtime = [line.strip() for line in deps_file.read_text().splitlines() if line.strip()]
    return destdir, runtime
```

- [ ] **Step 4: Create `tools/container/build.sh`**

```bash
#!/usr/bin/env bash
# Runs inside the target distro container. Installs build dependencies and any
# already-built emcomm packages from /work/deps, then runs the recipe's build.sh
# so that it installs into /work/destdir/opt/emcomm.
set -euo pipefail

bash /emcomm/tools/container/repos.sh

install_packages() {
  case "$FAMILY" in
    debian)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      # shellcheck disable=SC2086  # BUILD_DEPS is a word list
      apt-get install -y -qq --no-install-recommends $BUILD_DEPS >/dev/null
      shopt -s nullglob
      local debs=(/work/deps/*.deb)
      shopt -u nullglob
      if ((${#debs[@]})); then apt-get install -y -qq "${debs[@]}" >/dev/null; fi
      ;;
    fedora|el)
      # shellcheck disable=SC2086
      dnf -y -q install $BUILD_DEPS
      shopt -s nullglob
      local rpms=(/work/deps/*.rpm)
      shopt -u nullglob
      if ((${#rpms[@]})); then dnf -y -q install "${rpms[@]}"; fi
      ;;
    *)
      echo "unsupported family: $FAMILY" >&2
      exit 1
      ;;
  esac
}

install_packages

export PREFIX=/opt/emcomm
export DESTDIR=/work/destdir
export SRC=/work/src
JOBS=$(nproc)
export JOBS
export PKG_CONFIG_PATH=/opt/emcomm/lib/pkgconfig
export CMAKE_PREFIX_PATH=/opt/emcomm
export LDFLAGS="-Wl,-rpath,/opt/emcomm/lib ${LDFLAGS:-}"

cd "$SRC"
bash "$RECIPE_DIR/build.sh"
find "$DESTDIR" -name '*.la' -delete
bash /emcomm/tools/container/runtime-deps.sh "$DESTDIR" > /work/runtime-deps.txt
```

Also create `tools/container/repos.sh`. It is shared by build.sh and smoke.sh:

```bash
#!/usr/bin/env bash
# Install the target's extra repos and apt pins written by the build tool into /work/repos.
set -euo pipefail
shopt -s nullglob
case "$FAMILY" in
  debian)
    for f in /work/repos/*.sources; do cp "$f" "/etc/apt/sources.list.d/emcomm-$(basename "$f")"; done
    for f in /work/repos/*.pref; do cp "$f" "/etc/apt/preferences.d/emcomm-$(basename "$f")"; done
    ;;
esac
```

- [ ] **Step 5: Create `tools/container/runtime-deps.sh`**

```bash
#!/usr/bin/env bash
# Print the distro packages that own the shared libraries needed by ELF files under $1.
# Libraries under /opt/emcomm (our own packages) and unresolved libraries are skipped;
# the smoke test catches anything left unresolved after installation.
set -euo pipefail
root=$1
declare -A libs=()

while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q '^ELF'; then
    while read -r lib; do
      libs["$lib"]=1
    done < <(ldd "$f" 2>/dev/null | awk '$2 == "=>" && $3 ~ /^\// {print $3}')
  fi
done < <(find "$root" -type f -print0)

owner() {
  local lib=$1 real
  real=$(readlink -f "$lib")
  case "$FAMILY" in
    debian)
      dpkg -S "$lib" 2>/dev/null || dpkg -S "$real" 2>/dev/null || dpkg -S "/usr$lib" 2>/dev/null || true
      ;;
    fedora|el)
      rpm -qf --qf '%{NAME}\n' "$real" 2>/dev/null | grep -v 'not owned' || true
      ;;
  esac
}

for lib in "${!libs[@]}"; do
  case "$lib" in /opt/emcomm/*) continue ;; esac
  owner "$lib"
done | sed -E 's/^([^:, ]+)(:[a-z0-9]+)?: .*/\1/' | grep -v '^emcomm-' | sort -u
```

- [ ] **Step 6: Write the container integration test**

`tools/tests/integration/test_container_build.py`:

```python
import platform
import shutil

import pytest

from emcomm_build.container import Engine, run_build
from emcomm_build.model import load_recipes, load_targets

from conftest import REAL_ROOT, TARGETS, write_recipe

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
```

- [ ] **Step 7: Run the tests**

Run: `uv run --directory tools pytest -q tests/test_container.py && uv run --directory tools pytest -q -m container tests/integration/test_container_build.py`
Expected: unit tests PASS. The integration tests PASS on a host with podman and network access (each pulls an image and installs `build-essential`/`gcc`).

Run: `shellcheck tools/container/*.sh`
Expected: no findings.

- [ ] **Step 8: Commit**

```bash
git add tools
git commit -m "feat(build): containerized recipe builds with runtime dependency detection"
```

---

### Task 7: nFPM packaging

**Files:**
- Create: `tools/src/emcomm_build/package.py`
- Test: `tools/tests/test_package.py`

**Interfaces:**
- Consumes: `model.Recipe`, `model.Target`, `plan.full_release`.
- Produces:
  - `MAINTAINER: str`
  - `depends_list(recipe, target, recipes, runtime_deps) -> list[str]`
  - `content_entries(tree: Path) -> list[dict]`: one entry per file or symlink. Paths under `/etc/` are `type: config|noreplace`.
  - `nfpm_config(recipe, target, arch, recipes, tree: Path | None, runtime_deps) -> dict`
  - `build_package(cfg, fmt, out, workdir, *, run=subprocess.run) -> Path`

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_package.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q tests/test_package.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.package'`.

- [ ] **Step 3: Implement `package.py`**

```python
"""Turn a built tree into .deb/.rpm packages with nFPM."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml

from .model import Recipe, Target
from .plan import full_release

MAINTAINER = "emcommOS maintainers <maintainers@emcommos.invalid>"


def depends_list(
    recipe: Recipe, target: Target, recipes: dict[str, Recipe], runtime_deps: list[str]
) -> list[str]:
    deps = set(runtime_deps) | set(recipe.deps_for(target.family).run)
    deps |= {recipes[d].package for d in (*recipe.depends_on, *recipe.requires)}
    if recipe.name != "base" and "base" in recipes:
        deps.add(recipes["base"].package)
    return sorted(deps)


def content_entries(tree: Path) -> list[dict]:
    entries: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(tree):
        here = Path(dirpath)
        names = [d for d in dirnames if (here / d).is_symlink()] + filenames
        for name in sorted(names):
            path = here / name
            dst = "/" + path.relative_to(tree).as_posix()
            if path.is_symlink():
                entries.append({"src": os.readlink(path), "dst": dst, "type": "symlink"})
            else:
                entry = {"src": str(path), "dst": dst,
                         "file_info": {"mode": path.stat().st_mode & 0o7777}}
                if dst.startswith("/etc/"):
                    entry["type"] = "config|noreplace"
                entries.append(entry)
    return sorted(entries, key=lambda e: e["dst"])


def nfpm_config(
    recipe: Recipe,
    target: Target,
    arch: str,
    recipes: dict[str, Recipe],
    tree: Path | None,
    runtime_deps: list[str],
) -> dict:
    cfg: dict = {
        "name": recipe.package,
        "arch": arch,
        "platform": "linux",
        "version": recipe.version,
        "version_schema": "none",
        "release": full_release(recipe, target),
        "maintainer": MAINTAINER,
        "description": recipe.description or recipe.summary,
        "vendor": "emcommOS",
        "license": recipe.license,
        "depends": depends_list(recipe, target, recipes, runtime_deps),
        "contents": content_entries(tree) if tree else [],
    }
    if recipe.homepage:
        cfg["homepage"] = recipe.homepage
    if target.format == "rpm":
        cfg["rpm"] = {"summary": recipe.summary}
    return cfg


def build_package(
    cfg: dict,
    fmt: str,
    out: Path,
    workdir: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    cfg_path = workdir / f"nfpm-{fmt}.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["nfpm", "package", "--config", str(cfg_path), "--packager", fmt, "--target", str(out)],
        check=True)
    return out
```

- [ ] **Step 4: Run the tests**

Run: `uv run --directory tools pytest -q tests/test_package.py && uv run --directory tools ruff check .`
Expected: PASS. The `nfpm` test is skipped if nfpm isn't installed; install it from https://github.com/goreleaser/nfpm/releases (v2.41.1) to run it.

- [ ] **Step 5: Commit**

```bash
git add tools
git commit -m "feat(build): nFPM package configs with auto runtime dependencies"
```

---

### Task 8: Build orchestrator, smoke tests, and the `build` command

**Files:**
- Create: `tools/src/emcomm_build/build.py`, `tools/container/smoke.sh`
- Modify: `tools/src/emcomm_build/cli.py` (add `build`)
- Test: `tools/tests/test_build.py`, `tools/tests/integration/test_build_smoke.py`

**Interfaces:**
- Consumes: `plan.{plan_builds, closure, package_filename, repo_path, published_files, fetch_manifest}`, `fetch.fetch_source`, `container.{Engine, run_build}`, `package.{nfpm_config, build_package}`, `net.download`.
- Produces:
  - `BuildError(Exception)`
  - `BuildSettings(root, target: Target, arch, out: Path, work: Path, repo_url: str | None, channel="testing", only=(), force=False, smoke=True, engine=Engine())`
  - `host_arch() -> str`
  - `stage(recipes, names, settings, manifest, dest: Path) -> list[Path]`: copies or downloads the packages for `closure(names)` into `dest`.
  - `smoke(recipes, names, settings, manifest) -> None`
  - `run(settings, *, recipes=None) -> list[Path]`: returns the built package paths.
- Smoke contract: each recipe may ship `recipes/<name>/smoke.sh`. It runs with `bash` in a fresh container after every package is installed, with `/opt/emcomm/bin` on PATH and the repo at `/emcomm`. Before any recipe smoke script runs, every ELF under `/opt/emcomm` must resolve all of its libraries.

- [ ] **Step 1: Write the failing unit tests**

`tools/tests/test_build.py`:

```python
import pytest

from emcomm_build import build as b
from emcomm_build.model import load_recipes, load_targets

from conftest import app, write_recipe


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q tests/test_build.py`
Expected: FAIL with `ImportError: cannot import name 'build'`.

- [ ] **Step 3: Implement `build.py`**

```python
"""Orchestrate fetch → container build → package → smoke for one target/arch."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .container import Engine, run_build
from .fetch import fetch_source
from .model import Recipe, Target, load_recipes
from .net import download
from .package import build_package, nfpm_config
from .container import write_repo_files
from .plan import (
    closure, fetch_manifest, package_filename, plan_builds, published_files, recipes_for_target,
)


class BuildError(Exception):
    """A build could not be completed."""


@dataclass(frozen=True)
class BuildSettings:
    root: Path
    target: Target
    arch: str
    out: Path
    work: Path
    repo_url: str | None
    channel: str = "testing"
    only: tuple[str, ...] = ()
    force: bool = False
    smoke: bool = True
    engine: Engine = field(default_factory=Engine)


def host_arch() -> str:
    machine = platform.machine()
    try:
        return {"x86_64": "amd64", "aarch64": "arm64"}[machine]
    except KeyError:
        raise BuildError(f"unsupported host architecture {machine}") from None


def stage(
    recipes: dict[str, Recipe],
    names: list[str],
    settings: BuildSettings,
    manifest: dict | None,
    dest: Path,
) -> list[Path]:
    """Put the packages for names (and everything they need) into dest."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    by_name = {p.rsplit("/", 1)[-1]: p for p in (manifest or {}).get("files", [])}
    staged = []
    for name in sorted(closure(recipes, names)):
        filename = package_filename(recipes[name], settings.target, settings.arch)
        local = settings.out / filename
        target_file = dest / filename
        if local.exists():
            shutil.copy2(local, target_file)
        elif filename in by_name and settings.repo_url:
            url = f"{settings.repo_url.rstrip('/')}/{settings.channel}/{by_name[filename]}"
            download(url, target_file)
        else:
            raise BuildError(f"{recipes[name].package}: {filename} is neither built nor published")
        staged.append(target_file)
    return staged


def smoke(
    recipes: dict[str, Recipe], names: list[str], settings: BuildSettings, manifest: dict | None
) -> None:
    workdir = settings.work / settings.target.name / settings.arch / "_smoke"
    staged = stage(recipes, names, settings, manifest, workdir / "pkgs")
    write_repo_files(settings.target, workdir / "repos")
    skip = " ".join(f"/opt/emcomm/{r.bundle_dir}" for r in recipes.values()
                    if r.bundle_dir and any(p.name.startswith(r.package) for p in staged))
    subprocess.run(
        [
            settings.engine.command, "run", "--rm",
            "-v", f"{settings.root}:/emcomm:ro,z",
            "-v", f"{workdir}:/work:z",
            "-e", f"FAMILY={settings.target.family}",
            "-e", f"SMOKE_RECIPES={' '.join(names)}",
            "-e", f"SMOKE_SKIP_PATHS={skip}",
            settings.target.image, "bash", "/emcomm/tools/container/smoke.sh",
        ],
        check=True,
    )


def run(settings: BuildSettings, *, recipes: dict[str, Recipe] | None = None) -> list[Path]:
    target, arch = settings.target, settings.arch
    recipes = recipes_for_target(recipes or load_recipes(settings.root), target)
    manifest = (
        fetch_manifest(settings.repo_url, settings.channel, target.name, arch)
        if settings.repo_url
        else None
    )
    published = published_files(manifest)
    todo = plan_builds(recipes, target, arch, published, settings.only, settings.force)
    if not todo:
        print(f"{target.name}/{arch}: everything is already published")
        return []

    settings.out.mkdir(parents=True, exist_ok=True)
    built: list[Path] = []
    for name in todo:
        r = recipes[name]
        print(f"==> {target.name}/{arch}: {r.package} {r.version}-{r.release}")
        workdir = settings.work / target.name / arch / name
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True)
        deps = [*r.depends_on, *r.requires]
        if deps:
            stage(recipes, deps, settings, manifest, workdir / "deps")
        else:
            (workdir / "deps").mkdir()

        if r.kind == "app":
            fetch_source(r, workdir, settings.root, settings.work / "cache", arch=arch)
            tree, runtime = run_build(settings.engine, r, target, settings.root, workdir)
        elif r.kind == "files":
            tree, runtime = r.dir / r.files_dir, []
        else:
            tree, runtime = None, []

        cfg = nfpm_config(r, target, arch, recipes, tree, runtime)
        out = settings.out / package_filename(r, target, arch)
        built.append(build_package(cfg, target.format, out, workdir))

    if settings.smoke:
        smoke(recipes, todo, settings, manifest)
    return built
```

- [ ] **Step 4: Create `tools/container/smoke.sh`**

```bash
#!/usr/bin/env bash
# Install freshly built packages into a pristine container, verify every ELF under
# /opt/emcomm resolves its shared libraries, then run each recipe's smoke.sh.
# SMOKE_SKIP_PATHS lists self-contained bundles (extracted AppImages) whose libraries are
# resolved by their own launcher, not by rpath.
set -euo pipefail
bash /emcomm/tools/container/repos.sh
case "$FAMILY" in
  debian)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq /work/pkgs/*.deb file >/dev/null
    ;;
  fedora|el)
    dnf -y -q install /work/pkgs/*.rpm file
    ;;
esac
export PATH=/opt/emcomm/bin:$PATH

failed=0
skipped() {
  local p
  for p in ${SMOKE_SKIP_PATHS:-}; do [[ $1 == "$p"/* ]] && return 0; done
  return 1
}
while IFS= read -r -d '' f; do
  skipped "$f" && continue
  if file -b "$f" | grep -q '^ELF' && ldd "$f" 2>/dev/null | grep -q 'not found'; then
    echo "unresolved libraries in $f:"
    ldd "$f" | grep 'not found'
    failed=1
  fi
done < <(find /opt/emcomm -type f -print0)
if ((failed)); then exit 1; fi

for name in $SMOKE_RECIPES; do
  script=/emcomm/recipes/$name/smoke.sh
  if [[ -f $script ]]; then
    echo "== smoke: $name"
    bash "$script"
  fi
done
echo "smoke OK"
```

- [ ] **Step 5: Add the `build` command to `cli.py`**

Add these imports:

```python
import os
from pathlib import Path

from .build import BuildError, BuildSettings, host_arch
from .build import run as run_builds
from .container import engine_from_env
```

Add this handler:

```python
def cmd_build(args: argparse.Namespace) -> int:
    root = repo_root()
    targets = load_targets(root)
    if args.target not in targets:
        raise DefinitionError(f"unknown target {args.target!r}; known: {', '.join(targets)}")
    arch = args.arch or host_arch()
    if arch != host_arch():
        raise DefinitionError(f"cannot build {arch} on a {host_arch()} host (no emulation)")
    settings = BuildSettings(
        root=root,
        target=targets[args.target],
        arch=arch,
        out=Path(args.out) if args.out else root / "dist" / args.target / arch,
        work=Path(args.work) if args.work else root / "build",
        repo_url=args.repo_url or os.environ.get("EMCOMM_REPO_URL") or None,
        channel=args.channel,
        only=tuple(args.only),
        force=args.force,
        smoke=not args.no_smoke,
        engine=engine_from_env(),
    )
    built = run_builds(settings)
    for path in built:
        print(f"built {path}")
    return 0
```

Register it in `build_parser`:

```python
    b = sub.add_parser("build", help="build packages for one target on this host")
    b.add_argument("--target", required=True)
    b.add_argument("--arch", help="defaults to the host architecture")
    b.add_argument("--out", help="output dir (default dist/<target>/<arch>)")
    b.add_argument("--work", help="scratch dir (default build/)")
    b.add_argument("--repo-url", help="published repo base URL (default $EMCOMM_REPO_URL)")
    b.add_argument("--channel", default="testing")
    b.add_argument("--only", action="append", default=[], help="build only this recipe + deps")
    b.add_argument("--force", action="store_true", help="rebuild even if already published")
    b.add_argument("--no-smoke", action="store_true")
    b.set_defaults(func=cmd_build)
```

In `main`, catch the extra error types:

```python
    except (DefinitionError, BuildError, FetchError, subprocess.CalledProcessError) as exc:
```

Add `import subprocess` and `from .fetch import FetchError` at the top.

- [ ] **Step 6: Write the end-to-end integration test**

`tools/tests/integration/test_build_smoke.py`:

```python
import shutil

import pytest

from emcomm_build.build import BuildSettings, host_arch, run
from emcomm_build.model import load_targets

from .test_container_build import hello_repo  # noqa: F401  (fixture)

pytestmark = [pytest.mark.container, pytest.mark.nfpm]


@pytest.mark.parametrize("target", ["debian-13", "fedora-44"])
def test_build_package_and_smoke(hello_repo, tmp_path, target):  # noqa: F811
    if shutil.which("nfpm") is None:
        pytest.skip("nfpm not installed")
    settings = BuildSettings(root=hello_repo, target=load_targets(hello_repo)[target],
                             arch=host_arch(), out=tmp_path / "dist", work=tmp_path / "work",
                             repo_url=None)
    built = run(settings)
    assert len(built) == 1 and built[0].exists()
```

- [ ] **Step 7: Run the tests**

Run: `uv run --directory tools pytest -q -m "not container and not nfpm" && uv run --directory tools ruff check . && shellcheck tools/container/*.sh`
Expected: PASS.

Run (with podman and nfpm installed): `uv run --directory tools pytest -q -m "container and nfpm"`
Expected: PASS; the output ends with `smoke OK`.

- [ ] **Step 8: Commit**

```bash
git add tools
git commit -m "feat(build): build orchestrator with dependency staging and smoke tests"
```

---

### Task 9: Signed repository publishing

**Files:**
- Create: `tools/src/emcomm_build/publish.py`, `tools/container/publish.sh`
- Modify: `tools/src/emcomm_build/cli.py` (add `publish`)
- Test: `tools/tests/test_publish.py`, `tools/tests/integration/test_publish_install.py`

**Interfaces:**
- Consumes: `model.{Target, RPM_ARCH, ARCHES}`, `plan.repo_path`, `container.Engine`, `package.{nfpm_config, build_package}` (tests only).
- Produces:
  - `place_packages(dist, repo, targets) -> dict[tuple[str, str], list[Path]]`. The input layout is `dist/<target>/<arch>/*.{deb,rpm}`.
  - `write_manifests(repo, targets) -> None`
  - `publish_command(engine, root, repo, targets, new_rpms, key_file, passphrase_file) -> list[str]`
  - `publish(root, dist, repo, targets, key_file, passphrase_file, public_key, *, engine=Engine(), run=subprocess.run) -> None`
- Channel tree layout (served statically):
  ```
  <channel>/emcomm-archive-keyring.asc
  <channel>/deb/dists/<target>/{Release,InRelease,Release.gpg,main/binary-<arch>/Packages{,.gz}}
  <channel>/deb/pool/<target>/*.deb
  <channel>/rpm/<target>/<x86_64|aarch64>/{*.rpm,repodata/,repodata/repomd.xml.asc}
  <channel>/manifest/<target>-<arch>.json
  ```
- Client config:
  - Debian: `URIs: <url>/<channel>/deb`, `Suites: debian-13`, `Components: main`, `Signed-By: /usr/share/keyrings/emcomm-archive-keyring.asc`
  - Fedora: `baseurl=<url>/<channel>/rpm/fedora-$releasever/$basearch`, `gpgcheck=1`, `repo_gpgcheck=1`

- [ ] **Step 1: Write the failing unit tests**

`tools/tests/test_publish.py`:

```python
import json
from pathlib import Path

from emcomm_build.container import Engine
from emcomm_build.model import load_targets
from emcomm_build.publish import place_packages, publish_command, write_manifests


def make_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "debian-13/amd64").mkdir(parents=True)
    (dist / "debian-13/amd64/emcomm-a_1.0-1+deb13_amd64.deb").write_text("d")
    (dist / "fedora-44/arm64").mkdir(parents=True)
    (dist / "fedora-44/arm64/emcomm-a-1.0-1.fc44.aarch64.rpm").write_text("r")
    return dist


def test_place_and_manifest(fake_repo, tmp_path):
    targets = load_targets(fake_repo)
    repo = tmp_path / "public/testing"
    placed = place_packages(make_dist(tmp_path), repo, targets)
    assert (repo / "deb/pool/debian-13/emcomm-a_1.0-1+deb13_amd64.deb").is_file()
    assert (repo / "rpm/fedora-44/aarch64/emcomm-a-1.0-1.fc44.aarch64.rpm").is_file()
    assert set(placed) == {("debian-13", "amd64"), ("fedora-44", "arm64")}
    write_manifests(repo, targets)
    m = json.loads((repo / "manifest/debian-13-amd64.json").read_text())
    assert m == {"target": "debian-13", "arch": "amd64",
                 "files": ["deb/pool/debian-13/emcomm-a_1.0-1+deb13_amd64.deb"]}
    assert not (repo / "manifest/debian-13-arm64.json").exists()
    assert json.loads((repo / "manifest/fedora-44-arm64.json").read_text())["files"] == [
        "rpm/fedora-44/aarch64/emcomm-a-1.0-1.fc44.aarch64.rpm"]


def test_publish_command(fake_repo, tmp_path):
    targets = load_targets(fake_repo)
    repo = tmp_path / "repo"
    place_packages(make_dist(tmp_path), repo, targets)
    cmd = publish_command(Engine(), Path("/src"), repo, targets,
                          ["rpm/fedora-44/aarch64/x.rpm"], tmp_path / "k.asc", tmp_path / "pp")
    assert "DEB_SUITES=debian-13" in cmd
    assert "RPM_DIRS=rpm/fedora-44/aarch64" in cmd
    assert "NEW_RPMS=rpm/fedora-44/aarch64/x.rpm" in cmd
    assert f"{tmp_path / 'k.asc'}:/keys/signing.asc:ro,z" in cmd
    assert cmd[-3:] == ["docker.io/library/debian:13", "bash", "/emcomm/tools/container/publish.sh"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q tests/test_publish.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.publish'`.

- [ ] **Step 3: Implement `publish.py`**

```python
"""Assemble and sign the static package repository tree for one channel."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .container import Engine
from .model import ARCHES, RPM_ARCH, Target
from .plan import repo_path

PUBLISH_IMAGE = "docker.io/library/debian:13"


def place_packages(
    dist: Path, repo: Path, targets: dict[str, Target]
) -> dict[tuple[str, str], list[Path]]:
    placed: dict[tuple[str, str], list[Path]] = {}
    for tdir in sorted(p for p in dist.iterdir() if p.is_dir()):
        target = targets[tdir.name]
        for adir in sorted(p for p in tdir.iterdir() if p.is_dir()):
            for pkg in sorted(adir.glob(f"*.{target.format}")):
                dest = repo / repo_path(target, adir.name, pkg.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pkg, dest)
                placed.setdefault((target.name, adir.name), []).append(dest)
    return placed


def write_manifests(repo: Path, targets: dict[str, Target]) -> None:
    for t in targets.values():
        for arch in ARCHES:
            if t.format == "deb":
                files = sorted(repo.glob(f"deb/pool/{t.name}/*_{arch}.deb"))
            else:
                files = sorted(repo.glob(f"rpm/{t.name}/{RPM_ARCH[arch]}/*.rpm"))
            if not files:
                continue
            manifest = {"target": t.name, "arch": arch,
                        "files": [f.relative_to(repo).as_posix() for f in files]}
            out = repo / "manifest" / f"{t.name}-{arch}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(manifest, indent=2) + "\n")


def publish_command(
    engine: Engine,
    root: Path,
    repo: Path,
    targets: dict[str, Target],
    new_rpms: list[str],
    key_file: Path,
    passphrase_file: Path,
) -> list[str]:
    deb_suites = sorted(
        t.name for t in targets.values()
        if t.format == "deb" and (repo / "deb/pool" / t.name).is_dir()
    )
    rpm_dirs = sorted(p.relative_to(repo).as_posix() for p in repo.glob("rpm/*/*") if p.is_dir())
    return [
        engine.command, "run", "--rm",
        "-v", f"{root}:/emcomm:ro,z",
        "-v", f"{repo}:/repo:z",
        "-v", f"{key_file}:/keys/signing.asc:ro,z",
        "-v", f"{passphrase_file}:/keys/passphrase:ro,z",
        "-e", f"DEB_SUITES={' '.join(deb_suites)}",
        "-e", f"RPM_DIRS={' '.join(rpm_dirs)}",
        "-e", f"NEW_RPMS={' '.join(new_rpms)}",
        PUBLISH_IMAGE, "bash", "/emcomm/tools/container/publish.sh",
    ]


def publish(
    root: Path,
    dist: Path,
    repo: Path,
    targets: dict[str, Target],
    key_file: Path,
    passphrase_file: Path,
    public_key: Path,
    *,
    engine: Engine = Engine(),
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    placed = place_packages(dist, repo, targets)
    new_rpms = [p.relative_to(repo).as_posix()
                for files in placed.values() for p in files if p.suffix == ".rpm"]
    run(publish_command(engine, root, repo, targets, new_rpms, key_file, passphrase_file),
        check=True)
    shutil.copy2(public_key, repo / "emcomm-archive-keyring.asc")
    write_manifests(repo, targets)
```

- [ ] **Step 4: Create `tools/container/publish.sh`**

```bash
#!/usr/bin/env bash
# Index and sign the channel tree mounted at /repo. Runs in debian:13 with the
# signing key mounted at /keys/signing.asc and its passphrase at /keys/passphrase.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends apt-utils createrepo-c rpm gnupg ca-certificates >/dev/null

GNUPGHOME=$(mktemp -d)
export GNUPGHOME
chmod 700 "$GNUPGHOME"
echo allow-loopback-pinentry > "$GNUPGHOME/gpg-agent.conf"
gpg --batch --quiet --pinentry-mode loopback --passphrase-file /keys/passphrase \
    --import /keys/signing.asc
KEYID=$(gpg --batch --list-secret-keys --with-colons | awk -F: '$1 == "sec" {print $5; exit}')
SIGN=(gpg --batch --yes --pinentry-mode loopback --passphrase-file /keys/passphrase
      --local-user "$KEYID")

cd /repo

for suite in $DEB_SUITES; do
  dist=deb/dists/$suite
  for arch in amd64 arm64; do
    mkdir -p "$dist/main/binary-$arch"
    (cd deb && apt-ftparchive --arch "$arch" packages "pool/$suite") > "$dist/main/binary-$arch/Packages"
    gzip -9kf "$dist/main/binary-$arch/Packages"
  done
  apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=emcommOS \
    -o APT::FTPArchive::Release::Label=emcommOS \
    -o "APT::FTPArchive::Release::Suite=$suite" \
    -o "APT::FTPArchive::Release::Codename=$suite" \
    -o "APT::FTPArchive::Release::Architectures=amd64 arm64" \
    -o APT::FTPArchive::Release::Components=main \
    release "$dist" > /tmp/Release
  mv /tmp/Release "$dist/Release"
  "${SIGN[@]}" --clearsign -o "$dist/InRelease" "$dist/Release"
  "${SIGN[@]}" --armor --detach-sign -o "$dist/Release.gpg" "$dist/Release"
done

cat > "$HOME/.rpmmacros" <<EOF
%_gpg_name $KEYID
%_gpg_path $GNUPGHOME
%_gpg_sign_cmd_extra_args --batch --pinentry-mode loopback --passphrase-file /keys/passphrase
EOF
for rpm_file in $NEW_RPMS; do
  rpmsign --addsign "$rpm_file" >/dev/null
done
for dir in $RPM_DIRS; do
  createrepo_c --quiet --update "$dir"
  "${SIGN[@]}" --armor --detach-sign -o "$dir/repodata/repomd.xml.asc" "$dir/repodata/repomd.xml"
done
echo "publish OK"
```

- [ ] **Step 5: Add the `publish` command to `cli.py`**

Add the import:

```python
from .publish import publish
```

Add the handler:

```python
def cmd_publish(args: argparse.Namespace) -> int:
    root = repo_root()
    publish(root, Path(args.dist), Path(args.repo_dir), load_targets(root),
            Path(args.key_file), Path(args.passphrase_file),
            Path(args.public_key) if args.public_key else root / "keys/emcomm-archive-keyring.asc",
            engine=engine_from_env())
    print(f"published {args.repo_dir}")
    return 0
```

Register it:

```python
    pub = sub.add_parser("publish", help="add built packages to a channel tree and sign it")
    pub.add_argument("--dist", required=True, help="dir laid out as <target>/<arch>/*.pkg")
    pub.add_argument("--repo-dir", required=True, help="local copy of the channel tree")
    pub.add_argument("--key-file", required=True, help="armored secret signing (sub)key")
    pub.add_argument("--passphrase-file", required=True, help="file with the key passphrase")
    pub.add_argument("--public-key", help="default keys/emcomm-archive-keyring.asc")
    pub.set_defaults(func=cmd_publish)
```

- [ ] **Step 6: Write the publish→install integration test**

`tools/tests/integration/test_publish_install.py`:

```python
import platform
import shutil
import subprocess

import pytest

from emcomm_build.build import host_arch
from emcomm_build.model import FamilyDeps, Recipe, load_targets
from emcomm_build.package import build_package, nfpm_config
from emcomm_build.plan import package_filename
from emcomm_build.publish import publish

from conftest import REAL_ROOT

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
```

The demo meta package has no `base` recipe, so `depends` is empty and the install needs nothing else.

- [ ] **Step 7: Run the tests**

Run: `uv run --directory tools pytest -q -m "not container and not nfpm" && shellcheck tools/container/*.sh`
Expected: PASS.

Run: `uv run --directory tools pytest -q -m "container and nfpm" tests/integration/test_publish_install.py`
Expected: PASS. Debian installs through signed `InRelease`, and Fedora installs with both the RPM signature check and the `repomd.xml` signature check enforced.

- [ ] **Step 8: Commit**

```bash
git add tools
git commit -m "feat(build): signed apt/dnf repository publishing with manifests"
```

---

### Task 10: `emcomm-base` and hamlib (Fedora) recipes

**Files:**
- Create: `recipes/base/recipe.yaml`, plus these files under `recipes/base/files/`:
  - `etc/profile.d/emcomm.sh`
  - `usr/lib/environment.d/50-emcomm.conf`
  - `opt/emcomm/libexec/emcomm-run`
- Create: `recipes/hamlib/recipe.yaml`, `recipes/hamlib/build.sh`, `recipes/hamlib/smoke.sh`

**Interfaces:**
- Produces:
  - Package `emcomm-base`. It puts `/opt/emcomm/bin` on PATH and `/opt/emcomm/share` on XDG_DATA_DIRS. It also ships `/opt/emcomm/libexec/emcomm-run PROG ARGS…`, which runs `/opt/emcomm/bin/PROG` when that exists and otherwise `PROG` from the system PATH. The systemd units (Task 23) use it, so one unit file works whether rigctld comes from Debian backports (`/usr/bin`) or from our Fedora build (`/opt/emcomm/bin`).
  - Package `emcomm-hamlib` (**Fedora only**, `families: [fedora]`). Fedora ships 4.6.5, which lacks the IC-7300MK2 model and the rigctld CVE fixes. Debian gets 4.7.2 from `trixie-backports` (Task 2 targets, Task 22 role).

- [ ] **Step 1: Create the base recipe**

`recipes/base/recipe.yaml`:

```yaml
name: base
kind: files
summary: emcommOS environment (PATH, menus, service launcher for /opt/emcomm)
description: >
  Adds /opt/emcomm/bin to PATH and /opt/emcomm/share to XDG_DATA_DIRS for login
  shells and systemd user sessions, and provides the emcomm-run launcher used by
  emcomm's systemd user units.
license: Apache-2.0
version: "1.0.0"
release: 1
files_dir: files
```

`recipes/base/files/etc/profile.d/emcomm.sh`:

```sh
# emcommOS: expose /opt/emcomm binaries and desktop entries.
case ":${PATH}:" in
  *:/opt/emcomm/bin:*) ;;
  *) PATH="/opt/emcomm/bin:${PATH}" ;;
esac
export PATH
case ":${XDG_DATA_DIRS:-}:" in
  *:/opt/emcomm/share:*) ;;
  *) XDG_DATA_DIRS="/opt/emcomm/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" ;;
esac
export XDG_DATA_DIRS
```

`recipes/base/files/usr/lib/environment.d/50-emcomm.conf`:

```
PATH=/opt/emcomm/bin:${PATH}
XDG_DATA_DIRS=/opt/emcomm/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}
```

`recipes/base/files/opt/emcomm/libexec/emcomm-run`, mode 0755 (`chmod 755` before committing; git keeps the bit and nFPM copies the mode):

```sh
#!/bin/sh
# Run PROG from /opt/emcomm/bin when emcomm packages it, otherwise from the system PATH.
# Lets one systemd unit work across distro families with different package sources.
prog=$1
shift
if [ -x "/opt/emcomm/bin/$prog" ]; then
  exec "/opt/emcomm/bin/$prog" "$@"
fi
exec "$prog" "$@"
```

- [ ] **Step 2: Create the hamlib recipe**

`recipes/hamlib/recipe.yaml` (no `sha256` yet; Step 3 adds it):

```yaml
name: hamlib
kind: app
summary: Ham radio rig control library and utilities (rigctl, rigctld)
license: LGPL-2.1-or-later AND GPL-2.0-or-later
homepage: https://hamlib.github.io/
version: "4.7.2"
release: 1
families: [fedora]   # Debian 13 uses trixie-backports (4.7.2)
source:
  type: github-release-asset
  repo: Hamlib/Hamlib
  ref: "{version}"
  asset: "hamlib-{version}.tar.gz"
upstream:
  type: github-releases
  repo: Hamlib/Hamlib
  tag_pattern: '(\d+\.\d+(?:\.\d+)?)'
deps:
  fedora:
    build: [readline-devel, libusb1-devel]
```

`recipes/hamlib/build.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
./configure --prefix="$PREFIX" --libdir="$PREFIX/lib" --disable-static \
  --with-libusb --without-cxx-binding --disable-winradio
make -j"$JOBS"
make install DESTDIR="$DESTDIR"
```

`recipes/hamlib/smoke.sh`:

```bash
#!/usr/bin/env bash
# Dummy rig directly, then through the rigctld hub exactly as emcomm apps use it.
set -euo pipefail
[[ $(/opt/emcomm/bin/rigctl -m 1 f) == 145000000 ]]
/opt/emcomm/bin/rigctld --version | grep -q 'Hamlib 4\.7'
/opt/emcomm/bin/rigctld -m 1 -T 127.0.0.1 -t 4532 &
pid=$!
trap 'kill $pid' EXIT
for _ in $(seq 40); do
  rigctl -m 2 -r 127.0.0.1:4532 f >/dev/null 2>&1 && break
  sleep 0.25
done
[[ $(rigctl -m 2 -r 127.0.0.1:4532 f) == 145000000 ]]
```

- [ ] **Step 3: Pin the release tarball checksum**

Run: `uv run --directory tools emcomm-build bump hamlib 4.7.2`
Expected: `bumped: hamlib`, and a `  sha256: <64 hex>` line now appears under `asset:`.

Run: `uv run --directory tools emcomm-build validate`
Expected: `ok: 3 targets, 2 recipes`

- [ ] **Step 4: Build and smoke-test**

Run: `uv run --directory tools emcomm-build build --target fedora-44 --only hamlib`
Expected: `emcomm-base` and `emcomm-hamlib` build, and the output ends with `smoke OK`.

Run: `uv run --directory tools emcomm-build build --target debian-13 --only base`
Expected: only `emcomm-base` builds (hamlib doesn't apply to Debian), followed by `smoke OK`.

If configure reports a missing library, add the matching `-devel` package to `deps.fedora.build` and re-run.

- [ ] **Step 5: Shellcheck and commit**

Run: `shellcheck recipes/*/build.sh recipes/*/smoke.sh recipes/base/files/opt/emcomm/libexec/emcomm-run`
Expected: no findings.

```bash
git add recipes/base recipes/hamlib
git commit -m "feat(recipes): emcomm-base (env + emcomm-run) and hamlib 4.7.2 for Fedora"
```

---

### Task 11: fldigi and flrig recipes (Debian)

**Files:**
- Create: `recipes/fldigi/{recipe.yaml,build.sh}`, `recipes/flrig/{recipe.yaml,build.sh}`

**Interfaces:**
- Produces: `emcomm-fldigi` (with flarq) and `emcomm-flrig`, both **Debian only** (`families: [debian]`). Debian 13 ships fldigi 4.2.06 and flrig 2.0.05; Fedora 43/44 already ship the current 4.2.13 and 2.0.12, so Fedora uses the distro packages. flmsg and flamp are current enough in both distros, so they get no recipes; the toolset metapackages depend on the distro packages (Task 25).
- fldigi builds against Debian's backports `libhamlib-dev` (4.7.2). The build container gets the backports pin from Task 6 because `libhamlib*` is pinned.

The source is a SourceForge git tag `vX.Y.ZZ` over https. A git checkout has no `configure`, so the build runs `autoreconf -fi`.

- [ ] **Step 1: Create the recipes**

`recipes/fldigi/recipe.yaml`:

```yaml
name: fldigi
kind: app
summary: Fldigi digital modem program and flarq (W1HKJ)
license: GPL-3.0-or-later
homepage: http://www.w1hkj.org/
version: "4.2.13"
release: 1
families: [debian]   # Fedora ships current fldigi
source:
  type: git
  url: https://git.code.sf.net/p/fldigi/fldigi
  ref: "v{version}"
upstream:
  type: git-tags
  url: https://git.code.sf.net/p/fldigi/fldigi
  tag_pattern: 'v(\d+\.\d+\.\d+)'
deps:
  debian:
    build: [autoconf, automake, libtool, gettext, autopoint, libfltk1.3-dev, libpng-dev,
            libsamplerate0-dev, libsndfile1-dev, portaudio19-dev, libpulse-dev, libx11-dev,
            libxft-dev, libudev-dev, libusb-1.0-0-dev, libhamlib-dev]
```

`recipes/fldigi/build.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
autoreconf -fi
./configure --prefix="$PREFIX" --with-hamlib --with-pulseaudio
make -j"$JOBS"
make install DESTDIR="$DESTDIR"
```

`recipes/flrig/recipe.yaml`:

```yaml
name: flrig
kind: app
summary: FLRig transceiver control program (W1HKJ)
license: GPL-3.0-or-later
homepage: http://www.w1hkj.org/
version: "2.0.12"
release: 1
families: [debian]   # Fedora ships current flrig
source:
  type: git
  url: https://git.code.sf.net/p/fldigi/flrig
  ref: "v{version}"
upstream:
  type: git-tags
  url: https://git.code.sf.net/p/fldigi/flrig
  tag_pattern: 'v(\d+\.\d+\.\d+)'
deps:
  debian:
    build: [autoconf, automake, libtool, gettext, autopoint, libfltk1.3-dev, libx11-dev, libxft-dev, libudev-dev]
```

`recipes/flrig/build.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
autoreconf -fi
./configure --prefix="$PREFIX"
make -j"$JOBS"
make install DESTDIR="$DESTDIR"
```

- [ ] **Step 2: Validate, build, smoke**

Run: `uv run --directory tools emcomm-build validate`
Expected: `ok: 3 targets, 4 recipes`

Run: `uv run --directory tools emcomm-build build --target debian-13 --only fldigi --only flrig`
Expected: `smoke OK`. For these GUI apps the smoke test is the generic ELF check: every library must resolve, including Debian's backports libhamlib.

If `autoreconf` fails because m4 macros are missing, add `pkg-config` and the gettext dev packages to the build deps. If a configure check fails, add the named library's `-dev` package.

- [ ] **Step 3: Commit**

```bash
git add recipes/fldigi recipes/flrig
git commit -m "feat(recipes): fldigi 4.2.13 and flrig 2.0.12 for Debian 13"
```

---

### Task 12: JS8Call recipe (upstream AppImage, prebuilt)

**Files:**
- Create: `recipes/js8call/{recipe.yaml,build.sh,smoke.sh,SHA256SUMS}`

**Interfaces:**
- Consumes: `arch-url` sources (Task 5), `bundle_dir` smoke skipping (Task 8).
- Produces: `emcomm-js8call` with the extracted upstream AppImage in `/opt/emcomm/lib/js8call/`, a `/opt/emcomm/bin/js8call` launcher, and a desktop entry.

JS8Call 3.x is developed as **JS8Call-improved**, which publishes only `JS8Call-v<ver>-{x86_64,aarch64}.AppImage`; every distro is still on 2.x. We extract the AppImage at package-build time, so the package needs no FUSE. The binaries keep upstream's bundled Qt. Upstream publishes no checksums, so `emcomm-build bump` pins our own (`SHA256SUMS`) and every later fetch verifies against them.

- [ ] **Step 1: Create the recipe**

`recipes/js8call/recipe.yaml`:

```yaml
name: js8call
kind: app
summary: JS8Call keyboard-to-keyboard weak-signal messaging (JS8Call-improved, upstream AppImage)
license: GPL-3.0-or-later
homepage: https://github.com/JS8Call-improved/JS8Call-improved
version: "3.0.3"
release: 1
bundle_dir: lib/js8call
source:
  type: arch-url
  urls:
    amd64: "https://github.com/JS8Call-improved/JS8Call-improved/releases/download/v{version}/JS8Call-v{version}-x86_64.AppImage"
    arm64: "https://github.com/JS8Call-improved/JS8Call-improved/releases/download/v{version}/JS8Call-v{version}-aarch64.AppImage"
upstream:
  type: github-releases
  repo: JS8Call-improved/JS8Call-improved
  tag_pattern: 'v(\d+\.\d+\.\d+)'
```

`recipes/js8call/build.sh`:

```bash
#!/usr/bin/env bash
# Extract the upstream AppImage (runs natively on this runner's arch; no FUSE needed).
set -euo pipefail
appimage=$(ls JS8Call-*.AppImage)
chmod +x "$appimage"
"./$appimage" --appimage-extract >/dev/null
lib=$DESTDIR$PREFIX/lib/js8call
mkdir -p "$DESTDIR$PREFIX/lib" "$DESTDIR$PREFIX/bin" "$DESTDIR$PREFIX/share/applications" \
  "$DESTDIR$PREFIX/share/icons/hicolor/256x256/apps"
mv squashfs-root "$lib"
cat > "$DESTDIR$PREFIX/bin/js8call" <<'EOF'
#!/bin/sh
exec /opt/emcomm/lib/js8call/AppRun "$@"
EOF
chmod 755 "$DESTDIR$PREFIX/bin/js8call"
desktop=$(find "$lib" -maxdepth 1 -name '*.desktop' | head -1)
sed -e 's|^Exec=.*|Exec=js8call|' -e 's|^Icon=.*|Icon=js8call|' "$desktop" \
  > "$DESTDIR$PREFIX/share/applications/js8call.desktop"
icon=$(find "$lib" -maxdepth 1 -name '*.png' | head -1)
if [[ -n $icon ]]; then
  cp "$icon" "$DESTDIR$PREFIX/share/icons/hicolor/256x256/apps/js8call.png"
fi
```

`recipes/js8call/smoke.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
test -x /opt/emcomm/lib/js8call/AppRun
test -x /opt/emcomm/bin/js8call
grep -q '^Exec=js8call' /opt/emcomm/share/applications/js8call.desktop
```

- [ ] **Step 2: Pin checksums**

Run: `uv run --directory tools emcomm-build bump js8call 3.0.3`
Expected: `bumped: js8call` and `recipes/js8call/SHA256SUMS` with two lines (x86_64 and aarch64).

If the download 404s, check the actual tag and asset names on the releases page (`gh release view -R JS8Call-improved/JS8Call-improved`) and fix `urls`/`tag_pattern`.

- [ ] **Step 3: Build and smoke**

Run: `uv run --directory tools emcomm-build build --target debian-13 --only js8call && uv run --directory tools emcomm-build build --target fedora-44 --only js8call`
Expected: `smoke OK` twice. The auto-detected runtime dependencies are the host libraries the bundle doesn't carry, such as libGL and fontconfig.

- [ ] **Step 4: Commit**

```bash
git add recipes/js8call
git commit -m "feat(recipes): JS8Call-improved 3.0.3 from the upstream AppImage"
```

---

### Task 13: Pat recipe (upstream static binary, prebuilt)

**Files:**
- Create: `recipes/pat/{recipe.yaml,build.sh,smoke.sh,SHA256SUMS}`

**Interfaces:**
- Produces: `emcomm-pat` with `/opt/emcomm/bin/pat` (upstream's static Go binary, no runtime dependencies) on every family. Distros carry 0.16 (Debian) or nothing (Fedora).

- [ ] **Step 1: Create the recipe**

`recipes/pat/recipe.yaml`:

```yaml
name: pat
kind: app
summary: Pat cross-platform Winlink client (upstream release binary)
license: MIT
homepage: https://getpat.io/
version: "1.0.0"
release: 1
source:
  type: arch-url
  urls:
    amd64: "https://github.com/la5nta/pat/releases/download/v{version}/pat_{version}_linux_amd64.tar.gz"
    arm64: "https://github.com/la5nta/pat/releases/download/v{version}/pat_{version}_linux_arm64.tar.gz"
upstream:
  type: github-releases
  repo: la5nta/pat
  tag_pattern: 'v(\d+\.\d+\.\d+)'
```

`recipes/pat/build.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
tar -xzf pat_*_linux_*.tar.gz
bin=$(find . -type f -name pat -perm -u+x | head -1)
[[ -n $bin ]] || { echo "pat binary not found in the release tarball" >&2; exit 1; }
install -D -m 0755 "$bin" "$DESTDIR$PREFIX/bin/pat"
```

`recipes/pat/smoke.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
pat version | grep -qi pat
```

- [ ] **Step 2: Pin checksums, build, smoke**

Run: `uv run --directory tools emcomm-build bump pat 1.0.0`
Expected: `bumped: pat`, and `SHA256SUMS` has two lines.

Run: `uv run --directory tools emcomm-build build --target debian-13 --only pat && uv run --directory tools emcomm-build build --target fedora-44 --only pat`
Expected: `smoke OK` twice.

- [ ] **Step 3: Commit**

```bash
git add recipes/pat
git commit -m "feat(recipes): Pat 1.0.0 from the upstream release binary"
```

---

### Task 14: Freshness report (distro vs upstream)

**Files:**
- Create: `freshness.yaml`, `tools/src/emcomm_build/freshness.py`
- Modify: `tools/src/emcomm_build/cli.py` (add `freshness`)
- Test: `tools/tests/test_freshness.py`

**Interfaces:**
- Consumes: `upstream.{list_tags, pick_latest}`, `model.Upstream`.
- Produces:
  - `freshness.debian_versions(pkg, *, http_text=...) -> dict[str, str]` (suite → version), from Debian madison.
  - `freshness.fedora_version(pkg, release, *, http_json=...) -> str | None`, from Fedora mdapi.
  - `freshness.report(entries, ...) -> list[dict]`
  - CLI: `emcomm-build freshness`. It prints, per app, the latest upstream release and the versions in trixie, trixie-backports, f43, and f44. Rows where a distro already matches upstream are marked `=`.
- Purpose: choosing between distro, prebuilt, and source stays a reviewed decision (spec §4.1) and never happens automatically.

- [ ] **Step 1: Create `freshness.yaml`**

```yaml
# Apps to compare against distro packages. Package names are binary package names.
apps:
  hamlib:
    upstream: {type: github-releases, repo: Hamlib/Hamlib, tag_pattern: '(\d+\.\d+(?:\.\d+)?)'}
    debian: libhamlib-utils
    fedora: hamlib
  wsjtx:
    upstream: {type: github-releases, repo: WSJTX/wsjtx, tag_pattern: 'v(\d+\.\d+\.\d+)'}
    debian: wsjtx
    fedora: wsjtx
  js8call:
    upstream: {type: github-releases, repo: JS8Call-improved/JS8Call-improved, tag_pattern: 'v(\d+\.\d+\.\d+)'}
    debian: js8call
    fedora: js8call
  fldigi:
    upstream: {type: git-tags, url: "https://git.code.sf.net/p/fldigi/fldigi", tag_pattern: 'v(\d+\.\d+\.\d+)'}
    debian: fldigi
    fedora: fldigi
  flrig:
    upstream: {type: git-tags, url: "https://git.code.sf.net/p/fldigi/flrig", tag_pattern: 'v(\d+\.\d+\.\d+)'}
    debian: flrig
    fedora: flrig
  flmsg:
    upstream: {type: git-tags, url: "https://git.code.sf.net/p/fldigi/flmsg", tag_pattern: 'v(\d+\.\d+\.\d+)'}
    debian: flmsg
    fedora: flmsg
  flamp:
    upstream: {type: git-tags, url: "https://git.code.sf.net/p/fldigi/flamp", tag_pattern: 'v(\d+\.\d+\.\d+)'}
    debian: flamp
    fedora: flamp
  direwolf:
    upstream: {type: git-tags, url: "https://github.com/wb2osz/direwolf", tag_pattern: '(\d+\.\d+(?:\.\d+)?)'}
    debian: direwolf
    fedora: direwolf
  pat:
    upstream: {type: github-releases, repo: la5nta/pat, tag_pattern: 'v(\d+\.\d+\.\d+)'}
    debian: pat
  wfview:
    upstream: {type: git-tags, url: "https://gitlab.com/eliggett/wfview.git", tag_pattern: 'v(\d+\.\d+)'}
    debian: wfview
    fedora: wfview
```

- [ ] **Step 2: Write the failing tests**

`tools/tests/test_freshness.py`:

```python
from emcomm_build.freshness import debian_versions, fedora_version, report
from emcomm_build.model import Upstream

MADISON = """\
 wsjtx | 2.7.0+repack-1   | trixie           | source, amd64, arm64
 wsjtx | 3.0.2+repack-1~bpo13+1 | trixie-backports | source, amd64, arm64
 wsjtx | 3.0.2+repack-1   | forky            | source, amd64, arm64
"""


def test_debian_versions_strip_revision():
    v = debian_versions("wsjtx", http_text=lambda url: MADISON)
    assert v == {"trixie": "2.7.0", "trixie-backports": "3.0.2", "forky": "3.0.2"}


def test_fedora_version():
    assert fedora_version("wsjtx", 44, http_json=lambda url: {"version": "3.0.1"}) == "3.0.1"

    def missing(url):
        raise LookupError

    assert fedora_version("pat", 44, http_json=missing) is None


def test_report_marks_current():
    entries = {"wsjtx": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="x"),
                         "debian": "wsjtx", "fedora": "wsjtx"}}
    rows = report(entries, tags=lambda up: ["v3.0.2", "v3.0.1"],
                  deb=lambda pkg: {"trixie": "2.7.0", "trixie-backports": "3.0.2"},
                  fed=lambda pkg, rel: "3.0.1")
    assert rows == [{"app": "wsjtx", "upstream": "3.0.2", "trixie": "2.7.0",
                     "trixie-backports": "=3.0.2", "f43": "3.0.1", "f44": "3.0.1"}]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --directory tools pytest -q tests/test_freshness.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm_build.freshness'`.

- [ ] **Step 4: Implement `freshness.py`**

```python
"""Compare upstream releases with Debian/Fedora package versions."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

import yaml

from .model import Upstream
from .upstream import list_tags, pick_latest

SUITES = ("trixie", "trixie-backports")
FEDORA = (43, 44)


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _upstream_version(raw: str) -> str:
    """Strip Debian/Fedora packaging decorations: epoch, +repack, ~bpo, -revision."""
    v = raw.split(":", 1)[-1]
    v = v.rsplit("-", 1)[0] if "-" in v else v
    return re.split(r"[+~]", v, maxsplit=1)[0]


def debian_versions(pkg: str, *, http_text: Callable[[str], str] | None = None) -> dict[str, str]:
    url = "https://qa.debian.org/madison.php?text=on&package=" + urllib.parse.quote(pkg)
    text = http_text(url) if http_text else _get(url).decode()
    versions: dict[str, str] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            versions.setdefault(parts[2], _upstream_version(parts[1]))
    return versions


def fedora_version(pkg: str, release: int, *,
                   http_json: Callable[[str], dict] | None = None) -> str | None:
    url = f"https://mdapi.fedoraproject.org/f{release}/pkg/{urllib.parse.quote(pkg)}"
    try:
        data = http_json(url) if http_json else json.loads(_get(url))
    except (LookupError, urllib.error.HTTPError):
        return None
    return data.get("version")


def load_entries(root: Path) -> dict[str, dict]:
    data = yaml.safe_load((root / "freshness.yaml").read_text())
    return {name: {**e, "upstream": Upstream(**e["upstream"])} for name, e in data["apps"].items()}


def report(entries: dict[str, dict], *, tags=list_tags, deb=debian_versions,
           fed=fedora_version) -> list[dict]:
    rows = []
    for name, e in entries.items():
        latest = pick_latest(tags(e["upstream"]), e["upstream"].tag_pattern) or "?"
        row = {"app": name, "upstream": latest}
        dv = deb(e["debian"]) if e.get("debian") else {}
        for suite in SUITES:
            row[suite] = dv.get(suite, "-")
        for rel in FEDORA:
            row[f"f{rel}"] = (fed(e["fedora"], rel) if e.get("fedora") else None) or "-"
        for key in (*SUITES, *(f"f{r}" for r in FEDORA)):
            if row[key] == latest:
                row[key] = f"={latest}"
        rows.append(row)
    return rows
```

The test expects `trixie-backports: "=3.0.2"` and `f43: "3.0.1"`, which matches this marking.

- [ ] **Step 5: Add the CLI command**

In `cli.py`, add `from .freshness import load_entries, report` and:

```python
def cmd_freshness(args: argparse.Namespace) -> int:
    rows = report(load_entries(repo_root()))
    cols = ["app", "upstream", "trixie", "trixie-backports", "f43", "f44"]
    print("  ".join(f"{c:<18}" for c in cols))
    for row in rows:
        print("  ".join(f"{row[c]:<18}" for c in cols))
    print("(= means the distro already ships the latest upstream release)")
    return 0
```

Register it in `build_parser`:

```python
    sub.add_parser("freshness", help="compare distro package versions with upstream").set_defaults(
        func=cmd_freshness)
```

- [ ] **Step 6: Run the tests and a live report**

Run: `uv run --directory tools pytest -q && uv run --directory tools ruff check .`
Expected: PASS.

Run: `uv run --directory tools emcomm-build freshness`
Expected: a table that matches the sourcing in spec §4.1: hamlib, WSJT-X, and Direwolf show `=` in trixie-backports, fldigi shows `=` on f43 and f44, and so on. Note any surprises in the PR.

- [ ] **Step 7: Commit**

```bash
git add freshness.yaml tools
git commit -m "feat(build): freshness report comparing distro packages with upstream"
```

---

### Task 15: `emcomm` CLI scaffolding, models, and operator profiles

**Files:**
- Create: `cli/pyproject.toml`, `cli/src/emcomm/__init__.py`, `cli/src/emcomm/{paths,models,validation,profiles,cli}.py`
- Create: `cli/src/emcomm/commands/__init__.py` (empty), `cli/src/emcomm/commands/operator.py`
- Create: `cli/src/emcomm/schemas/__init__.py` (empty), `cli/src/emcomm/schemas/{operator,station,radio}.schema.json`
- Test: `cli/tests/conftest.py`, `cli/tests/test_models.py`, `cli/tests/test_operator.py`

**Interfaces:**
- Produces:
  - `paths.Paths(etc, share, home, udev_rules, sysfs)`. Properties: `xdg_config`, `user_config`, `state`, `operators_dir`, `active_file`, `stations_dir`, `radios_dir`, `ansible_dir`. Constructor `Paths.from_env(env=os.environ)`, where `EMCOMM_ROOT` relocates everything for tests and `EMCOMM_SHARE`/`EMCOMM_SYSFS` override individual paths.
  - `models`: `Operator(callsign, name="", grid="")`, `UsbHint(vendor_id="", product_id="", serial_prefix="", product_contains="", interface="")`, `RadioDef(id, vendor, model, hamlib_model, baud, ptt, set_conf=(), cat_hints=(), audio_hints=(), notes=())` with `.label`, `UsbMatch(vendor_id, product_id, serial="", interface="")`, `Station(name, radio, cat=None, audio=None, ptt=None)` with `.cat_link`, `.alsa_id`, `.ptt_method(radio)`, plus `normalize_callsign(s)`, `normalize_grid(s)`, `ax25_callsign(s)`, and `PTT_METHODS`.
  - `validation`: `ProfileError(Exception)` and `validate(kind, data, where)`.
  - `profiles`: `save_operator`, `load_operator`, `list_operators`, `save_station`, `load_station`, `list_stations`, `station_to_dict`, `station_from_dict`.
  - `cli.main(argv=None, paths=None) -> int`. Command modules expose `register(sub)` and set `func(args, paths) -> int`.

- [ ] **Step 1: Create `cli/pyproject.toml`**

```toml
[project]
name = "emcomm"
version = "0.1.0"
description = "emcommOS operator CLI"
requires-python = ">=3.12"
license = "Apache-2.0"
dependencies = ["pyyaml>=6", "jsonschema>=4.17", "tomli-w>=1.0"]

[project.scripts]
emcomm = "emcomm.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/emcomm"]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

`cli/src/emcomm/__init__.py`: `__version__ = "0.1.0"`

- [ ] **Step 2: Create the schemas**

`cli/src/emcomm/schemas/operator.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["callsign"],
  "properties": {
    "callsign": {"type": "string"},
    "name": {"type": "string"},
    "grid": {"type": "string"}
  }
}
```

`cli/src/emcomm/schemas/station.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["name", "radio"],
  "properties": {
    "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,7}$"},
    "radio": {"type": "string"},
    "ptt": {"enum": ["cat", "rts", "dtr", "vox"]},
    "cat": {"$ref": "#/$defs/match"},
    "audio": {"$ref": "#/$defs/match"}
  },
  "$defs": {
    "match": {
      "type": "object",
      "additionalProperties": false,
      "required": ["vendor_id", "product_id"],
      "properties": {
        "vendor_id": {"type": "string", "pattern": "^[0-9a-f]{4}$"},
        "product_id": {"type": "string", "pattern": "^[0-9a-f]{4}$"},
        "serial": {"type": "string", "pattern": "^[^\"\\\\]*$"},
        "interface": {"type": "string", "pattern": "^[0-9a-f]{2}$"}
      }
    }
  }
}
```

`cli/src/emcomm/schemas/radio.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "vendor", "model", "hamlib_model", "baud", "ptt"],
  "properties": {
    "id": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
    "vendor": {"type": "string", "minLength": 1},
    "model": {"type": "string", "minLength": 1},
    "hamlib_model": {"type": "integer", "minimum": 1},
    "baud": {"enum": [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]},
    "ptt": {"enum": ["cat", "rts", "dtr", "vox"]},
    "set_conf": {"type": "object", "additionalProperties": {"type": ["string", "integer"]}},
    "usb_hints": {
      "type": "object",
      "additionalProperties": false,
      "properties": {"cat": {"$ref": "#/$defs/hints"}, "audio": {"$ref": "#/$defs/hints"}}
    },
    "notes": {"type": "array", "items": {"type": "string"}}
  },
  "$defs": {
    "hints": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "minProperties": 1,
        "properties": {
          "vendor_id": {"type": "string", "pattern": "^[0-9a-f]{4}$"},
          "product_id": {"type": "string", "pattern": "^[0-9a-f]{4}$"},
          "serial_prefix": {"type": "string"},
          "product_contains": {"type": "string"},
          "interface": {"type": "string", "pattern": "^[0-9a-f]{2}$"}
        }
      }
    }
  }
}
```

- [ ] **Step 3: Write the failing tests**

`cli/tests/conftest.py`:

```python
from pathlib import Path

import pytest

from emcomm.paths import Paths

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def paths(tmp_path) -> Paths:
    return Paths(etc=tmp_path / "etc/emcomm", share=REPO_ROOT, home=tmp_path / "home",
                 udev_rules=tmp_path / "udev", sysfs=tmp_path / "sys")
```

`share=REPO_ROOT` makes `paths.radios_dir` resolve to the repo's `radios/` directory, which is added in Task 16.

`cli/tests/test_models.py`:

```python
import pytest

from emcomm.models import Station, ax25_callsign, normalize_callsign, normalize_grid
from emcomm.paths import Paths


@pytest.mark.parametrize("raw,expected", [("k7abc", "K7ABC"), (" ve7/k7abc ", "VE7/K7ABC"),
                                          ("K7ABC/P", "K7ABC/P"), ("W1AW", "W1AW")])
def test_callsign_ok(raw, expected):
    assert normalize_callsign(raw) == expected


@pytest.mark.parametrize("raw", ["", "KABC", "K7 ABC", "K7ABC!"])
def test_callsign_bad(raw):
    with pytest.raises(ValueError):
        normalize_callsign(raw)


def test_grid():
    assert normalize_grid("dn16BK") == "DN16bk"
    assert normalize_grid("dn16") == "DN16"
    assert normalize_grid("") == ""
    with pytest.raises(ValueError):
        normalize_grid("ZZ99")


def test_ax25_callsign():
    assert ax25_callsign("VE7/K7ABC") == "K7ABC"
    assert ax25_callsign("K7ABC/P") == "K7ABC"


def test_station_derived_names():
    st = Station(name="kit-a", radio="icom-ic7300")
    assert st.cat_link == "/dev/emcomm/cat-kit-a"
    assert st.alsa_id == "EMCOMM_KIT_A"


def test_paths_from_env(tmp_path):
    p = Paths.from_env({"EMCOMM_ROOT": str(tmp_path)})
    assert p.stations_dir == tmp_path / "etc/emcomm/stations"
    assert p.operators_dir == tmp_path / "home/.config/emcomm/operators"
    assert p.radios_dir == tmp_path / "opt/emcomm/share/emcomm/radios"
```

`cli/tests/test_operator.py`:

```python
from emcomm.cli import main


def test_add_list_show(paths, capsys):
    assert main(["operator", "add", "k7abc", "--name", "Pat Q", "--grid", "dn16bk"],
                paths=paths) == 0
    assert (paths.operators_dir / "k7abc.toml").is_file()
    assert main(["operator", "list"], paths=paths) == 0
    assert "K7ABC" in capsys.readouterr().out
    assert main(["operator", "show", "K7ABC"], paths=paths) == 0
    out = capsys.readouterr().out
    assert "grid: DN16bk" in out and "name: Pat Q" in out


def test_portable_callsign_file_name(paths):
    assert main(["operator", "add", "VE7/K7ABC"], paths=paths) == 0
    assert (paths.operators_dir / "ve7_k7abc.toml").is_file()


def test_invalid_callsign(paths, capsys):
    assert main(["operator", "add", "nope"], paths=paths) == 1
    assert "invalid callsign" in capsys.readouterr().err


def test_show_missing(paths, capsys):
    assert main(["operator", "show", "K7ZZZ"], paths=paths) == 1
    assert "emcomm operator add" in capsys.readouterr().err


def test_list_empty(paths, capsys):
    assert main(["operator", "list"], paths=paths) == 0
    assert "no operators yet" in capsys.readouterr().out
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm.paths'`.

- [ ] **Step 5: Implement `paths.py`**

```python
"""Filesystem locations used by emcomm, relocatable for tests."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    etc: Path
    share: Path
    home: Path
    udev_rules: Path
    sysfs: Path

    @property
    def xdg_config(self) -> Path:
        return self.home / ".config"

    @property
    def user_config(self) -> Path:
        return self.xdg_config / "emcomm"

    @property
    def state(self) -> Path:
        return self.home / ".local/state/emcomm"

    @property
    def operators_dir(self) -> Path:
        return self.user_config / "operators"

    @property
    def active_file(self) -> Path:
        return self.user_config / "active.toml"

    @property
    def stations_dir(self) -> Path:
        return self.etc / "stations"

    @property
    def radios_dir(self) -> Path:
        return self.share / "radios"

    @property
    def ansible_dir(self) -> Path:
        return self.share / "ansible"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Paths:
        root = env.get("EMCOMM_ROOT")
        if root:
            r = Path(root)
            return cls(
                etc=r / "etc/emcomm",
                share=Path(env.get("EMCOMM_SHARE", r / "opt/emcomm/share/emcomm")),
                home=r / "home",
                udev_rules=r / "etc/udev/rules.d",
                sysfs=Path(env.get("EMCOMM_SYSFS", r / "sys")),
            )
        return cls(
            etc=Path("/etc/emcomm"),
            share=Path(env.get("EMCOMM_SHARE", "/opt/emcomm/share/emcomm")),
            home=Path.home(),
            udev_rules=Path("/etc/udev/rules.d"),
            sysfs=Path(env.get("EMCOMM_SYSFS", "/sys")),
        )
```

- [ ] **Step 6: Implement `models.py`**

```python
"""Operator, radio and station data types plus input normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass

CALLSIGN_RE = re.compile(
    r"^(?=[A-Z0-9/]{3,15}$)(?:[A-Z0-9]{1,4}/)?[A-Z0-9]*\d[A-Z0-9]*[A-Z](?:/[A-Z0-9]{1,4})?$"
)
GRID_RE = re.compile(r"^[A-R]{2}\d{2}(?:[A-X]{2})?$", re.IGNORECASE)
PTT_METHODS = ("cat", "rts", "dtr", "vox")


def normalize_callsign(raw: str) -> str:
    value = raw.strip().upper()
    if not CALLSIGN_RE.match(value):
        raise ValueError(f"invalid callsign {raw!r}")
    return value


def normalize_grid(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if not GRID_RE.match(value):
        raise ValueError(f"invalid Maidenhead grid {raw!r}")
    return value[:2].upper() + value[2:4] + value[4:].lower()


def ax25_callsign(callsign: str) -> str:
    """Base call without portable prefixes/suffixes (AX.25 allows at most 6 chars + SSID)."""
    parts = [p for p in callsign.split("/") if any(c.isdigit() for c in p)]
    return max(parts, key=len) if parts else callsign


@dataclass(frozen=True)
class Operator:
    callsign: str
    name: str = ""
    grid: str = ""


@dataclass(frozen=True)
class UsbHint:
    vendor_id: str = ""
    product_id: str = ""
    serial_prefix: str = ""
    product_contains: str = ""
    interface: str = ""


@dataclass(frozen=True)
class RadioDef:
    id: str
    vendor: str
    model: str
    hamlib_model: int
    baud: int
    ptt: str
    set_conf: tuple[tuple[str, str], ...] = ()
    cat_hints: tuple[UsbHint, ...] = ()
    audio_hints: tuple[UsbHint, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.vendor} {self.model}"


@dataclass(frozen=True)
class UsbMatch:
    vendor_id: str
    product_id: str
    serial: str = ""
    interface: str = ""


@dataclass(frozen=True)
class Station:
    name: str
    radio: str
    cat: UsbMatch | None = None
    audio: UsbMatch | None = None
    ptt: str | None = None

    @property
    def cat_link(self) -> str:
        return f"/dev/emcomm/cat-{self.name}"

    @property
    def alsa_id(self) -> str:
        return "EMCOMM_" + self.name.upper().replace("-", "_")

    def ptt_method(self, radio: RadioDef) -> str:
        return self.ptt or radio.ptt
```

The callsign regex needs a digit followed later by a letter, so `"W1AW"` passes and `"KABC"` fails. ALSA card ids are limited to 15 characters: `EMCOMM_` is 7, and station names are capped at 8 by the schema.

- [ ] **Step 7: Implement `validation.py` and `profiles.py`**

`validation.py`:

```python
"""JSON-schema validation for profile and definition files."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema


class ProfileError(Exception):
    """A profile or definition is missing or invalid."""


@cache
def _schema(kind: str) -> dict[str, Any]:
    return json.loads(resources.files("emcomm.schemas").joinpath(f"{kind}.schema.json").read_text())


def validate(kind: str, data: Any, where: Path | str) -> None:
    try:
        jsonschema.validate(data, _schema(kind))
    except jsonschema.ValidationError as exc:
        loc = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ProfileError(f"{where}: {loc}: {exc.message}") from None
```

`profiles.py`:

```python
"""Load and save operator profiles and station kits as TOML."""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from .models import Operator, Station, UsbMatch, normalize_callsign, normalize_grid
from .paths import Paths
from .validation import ProfileError, validate


def _write_toml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(tomli_w.dumps(data))
    tmp.replace(path)
    return path


def _read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path}: {exc}") from None


def operator_path(paths: Paths, callsign: str) -> Path:
    return paths.operators_dir / f"{callsign.lower().replace('/', '_')}.toml"


def save_operator(paths: Paths, op: Operator) -> Path:
    data = {"callsign": op.callsign}
    if op.name:
        data["name"] = op.name
    if op.grid:
        data["grid"] = op.grid
    validate("operator", data, "operator")
    return _write_toml(operator_path(paths, op.callsign), data)


def _operator_from(data: dict, where: Path) -> Operator:
    validate("operator", data, where)
    return Operator(callsign=normalize_callsign(data["callsign"]), name=data.get("name", ""),
                    grid=normalize_grid(data.get("grid", "")))


def load_operator(paths: Paths, callsign: str) -> Operator:
    path = operator_path(paths, normalize_callsign(callsign))
    if not path.is_file():
        raise ProfileError(
            f"no operator profile for {callsign}; create one with `emcomm operator add {callsign}`"
        )
    return _operator_from(_read_toml(path), path)


def list_operators(paths: Paths) -> list[Operator]:
    if not paths.operators_dir.is_dir():
        return []
    return [_operator_from(_read_toml(p), p) for p in sorted(paths.operators_dir.glob("*.toml"))]


def station_to_dict(st: Station) -> dict:
    data: dict = {"name": st.name, "radio": st.radio}
    if st.ptt:
        data["ptt"] = st.ptt
    for key, match in (("cat", st.cat), ("audio", st.audio)):
        if match:
            m = {"vendor_id": match.vendor_id, "product_id": match.product_id}
            if match.serial:
                m["serial"] = match.serial
            if match.interface:
                m["interface"] = match.interface
            data[key] = m
    return data


def station_from_dict(data: dict, where: Path | str) -> Station:
    validate("station", data, where)

    def match(key: str) -> UsbMatch | None:
        m = data.get(key)
        return UsbMatch(**m) if m else None

    return Station(name=data["name"], radio=data["radio"], cat=match("cat"),
                   audio=match("audio"), ptt=data.get("ptt"))


def save_station(paths: Paths, st: Station) -> Path:
    data = station_to_dict(st)
    validate("station", data, "station")
    return _write_toml(paths.stations_dir / f"{st.name}.toml", data)


def load_station(paths: Paths, name: str) -> Station:
    path = paths.stations_dir / f"{name}.toml"
    if not path.is_file():
        raise ProfileError(f"no station kit named {name!r}; see `emcomm station list`")
    return station_from_dict(_read_toml(path), path)


def list_stations(paths: Paths) -> list[Station]:
    if not paths.stations_dir.is_dir():
        return []
    return [station_from_dict(_read_toml(p), p) for p in sorted(paths.stations_dir.glob("*.toml"))]
```

- [ ] **Step 8: Implement `commands/operator.py` and `cli.py`**

`commands/operator.py`:

```python
"""`emcomm operator` — operator profiles (who is operating)."""

from __future__ import annotations

import argparse

from ..models import Operator, normalize_callsign, normalize_grid
from ..paths import Paths
from ..profiles import list_operators, load_operator, save_operator


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("operator", help="manage operator profiles")
    actions = p.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add", help="create or update an operator profile")
    add.add_argument("callsign")
    add.add_argument("--name", default="")
    add.add_argument("--grid", default="", help="Maidenhead locator, e.g. DN16bk")
    add.set_defaults(func=cmd_add)
    actions.add_parser("list", help="list operator profiles").set_defaults(func=cmd_list)
    show = actions.add_parser("show", help="show one operator profile")
    show.add_argument("callsign")
    show.set_defaults(func=cmd_show)


def cmd_add(args: argparse.Namespace, paths: Paths) -> int:
    op = Operator(callsign=normalize_callsign(args.callsign), name=args.name.strip(),
                  grid=normalize_grid(args.grid))
    print(f"saved {op.callsign} -> {save_operator(paths, op)}")
    return 0


def cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    ops = list_operators(paths)
    if not ops:
        print("no operators yet; add one with `emcomm operator add CALLSIGN`")
    for op in ops:
        print(f"{op.callsign:<12} {op.grid:<8} {op.name}")
    return 0


def cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    op = load_operator(paths, args.callsign)
    print(f"callsign: {op.callsign}\nname: {op.name}\ngrid: {op.grid}")
    return 0
```

`cli.py`:

```python
"""emcomm command line entry point."""

from __future__ import annotations

import argparse
import sys

from .commands import operator
from .paths import Paths
from .validation import ProfileError

COMMANDS = [operator]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="emcomm", description="emcommOS station tool")
    sub = parser.add_subparsers(dest="command", required=True)
    for module in COMMANDS:
        module.register(sub)
    return parser


def main(argv: list[str] | None = None, paths: Paths | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = paths or Paths.from_env()
    try:
        return args.func(args, paths)
    except (ProfileError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"error: {exc.filename}: permission denied (try sudo)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9: Run the tests**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add cli
git commit -m "feat(cli): emcomm CLI scaffolding, models and operator profiles"
```

---

### Task 16: Radio definitions

**Files:**
- Create: `radios/{icom-ic7300,icom-ic705,yaesu-ft991a,kenwood-ts590sg,generic-vox,generic-rts}.yaml`
- Create: `cli/src/emcomm/radios.py`, `cli/src/emcomm/commands/radios.py`
- Modify: `cli/src/emcomm/cli.py` (`COMMANDS = [operator, radios]`)
- Test: `cli/tests/test_radios.py`

**Interfaces:**
- Consumes: `models.{RadioDef, UsbHint}` and `validation.{validate, ProfileError}`.
- Produces: `radios.radio_from_dict(data) -> RadioDef` and `radios.load_radios(directory) -> dict[str, RadioDef]`. CLI: `emcomm radios [ID]`.

Hamlib model numbers come from hamlib 4.7.2 `riglist.h`: dummy 1, NET rigctl 2, FT-991/991A 1035, TS-590SG 2037, IC-7300 3073, IC-705 3085.

- [ ] **Step 1: Write the radio definitions**

`radios/icom-ic7300.yaml`:

```yaml
id: icom-ic7300
vendor: Icom
model: IC-7300
hamlib_model: 3073
baud: 19200
ptt: cat
usb_hints:
  cat:
    - {vendor_id: "10c4", product_id: "ea60", serial_prefix: "IC-7300"}
  audio:
    - {vendor_id: "08bb", product_id: "2901"}
notes:
  - "MENU > SET > Connectors > CI-V > CI-V USB Baud Rate: 19200"
  - "MENU > SET > Connectors > CI-V > CI-V USB Echo Back: OFF"
  - "MENU > SET > Connectors > CI-V > CI-V USB Port: Unlink from [REMOTE]"
  - "MENU > SET > Connectors > DATA MOD: USB"
  - "Start USB MOD Level near 50% and adjust for minimal ALC on transmit"
```

`radios/icom-ic705.yaml`:

```yaml
id: icom-ic705
vendor: Icom
model: IC-705
hamlib_model: 3085
baud: 19200
ptt: cat
usb_hints:
  cat:
    - {product_contains: "IC-705", interface: "00"}
  audio:
    - {vendor_id: "08bb", product_id: "2901"}
notes:
  - "MENU > SET > Connectors > CI-V > CI-V USB Baud Rate: 19200"
  - "MENU > SET > Connectors > CI-V > CI-V USB Echo Back: OFF"
  - "MENU > SET > Connectors > MOD Input > DATA MOD: USB"
  - "The second USB serial port (interface 02) carries GPS NMEA, not CAT"
```

`radios/yaesu-ft991a.yaml`:

```yaml
id: yaesu-ft991a
vendor: Yaesu
model: FT-991A
hamlib_model: 1035
baud: 38400
ptt: cat
usb_hints:
  cat:
    - {vendor_id: "10c4", product_id: "ea70", interface: "00"}
  audio:
    - {vendor_id: "08bb", product_id: "29b3"}
notes:
  - "CAT RATE: 38400"
  - "CAT RTS: DISABLE"
  - "DATA PORT SELECT: USB"
  - "Use the Enhanced COM port (interface 00) for CAT; the Standard port is for PTT/keying"
  - "Operate digital modes in DATA-U"
```

`radios/kenwood-ts590sg.yaml`:

```yaml
id: kenwood-ts590sg
vendor: Kenwood
model: TS-590SG
hamlib_model: 2037
baud: 115200
ptt: cat
notes:
  - "Set the USB COM port speed to 115200 in the radio's menu"
  - "Select USB audio as the DATA mode audio input"
  - "No USB hints yet: pick the CAT port and sound card with --cat/--audio"
```

`radios/generic-vox.yaml`:

```yaml
id: generic-vox
vendor: Generic
model: VOX (audio only)
hamlib_model: 1
baud: 9600
ptt: vox
notes:
  - "Enable VOX on the radio or interface. rigctld runs hamlib's dummy rig so apps still have a CAT endpoint."
```

`radios/generic-rts.yaml`:

```yaml
id: generic-rts
vendor: Generic
model: Serial RTS PTT (e.g. Digirig without CAT)
hamlib_model: 1
baud: 9600
ptt: rts
usb_hints:
  cat:
    - {vendor_id: "10c4", product_id: "ea60"}
  audio:
    - {vendor_id: "0d8c", product_id: "0012"}
    - {vendor_id: "0d8c", product_id: "013c"}
notes:
  - "PTT is keyed by RTS on the interface's serial port; frequency control is not available."
```

- [ ] **Step 2: Write the failing tests**

`cli/tests/test_radios.py`:

```python
import pytest

from emcomm.cli import main
from emcomm.radios import load_radios
from emcomm.validation import ProfileError


def test_repo_radios_load(paths):
    radios = load_radios(paths.radios_dir)
    assert radios["icom-ic7300"].hamlib_model == 3073
    assert radios["icom-ic7300"].cat_hints[0].serial_prefix == "IC-7300"
    assert radios["generic-rts"].ptt == "rts"
    assert len(radios["generic-rts"].audio_hints) == 2


def test_id_must_match_filename(tmp_path):
    (tmp_path / "foo.yaml").write_text(
        "id: bar\nvendor: X\nmodel: Y\nhamlib_model: 1\nbaud: 9600\nptt: vox\n")
    with pytest.raises(ProfileError, match="file name"):
        load_radios(tmp_path)


def test_bad_baud(tmp_path):
    (tmp_path / "foo.yaml").write_text(
        "id: foo\nvendor: X\nmodel: Y\nhamlib_model: 1\nbaud: 1234\nptt: vox\n")
    with pytest.raises(ProfileError, match="baud"):
        load_radios(tmp_path)


def test_radios_command(paths, capsys):
    assert main(["radios"], paths=paths) == 0
    assert "icom-ic7300" in capsys.readouterr().out
    assert main(["radios", "yaesu-ft991a"], paths=paths) == 0
    assert "CAT RATE: 38400" in capsys.readouterr().out
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_radios.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm.radios'`.

- [ ] **Step 4: Implement `radios.py` and `commands/radios.py`**

`radios.py`:

```python
"""Radio definitions shipped in /opt/emcomm/share/emcomm/radios."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import RadioDef, UsbHint
from .validation import ProfileError, validate


def radio_from_dict(data: dict) -> RadioDef:
    hints = data.get("usb_hints", {})
    return RadioDef(
        id=data["id"],
        vendor=data["vendor"],
        model=data["model"],
        hamlib_model=data["hamlib_model"],
        baud=data["baud"],
        ptt=data["ptt"],
        set_conf=tuple(sorted((k, str(v)) for k, v in data.get("set_conf", {}).items())),
        cat_hints=tuple(UsbHint(**h) for h in hints.get("cat", [])),
        audio_hints=tuple(UsbHint(**h) for h in hints.get("audio", [])),
        notes=tuple(data.get("notes", [])),
    )


def load_radios(directory: Path) -> dict[str, RadioDef]:
    if not directory.is_dir():
        raise ProfileError(f"radio definitions not found in {directory}")
    radios: dict[str, RadioDef] = {}
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        validate("radio", data, path)
        if data["id"] != path.stem:
            raise ProfileError(f"{path}: id {data['id']!r} must match the file name")
        radios[data["id"]] = radio_from_dict(data)
    return radios
```

`commands/radios.py`:

```python
"""`emcomm radios` — list supported radio definitions."""

from __future__ import annotations

import argparse

from ..paths import Paths
from ..radios import load_radios
from ..validation import ProfileError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("radios", help="list radio definitions, or show one")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=cmd_radios)


def cmd_radios(args: argparse.Namespace, paths: Paths) -> int:
    radios = load_radios(paths.radios_dir)
    if args.id is None:
        for r in radios.values():
            print(f"{r.id:<18} {r.label:<40} hamlib {r.hamlib_model:<5} ptt {r.ptt}")
        return 0
    if args.id not in radios:
        raise ProfileError(f"unknown radio {args.id!r}; see `emcomm radios`")
    r = radios[args.id]
    print(f"{r.label}\n  hamlib model: {r.hamlib_model}\n  baud: {r.baud}\n  ptt: {r.ptt}")
    if r.notes:
        print("  radio settings:")
        for note in r.notes:
            print(f"    - {note}")
    return 0
```

In `cli.py`, change the import to `from .commands import operator, radios` and set `COMMANDS = [operator, radios]`.

- [ ] **Step 5: Run the tests**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS. (Task 25's `core` smoke test checks every `hamlib_model` against the real `rigctl -l` on each target.)

- [ ] **Step 6: Commit**

```bash
git add radios cli
git commit -m "feat(cli): radio definitions and emcomm radios"
```

---

### Task 17: USB device detection

**Files:**
- Create: `cli/src/emcomm/detect.py`
- Test: `cli/tests/sysfs.py` (helpers), `cli/tests/test_detect.py`

**Interfaces:**
- Consumes: `models.{UsbHint, UsbMatch}`.
- Produces:
  - `Detected(kind: "tty" | "sound", node, vendor_id, product_id, serial, product, interface)`
  - `scan(sysfs: Path) -> list[Detected]`
  - `hint_matches(hint, d) -> bool`
  - `candidates(hints, devices, kind) -> list[Detected]`
  - `find_node(devices, kind, node) -> Detected` (raises `ProfileError`)
  - `to_match(d) -> UsbMatch` (tty keeps the interface number; sound drops it)
- Test helpers in `cli/tests/sysfs.py`: `make_usb(sysfs, port, vid, pid, serial="", product="", iface="00") -> Path` and `add_tty(sysfs, iface_dir, name)`, `add_sound(sysfs, iface_dir, name)`.

- [ ] **Step 1: Write the sysfs test helpers and failing tests**

`cli/tests/sysfs.py`:

```python
"""Build a minimal fake /sys tree with the same shape as the real one."""

from pathlib import Path


def make_usb(sysfs: Path, port: str, vid: str, pid: str, serial: str = "", product: str = "",
             iface: str = "00") -> Path:
    dev = sysfs / "devices/pci0000:00/0000:00:14.0/usb1" / port
    dev.mkdir(parents=True, exist_ok=True)
    (dev / "idVendor").write_text(vid + "\n")
    (dev / "idProduct").write_text(pid + "\n")
    if serial:
        (dev / "serial").write_text(serial + "\n")
    if product:
        (dev / "product").write_text(product + "\n")
    iface_dir = dev / f"{port}:1.{int(iface, 16)}"
    iface_dir.mkdir(exist_ok=True)
    (iface_dir / "bInterfaceNumber").write_text(iface + "\n")
    return iface_dir


def add_tty(sysfs: Path, iface_dir: Path, name: str) -> None:
    node = iface_dir / name / "tty" / name
    node.mkdir(parents=True)
    (sysfs / "class/tty").mkdir(parents=True, exist_ok=True)
    (sysfs / "class/tty" / name).symlink_to(node)


def add_sound(sysfs: Path, iface_dir: Path, name: str) -> None:
    node = iface_dir / "sound" / name
    node.mkdir(parents=True)
    (sysfs / "class/sound").mkdir(parents=True, exist_ok=True)
    (sysfs / "class/sound" / name).symlink_to(node)
```

`cli/tests/test_detect.py`:

```python
import pytest

from emcomm.detect import candidates, find_node, hint_matches, scan, to_match
from emcomm.models import UsbHint
from emcomm.validation import ProfileError

from sysfs import add_sound, add_tty, make_usb


@pytest.fixture
def ic7300_and_ft991a(tmp_path):
    sysfs = tmp_path / "sys"
    add_tty(sysfs, make_usb(sysfs, "1-1", "10c4", "ea60", "IC-7300 03001234 A", "IC-7300"), "ttyUSB0")
    add_sound(sysfs, make_usb(sysfs, "1-2", "08bb", "2901", product="USB Audio CODEC"), "card1")
    add_tty(sysfs, make_usb(sysfs, "1-3", "10c4", "ea70", "00A5B1C2", "CP2105", iface="00"), "ttyUSB1")
    add_tty(sysfs, make_usb(sysfs, "1-3", "10c4", "ea70", "00A5B1C2", "CP2105", iface="01"), "ttyUSB2")
    return sysfs


def test_scan(ic7300_and_ft991a):
    found = {d.node: d for d in scan(ic7300_and_ft991a)}
    assert set(found) == {"ttyUSB0", "ttyUSB1", "ttyUSB2", "card1"}
    assert found["ttyUSB0"].serial == "IC-7300 03001234 A"
    assert found["ttyUSB2"].interface == "01"
    assert found["card1"].kind == "sound"
    assert found["card1"].vendor_id == "08bb"


def test_scan_empty(tmp_path):
    assert scan(tmp_path / "nothing") == []


def test_hints(ic7300_and_ft991a):
    devices = scan(ic7300_and_ft991a)
    ic = [UsbHint(vendor_id="10c4", product_id="ea60", serial_prefix="IC-7300")]
    assert [d.node for d in candidates(ic, devices, "tty")] == ["ttyUSB0"]
    ft = [UsbHint(vendor_id="10c4", product_id="ea70", interface="00")]
    assert [d.node for d in candidates(ft, devices, "tty")] == ["ttyUSB1"]
    by_name = [UsbHint(product_contains="IC-7300")]
    assert hint_matches(by_name[0], find_node(devices, "tty", "ttyUSB0"))


def test_find_node_errors(ic7300_and_ft991a):
    with pytest.raises(ProfileError, match="ttyUSB9"):
        find_node(scan(ic7300_and_ft991a), "tty", "ttyUSB9")


def test_to_match(ic7300_and_ft991a):
    devices = scan(ic7300_and_ft991a)
    tty = to_match(find_node(devices, "tty", "ttyUSB1"))
    assert (tty.vendor_id, tty.product_id, tty.interface) == ("10c4", "ea70", "00")
    snd = to_match(find_node(devices, "sound", "card1"))
    assert snd.interface == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_detect.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm.detect'`.

- [ ] **Step 3: Implement `detect.py`**

```python
"""Find USB serial ports and sound cards by walking sysfs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import UsbHint, UsbMatch
from .validation import ProfileError

PATTERNS = (("tty", "class/tty/ttyUSB*"), ("tty", "class/tty/ttyACM*"),
            ("sound", "class/sound/card*"))


@dataclass(frozen=True)
class Detected:
    kind: str
    node: str
    vendor_id: str
    product_id: str
    serial: str
    product: str
    interface: str


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _usb_ancestors(device: Path) -> tuple[Path | None, Path | None]:
    iface = None
    for p in (device, *device.parents):
        if iface is None and (p / "bInterfaceNumber").is_file():
            iface = p
        if (p / "idVendor").is_file():
            return iface, p
    return iface, None


def scan(sysfs: Path) -> list[Detected]:
    found = []
    for kind, pattern in PATTERNS:
        for entry in sorted(sysfs.glob(pattern)):
            iface, dev = _usb_ancestors(entry.resolve())
            if dev is None:
                continue
            found.append(Detected(
                kind=kind,
                node=entry.name,
                vendor_id=_read(dev / "idVendor"),
                product_id=_read(dev / "idProduct"),
                serial=_read(dev / "serial"),
                product=_read(dev / "product"),
                interface=_read(iface / "bInterfaceNumber") if iface else "",
            ))
    return found


def hint_matches(hint: UsbHint, d: Detected) -> bool:
    return (
        (not hint.vendor_id or hint.vendor_id == d.vendor_id)
        and (not hint.product_id or hint.product_id == d.product_id)
        and d.serial.startswith(hint.serial_prefix)
        and hint.product_contains in d.product
        and (not hint.interface or hint.interface == d.interface)
    )


def candidates(hints: tuple[UsbHint, ...] | list[UsbHint], devices: list[Detected],
               kind: str) -> list[Detected]:
    return [d for d in devices if d.kind == kind and any(hint_matches(h, d) for h in hints)]


def find_node(devices: list[Detected], kind: str, node: str) -> Detected:
    for d in devices:
        if d.kind == kind and d.node == node:
            return d
    available = ", ".join(d.node for d in devices if d.kind == kind) or "none"
    raise ProfileError(f"no USB {kind} device {node!r} (available: {available})")


def to_match(d: Detected) -> UsbMatch:
    return UsbMatch(vendor_id=d.vendor_id, product_id=d.product_id, serial=d.serial,
                    interface=d.interface if d.kind == "tty" else "")
```

- [ ] **Step 4: Run the tests**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli
git commit -m "feat(cli): detect USB serial ports and sound cards from sysfs"
```

---

### Task 18: Station kits and generated udev rules

**Files:**
- Create: `cli/src/emcomm/udev.py`, `cli/src/emcomm/commands/station.py`
- Modify: `cli/src/emcomm/cli.py` (`COMMANDS = [operator, radios, station]`)
- Test: `cli/tests/test_udev.py`, `cli/tests/test_station.py`

**Interfaces:**
- Consumes: `detect.*`, `profiles.{save_station, load_station, list_stations}`, `radios.load_radios`, `models.*`.
- Produces:
  - `udev.udev_env_value(s) -> str`
  - `udev.render_rules(station, radio) -> str`: per kit device, the symlink/ALSA rule plus a rule that disables USB autosuspend for that device
  - `udev.apply_udev(paths, stations, radios, *, run=subprocess.run) -> bool`: True if any rules file changed. It deletes stale `70-emcomm-*.rules` files and reloads udev only when `paths.udev_rules == Path("/etc/udev/rules.d")`.
  - CLI:
    - `emcomm station detect`
    - `emcomm station add NAME --radio ID [--cat NODE] [--audio NODE] [--ptt M] [--no-udev]`
    - `emcomm station list`
    - `emcomm station apply-udev`, which prints `udev: updated` or `udev: up to date`

- [ ] **Step 1: Write the failing tests**

`cli/tests/test_udev.py`:

```python
from emcomm.models import RadioDef, Station, UsbMatch
from emcomm.udev import apply_udev, render_rules, udev_env_value

IC7300 = RadioDef(id="icom-ic7300", vendor="Icom", model="IC-7300", hamlib_model=3073,
                  baud=19200, ptt="cat")
KIT = Station(name="kita", radio="icom-ic7300",
              cat=UsbMatch("10c4", "ea60", "IC-7300 03001234 A", "00"),
              audio=UsbMatch("08bb", "2901"))


def test_env_value_matches_udev_escaping():
    assert udev_env_value("IC-7300 03001234 A") == "IC-7300_03001234_A"
    assert udev_env_value("a/b") == "a_b"


def test_render_rules():
    text = render_rules(KIT, IC7300)
    lines = text.splitlines()
    assert lines[0].startswith("# Managed by emcomm")
    assert lines[1] == (
        'SUBSYSTEM=="tty", ENV{ID_VENDOR_ID}=="10c4", ENV{ID_MODEL_ID}=="ea60", '
        'ENV{ID_SERIAL_SHORT}=="IC-7300_03001234_A", ENV{ID_USB_INTERFACE_NUM}=="00", '
        'SYMLINK+="emcomm/cat-kita", ENV{ID_MM_DEVICE_IGNORE}="1"'
    )
    assert lines[2] == (
        'ACTION=="add", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="10c4", '
        'ATTR{idProduct}=="ea60", ATTR{serial}=="IC-7300 03001234 A", TEST=="power/control", '
        'ATTR{power/control}="on"'
    )
    assert lines[3] == (
        'SUBSYSTEM=="sound", KERNEL=="card*", ATTRS{idVendor}=="08bb", '
        'ATTRS{idProduct}=="2901", ATTR{id}="EMCOMM_KITA"'
    )
    assert lines[4].endswith('ATTR{idProduct}=="2901", TEST=="power/control", ATTR{power/control}="on"')


def test_render_without_devices():
    assert len(render_rules(Station(name="bench", radio="generic-vox"), IC7300).splitlines()) == 1


def test_apply_writes_and_prunes(paths):
    paths.udev_rules.mkdir(parents=True)
    stale = paths.udev_rules / "70-emcomm-old.rules"
    stale.write_text("x")
    other = paths.udev_rules / "99-local.rules"
    other.write_text("keep")
    calls = []
    assert apply_udev(paths, [KIT], {"icom-ic7300": IC7300}, run=calls.append) is True
    assert (paths.udev_rules / "70-emcomm-kita.rules").is_file()
    assert not stale.exists() and other.exists()
    assert calls == []  # not the real /etc/udev/rules.d, so no udevadm
    assert apply_udev(paths, [KIT], {"icom-ic7300": IC7300}, run=calls.append) is False
```

`cli/tests/test_station.py`:

```python
import tomllib

from emcomm.cli import main

from sysfs import add_sound, add_tty, make_usb


def plug_ic7300(paths):
    add_tty(paths.sysfs, make_usb(paths.sysfs, "1-1", "10c4", "ea60", "IC-7300 0300 A",
                                  "IC-7300"), "ttyUSB0")
    add_sound(paths.sysfs, make_usb(paths.sysfs, "1-2", "08bb", "2901"), "card1")


def test_add_auto_detects(paths, capsys):
    plug_ic7300(paths)
    assert main(["station", "add", "kita", "--radio", "icom-ic7300"], paths=paths) == 0
    data = tomllib.loads((paths.stations_dir / "kita.toml").read_text())
    assert data["cat"] == {"vendor_id": "10c4", "product_id": "ea60",
                           "serial": "IC-7300 0300 A", "interface": "00"}
    assert data["audio"] == {"vendor_id": "08bb", "product_id": "2901"}
    assert (paths.udev_rules / "70-emcomm-kita.rules").is_file()
    out = capsys.readouterr().out
    assert "/dev/emcomm/cat-kita" in out and "CI-V USB Baud Rate" in out


def test_add_explicit_nodes(paths):
    plug_ic7300(paths)
    assert main(["station", "add", "kitb", "--radio", "generic-rts", "--cat", "ttyUSB0",
                 "--audio", "card1", "--no-udev"], paths=paths) == 0
    assert not paths.udev_rules.exists()


def test_add_ambiguous(paths, capsys):
    plug_ic7300(paths)
    add_tty(paths.sysfs, make_usb(paths.sysfs, "1-5", "10c4", "ea60", "IC-7300 0999 A",
                                  "IC-7300"), "ttyUSB3")
    assert main(["station", "add", "kita", "--radio", "icom-ic7300"], paths=paths) == 1
    assert "ttyUSB0, ttyUSB3" in capsys.readouterr().err


def test_add_without_hardware(paths, capsys):
    assert main(["station", "add", "bench", "--radio", "generic-vox", "--no-udev"],
                paths=paths) == 0
    assert "cat" not in tomllib.loads((paths.stations_dir / "bench.toml").read_text())


def test_unknown_radio(paths, capsys):
    assert main(["station", "add", "x", "--radio", "nope"], paths=paths) == 1
    assert "emcomm radios" in capsys.readouterr().err


def test_list_and_detect(paths, capsys):
    plug_ic7300(paths)
    main(["station", "add", "kita", "--radio", "icom-ic7300", "--no-udev"], paths=paths)
    capsys.readouterr()
    assert main(["station", "list"], paths=paths) == 0
    assert "EMCOMM_KITA" in capsys.readouterr().out
    assert main(["station", "detect"], paths=paths) == 0
    assert "10c4:ea60" in capsys.readouterr().out


def test_apply_udev_command(paths, capsys):
    plug_ic7300(paths)
    main(["station", "add", "kita", "--radio", "icom-ic7300", "--no-udev"], paths=paths)
    capsys.readouterr()
    assert main(["station", "apply-udev"], paths=paths) == 0
    assert "udev: updated" in capsys.readouterr().out
    assert main(["station", "apply-udev"], paths=paths) == 0
    assert "udev: up to date" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_udev.py tests/test_station.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm.udev'`.

- [ ] **Step 3: Implement `udev.py`**

```python
"""Generate udev rules giving each station kit stable device names.

Rules are numbered 70 so ENV{ID_*} from 60-persistent-serial.rules is available and
ID_MM_DEVICE_IGNORE is set before ModemManager's 77/80 rules probe the port.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .models import RadioDef, Station, UsbMatch
from .paths import Paths

SYSTEM_RULES = Path("/etc/udev/rules.d")
UDEV_UNSAFE = re.compile(r"[^A-Za-z0-9#+\-.:=@_]")


def udev_env_value(value: str) -> str:
    """Mirror how udev's usb_id sanitizes strings into ID_* properties."""
    return UDEV_UNSAFE.sub("_", value.strip())


def rules_path(paths: Paths, station: Station) -> Path:
    return paths.udev_rules / f"70-emcomm-{station.name}.rules"


def _no_autosuspend(m: UsbMatch) -> str:
    """Laptops autosuspend idle USB devices, which drops CAT/audio mid-QSO; keep kit devices on."""
    keys = ['ACTION=="add"', 'SUBSYSTEM=="usb"', 'ENV{DEVTYPE}=="usb_device"',
            f'ATTR{{idVendor}}=="{m.vendor_id}"', f'ATTR{{idProduct}}=="{m.product_id}"']
    if m.serial:
        keys.append(f'ATTR{{serial}}=="{m.serial}"')
    keys += ['TEST=="power/control"', 'ATTR{power/control}="on"']
    return ", ".join(keys)


def render_rules(station: Station, radio: RadioDef) -> str:
    lines = [f"# Managed by emcomm: station {station.name} ({radio.label}). "
             "Regenerate with `emcomm station apply-udev`."]
    if station.cat:
        m = station.cat
        keys = ['SUBSYSTEM=="tty"', f'ENV{{ID_VENDOR_ID}}=="{m.vendor_id}"',
                f'ENV{{ID_MODEL_ID}}=="{m.product_id}"']
        if m.serial:
            keys.append(f'ENV{{ID_SERIAL_SHORT}}=="{udev_env_value(m.serial)}"')
        if m.interface:
            keys.append(f'ENV{{ID_USB_INTERFACE_NUM}}=="{m.interface}"')
        keys += [f'SYMLINK+="emcomm/cat-{station.name}"', 'ENV{ID_MM_DEVICE_IGNORE}="1"']
        lines.append(", ".join(keys))
        lines.append(_no_autosuspend(m))
    if station.audio:
        m = station.audio
        keys = ['SUBSYSTEM=="sound"', 'KERNEL=="card*"', f'ATTRS{{idVendor}}=="{m.vendor_id}"',
                f'ATTRS{{idProduct}}=="{m.product_id}"']
        if m.serial:
            keys.append(f'ATTRS{{serial}}=="{m.serial}"')
        keys.append(f'ATTR{{id}}="{station.alsa_id}"')
        lines.append(", ".join(keys))
        lines.append(_no_autosuspend(m))
    return "\n".join(lines) + "\n"


def apply_udev(
    paths: Paths,
    stations: list[Station],
    radios: dict[str, RadioDef],
    *,
    run: Callable = subprocess.run,
) -> bool:
    paths.udev_rules.mkdir(parents=True, exist_ok=True)
    changed = False
    wanted = set()
    for st in stations:
        path = rules_path(paths, st)
        wanted.add(path)
        text = render_rules(st, radios[st.radio])
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            changed = True
    for path in paths.udev_rules.glob("70-emcomm-*.rules"):
        if path not in wanted:
            path.unlink()
            changed = True
    if changed and paths.udev_rules == SYSTEM_RULES:
        run(["udevadm", "control", "--reload"], check=True)
        run(["udevadm", "trigger", "--action=add", "--subsystem-match=tty",
             "--subsystem-match=sound"], check=True)
    return changed
```

- [ ] **Step 4: Implement `commands/station.py`**

```python
"""`emcomm station` — station kits (radio + interface on this machine)."""

from __future__ import annotations

import argparse

from ..detect import candidates, find_node, scan, to_match
from ..models import PTT_METHODS, RadioDef, Station, UsbHint
from ..paths import Paths
from ..profiles import list_stations, save_station
from ..radios import load_radios
from ..udev import apply_udev
from ..validation import ProfileError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("station", help="manage station kits")
    actions = p.add_subparsers(dest="action", required=True)
    actions.add_parser("detect", help="list USB serial ports and sound cards").set_defaults(
        func=cmd_detect)
    add = actions.add_parser("add", help="create or update a station kit (needs root)")
    add.add_argument("name", help="short kit name: lowercase letters, digits, '-', max 8")
    add.add_argument("--radio", required=True, help="radio definition id (see `emcomm radios`)")
    add.add_argument("--cat", help="serial node for CAT/PTT, e.g. ttyUSB0 (default: auto)")
    add.add_argument("--audio", help="sound card node, e.g. card1 (default: auto)")
    add.add_argument("--ptt", choices=PTT_METHODS, help="override the radio's PTT method")
    add.add_argument("--no-udev", action="store_true", help="do not write udev rules")
    add.set_defaults(func=cmd_add)
    actions.add_parser("list", help="list station kits").set_defaults(func=cmd_list)
    actions.add_parser("apply-udev", help="regenerate udev rules (needs root)").set_defaults(
        func=cmd_apply_udev)


def cmd_detect(args: argparse.Namespace, paths: Paths) -> int:
    devices = scan(paths.sysfs)
    if not devices:
        print("no USB serial ports or sound cards found")
    for d in devices:
        iface = f" if{d.interface}" if d.interface else ""
        print(f"{d.kind:<6} {d.node:<8} {d.vendor_id}:{d.product_id}{iface:<5} "
              f"{d.product} [{d.serial}]")
    return 0


def _pick(kind: str, flag: str | None, hints: tuple[UsbHint, ...], devices, option: str):
    if flag:
        return to_match(find_node(devices, kind, flag))
    if not hints:
        return None
    found = candidates(hints, devices, kind)
    if len(found) > 1:
        names = ", ".join(d.node for d in found)
        raise ProfileError(f"several {kind} devices match ({names}); choose one with {option}")
    return to_match(found[0]) if found else None


def cmd_add(args: argparse.Namespace, paths: Paths) -> int:
    radios = load_radios(paths.radios_dir)
    if args.radio not in radios:
        raise ProfileError(f"unknown radio {args.radio!r}; see `emcomm radios`")
    radio: RadioDef = radios[args.radio]
    devices = scan(paths.sysfs)
    station = Station(
        name=args.name,
        radio=radio.id,
        cat=_pick("tty", args.cat, radio.cat_hints, devices, "--cat"),
        audio=_pick("sound", args.audio, radio.audio_hints, devices, "--audio"),
        ptt=args.ptt,
    )
    path = save_station(paths, station)
    print(f"saved station {station.name} ({radio.label}) -> {path}")
    if station.cat:
        print(f"  CAT/PTT port: {station.cat_link}")
    elif station.ptt_method(radio) in ("rts", "dtr") or radio.hamlib_model != 1:
        print("  warning: no CAT serial port found; plug in the radio or pass --cat")
    if station.audio:
        print(f"  sound card:   {station.alsa_id} (replug the radio after udev rules change)")
    if not args.no_udev:
        _apply(paths, radios)
    if radio.notes:
        print("  radio settings:")
        for note in radio.notes:
            print(f"    - {note}")
    return 0


def cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    stations = list_stations(paths)
    if not stations:
        print("no station kits yet; add one with `emcomm station add NAME --radio ID`")
    for st in stations:
        cat = st.cat_link if st.cat else "-"
        audio = st.alsa_id if st.audio else "-"
        print(f"{st.name:<9} {st.radio:<18} {cat:<26} {audio}")
    return 0


def _apply(paths: Paths, radios: dict[str, RadioDef]) -> None:
    changed = apply_udev(paths, list_stations(paths), radios)
    print("udev: updated" if changed else "udev: up to date")


def cmd_apply_udev(args: argparse.Namespace, paths: Paths) -> int:
    _apply(paths, load_radios(paths.radios_dir))
    return 0
```

In `cli.py`, import `station` and set `COMMANDS = [operator, radios, station]`.

- [ ] **Step 5: Run the tests**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add cli
git commit -m "feat(cli): station kits with auto-detection and generated udev rules"
```

---

### Task 19: Config renderers — WSJT-X, JS8Call, fldigi (managed keys only)

**Files:**
- Create: `cli/src/emcomm/render/__init__.py` (empty), `cli/src/emcomm/render/{context,ini,qtini,xml,fldigi}.py`
- Test: `cli/tests/fixtures/WSJT-X.ini`, `cli/tests/fixtures/fldigi_def.xml`, `cli/tests/test_render_qt_fldigi.py`

**Interfaces:**
- Consumes: `models.{Operator, Station, RadioDef}`.
- Produces:
  - `context.RIGCTLD_ADDR = "127.0.0.1:4532"`
  - `context.RenderContext(operator, station, radio)`, with `.ptt -> str` and `.alsa_device -> str | None` (`"sysdefault:CARD=<alsa_id>"`)
  - `ini.set_ini_keys(text, section, values) -> str`: changes only the named keys, byte-for-byte preserving everything else.
  - `qtini.PTT_VARIANT`, `qtini.wsjtx_values(ctx) -> dict[str, str]`, `qtini.render_wsjtx(existing, ctx) -> str` (used for both `WSJT-X.ini` and `JS8Call.ini`)
  - `xml.set_xml_elements(text, root, values) -> str`
  - `fldigi.fldigi_values(ctx)`, `fldigi.render_fldigi(existing, ctx) -> str`
- A renderer always has the signature `(existing: str | None, ctx: RenderContext) -> str | None`. `None` means "nothing to write for this station".

- [ ] **Step 1: Create the fixtures**

`cli/tests/fixtures/WSJT-X.ini`. Its shape matches real WSJT-X files; the `\0` sequences are literal backslash text:

```ini
[Common]
Mode=FT8
NDepth=3

[Configuration]
MyCall=N0CALL
Font="Sans Serif,10,-1,5,50,0,0,0,0,0"
Rig=None
PTTMethod=@Variant(\0\0\0\x7f\0\0\0\x1eTransceiverFactory::PTTMethod\0\0\0\0\xfPTT_method_VOX\0)
SoundInName=default
DecodeAtStartup=true

[MainWindow]
geometry=@ByteArray(\x1\xd9\xd0\xcb)
```

`cli/tests/fixtures/fldigi_def.xml`:

```xml
<FLDIGI_DEFS>
<MYCALL>N0CALL</MYCALL>
<MYQTH>Somewhere</MYQTH>
<HAMRIGMODEL>0</HAMRIGMODEL>
<WFREFLEVEL>-20</WFREFLEVEL>
</FLDIGI_DEFS>
```

- [ ] **Step 2: Write the failing tests**

`cli/tests/test_render_qt_fldigi.py`:

```python
from pathlib import Path

from emcomm.models import Operator, RadioDef, Station, UsbMatch
from emcomm.render.context import RenderContext
from emcomm.render.fldigi import render_fldigi
from emcomm.render.ini import set_ini_keys
from emcomm.render.qtini import PTT_VARIANT, render_wsjtx
from emcomm.render.xml import set_xml_elements

FIX = Path(__file__).parent / "fixtures"
IC7300 = RadioDef(id="icom-ic7300", vendor="Icom", model="IC-7300", hamlib_model=3073,
                  baud=19200, ptt="cat")
VOX = RadioDef(id="generic-vox", vendor="Generic", model="VOX", hamlib_model=1, baud=9600,
               ptt="vox")
OP = Operator(callsign="K7ABC", name="Pat Q", grid="DN16bk")
KIT = Station(name="kita", radio="icom-ic7300", cat=UsbMatch("10c4", "ea60"),
              audio=UsbMatch("08bb", "2901"))


def ctx(radio=IC7300, station=KIT, op=OP):
    return RenderContext(operator=op, station=station, radio=radio)


def test_set_ini_keys_preserves_other_lines():
    original = (FIX / "WSJT-X.ini").read_text()
    out = set_ini_keys(original, "Configuration", {"MyCall": "K7ABC", "MyGrid": "DN16bk"})
    assert "MyCall=K7ABC\n" in out
    # new keys are appended at the end of the section, before the blank separator line
    assert "DecodeAtStartup=true\nMyGrid=DN16bk\n\n[MainWindow]" in out
    for line in original.splitlines():
        if not line.startswith("MyCall="):
            assert line in out.splitlines()


def test_set_ini_keys_creates_section_and_file():
    assert set_ini_keys("", "Configuration", {"A": "1"}) == "[Configuration]\nA=1\n"
    assert set_ini_keys("[X]\nk=v", "Configuration", {"A": "1"}) == "[X]\nk=v\n\n[Configuration]\nA=1\n"


def test_wsjtx_render():
    out = render_wsjtx((FIX / "WSJT-X.ini").read_text(), ctx())
    lines = out.splitlines()
    assert "MyCall=K7ABC" in lines
    assert "MyGrid=DN16bk" in lines
    assert "Rig=Hamlib NET rigctl" in lines
    assert "CATNetworkPort=127.0.0.1:4532" in lines
    assert "PTTMethod=" + PTT_VARIANT.format("CAT") in lines
    assert 'SoundInName="sysdefault:CARD=EMCOMM_KITA"' in lines
    assert 'SoundOutName="sysdefault:CARD=EMCOMM_KITA"' in lines
    assert "Mode=FT8" in lines and "geometry=@ByteArray(\\x1\\xd9\\xd0\\xcb)" in lines


def test_wsjtx_vox_and_no_audio():
    out = render_wsjtx(None, ctx(radio=VOX, station=Station(name="bench", radio="generic-vox")))
    assert "PTTMethod=" + PTT_VARIANT.format("VOX") in out.splitlines()
    assert "SoundInName" not in out


def test_variant_literal_is_exact():
    assert PTT_VARIANT.format("CAT") == (
        r"@Variant(\0\0\0\x7f\0\0\0\x1eTransceiverFactory::PTTMethod\0\0\0\0\xfPTT_method_CAT\0)"
    )


def test_set_xml_elements():
    out = set_xml_elements((FIX / "fldigi_def.xml").read_text(), "FLDIGI_DEFS",
                           {"MYCALL": "K7ABC", "MYLOC": "DN16bk", "MYNAME": "A&B"})
    assert "<MYCALL>K7ABC</MYCALL>" in out
    assert "<MYLOC>DN16bk</MYLOC>" in out
    assert "<MYNAME>A&amp;B</MYNAME>" in out
    assert "<WFREFLEVEL>-20</WFREFLEVEL>" in out
    assert out.rstrip().endswith("</FLDIGI_DEFS>")


def test_fldigi_render():
    out = render_fldigi((FIX / "fldigi_def.xml").read_text(), ctx())
    for tag, value in (("MYCALL", "K7ABC"), ("MYLOC", "DN16bk"), ("MYNAME", "Pat Q"),
                       ("CHKUSEHAMLIBIS", "1"), ("HAMRIGMODEL", "2"),
                       ("HAMRIGDEVICE", "127.0.0.1:4532"), ("HAMLIBCMDPTT", "1"),
                       ("CHKUSERIGCATIS", "0"), ("CHKUSEXMLRPCIS", "0")):
        assert f"<{tag}>{value}</{tag}>" in out
    assert "<HAMRIGNAME></HAMRIGNAME>" in out
    assert "<MYQTH>Somewhere</MYQTH>" in out
    vox = render_fldigi(None, ctx(radio=VOX))
    assert "<HAMLIBCMDPTT>0</HAMLIBCMDPTT>" in vox
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_render_qt_fldigi.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm.render'`.

- [ ] **Step 4: Implement `render/context.py` and `render/ini.py`**

`render/context.py`:

```python
"""Inputs shared by every config renderer."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Operator, RadioDef, Station

RIGCTLD_ADDR = "127.0.0.1:4532"


@dataclass(frozen=True)
class RenderContext:
    operator: Operator
    station: Station
    radio: RadioDef

    @property
    def ptt(self) -> str:
        return self.station.ptt_method(self.radio)

    @property
    def alsa_device(self) -> str | None:
        return f"sysdefault:CARD={self.station.alsa_id}" if self.station.audio else None
```

`render/ini.py`:

```python
"""Line-level editing of Qt/INI files that leaves unmanaged bytes untouched."""

from __future__ import annotations

from collections.abc import Mapping


def set_ini_keys(text: str, section: str, values: Mapping[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    header = f"[{section}]"
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        return "".join([*lines, header + "\n", *(f"{k}={v}\n" for k, v in values.items())])

    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
               len(lines))
    remaining = dict(values)
    for i in range(start + 1, end):
        if "=" in lines[i]:
            key = lines[i].split("=", 1)[0].strip()
            if key in remaining:
                lines[i] = f"{key}={remaining.pop(key)}\n"
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines[insert_at:insert_at] = [f"{k}={v}\n" for k, v in remaining.items()]
    return "".join(lines)
```

- [ ] **Step 5: Implement `render/qtini.py`, `render/xml.py`, and `render/fldigi.py`**

`render/qtini.py`:

```python
"""WSJT-X / JS8Call [Configuration] keys pointing at the rigctld hub."""

from __future__ import annotations

from .context import RIGCTLD_ADDR, RenderContext
from .ini import set_ini_keys

# QSettings serialization of TransceiverFactory::PTTMethod; both enum names are 14 chars.
PTT_VARIANT = (
    r"@Variant(\0\0\0\x7f\0\0\0\x1eTransceiverFactory::PTTMethod\0\0\0\0\xfPTT_method_{}\0)"
)


def wsjtx_values(ctx: RenderContext) -> dict[str, str]:
    values = {
        "MyCall": ctx.operator.callsign,
        "Rig": "Hamlib NET rigctl",
        "CATNetworkPort": RIGCTLD_ADDR,
        "PTTMethod": PTT_VARIANT.format("VOX" if ctx.ptt == "vox" else "CAT"),
    }
    if ctx.operator.grid:
        values["MyGrid"] = ctx.operator.grid
    if ctx.alsa_device:
        values["SoundInName"] = values["SoundOutName"] = f'"{ctx.alsa_device}"'
    return values


def render_wsjtx(existing: str | None, ctx: RenderContext) -> str:
    return set_ini_keys(existing or "", "Configuration", wsjtx_values(ctx))
```

`render/xml.py`:

```python
"""Element-level editing of flat XML settings files (fldigi_def.xml style)."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping


def set_xml_elements(text: str, root: str, values: Mapping[str, str]) -> str:
    if not text.strip():
        text = f"<{root}>\n</{root}>\n"
    for tag, value in values.items():
        element = f"<{tag}>{html.escape(value, quote=False)}</{tag}>"
        pattern = re.compile(rf"<{tag}>.*?</{tag}>|<{tag}\s*/>", re.S)
        text, n = pattern.subn(lambda _m, e=element: e, text, count=1)
        if n == 0:
            close = text.rfind(f"</{root}>")
            if close < 0:
                raise ValueError(f"settings file has no </{root}> element")
            text = text[:close] + element + "\n" + text[close:]
    return text
```

`render/fldigi.py`:

```python
"""fldigi_def.xml: identity plus hamlib NET rigctl (model 2) via the hub."""

from __future__ import annotations

from .context import RIGCTLD_ADDR, RenderContext
from .xml import set_xml_elements


def fldigi_values(ctx: RenderContext) -> dict[str, str]:
    values = {
        "MYCALL": ctx.operator.callsign,
        "CHKUSEHAMLIBIS": "1",
        "HAMRIGMODEL": "2",
        "HAMRIGNAME": "",
        "HAMRIGDEVICE": RIGCTLD_ADDR,
        "HAMLIBCMDPTT": "0" if ctx.ptt == "vox" else "1",
        "CHKUSERIGCATIS": "0",
        "CHKUSEXMLRPCIS": "0",
    }
    if ctx.operator.name:
        values["MYNAME"] = ctx.operator.name
    if ctx.operator.grid:
        values["MYLOC"] = ctx.operator.grid
    return values


def render_fldigi(existing: str | None, ctx: RenderContext) -> str:
    return set_xml_elements(existing or "", "FLDIGI_DEFS", fldigi_values(ctx))
```

`HAMRIGNAME` is cleared on purpose: fldigi re-derives the model from a non-empty name.

- [ ] **Step 6: Run the tests**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add cli
git commit -m "feat(cli): managed-key renderers for WSJT-X, JS8Call and fldigi"
```

---

### Task 20: Config renderers — Pat, Direwolf, rigctld

**Files:**
- Create: `cli/src/emcomm/render/{pat,direwolf,rigctld}.py`
- Test: `cli/tests/test_render_services.py`

**Interfaces:**
- Consumes: `render.context.{RenderContext, RIGCTLD_ADDR}`, `models.ax25_callsign`.
- Produces:
  - `pat.PAT_DEFAULTS: dict` and `pat.render_pat(existing, ctx) -> str`. Invalid existing JSON raises `ValueError`.
  - `direwolf.render_direwolf(existing, ctx) -> str | None`: `None` when the station has no sound card. The file is fully owned by emcomm.
  - `rigctld.rigctld_args(ctx) -> list[str]` and `rigctld.render_rigctld(existing, ctx) -> str`: writes `RIGCTLD_ARGS="..."`, read through `EnvironmentFile=` by `emcomm-rigctld.service`.

- [ ] **Step 1: Write the failing tests**

`cli/tests/test_render_services.py`:

```python
import json

import pytest

from emcomm.models import Operator, RadioDef, Station, UsbMatch
from emcomm.render.context import RenderContext
from emcomm.render.direwolf import render_direwolf
from emcomm.render.pat import render_pat
from emcomm.render.rigctld import render_rigctld, rigctld_args

IC7300 = RadioDef(id="icom-ic7300", vendor="Icom", model="IC-7300", hamlib_model=3073,
                  baud=19200, ptt="cat", set_conf=(("auto_power_on", "0"),))
RTS = RadioDef(id="generic-rts", vendor="Generic", model="RTS", hamlib_model=1, baud=9600,
               ptt="rts")
VOX = RadioDef(id="generic-vox", vendor="Generic", model="VOX", hamlib_model=1, baud=9600,
               ptt="vox")
OP = Operator(callsign="VE7/K7ABC", grid="DN16bk")
KIT = Station(name="kita", radio="x", cat=UsbMatch("10c4", "ea60"), audio=UsbMatch("08bb", "2901"))


def c(radio, station=KIT):
    return RenderContext(operator=OP, station=station, radio=radio)


def test_pat_new_file_uses_defaults():
    data = json.loads(render_pat(None, c(IC7300)))
    assert data["mycall"] == "VE7/K7ABC"
    assert data["locator"] == "DN16bk"
    assert data["http_addr"] == "localhost:8080"
    assert data["hamlib_rigs"]["emcomm"] == {"network": "tcp", "address": "127.0.0.1:4532",
                                             "VFO": ""}
    assert data["ardop"]["rig"] == "emcomm" and data["ardop"]["ptt_ctrl"] is True
    assert data["varahf"]["ptt_ctrl"] is True


def test_pat_preserves_unmanaged_keys():
    existing = json.dumps({"mycall": "N0CALL", "secure_login_password": "s3cret",
                           "hamlib_rigs": {"ft8": {"address": "x"}}, "ardop": {"addr": "h:1"}})
    data = json.loads(render_pat(existing, c(VOX)))
    assert data["secure_login_password"] == "s3cret"
    assert data["hamlib_rigs"]["ft8"] == {"address": "x"}
    assert data["ardop"] == {"addr": "h:1", "rig": "emcomm", "ptt_ctrl": False}


def test_pat_invalid_json():
    with pytest.raises(ValueError, match="pat"):
        render_pat("{nope", c(IC7300))


def test_direwolf():
    out = render_direwolf(None, c(IC7300))
    assert "ADEVICE plughw:CARD=EMCOMM_KITA,DEV=0" in out
    assert "MYCALL K7ABC\n" in out
    assert "PTT RIG 2 127.0.0.1:4532" in out
    assert "PTT" not in render_direwolf(None, c(VOX))
    assert render_direwolf(None, c(IC7300, Station(name="b", radio="x"))) is None


def test_rigctld_args():
    assert rigctld_args(c(IC7300)) == [
        "-m", "3073", "-T", "127.0.0.1", "-t", "4532", "-r", "/dev/emcomm/cat-kita",
        "-s", "19200", "--set-conf=auto_power_on=0"]
    assert rigctld_args(c(RTS)) == [
        "-m", "1", "-T", "127.0.0.1", "-t", "4532", "-P", "RTS", "-p", "/dev/emcomm/cat-kita"]
    assert rigctld_args(c(VOX, Station(name="b", radio="x"))) == [
        "-m", "1", "-T", "127.0.0.1", "-t", "4532"]
    assert render_rigctld(None, c(VOX, Station(name="b", radio="x"))).endswith(
        'RIGCTLD_ARGS="-m 1 -T 127.0.0.1 -t 4532"\n')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_render_services.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'emcomm.render.pat'`.

- [ ] **Step 3: Implement the renderers**

`render/pat.py`:

```python
"""Pat config.json: identity plus an "emcomm" hamlib rig on the rigctld hub.

Secrets (secure_login_password) are never written; Pat prompts for them.
"""

from __future__ import annotations

import copy
import json

from .context import RIGCTLD_ADDR, RenderContext

# Mirrors Pat v1.0.0 cfg.DefaultConfig for a fresh file.
PAT_DEFAULTS: dict = {
    "mycall": "",
    "secure_login_password": "",
    "auxiliary_addresses": [],
    "locator": "",
    "service_codes": ["PUBLIC"],
    "http_addr": "localhost:8080",
    "motd": ["Open source Winlink client - getpat.io"],
    "connect_aliases": {"telnet": "telnet://{mycall}:CMSTelnet@cms.winlink.org:8772/wl2k"},
    "listen": [],
    "hamlib_rigs": {},
    "auto_download_size_limit": -1,
    "ax25": {"engine": "agwpe", "rig": "",
             "beacon": {"every": 3600, "message": "Winlink P2P", "destination": "IDENT"}},
    "agwpe": {"addr": "localhost:8000", "radio_port": 0},
    "ardop": {"addr": "localhost:8515", "rig": "", "ptt_ctrl": False, "beacon_interval": 0,
              "cwid_enabled": True},
    "telnet": {"listen_addr": ":8774", "password": ""},
    "varahf": {"addr": "localhost:8300", "bandwidth": 2300, "rig": "", "ptt_ctrl": False},
    "varafm": {"addr": "localhost:8300", "rig": "", "ptt_ctrl": False},
    "gpsd": {"addr": "localhost:2947", "enable_http": False, "allow_forms": False,
             "use_server_time": False},
}


def render_pat(existing: str | None, ctx: RenderContext) -> str:
    if existing and existing.strip():
        try:
            data = json.loads(existing)
        except json.JSONDecodeError as exc:
            raise ValueError(f"pat config.json is not valid JSON: {exc}") from None
    else:
        data = copy.deepcopy(PAT_DEFAULTS)
    data["mycall"] = ctx.operator.callsign
    if ctx.operator.grid:
        data["locator"] = ctx.operator.grid
    data.setdefault("hamlib_rigs", {})["emcomm"] = {
        "network": "tcp", "address": RIGCTLD_ADDR, "VFO": ""}
    ptt_ctrl = ctx.ptt != "vox"
    for transport in ("ardop", "varahf"):
        section = data.setdefault(transport, {})
        section["rig"] = "emcomm"
        section["ptt_ctrl"] = ptt_ctrl
    data.setdefault("ax25", {})["rig"] = "emcomm"
    return json.dumps(data, indent=2) + "\n"
```

`render/direwolf.py`:

```python
"""direwolf.conf for the emcomm-direwolf user service (fully managed)."""

from __future__ import annotations

from ..models import ax25_callsign
from .context import RIGCTLD_ADDR, RenderContext


def render_direwolf(existing: str | None, ctx: RenderContext) -> str | None:
    if not ctx.alsa_device:
        return None
    lines = [
        "# Managed by emcomm: regenerated by `emcomm use`. Change profiles instead of this file.",
        f"ADEVICE plughw:CARD={ctx.station.alsa_id},DEV=0",
        "ACHANNELS 1",
        "CHANNEL 0",
        f"MYCALL {ax25_callsign(ctx.operator.callsign)}",
        "MODEM 1200",
    ]
    if ctx.ptt != "vox":
        lines.append(f"PTT RIG 2 {RIGCTLD_ADDR}")
    lines += ["AGWPORT 8000", "KISSPORT 8001"]
    return "\n".join(lines) + "\n"
```

`render/rigctld.py`:

```python
"""Arguments for the rigctld hub (emcomm-rigctld.service EnvironmentFile)."""

from __future__ import annotations

from .context import RenderContext

DUMMY_MODEL = 1


def rigctld_args(ctx: RenderContext) -> list[str]:
    args = ["-m", str(ctx.radio.hamlib_model), "-T", "127.0.0.1", "-t", "4532"]
    has_cat = ctx.station.cat is not None
    if ctx.radio.hamlib_model != DUMMY_MODEL and has_cat:
        args += ["-r", ctx.station.cat_link, "-s", str(ctx.radio.baud)]
    if ctx.ptt in ("rts", "dtr") and has_cat:
        args += ["-P", ctx.ptt.upper(), "-p", ctx.station.cat_link]
    if ctx.radio.set_conf:
        args.append("--set-conf=" + ",".join(f"{k}={v}" for k, v in ctx.radio.set_conf))
    return args


def render_rigctld(existing: str | None, ctx: RenderContext) -> str:
    return (
        "# Managed by emcomm: regenerated by `emcomm use`.\n"
        f'RIGCTLD_ARGS="{" ".join(rigctld_args(ctx))}"\n'
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli
git commit -m "feat(cli): Pat, Direwolf and rigctld hub renderers"
```

---

### Task 21: `emcomm use` and `emcomm status`

**Files:**
- Create: `cli/src/emcomm/apply.py`, `cli/src/emcomm/commands/use.py`, `cli/src/emcomm/commands/status.py`
- Modify: `cli/src/emcomm/cli.py` (`COMMANDS = [operator, radios, station, use, status]`)
- Test: `cli/tests/test_use.py`

**Interfaces:**
- Consumes: every renderer from Tasks 19–20, `profiles.{load_operator, load_station}`, `radios.load_radios`.
- Produces:
  - `apply.AppConfig(app, relpath, render)` and `apply.APP_CONFIGS`
  - `apply.SERVICES = ("emcomm-rigctld.service", "emcomm-direwolf.service", "emcomm-pat.service")`
  - `apply.FileChange(app, path, old, new)`
  - `apply.plan_changes(paths, ctx) -> list[FileChange]`
  - `apply.render_diff(changes, home) -> str`
  - `apply.apply_changes(paths, changes, now) -> Path | None` (returns the backup dir)
  - `apply.save_active(paths, callsign, station)` and `apply.load_active(paths) -> dict | None`
  - `apply.restart_services(run=subprocess.run) -> bool`
  - CLI: `emcomm use CALLSIGN --station NAME [--dry-run] [--yes]` and `emcomm status`
- Files written, relative to the user's home:
  - `.config/emcomm/rigctld.env`
  - `.config/WSJT-X.ini`
  - `.config/JS8Call.ini`
  - `.fldigi/fldigi_def.xml`
  - `.config/pat/config.json`
  - `.config/emcomm/direwolf.conf`

- [ ] **Step 1: Write the failing tests**

`cli/tests/test_use.py`:

```python
import tomllib

import pytest

from emcomm.cli import main
from emcomm.commands import use as use_cmd


@pytest.fixture
def ready(paths, monkeypatch):
    calls = []
    monkeypatch.setattr(use_cmd, "restart_services", lambda: calls.append("restart") or True)
    assert main(["operator", "add", "K7ABC", "--grid", "DN16bk"], paths=paths) == 0
    assert main(["station", "add", "bench", "--radio", "generic-vox", "--no-udev"],
                paths=paths) == 0
    return calls


def test_use_writes_configs_and_active(paths, ready, capsys):
    capsys.readouterr()
    assert main(["use", "k7abc", "--station", "bench", "--yes"], paths=paths) == 0
    ini = (paths.home / ".config/WSJT-X.ini").read_text()
    assert "MyCall=K7ABC" in ini and "CATNetworkPort=127.0.0.1:4532" in ini
    assert (paths.home / ".config/pat/config.json").is_file()
    assert (paths.home / ".fldigi/fldigi_def.xml").is_file()
    assert 'RIGCTLD_ARGS="-m 1' in (paths.home / ".config/emcomm/rigctld.env").read_text()
    assert not (paths.home / ".config/emcomm/direwolf.conf").exists()  # no sound card
    active = tomllib.loads(paths.active_file.read_text())
    assert active == {"operator": "K7ABC", "station": "bench"}
    assert ready == ["restart"]
    assert "+MyCall=K7ABC" in capsys.readouterr().out


def test_use_backs_up_and_preserves(paths, ready):
    ini = paths.home / ".config/WSJT-X.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text("[Configuration]\nMyCall=N0CALL\nFont=Mono\n")
    assert main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths) == 0
    assert "Font=Mono" in ini.read_text()
    backups = list((paths.state / "backups").glob("*/.config/WSJT-X.ini"))
    assert len(backups) == 1 and "N0CALL" in backups[0].read_text()


def test_dry_run_changes_nothing(paths, ready, capsys):
    assert main(["use", "K7ABC", "--station", "bench", "--dry-run"], paths=paths) == 0
    assert not (paths.home / ".config/WSJT-X.ini").exists()
    assert not paths.active_file.exists()
    assert "+MyCall=K7ABC" in capsys.readouterr().out


def test_second_run_is_noop(paths, ready, capsys):
    main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths)
    capsys.readouterr()
    assert main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths) == 0
    assert "already up to date" in capsys.readouterr().out


def test_declined_confirmation(paths, ready, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert main(["use", "K7ABC", "--station", "bench"], paths=paths) == 1
    assert not (paths.home / ".config/WSJT-X.ini").exists()


def test_status(paths, ready, capsys):
    assert main(["status"], paths=paths) == 0
    assert "no active operator" in capsys.readouterr().out
    main(["use", "K7ABC", "--station", "bench", "--yes"], paths=paths)
    capsys.readouterr()
    assert main(["status"], paths=paths) == 0
    out = capsys.readouterr().out
    assert "operator: K7ABC" in out and "station: bench (Generic VOX (audio only))" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_use.py`
Expected: FAIL with `ImportError: cannot import name 'use'`.

- [ ] **Step 3: Implement `apply.py`**

```python
"""Plan, diff, back up and write rendered app configs for the active selection."""

from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tomli_w

from .paths import Paths
from .render.context import RenderContext
from .render.direwolf import render_direwolf
from .render.fldigi import render_fldigi
from .render.pat import render_pat
from .render.qtini import render_wsjtx
from .render.rigctld import render_rigctld

Renderer = Callable[[str | None, RenderContext], str | None]


@dataclass(frozen=True)
class AppConfig:
    app: str
    relpath: str
    render: Renderer


APP_CONFIGS = (
    AppConfig("rigctld", ".config/emcomm/rigctld.env", render_rigctld),
    AppConfig("wsjtx", ".config/WSJT-X.ini", render_wsjtx),
    AppConfig("js8call", ".config/JS8Call.ini", render_wsjtx),
    AppConfig("fldigi", ".fldigi/fldigi_def.xml", render_fldigi),
    AppConfig("pat", ".config/pat/config.json", render_pat),
    AppConfig("direwolf", ".config/emcomm/direwolf.conf", render_direwolf),
)
SERVICES = ("emcomm-rigctld.service", "emcomm-direwolf.service", "emcomm-pat.service")


@dataclass(frozen=True)
class FileChange:
    app: str
    path: Path
    old: str | None
    new: str


def plan_changes(paths: Paths, ctx: RenderContext) -> list[FileChange]:
    changes = []
    for cfg in APP_CONFIGS:
        path = paths.home / cfg.relpath
        old = path.read_text() if path.exists() else None
        new = cfg.render(old, ctx)
        if new is not None and new != old:
            changes.append(FileChange(cfg.app, path, old, new))
    return changes


def render_diff(changes: list[FileChange], home: Path) -> str:
    out: list[str] = []
    for c in changes:
        rel = c.path.relative_to(home).as_posix()
        out.extend(difflib.unified_diff(
            (c.old or "").splitlines(keepends=True), c.new.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}"))
    return "".join(out)


def apply_changes(paths: Paths, changes: list[FileChange], now: datetime) -> Path | None:
    backup = paths.state / "backups" / now.strftime("%Y%m%dT%H%M%S")
    for c in changes:
        if c.old is not None:
            dest = backup / c.path.relative_to(paths.home)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(c.path, dest)
        c.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = c.path.with_name(c.path.name + ".emcomm-tmp")
        tmp.write_text(c.new)
        if c.old is not None:
            shutil.copymode(c.path, tmp)
        os.replace(tmp, c.path)
    return backup if backup.exists() else None


def save_active(paths: Paths, callsign: str, station: str) -> None:
    paths.active_file.parent.mkdir(parents=True, exist_ok=True)
    paths.active_file.write_text(tomli_w.dumps({"operator": callsign, "station": station}))


def load_active(paths: Paths) -> dict | None:
    if not paths.active_file.is_file():
        return None
    return tomllib.loads(paths.active_file.read_text())


def restart_services(run: Callable = subprocess.run) -> bool:
    """Restart emcomm user services that are already running; never starts stopped ones."""
    try:
        result = run(["systemctl", "--user", "try-restart", *SERVICES],
                     capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0
```

- [ ] **Step 4: Implement `commands/use.py` and `commands/status.py`**

`commands/use.py`:

```python
"""`emcomm use` — apply an operator + station to every app's config."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from ..apply import apply_changes, plan_changes, render_diff, restart_services, save_active
from ..paths import Paths
from ..profiles import load_operator, load_station
from ..radios import load_radios
from ..render.context import RenderContext
from ..validation import ProfileError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("use", help="switch operator/station and update app configs")
    p.add_argument("callsign")
    p.add_argument("--station", required=True)
    p.add_argument("--dry-run", action="store_true", help="show the diff only")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_use)


def cmd_use(args: argparse.Namespace, paths: Paths) -> int:
    operator = load_operator(paths, args.callsign)
    station = load_station(paths, args.station)
    radios = load_radios(paths.radios_dir)
    if station.radio not in radios:
        raise ProfileError(f"station {station.name} uses unknown radio {station.radio!r}")
    ctx = RenderContext(operator=operator, station=station, radio=radios[station.radio])
    changes = plan_changes(paths, ctx)
    if not changes:
        print("configs already up to date")
        if not args.dry_run:
            save_active(paths, operator.callsign, station.name)
        return 0
    print(render_diff(changes, paths.home), end="")
    if args.dry_run:
        return 0
    if not args.yes and input("Apply these changes? [y/N] ").strip().lower() not in ("y", "yes"):
        print("aborted")
        return 1
    backup = apply_changes(paths, changes, datetime.now())
    save_active(paths, operator.callsign, station.name)
    print(f"updated {len(changes)} file(s) for {operator.callsign} on {station.name}")
    if backup:
        print(f"previous files saved in {backup}")
    if not restart_services():
        print("note: could not restart emcomm user services; restart them yourself if running",
              file=sys.stderr)
    return 0
```

`commands/status.py`:

```python
"""`emcomm status` — show the active operator and station."""

from __future__ import annotations

import argparse

from ..apply import load_active
from ..paths import Paths
from ..profiles import load_station
from ..radios import load_radios


def register(sub: argparse._SubParsersAction) -> None:
    sub.add_parser("status", help="show the active operator and station").set_defaults(
        func=cmd_status)


def cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    active = load_active(paths)
    if not active:
        print("no active operator/station; run `emcomm use CALLSIGN --station NAME`")
        return 0
    station = load_station(paths, active["station"])
    radio = load_radios(paths.radios_dir).get(station.radio)
    label = radio.label if radio else station.radio
    print(f"operator: {active['operator']}")
    print(f"station: {station.name} ({label})")
    if station.cat:
        print(f"cat: {station.cat_link}")
    if station.audio:
        print(f"audio: {station.alsa_id}")
    return 0
```

In `cli.py`, set `from .commands import operator, radios, station, status, use` and `COMMANDS = [operator, radios, station, use, status]`.

- [ ] **Step 5: Run the tests**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add cli
git commit -m "feat(cli): emcomm use with diff, backups and service restart; emcomm status"
```

---

### Task 22: Ansible collection — `base` role and Molecule

**Files:**
- Create: `ansible/ansible_collections/emcomm/station/{galaxy.yml,README.md,meta/runtime.yml}`
- Create: `ansible/ansible_collections/emcomm/station/playbooks/station.yml`
- Create: `ansible/ansible_collections/emcomm/station/roles/base/{defaults/main.yml,vars/Debian.yml,vars/RedHat.yml,tasks/main.yml,tasks/repo-Debian.yml,tasks/repo-RedHat.yml,templates/emcomm.sources.j2}`
- Create: symlink `roles/base/files/emcomm-archive-keyring.asc` → `../../../../../../../keys/emcomm-archive-keyring.asc`
- Create: `ansible/ansible_collections/emcomm/station/extensions/molecule/default/{molecule.yml,Containerfile.j2,prepare.yml,converge.yml,verify.yml}`
- Create: `ansible/requirements-dev.txt`

**Interfaces:**
- Produces the role variables:
  - `emcomm_repo_url` (required)
  - `emcomm_channel` (default `testing`)
  - `emcomm_users` (default `[]`)
  - `emcomm_repo_refresh` (default `true`)
  - `emcomm_chrony_enable` (default `true`)
- On Debian it also writes `/etc/apt/sources.list.d/emcomm-backports.sources` and `/etc/apt/preferences.d/emcomm-backports.pref`, with the same pin as `targets.yaml`.
- Produces the repo files:
  - Debian: `/etc/apt/sources.list.d/emcomm.sources` and `/usr/share/keyrings/emcomm-archive-keyring.asc`
  - Fedora: `/etc/yum.repos.d/emcomm-<channel>.repo` and `/etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm`

  These paths and names must match `bootstrap.sh` (Task 24).
- Playbook `playbooks/station.yml`, consumed by `emcomm bootstrap` (Task 24).

- [ ] **Step 1: Create the collection metadata and playbook**

`galaxy.yml`:

```yaml
namespace: emcomm
name: station
version: 0.1.0
readme: README.md
authors:
  - emcommOS contributors
license:
  - Apache-2.0
description: Provision emcommOS ham radio / emcomm stations
dependencies: {}
```

`README.md`:

```markdown
# emcomm.station

Roles that turn a Debian 13 or Fedora machine into an emcommOS station:
`base` (repository, time sync, radio groups), `toolsets` (emcomm metapackages),
`radio_hw` (station kits and udev rules) and `services` (systemd user units for
rigctld, Direwolf and Pat). Run it with `emcomm bootstrap` or `playbooks/station.yml`.
```

`meta/runtime.yml`:

```yaml
requires_ansible: ">=2.16"
```

`playbooks/station.yml`:

```yaml
- name: Provision an emcommOS station
  hosts: all
  become: true
  roles:
    - emcomm.station.base
    - emcomm.station.toolsets
    - emcomm.station.radio_hw
    - emcomm.station.services
```

`ansible/requirements-dev.txt`:

```
ansible-core>=2.16
ansible-lint>=24
molecule>=24
molecule-plugins[podman]>=23.5
```

- [ ] **Step 2: Create the base role**

`roles/base/defaults/main.yml`:

```yaml
# Base URL of the emcommOS package repository, without trailing slash.
emcomm_repo_url: ""
emcomm_channel: testing
# Users who operate radios; added to the serial/audio groups.
emcomm_users: []
# Refresh package metadata after changing the repository definition.
emcomm_repo_refresh: true
# Install and enable chrony (disable in containers without systemd).
emcomm_chrony_enable: true
```

`roles/base/vars/Debian.yml`:

```yaml
emcomm_radio_groups: [dialout, audio, plugdev]
emcomm_chrony_service: chrony
# Must match the debian-13 extra_repos entry in targets.yaml (tools/tests/test_ansible_sync.py).
emcomm_backports_suite: trixie-backports
emcomm_backports_packages: ["libhamlib*", "wsjtx*", "direwolf"]
emcomm_backports_priority: 500
```

`roles/base/vars/RedHat.yml`:

```yaml
emcomm_radio_groups: [dialout, audio, lock]
emcomm_chrony_service: chronyd
```

`roles/base/tasks/main.yml`:

```yaml
- name: Check prerequisites
  ansible.builtin.assert:
    that:
      - emcomm_repo_url | length > 0
      - ansible_os_family in ["Debian", "RedHat"]
    fail_msg: >-
      Set emcomm_repo_url and run on a Debian- or Fedora-family system
      (other distributions arrive in later milestones).

- name: Load OS family variables
  ansible.builtin.include_vars: "{{ ansible_os_family }}.yml"

- name: Configure the emcommOS repository
  ansible.builtin.include_tasks: "repo-{{ ansible_os_family }}.yml"

- name: Install chrony
  ansible.builtin.package:
    name: chrony
    state: present
  when: emcomm_chrony_enable

- name: Enable chrony
  ansible.builtin.service:
    name: "{{ emcomm_chrony_service }}"
    enabled: true
    state: started
  when: emcomm_chrony_enable

- name: Ensure radio groups exist
  ansible.builtin.group:
    name: "{{ item }}"
    system: true
  loop: "{{ emcomm_radio_groups }}"

- name: Add operators to radio groups
  ansible.builtin.user:
    name: "{{ item }}"
    groups: "{{ emcomm_radio_groups }}"
    append: true
  loop: "{{ emcomm_users }}"
```

`roles/base/tasks/repo-Debian.yml`:

```yaml
- name: Install the emcommOS signing key
  ansible.builtin.copy:
    src: emcomm-archive-keyring.asc
    dest: /usr/share/keyrings/emcomm-archive-keyring.asc
    mode: "0644"

- name: Add the emcommOS apt source
  ansible.builtin.template:
    src: emcomm.sources.j2
    dest: /etc/apt/sources.list.d/emcomm.sources
    mode: "0644"
  register: emcomm_apt_source

- name: Add Debian backports (only pinned packages are taken from it)
  ansible.builtin.copy:
    dest: /etc/apt/sources.list.d/emcomm-backports.sources
    mode: "0644"
    content: |
      # Managed by emcommOS. Only packages listed in preferences.d/emcomm-backports.pref
      # are installed from backports.
      Types: deb
      URIs: http://deb.debian.org/debian
      Suites: {{ emcomm_backports_suite }}
      Components: main
      Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
  register: emcomm_backports_source

- name: Pin selected packages to backports
  ansible.builtin.copy:
    dest: /etc/apt/preferences.d/emcomm-backports.pref
    mode: "0644"
    content: |
      Package: {{ emcomm_backports_packages | join(' ') }}
      Pin: release n={{ emcomm_backports_suite }}
      Pin-Priority: {{ emcomm_backports_priority }}

- name: Refresh apt metadata
  ansible.builtin.apt:
    update_cache: true
  when: (emcomm_apt_source.changed or emcomm_backports_source.changed) and emcomm_repo_refresh
```

`roles/base/templates/emcomm.sources.j2`:

```
Types: deb
URIs: {{ emcomm_repo_url }}/{{ emcomm_channel }}/deb
Suites: {{ ansible_distribution | lower }}-{{ ansible_distribution_major_version }}
Components: main
Signed-By: /usr/share/keyrings/emcomm-archive-keyring.asc
```

`roles/base/tasks/repo-RedHat.yml`:

```yaml
- name: Install the emcommOS signing key
  ansible.builtin.copy:
    src: emcomm-archive-keyring.asc
    dest: /etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm
    mode: "0644"

- name: Add the emcommOS dnf repository
  ansible.builtin.yum_repository:
    name: "emcomm-{{ emcomm_channel }}"
    description: "emcommOS {{ emcomm_channel }}"
    baseurl: "{{ emcomm_repo_url }}/{{ emcomm_channel }}/rpm/{{ ansible_distribution | lower }}-$releasever/$basearch"
    gpgcheck: true
    repo_gpgcheck: true
    gpgkey: file:///etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm
    enabled: true
```

Create the key symlink:

```bash
mkdir -p ansible/ansible_collections/emcomm/station/roles/base/files
ln -s ../../../../../../../keys/emcomm-archive-keyring.asc \
  ansible/ansible_collections/emcomm/station/roles/base/files/emcomm-archive-keyring.asc
test -s ansible/ansible_collections/emcomm/station/roles/base/files/emcomm-archive-keyring.asc
```

- [ ] **Step 3: Create the Molecule scenario**

`extensions/molecule/default/molecule.yml`:

```yaml
driver:
  name: podman
platforms:
  - name: emcomm-debian-13
    image: docker.io/library/debian:13
    dockerfile: Containerfile.j2
    pre_build_image: false
    command: /sbin/init
    systemd: always
  - name: emcomm-fedora-44
    image: registry.fedoraproject.org/fedora:44
    dockerfile: Containerfile.j2
    pre_build_image: false
    command: /sbin/init
    systemd: always
provisioner:
  name: ansible
  inventory:
    group_vars:
      all:
        emcomm_repo_url: https://repo.invalid
        emcomm_repo_refresh: false
        emcomm_toolsets: []
        emcomm_stations: []
        emcomm_users: [operator]
verifier:
  name: ansible
```

`extensions/molecule/default/Containerfile.j2`:

```
FROM {{ item.image }}
RUN if command -v apt-get >/dev/null; then \
      apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv python3 sudo udev && apt-get clean; \
    else \
      dnf -y install systemd python3 sudo systemd-udev && dnf clean all; \
    fi
```

`extensions/molecule/default/prepare.yml`:

```yaml
- name: Prepare
  hosts: all
  tasks:
    - name: Create an operator account
      ansible.builtin.user:
        name: operator
```

`extensions/molecule/default/converge.yml`:

```yaml
- name: Converge
  ansible.builtin.import_playbook: emcomm.station.station
```

`extensions/molecule/default/verify.yml`:

```yaml
- name: Verify
  hosts: all
  gather_facts: true
  tasks:
    - name: Read the Debian apt source
      ansible.builtin.slurp:
        src: /etc/apt/sources.list.d/emcomm.sources
      register: emcomm_sources
      when: ansible_os_family == "Debian"

    - name: Check the apt source
      ansible.builtin.assert:
        that:
          - "'URIs: https://repo.invalid/testing/deb' in (emcomm_sources.content | b64decode)"
          - "'Suites: debian-13' in (emcomm_sources.content | b64decode)"
      when: ansible_os_family == "Debian"

    - name: Read the backports pin
      ansible.builtin.slurp:
        src: /etc/apt/preferences.d/emcomm-backports.pref
      register: emcomm_pin
      when: ansible_os_family == "Debian"

    - name: Check the backports pin
      ansible.builtin.assert:
        that:
          - "'Pin: release n=trixie-backports' in (emcomm_pin.content | b64decode)"
          - "'libhamlib*' in (emcomm_pin.content | b64decode)"
      when: ansible_os_family == "Debian"

    - name: Read the dnf repo
      ansible.builtin.slurp:
        src: /etc/yum.repos.d/emcomm-testing.repo
      register: emcomm_repo
      when: ansible_os_family == "RedHat"

    - name: Check the dnf repo
      ansible.builtin.assert:
        that:
          - "'rpm/fedora-$releasever/$basearch' in (emcomm_repo.content | b64decode)"
          - "'repo_gpgcheck = 1' in (emcomm_repo.content | b64decode)"
      when: ansible_os_family == "RedHat"

    - name: Read operator groups
      ansible.builtin.command: id -nG operator
      register: emcomm_groups
      changed_when: false

    - name: Operator is in dialout and audio
      ansible.builtin.assert:
        that:
          - "'dialout' in emcomm_groups.stdout.split()"
          - "'audio' in emcomm_groups.stdout.split()"
```

Task 23 extends `verify.yml` with checks for the user units.

- [ ] **Step 4: Stub the remaining roles so the playbook runs**

Create the files below so the playbook resolves. Task 23 replaces them:

- `roles/toolsets/tasks/main.yml`
- `roles/radio_hw/tasks/main.yml`
- `roles/services/tasks/main.yml`

Each contains:

```yaml
- name: Placeholder until this role is implemented
  ansible.builtin.meta: noop
```

- [ ] **Step 4b: Guard against pin drift between CI and real machines**

`tools/tests/test_ansible_sync.py`:

```python
import yaml

from emcomm_build.model import load_targets

from conftest import REAL_ROOT

VARS = REAL_ROOT / "ansible/ansible_collections/emcomm/station/roles/base/vars/Debian.yml"


def test_backports_pin_matches_targets():
    repo = load_targets(REAL_ROOT)["debian-13"].extra_repos[0]
    role = yaml.safe_load(VARS.read_text())
    assert role["emcomm_backports_packages"] == list(repo.pin_packages)
    assert role["emcomm_backports_priority"] == repo.pin_priority
    assert f"Suites: {role['emcomm_backports_suite']}" in repo.deb822
```

Run: `uv run --directory tools pytest -q tests/test_ansible_sync.py`
Expected: PASS.

- [ ] **Step 5: Lint and run Molecule**

```bash
python3 -m venv .venv-ansible && . .venv-ansible/bin/activate
pip install -r ansible/requirements-dev.txt
ansible-galaxy collection install containers.podman
export ANSIBLE_COLLECTIONS_PATH=$PWD/ansible
cd ansible/ansible_collections/emcomm/station
ansible-lint
molecule test
```

Expected: ansible-lint reports `Passed`. molecule test passes converge, idempotence, and verify on both platforms.

Add `.venv-ansible/` to `.gitignore`.

- [ ] **Step 6: Commit**

```bash
git add ansible .gitignore tools/tests/test_ansible_sync.py
git commit -m "feat(ansible): emcomm.station collection with base role and molecule tests"
```

---

### Task 23: Ansible roles — `toolsets`, `radio_hw`, `services`

**Files:**
- Replace: `roles/toolsets/tasks/main.yml`, `roles/radio_hw/tasks/main.yml`, `roles/services/tasks/main.yml`
- Create: `roles/toolsets/defaults/main.yml`, `roles/radio_hw/defaults/main.yml`, `roles/radio_hw/templates/station.toml.j2`
- Create: `roles/services/files/{emcomm-rigctld,emcomm-direwolf,emcomm-pat}.service`
- Modify: `extensions/molecule/default/verify.yml` (append the unit checks)

All paths are under `ansible/ansible_collections/emcomm/station/`.

**Interfaces:**
- Consumes: the packages `emcomm-<toolset>`, the `/opt/emcomm/bin/emcomm station apply-udev` command (Task 18), and the env and config files written by `emcomm use` (Task 21).
- Produces:
  - Role variables `emcomm_toolsets` (default `[standard]`) and `emcomm_stations` (default `[]`). Each list item has the station schema shape: `name`, `radio`, optional `ptt`, `cat`, `audio`.
  - User units in `/etc/systemd/user/`. They are not enabled; operators start them with `systemctl --user enable --now emcomm-rigctld` (mode switching arrives in M2). Each runs its program through `/opt/emcomm/libexec/emcomm-run` (Task 10), so the same unit works with distro binaries (Debian rigctld/direwolf) and emcomm-built ones (Fedora rigctld, Pat).

- [ ] **Step 1: Write the roles**

`roles/toolsets/defaults/main.yml`:

```yaml
# emcomm toolsets to install (package emcomm-<name>). "standard" = core + digital + winlink.
emcomm_toolsets: [standard]
```

`roles/toolsets/tasks/main.yml`:

```yaml
- name: Install emcommOS toolsets
  ansible.builtin.package:
    name: "{{ emcomm_toolsets | map('regex_replace', '^', 'emcomm-') | list }}"
    state: present
  when: emcomm_toolsets | length > 0
```

`roles/radio_hw/defaults/main.yml`:

```yaml
# Station kits for this machine, same fields as /etc/emcomm/stations/<name>.toml, e.g.
# - {name: kita, radio: icom-ic7300,
#    cat: {vendor_id: "10c4", product_id: "ea60", serial: "IC-7300 03001234 A", interface: "00"},
#    audio: {vendor_id: "08bb", product_id: "2901"}}
emcomm_stations: []
```

`roles/radio_hw/templates/station.toml.j2`:

```
# Managed by Ansible (emcomm.station.radio_hw)
name = "{{ item.name }}"
radio = "{{ item.radio }}"
{% if item.ptt is defined %}
ptt = "{{ item.ptt }}"
{% endif %}
{% for section in ['cat', 'audio'] %}
{% if item[section] is defined %}

[{{ section }}]
{% for key, value in item[section] | dictsort %}
{{ key }} = "{{ value }}"
{% endfor %}
{% endif %}
{% endfor %}
```

`roles/radio_hw/tasks/main.yml`:

```yaml
- name: Create the station kit directory
  ansible.builtin.file:
    path: /etc/emcomm/stations
    state: directory
    mode: "0755"

- name: Write station kits
  ansible.builtin.template:
    src: station.toml.j2
    dest: "/etc/emcomm/stations/{{ item.name }}.toml"
    mode: "0644"
  loop: "{{ emcomm_stations }}"
  loop_control:
    label: "{{ item.name }}"

- name: Generate udev rules for station kits
  ansible.builtin.command: /opt/emcomm/bin/emcomm station apply-udev
  register: emcomm_udev
  changed_when: "'udev: updated' in emcomm_udev.stdout"
  when: emcomm_stations | length > 0
```

`roles/services/files/emcomm-rigctld.service`:

```ini
[Unit]
Description=emcommOS rigctld hub (127.0.0.1:4532)
Documentation=man:rigctld(1)

[Service]
EnvironmentFile=%h/.config/emcomm/rigctld.env
ExecStart=/opt/emcomm/libexec/emcomm-run rigctld $RIGCTLD_ARGS
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`roles/services/files/emcomm-direwolf.service`:

```ini
[Unit]
Description=emcommOS Dire Wolf soundcard modem/TNC (AGW 8000, KISS 8001)
Wants=emcomm-rigctld.service
After=emcomm-rigctld.service

[Service]
ExecStart=/opt/emcomm/libexec/emcomm-run direwolf -t 0 -c %h/.config/emcomm/direwolf.conf
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`roles/services/files/emcomm-pat.service`:

```ini
[Unit]
Description=emcommOS Pat Winlink client (web UI on localhost:8080)
Wants=emcomm-rigctld.service
After=emcomm-rigctld.service

[Service]
ExecStart=/opt/emcomm/libexec/emcomm-run pat http
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`roles/services/tasks/main.yml`:

```yaml
- name: Install emcomm systemd user units
  ansible.builtin.copy:
    src: "{{ item }}"
    dest: "/etc/systemd/user/{{ item }}"
    mode: "0644"
  loop:
    - emcomm-rigctld.service
    - emcomm-direwolf.service
    - emcomm-pat.service
```

- [ ] **Step 2: Extend the Molecule verification**

Append to `extensions/molecule/default/verify.yml` (inside `tasks:`):

```yaml
    - name: Stat user units
      ansible.builtin.stat:
        path: "/etc/systemd/user/{{ item }}"
      register: emcomm_units
      loop: [emcomm-rigctld.service, emcomm-direwolf.service, emcomm-pat.service]

    - name: User units are installed
      ansible.builtin.assert:
        that: emcomm_units.results | map(attribute='stat.exists') | list is all

    - name: Station directory exists
      ansible.builtin.stat:
        path: /etc/emcomm/stations
      register: emcomm_stations_dir

    - name: Check station directory
      ansible.builtin.assert:
        that: emcomm_stations_dir.stat.isdir
```

- [ ] **Step 3: Unit-test the station template against the CLI parser**

The template must produce TOML that `emcomm` accepts. Add `cli/tests/test_ansible_station_template.py`:

```python
from pathlib import Path

import jinja2
import tomllib

from emcomm.profiles import station_from_dict

TEMPLATE = (Path(__file__).resolve().parents[2] / "ansible/ansible_collections/emcomm/station"
            / "roles/radio_hw/templates/station.toml.j2")


def render(item):
    env = jinja2.Environment(trim_blocks=True)  # Ansible's template module default
    return env.from_string(TEMPLATE.read_text()).render(item=item)


def test_template_round_trips():
    item = {"name": "kita", "radio": "icom-ic7300", "ptt": "cat",
            "cat": {"vendor_id": "10c4", "product_id": "ea60", "serial": "IC-7300 0300 A",
                    "interface": "00"},
            "audio": {"vendor_id": "08bb", "product_id": "2901"}}
    st = station_from_dict(tomllib.loads(render(item)), "test")
    assert st.cat.serial == "IC-7300 0300 A" and st.audio.product_id == "2901"


def test_template_minimal():
    st = station_from_dict(tomllib.loads(render({"name": "b", "radio": "generic-vox"})), "t")
    assert st.cat is None and st.ptt is None
```

Add `jinja2>=3.1` to the `dev` dependency group in `cli/pyproject.toml`. The template keeps every `{% %}` tag at column 0, so Ansible's default `trim_blocks=True` is the only setting needed for clean output.

- [ ] **Step 4: Run lint, Molecule, and the template test**

Run: `uv run --directory cli pytest -q tests/test_ansible_station_template.py`
Expected: PASS.

Run (from `ansible/ansible_collections/emcomm/station`, with `ANSIBLE_COLLECTIONS_PATH` set as in Task 22): `ansible-lint && molecule test`
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add ansible cli
git commit -m "feat(ansible): toolsets, radio_hw and services roles"
```

---

### Task 24: Bootstrap with consent, uninstall, and `emcomm bootstrap|uninstall`

**Files:**
- Create: `cli/src/emcomm/commands/bootstrap.py`, `cli/src/emcomm/commands/uninstall.py`, `bootstrap.sh`
- Modify: `cli/src/emcomm/cli.py` (add `bootstrap` and `uninstall` to `COMMANDS`)
- Test: `cli/tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `paths.ansible_dir` and `paths.share / "bootstrap.sh"`, both installed by the `cli` package in Task 25, plus `playbooks/station.yml` from Task 22.
- Produces:
  - `bootstrap.bootstrap_vars(repo_url, channel, toolsets, users, overrides) -> dict`
  - `bootstrap.parse_overrides(["k=v", ...]) -> dict` (values are parsed as JSON when possible, otherwise kept as strings)
  - `bootstrap.playbook_command(paths, vars_file, check) -> list[str]`
  - CLI: `emcomm bootstrap --repo-url URL [--channel testing] [--toolsets standard] [--user NAME] [--set KEY=VALUE]... [--check] [--yes]`, which prints a summary and asks for confirmation unless `--yes` is given
  - CLI: `emcomm uninstall [--yes]`, which runs the packaged `bootstrap.sh --uninstall` from a temp copy
  - `bootstrap.sh [--repo-url URL] [--channel C] [--toolsets a,b] [--no-provision] [--yes] [--uninstall]` with env equivalents `EMCOMM_REPO_URL`, `EMCOMM_CHANNEL`, `EMCOMM_TOOLSETS`. It verifies the repository key against the pinned fingerprint from `keys/fingerprint.txt`.
- BYOD rules (spec §2):
  - Show every change before making it and ask for confirmation. Read the answer from `/dev/tty` so `curl | sh` still works; with no terminal, require `--yes`.
  - Make every change reversible with `--uninstall`. Uninstall keeps the user's own files: `~/.config/*` and app settings.

- [ ] **Step 1: Write the failing tests**

`cli/tests/test_bootstrap.py`:

```python
import json
import re
import subprocess
from pathlib import Path

from emcomm.cli import main
from emcomm.commands import bootstrap as bs
from emcomm.commands import uninstall as un

REPO = Path(__file__).resolve().parents[2]


def test_vars_and_overrides():
    overrides = bs.parse_overrides(["emcomm_chrony_enable=false", "note=hello"])
    assert overrides == {"emcomm_chrony_enable": False, "note": "hello"}
    assert bs.bootstrap_vars("https://r/", "testing", "core,digital", ["alice"], overrides) == {
        "emcomm_repo_url": "https://r", "emcomm_channel": "testing",
        "emcomm_toolsets": ["core", "digital"], "emcomm_users": ["alice"],
        "emcomm_chrony_enable": False, "note": "hello"}


def test_playbook_command(paths, tmp_path):
    cmd = bs.playbook_command(paths, tmp_path / "v.json", check=True)
    assert cmd[:4] == ["ansible-playbook", "-i", "localhost,", "-c"]
    assert cmd[5].endswith("ansible_collections/emcomm/station/playbooks/station.yml")
    assert f"@{tmp_path / 'v.json'}" in cmd
    assert cmd[-1] == "--check"


def test_bootstrap_runs_ansible(paths, monkeypatch, capsys):
    seen = {}

    def fake_run(cmd, env, check):
        seen["env"] = env
        seen["vars"] = json.loads(Path(cmd[cmd.index("-e") + 1][1:]).read_text())
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(bs.subprocess, "run", fake_run)
    monkeypatch.setattr(bs.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "alice")
    assert main(["bootstrap", "--repo-url", "https://r", "--toolsets", "core", "--yes"],
                paths=paths) == 0
    assert seen["vars"]["emcomm_users"] == ["alice"]
    assert seen["env"]["ANSIBLE_COLLECTIONS_PATH"] == str(paths.ansible_dir)
    assert "emcomm-core" in capsys.readouterr().out


def test_bootstrap_declined(paths, monkeypatch):
    monkeypatch.setattr(bs.os, "geteuid", lambda: 0)
    monkeypatch.setattr("builtins.input", lambda _p: "n")
    assert main(["bootstrap", "--repo-url", "https://r"], paths=paths) == 1


def test_bootstrap_needs_root(paths, monkeypatch, capsys):
    monkeypatch.setattr(bs.os, "geteuid", lambda: 1000)
    assert main(["bootstrap", "--repo-url", "https://r", "--yes"], paths=paths) == 1
    assert "sudo" in capsys.readouterr().err


def test_uninstall_runs_packaged_script(paths, monkeypatch, tmp_path):
    script = paths.share / "bootstrap.sh"
    calls = []
    monkeypatch.setattr(un.os, "geteuid", lambda: 0)
    monkeypatch.setattr(un.subprocess, "run",
                        lambda cmd, check: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    assert script.is_file()  # the repo root doubles as share in tests
    assert main(["uninstall", "--yes"], paths=paths) == 0
    assert calls[0][0] == "sh" and calls[0][1].endswith("bootstrap.sh")
    assert calls[0][2:] == ["--uninstall", "--yes"]
    assert calls[0][1] != str(script)  # runs a temp copy; the package removes the original


def test_bootstrap_sh_pins_project_fingerprint():
    fpr = (REPO / "keys/fingerprint.txt").read_text().strip()
    script = (REPO / "bootstrap.sh").read_text()
    assert re.search(rf'^EMCOMM_KEY_FINGERPRINT="{fpr}"$', script, re.M)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_bootstrap.py`
Expected: FAIL with `ImportError: cannot import name 'bootstrap'`.

- [ ] **Step 3: Implement `commands/bootstrap.py`**

```python
"""`emcomm bootstrap` — apply the emcomm.station playbook to this machine (with consent)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..paths import Paths
from ..validation import ProfileError

PLAYBOOK = "ansible_collections/emcomm/station/playbooks/station.yml"


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("bootstrap", help="set this machine up as an emcomm station (root)")
    p.add_argument("--repo-url", default=os.environ.get("EMCOMM_REPO_URL", ""))
    p.add_argument("--channel", default=os.environ.get("EMCOMM_CHANNEL", "testing"))
    p.add_argument("--toolsets", default=os.environ.get("EMCOMM_TOOLSETS", "standard"),
                   help="comma-separated toolsets (default: standard)")
    p.add_argument("--user", action="append", default=[],
                   help="account to add to radio groups (default: the sudo user)")
    p.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
                   help="extra Ansible variable (advanced / managed installs)")
    p.add_argument("--check", action="store_true", help="dry run (ansible --check)")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_bootstrap)


def parse_overrides(items: list[str]) -> dict:
    out = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise ProfileError(f"--set expects KEY=VALUE, got {item!r}")
        try:
            out[key] = json.loads(value)
        except json.JSONDecodeError:
            out[key] = value
    return out


def bootstrap_vars(repo_url: str, channel: str, toolsets: str, users: list[str],
                   overrides: dict) -> dict:
    return {
        "emcomm_repo_url": repo_url.rstrip("/"),
        "emcomm_channel": channel,
        "emcomm_toolsets": [t.strip() for t in toolsets.split(",") if t.strip()],
        "emcomm_users": users,
        **overrides,
    }


def playbook_command(paths: Paths, vars_file: Path, check: bool) -> list[str]:
    cmd = ["ansible-playbook", "-i", "localhost,", "-c", "local",
           str(paths.ansible_dir / PLAYBOOK), "-e", f"@{vars_file}"]
    if check:
        cmd.append("--check")
    return cmd


def _summary(data: dict) -> str:
    toolsets = ", ".join(f"emcomm-{t}" for t in data["emcomm_toolsets"]) or "(none)"
    users = ", ".join(data["emcomm_users"]) or "(none)"
    return "\n".join([
        "emcomm bootstrap will:",
        f"  - configure the emcommOS repository ({data['emcomm_repo_url']}, "
        f"{data['emcomm_channel']})",
        "  - on Debian: enable trixie-backports, pinned to hamlib/WSJT-X/Direwolf only",
        f"  - install toolsets: {toolsets} (may upgrade those distro packages)",
        "  - install and enable chrony (time sync, needed for FT8/JS8)",
        f"  - add {users} to the radio groups (dialout, audio, ...)",
        "  - install emcomm systemd user units (not enabled)",
        "Undo with: sudo emcomm uninstall",
    ])


def cmd_bootstrap(args: argparse.Namespace, paths: Paths) -> int:
    if not args.repo_url:
        raise ProfileError("set --repo-url or EMCOMM_REPO_URL")
    if os.geteuid() != 0 and not args.check:
        raise ProfileError("bootstrap changes system configuration; run it with sudo")
    users = args.user or [os.environ.get("SUDO_USER") or getpass.getuser()]
    users = [u for u in users if u != "root"]
    data = bootstrap_vars(args.repo_url, args.channel, args.toolsets, users,
                          parse_overrides(args.overrides))
    print(_summary(data))
    if not args.yes and input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
        print("aborted; nothing was changed")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        vars_file = Path(tmp) / "vars.json"
        vars_file.write_text(json.dumps(data))
        env = {**os.environ, "ANSIBLE_COLLECTIONS_PATH": str(paths.ansible_dir)}
        result = subprocess.run(playbook_command(paths, vars_file, args.check), env=env,
                                check=False)
    return result.returncode
```

- [ ] **Step 4: Implement `commands/uninstall.py`**

```python
"""`emcomm uninstall` — remove everything emcommOS added (runs bootstrap.sh --uninstall)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..paths import Paths
from ..validation import ProfileError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("uninstall", help="remove emcommOS packages, repo, pins, units, rules")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_uninstall)


def cmd_uninstall(args: argparse.Namespace, paths: Paths) -> int:
    if os.geteuid() != 0:
        raise ProfileError("uninstall changes system configuration; run it with sudo")
    script = paths.share / "bootstrap.sh"
    if not script.is_file():
        raise ProfileError(f"{script} not found; run bootstrap.sh --uninstall manually")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "bootstrap.sh"
        shutil.copy2(script, copy)  # the package being removed owns the original
        cmd = ["sh", str(copy), "--uninstall"] + (["--yes"] if args.yes else [])
        return subprocess.run(cmd, check=False).returncode
```

The test's fake `run` takes `check`, so it passes `check=False` through unchanged.

In `cli.py`, add `bootstrap` and `uninstall` to the command imports and to `COMMANDS`.

- [ ] **Step 5: Create `bootstrap.sh`**

```sh
#!/bin/sh
# emcommOS bootstrap: shows what it will change, asks first, trusts the emcommOS signing key
# (pinned below), adds the package repository, installs the emcomm CLI, then sets the machine
# up with Ansible. Everything can be undone with --uninstall.
#
#   curl -fsSL "$EMCOMM_REPO_URL/bootstrap.sh" | sudo EMCOMM_REPO_URL="$EMCOMM_REPO_URL" sh
#   sudo sh bootstrap.sh --repo-url URL [--channel testing] [--toolsets standard]
#                        [--no-provision] [--yes] [--uninstall]
set -eu

EMCOMM_KEY_FINGERPRINT="__FINGERPRINT__"
REPO_URL=${EMCOMM_REPO_URL:-}
CHANNEL=${EMCOMM_CHANNEL:-testing}
TOOLSETS=${EMCOMM_TOOLSETS:-standard}
PROVISION=1
YES=0
UNINSTALL=0

die() { echo "bootstrap: $*" >&2; exit 1; }

confirm() {
  [ "$YES" -eq 1 ] && return 0
  [ -r /dev/tty ] || die "no terminal to confirm on; re-run with --yes"
  printf '%s [y/N] ' "$1" > /dev/tty
  read -r answer < /dev/tty
  case $answer in y|Y|yes|YES) return 0 ;; *) echo "aborted; nothing was changed"; exit 1 ;; esac
}

while [ $# -gt 0 ]; do
  case $1 in
    --repo-url) REPO_URL=$2; shift 2 ;;
    --channel) CHANNEL=$2; shift 2 ;;
    --toolsets) TOOLSETS=$2; shift 2 ;;
    --no-provision) PROVISION=0; shift ;;
    --yes|-y) YES=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done
REPO_URL=${REPO_URL%/}

[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"
# shellcheck source=/dev/null
. /etc/os-release
case " ${ID_LIKE:-} $ID " in
  *" debian "*) FAMILY=debian ;;
  *" fedora "*|*" rhel "*) FAMILY=fedora ;;
  *) die "unsupported distribution '$ID' (M1 supports Debian 13 and Fedora)" ;;
esac

uninstall() {
  echo "emcommOS uninstall will remove: emcomm packages (and dependencies only they needed),"
  echo "  the emcommOS repository and key, the backports source and pin, emcomm user units,"
  echo "  emcomm udev rules and /etc/emcomm. Your files in ~/.config and app settings are kept."
  confirm "Remove emcommOS?"
  if [ "$FAMILY" = debian ]; then
    pkgs=$(dpkg-query -W -f='${db:Status-Abbrev}${Package}\n' 'emcomm-*' 2>/dev/null \
           | awk '/^ii/ {print substr($0, 4)}')
    if [ -n "$pkgs" ]; then
      # shellcheck disable=SC2086
      apt-get remove -y $pkgs
      apt-get autoremove -y
    fi
    rm -f /etc/apt/sources.list.d/emcomm.sources /etc/apt/sources.list.d/emcomm-backports.sources \
          /etc/apt/preferences.d/emcomm-backports.pref /usr/share/keyrings/emcomm-archive-keyring.asc
    apt-get update -qq || true
  else
    pkgs=$(rpm -qa --qf '%{NAME}\n' 'emcomm-*')
    if [ -n "$pkgs" ]; then
      # shellcheck disable=SC2086
      dnf -y remove $pkgs
    fi
    rm -f /etc/yum.repos.d/emcomm-*.repo /etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm
  fi
  rm -f /etc/systemd/user/emcomm-*.service /etc/udev/rules.d/70-emcomm-*.rules
  rm -rf /etc/emcomm
  udevadm control --reload 2>/dev/null || true
  echo "emcommOS removed. Group memberships (dialout, audio) and chrony were left in place."
}

if [ "$UNINSTALL" -eq 1 ]; then
  uninstall
  exit 0
fi

[ -n "$REPO_URL" ] || die "set EMCOMM_REPO_URL or pass --repo-url"
echo "emcommOS bootstrap will:"
echo "  - trust the emcommOS signing key $EMCOMM_KEY_FINGERPRINT"
echo "  - add the package repository $REPO_URL/$CHANNEL"
echo "  - install emcomm-cli (with ansible-core)"
if [ "$PROVISION" -eq 1 ]; then
  echo "  - then run 'emcomm bootstrap' for toolsets: $TOOLSETS (it lists its own changes)"
fi
echo "Undo later with: sudo sh bootstrap.sh --uninstall  (or: sudo emcomm uninstall)"
confirm "Continue?"

if [ "$FAMILY" = debian ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq gpg curl ca-certificates >/dev/null
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$REPO_URL/$CHANNEL/emcomm-archive-keyring.asc" -o "$tmp/key.asc"
fpr=$(GNUPGHOME="$tmp" gpg --batch --show-keys --with-colons "$tmp/key.asc" \
      | awk -F: '/^fpr/ {print $10; exit}')
[ "$fpr" = "$EMCOMM_KEY_FINGERPRINT" ] ||
  die "repository key $fpr does not match the pinned emcommOS key $EMCOMM_KEY_FINGERPRINT"

if [ "$FAMILY" = debian ]; then
  install -m 0644 "$tmp/key.asc" /usr/share/keyrings/emcomm-archive-keyring.asc
  cat > /etc/apt/sources.list.d/emcomm.sources <<EOF
Types: deb
URIs: $REPO_URL/$CHANNEL/deb
Suites: $ID-${VERSION_ID%%.*}
Components: main
Signed-By: /usr/share/keyrings/emcomm-archive-keyring.asc
EOF
  apt-get update -qq
  apt-get install -y emcomm-cli
else
  install -m 0644 "$tmp/key.asc" /etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm
  cat > "/etc/yum.repos.d/emcomm-$CHANNEL.repo" <<EOF
[emcomm-$CHANNEL]
name=emcommOS $CHANNEL
baseurl=$REPO_URL/$CHANNEL/rpm/$ID-\$releasever/\$basearch
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm
EOF
  dnf -y install emcomm-cli
fi

if [ "$PROVISION" -eq 1 ]; then
  set -- --repo-url "$REPO_URL" --channel "$CHANNEL" --toolsets "$TOOLSETS"
  [ "$YES" -eq 1 ] && set -- "$@" --yes
  exec /opt/emcomm/bin/emcomm bootstrap "$@"
fi
echo "emcomm CLI installed; run 'sudo emcomm bootstrap' to finish setting up this machine."
```

Pin the project key fingerprint (from Task 1):

```bash
sed -i "s/__FINGERPRINT__/$(cat keys/fingerprint.txt)/" bootstrap.sh
chmod +x bootstrap.sh
```

- [ ] **Step 6: Run the tests and shellcheck**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check . && shellcheck bootstrap.sh`
Expected: PASS, no findings.

- [ ] **Step 7: Commit**

```bash
git add cli bootstrap.sh
git commit -m "feat: consent-first bootstrap with uninstall; emcomm bootstrap/uninstall"
```

---

### Task 25: `emcomm-cli` package and toolset metapackages

**Files:**
- Create: `recipes/cli/{recipe.yaml,build.sh,smoke.sh}`
- Create: `recipes/{core,digital,winlink,standard}/recipe.yaml`, `recipes/core/smoke.sh`

**Interfaces:**
- Consumes: `cli/`, `radios/`, `ansible/`, and `bootstrap.sh` from the repo (a `local` source), plus every recipe from Tasks 10–13.
- Produces:
  - `emcomm-cli`:
    - venv at `/opt/emcomm/lib/emcomm-cli` and `/opt/emcomm/bin/emcomm`
    - `/opt/emcomm/share/emcomm/{radios,ansible,bootstrap.sh}`
    - depends on distro `python3` and `ansible-core`
  - Metapackages that mix our packages with **version-floored distro packages** per family (spec §4.1). Debian floors resolve from backports through the pin.

    | Toolset | Debian 13 | Fedora 43/44 |
    |---|---|---|
    | `emcomm-core` | cli, wfview (Task 28), flrig*, `libhamlib-utils (>= 4.7.2)` | cli, wfview, hamlib*, `flrig >= 2.0.12` |
    | `emcomm-digital` | core, js8call, fldigi*, `wsjtx (>= 3.0.2)`, `flmsg (>= 4.0.23)`, `flamp (>= 2.2.14)` | core, js8call, `wsjtx >= 3.0.1`, `fldigi >= 4.2.13`, `flmsg >= 4.0.23`, `flamp >= 2.2.14` |
    | `emcomm-winlink` | core, pat, `direwolf (>= 1.8.1)` | core, pat, `direwolf >= 1.8.1` |
    | `emcomm-standard` | core + digital + winlink | same |

    `*` = our build, which only exists for that family; `recipes_for_target` drops it elsewhere. Debian relations are written `pkg (>= v)` and rpm relations `pkg >= v`.

- [ ] **Step 1: Create the CLI package recipe**

`recipes/cli/recipe.yaml`:

```yaml
name: cli
kind: app
summary: emcommOS operator CLI, radio definitions, Ansible collection and bootstrap script
license: Apache-2.0
version: "0.1.0"
release: 1
source:
  type: local
  paths: [cli, radios, ansible, bootstrap.sh]
deps:
  debian:
    build: [python3, python3-venv]
    run: [python3, ansible-core, python3-apt]        # apt module needs python3-apt
  fedora:
    build: [python3]
    run: [python3, ansible-core, python3-libdnf5]    # dnf5 module needs libdnf5 bindings
```

`recipes/cli/build.sh`. The venv is created at its final path and then copied, so shebangs and `pyvenv.cfg` point at `/opt/emcomm`, never at DESTDIR:

```bash
#!/usr/bin/env bash
set -euo pipefail
venv=$PREFIX/lib/emcomm-cli
rm -rf "$venv"
python3 -m venv "$venv"
"$venv/bin/pip" install --quiet --no-cache-dir "$SRC/cli"
share=$DESTDIR$PREFIX/share/emcomm
mkdir -p "$DESTDIR$PREFIX/lib" "$DESTDIR$PREFIX/bin" "$share"
cp -a "$venv" "$DESTDIR$PREFIX/lib/"
ln -s ../lib/emcomm-cli/bin/emcomm "$DESTDIR$PREFIX/bin/emcomm"
cp -a "$SRC/radios" "$share/radios"
cp -a "$SRC/ansible" "$share/ansible"
find "$share/ansible" -type d -name molecule -prune -exec rm -rf {} +
install -m 0644 "$SRC/bootstrap.sh" "$share/bootstrap.sh"
```

`recipes/cli/smoke.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
emcomm --help >/dev/null
emcomm radios | grep -q icom-ic7300
test -f /opt/emcomm/share/emcomm/ansible/ansible_collections/emcomm/station/playbooks/station.yml
test -s /opt/emcomm/share/emcomm/ansible/ansible_collections/emcomm/station/roles/base/files/emcomm-archive-keyring.asc
grep -q '^EMCOMM_KEY_FINGERPRINT="[0-9A-F]\{40\}"$' /opt/emcomm/share/emcomm/bootstrap.sh
ansible-playbook --version >/dev/null
```

The `local` fetch follows symlinks (`shutil.copytree`), so Task 22's key symlink arrives as a real file. `bootstrap.sh` is copied as a single file (Task 5).

- [ ] **Step 2: Create the metapackages**

`recipes/core/recipe.yaml`:

```yaml
name: core
kind: meta
summary: emcommOS core toolset (rigctld hub, flrig, emcomm CLI)
license: Apache-2.0
version: "1.0.0"
release: 1
requires: [hamlib, flrig, cli]   # hamlib is Fedora-only, flrig Debian-only (see recipes)
deps:
  debian:
    run: ["libhamlib-utils (>= 4.7.2)"]
  fedora:
    run: ["flrig >= 2.0.12"]
```

`recipes/core/smoke.sh`. Every radio definition must name a model the installed rigctld knows; this runs against Debian's backports hamlib and our Fedora build:

```bash
#!/usr/bin/env bash
set -euo pipefail
rigctl=$(command -v /opt/emcomm/bin/rigctl || command -v rigctl)
[[ $("$rigctl" -m 1 f) == 145000000 ]]
models=$("$rigctl" -l | awk 'NR > 1 {print $1}')
for f in /opt/emcomm/share/emcomm/radios/*.yaml; do
  m=$(awk '/^hamlib_model:/ {print $2}' "$f")
  grep -qx "$m" <<<"$models" || { echo "$f: hamlib model $m not in rigctl -l"; exit 1; }
done
```

`recipes/digital/recipe.yaml`:

```yaml
name: digital
kind: meta
summary: emcommOS digital modes toolset (WSJT-X, JS8Call, fldigi, flmsg, flamp)
license: Apache-2.0
version: "1.0.0"
release: 1
requires: [core, js8call, fldigi]   # fldigi recipe is Debian-only
deps:
  debian:
    run: ["wsjtx (>= 3.0.2)", "flmsg (>= 4.0.23)", "flamp (>= 2.2.14)"]
  fedora:
    run: ["wsjtx >= 3.0.1", "fldigi >= 4.2.13", "flmsg >= 4.0.23", "flamp >= 2.2.14"]
```

`recipes/winlink/recipe.yaml`:

```yaml
name: winlink
kind: meta
summary: emcommOS Winlink/packet toolset (Pat, Direwolf)
license: Apache-2.0
version: "1.0.0"
release: 1
requires: [core, pat]
deps:
  debian:
    run: ["direwolf (>= 1.8.1)"]
  fedora:
    run: ["direwolf >= 1.8.1"]
```

`recipes/standard/recipe.yaml`:

```yaml
name: standard
kind: meta
summary: emcommOS opinionated default station (core + digital + winlink)
license: Apache-2.0
version: "1.0.0"
release: 1
requires: [core, digital, winlink]
```

- [ ] **Step 3: Build everything per target and install the default set**

Run: `uv run --directory tools emcomm-build validate`
Expected: `ok: 3 targets, 11 recipes`. Task 28 adds wfview, making 12.

Run: `uv run --directory tools emcomm-build build --target debian-13`
Expected: base, fldigi, flrig, js8call, pat, cli, and the metas build (no hamlib), and the output ends with `smoke OK`. The `core` smoke proves the backports pin resolved hamlib 4.7.2 and that every radio model exists.

Run: `uv run --directory tools emcomm-build build --target fedora-44`
Expected: base, hamlib, js8call, pat, cli, and the metas build (no fldigi/flrig), and the output ends with `smoke OK`.

If a distro floor isn't satisfiable (for example a distro update renamed a package), run `emcomm-build freshness` and adjust the meta's `deps`.

- [ ] **Step 4: Commit**

```bash
git add recipes/cli recipes/core recipes/digital recipes/winlink recipes/standard
git commit -m "feat(recipes): emcomm-cli package and per-family toolset metapackages"
```

---

### Task 26: GitHub Actions — CI, package builds and publishing, upstream watch

**Files:**
- Create: `.github/actions/setup-build-host/action.yml`
- Create: `.github/workflows/ci.yml`, `.github/workflows/packages.yml`, `.github/workflows/watch-upstream.yml`
- Commit: `tools/uv.lock`, `cli/uv.lock` (generated by earlier `uv run` calls)

**Interfaces:**
- Consumes: the secrets and variables from Task 1, and the commands `emcomm-build validate|build|publish|check`.
- Produces: `testing` packages on R2 at `$EMCOMM_REPO_URL/testing/...` after every merge to `main` that touches recipes, tools, cli, radios, ansible, keys, or targets; `bootstrap.sh` at `$EMCOMM_REPO_URL/bootstrap.sh`; and a daily PR when upstream releases a newer version.

- [ ] **Step 1: Create the composite action**

`.github/actions/setup-build-host/action.yml`:

```yaml
name: setup-build-host
description: Install podman and nfpm on an Ubuntu runner
runs:
  using: composite
  steps:
    - shell: bash
      run: |
        set -euo pipefail
        command -v podman >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq podman; }
        NFPM_VERSION=2.41.1
        case "$(uname -m)" in x86_64) a=x86_64 ;; aarch64) a=arm64 ;; esac
        curl -fsSL "https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}/nfpm_${NFPM_VERSION}_Linux_${a}.tar.gz" \
          | sudo tar -xz -C /usr/local/bin nfpm
        podman --version
        nfpm --version
```

- [ ] **Step 2: Create `ci.yml`**

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  python:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run --directory tools ruff check .
      - run: uv run --directory tools pytest -q -m "not container and not nfpm"
      - run: uv run --directory tools emcomm-build validate
      - run: uv run --directory cli ruff check .
      - run: uv run --directory cli pytest -q
  shell:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - run: shellcheck bootstrap.sh tools/container/*.sh recipes/*/*.sh tests/integration/*.sh
  packaging-integration:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - uses: ./.github/actions/setup-build-host
      - run: uv run --directory tools pytest -q -m "container or nfpm"
  ansible:
    runs-on: ubuntu-24.04
    env:
      ANSIBLE_COLLECTIONS_PATH: ${{ github.workspace }}/ansible
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r ansible/requirements-dev.txt && ansible-galaxy collection install containers.podman
      - working-directory: ansible/ansible_collections/emcomm/station
        run: ansible-lint && molecule test
```

- [ ] **Step 3: Create `packages.yml`**

```yaml
name: packages
on:
  push:
    branches: [main]
    paths: [recipes/**, tools/**, cli/**, radios/**, ansible/**, keys/**, targets.yaml, bootstrap.sh]
  workflow_dispatch:
    inputs:
      force:
        description: Rebuild every package even if already published
        type: boolean
        default: false
permissions:
  contents: read
jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        target: [debian-13, fedora-44, fedora-43]
        arch: [amd64, arm64]
    runs-on: ${{ matrix.arch == 'arm64' && 'ubuntu-24.04-arm' || 'ubuntu-24.04' }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - uses: ./.github/actions/setup-build-host
      - name: Build ${{ matrix.target }}/${{ matrix.arch }}
        run: >
          uv run --directory tools emcomm-build build
          --target ${{ matrix.target }} --arch ${{ matrix.arch }}
          --repo-url "${{ vars.EMCOMM_REPO_URL }}"
          --out "$GITHUB_WORKSPACE/dist/${{ matrix.target }}/${{ matrix.arch }}"
          ${{ inputs.force && '--force' || '' }}
      - uses: actions/upload-artifact@v4
        with:
          name: pkgs-${{ matrix.target }}-${{ matrix.arch }}
          path: dist/
          if-no-files-found: ignore

  publish:
    needs: build
    runs-on: ubuntu-24.04
    concurrency:
      group: publish-testing
      cancel-in-progress: false
    env:
      RCLONE_CONFIG_R2_TYPE: s3
      RCLONE_CONFIG_R2_PROVIDER: Cloudflare
      RCLONE_CONFIG_R2_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
      RCLONE_CONFIG_R2_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
      RCLONE_CONFIG_R2_ENDPOINT: https://${{ secrets.R2_ACCOUNT_ID }}.r2.cloudflarestorage.com
      RCLONE_CONFIG_R2_NO_CHECK_BUCKET: "true"
      BUCKET: ${{ vars.R2_BUCKET }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - uses: ./.github/actions/setup-build-host
      - run: sudo apt-get install -y -qq rclone
      - uses: actions/download-artifact@v4
        with:
          pattern: pkgs-*
          path: dist
          merge-multiple: true
      - id: count
        run: echo "n=$(find dist \( -name '*.deb' -o -name '*.rpm' \) 2>/dev/null | wc -l)" >> "$GITHUB_OUTPUT"
      - name: Fetch current channel tree
        if: steps.count.outputs.n != '0'
        run: mkdir -p public/testing && rclone sync "r2:$BUCKET/testing" public/testing
      - name: Write signing key
        if: steps.count.outputs.n != '0'
        env:
          KEY: ${{ secrets.EMCOMM_SIGNING_KEY }}
          PASS: ${{ secrets.EMCOMM_SIGNING_PASSPHRASE }}
        run: |
          umask 077
          printf '%s\n' "$KEY" > "$RUNNER_TEMP/signing.asc"
          printf '%s' "$PASS" > "$RUNNER_TEMP/passphrase"
      - name: Sign and index
        if: steps.count.outputs.n != '0'
        run: >
          uv run --directory tools emcomm-build publish
          --dist "$GITHUB_WORKSPACE/dist" --repo-dir "$GITHUB_WORKSPACE/public/testing"
          --key-file "$RUNNER_TEMP/signing.asc" --passphrase-file "$RUNNER_TEMP/passphrase"
      - name: Upload
        if: steps.count.outputs.n != '0'
        run: rclone sync public/testing "r2:$BUCKET/testing"
      - name: Upload bootstrap.sh
        run: rclone copyto bootstrap.sh "r2:$BUCKET/bootstrap.sh"
      - name: Remove key material
        if: always()
        run: rm -f "$RUNNER_TEMP/signing.asc" "$RUNNER_TEMP/passphrase"

  verify:
    needs: publish
    strategy:
      fail-fast: false
      matrix:
        target: [debian-13, fedora-44, fedora-43]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-build-host
      - run: tests/integration/repo-install.sh ${{ matrix.target }} "${{ vars.EMCOMM_REPO_URL }}" testing
```

- [ ] **Step 4: Create `watch-upstream.yml`**

```yaml
name: watch-upstream
on:
  schedule:
    - cron: "17 6 * * *"
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
jobs:
  check:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run --directory tools emcomm-build check --write
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - uses: peter-evans/create-pull-request@v7
        with:
          branch: bot/upstream-bumps
          title: "Upstream version bumps"
          commit-message: "chore(recipes): bump upstream versions"
          body: |
            Automated by `watch-upstream`. Dependent recipes had their `release` incremented.
            After merge, `packages` rebuilds and publishes to `testing`.
          delete-branch: true
```

PRs opened with `GITHUB_TOKEN` do not trigger `ci`. Re-run CI by closing and reopening the PR, or swap in a fine-grained PAT later.

- [ ] **Step 5: Validate the workflow syntax**

Run: `uvx actionlint` (or `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`)
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add .github tools/uv.lock cli/uv.lock
git commit -m "ci: tests, multi-arch package builds, signed publishing to R2, upstream watch"
```

---

### Task 27: M1 acceptance test, manual hardware checklist, README

**Files:**
- Create: `tests/integration/repo-install.sh`, `docs/testing/m1-manual-checks.md`, `README.md`

**Interfaces:**
- Consumes: the published repo, `bootstrap.sh --no-provision`, and the `emcomm` CLI.
- Produces: an automated check of the M1 acceptance criteria from spec §10, plus a manual hardware checklist.

- [ ] **Step 1: Create the acceptance script**

`tests/integration/repo-install.sh`:

```bash
#!/usr/bin/env bash
# M1 acceptance in a pristine container:
#   1. bootstrap.sh installs the CLI (pinned key), and emcomm bootstrap applies the playbook;
#   2. the rigctld hub answers through emcomm-run (distro or emcomm-built rigctld);
#   3. emcomm use renders WSJT-X.ini managed keys and keeps the user's own;
#   4. uninstall removes every emcomm package, repo file, pin, unit and /etc/emcomm.
# Usage: repo-install.sh <target> <repo-url> [channel]
set -euo pipefail
target=$1
url=$2
channel=${3:-testing}
case $target in
  debian-13) image=docker.io/library/debian:13 ;;
  fedora-44) image=registry.fedoraproject.org/fedora:44 ;;
  fedora-43) image=registry.fedoraproject.org/fedora:43 ;;
  *) echo "unknown target $target" >&2; exit 2 ;;
esac
root=$(cd "$(dirname "$0")/../.." && pwd)

podman run --rm -v "$root:/emcomm:ro,z" -e URL="$url" -e CHANNEL="$channel" "$image" bash -euo pipefail -c '
  if command -v apt-get >/dev/null; then
    apt-get update -qq && apt-get install -y -qq curl ca-certificates >/dev/null
    leftovers() { dpkg-query -W -f="\${db:Status-Abbrev}\${Package}\n" "emcomm-*" 2>/dev/null | grep "^ii" || true; }
  else
    leftovers() { rpm -qa "emcomm-*"; }
  fi
  sh /emcomm/bootstrap.sh --repo-url "$URL" --channel "$CHANNEL" --no-provision --yes
  emcomm bootstrap --repo-url "$URL" --channel "$CHANNEL" --toolsets core --yes \
    --set emcomm_chrony_enable=false
  export PATH=/opt/emcomm/bin:$PATH

  /opt/emcomm/libexec/emcomm-run rigctld -m 1 -T 127.0.0.1 -t 4532 &
  hub=$!
  for _ in $(seq 40); do rigctl -m 2 -r 127.0.0.1:4532 f >/dev/null 2>&1 && break; sleep 0.25; done
  test "$(rigctl -m 2 -r 127.0.0.1:4532 f)" = 145000000
  kill $hub

  emcomm operator add K7TST --grid DN16bk
  emcomm station add bench --radio generic-vox --no-udev
  mkdir -p ~/.config
  printf "[Configuration]\nFont=Keep Me\n" > ~/.config/WSJT-X.ini
  emcomm use K7TST --station bench --yes
  grep -qx "MyCall=K7TST" ~/.config/WSJT-X.ini
  grep -qx "MyGrid=DN16bk" ~/.config/WSJT-X.ini
  grep -qx "Rig=Hamlib NET rigctl" ~/.config/WSJT-X.ini
  grep -qx "CATNetworkPort=127.0.0.1:4532" ~/.config/WSJT-X.ini
  grep -qx "Font=Keep Me" ~/.config/WSJT-X.ini

  sh /emcomm/bootstrap.sh --uninstall --yes
  test -z "$(leftovers)"
  ! ls /etc/apt/sources.list.d/emcomm* /etc/apt/preferences.d/emcomm* /etc/yum.repos.d/emcomm* 2>/dev/null
  test ! -e /etc/emcomm
  ! ls /etc/systemd/user/emcomm-* 2>/dev/null
  grep -qx "Font=Keep Me" ~/.config/WSJT-X.ini   # user files untouched by uninstall
  echo "M1 acceptance OK"
'
```

Run `chmod +x tests/integration/repo-install.sh`.

- [ ] **Step 2: Create `docs/testing/m1-manual-checks.md`**

```markdown
# M1 manual hardware checks

Run on a real Debian 13 and a real Fedora machine after `sudo sh bootstrap.sh --repo-url URL`.
Record results (pass/fail, distro, **machine model** from
`cat /sys/class/dmi/id/product_name`, radio, notes) in the PR that closes M1. Run the USB
checks (2–3, 11) when you have physical access to a radio; the LAN checks (12–13) do not need it.

1. **Bootstrap**: `emcomm status` works; `id` shows `dialout` and `audio`; log out/in once.
2. **Detection**: plug in the radio; `emcomm station detect` lists its serial port and sound card.
3. **Station kit**: `sudo emcomm station add kita --radio <id>`; replug; `/dev/emcomm/cat-kita`
   exists and `aplay -l` shows card `EMCOMM_KITA`; `mmcli -L` does not list the radio.
4. **Hub**: `emcomm use <CALL> --station kita --yes`; `systemctl --user daemon-reload &&
   systemctl --user start emcomm-rigctld`; `rigctl -m 2 -r 127.0.0.1:4532 f` returns the
   radio's frequency; `rigctl -m 2 -r 127.0.0.1:4532 T 1; sleep 1; ... T 0` keys PTT
   (into a dummy load).
5. **WSJT-X**: Settings → Radio shows "Hamlib NET rigctl", 127.0.0.1:4532, PTT CAT;
   Test CAT and Test PTT succeed; Audio shows the EMCOMM card; FT8 decodes on a busy band.
6. **JS8Call**: same checks as WSJT-X. If the Audio dropdown lacks the EMCOMM card under Qt6,
   note the device name it shows (it may need a different SoundInName format).
7. **fldigi**: Configure → Rig → Hamlib shows "Use Hamlib", device 127.0.0.1:4532; frequency
   tracks the radio; PTT via Hamlib works. Select the audio device manually (M1 does not set
   fldigi audio) and note the PortAudio device name for M2.
8. **Direwolf**: `systemctl --user start emcomm-direwolf`; `journalctl --user -u
   emcomm-direwolf` shows the EMCOMM audio device opened and PTT via RIG.
9. **Pat**: `systemctl --user start emcomm-pat`; http://localhost:8080 loads; Settings shows
   rig "emcomm"; a telnet CMS connection works (enter Winlink password in Pat).
10. **Operator switch**: `emcomm operator add <CALL2>`; `emcomm use <CALL2> --station kita`
    shows a diff of only call/grid lines; apply and confirm apps show the new call;
    previous files are in `~/.local/state/emcomm/backups/`.
```

- [ ] **Step 3: Create `README.md`**

````markdown
# emcommOS

Distro-agnostic provisioning for ham radio / emergency-communications laptops:
current builds of hamlib, WSJT-X, JS8Call, fldigi, Direwolf, Pat and friends from signed
deb/rpm repositories, an Ansible collection to set the station up, and an `emcomm` CLI that
wires every app to your radio from operator + station profiles.

Status: **M1 (core station)**: Debian 13 and Fedora 43/44 on amd64 and arm64.
Design: `docs/superpowers/specs/2026-10-05-emcommos-design.md`.

## Install a station

```bash
curl -fsSL "$EMCOMM_REPO_URL/bootstrap.sh" | sudo EMCOMM_REPO_URL="$EMCOMM_REPO_URL" sh
```

Then:

```bash
emcomm operator add K7ABC --grid DN16bk --name "Your Name"
sudo emcomm station add kita --radio icom-ic7300     # auto-detects the plugged-in radio
emcomm use K7ABC --station kita                       # shows a diff, then updates app configs
systemctl --user enable --now emcomm-rigctld          # CAT/PTT hub on 127.0.0.1:4532
```

`emcomm radios` lists supported radios. Every app talks to the radio through rigctld on
127.0.0.1:4532, so switching radios or operators is one command.

## Develop

- Build tooling: `uv run --directory tools pytest -q`; build packages with
  `uv run --directory tools emcomm-build build --target debian-13` (needs podman + nfpm).
- CLI: `uv run --directory cli pytest -q`.
- Ansible: see `ansible/requirements-dev.txt`; `molecule test` in the collection directory.
- Maintainers: `docs/maintainer/setup.md`.

Prior art that inspired ideas (no code reused): EmComm Tools Community, 73Linux.
Licensed under Apache-2.0.
````

- [ ] **Step 4: Run the acceptance test against the published repo**

This step needs Task 26 to have published to `testing`.

Run: `shellcheck tests/integration/repo-install.sh && tests/integration/repo-install.sh debian-13 "$EMCOMM_REPO_URL" && tests/integration/repo-install.sh fedora-44 "$EMCOMM_REPO_URL"`
Expected: `M1 acceptance OK` twice.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/repo-install.sh docs/testing/m1-manual-checks.md README.md
git commit -m "test: M1 acceptance script, manual hardware checklist, README"
```

---

### Task 28: wfview and the Icom IC-7300MK2

**Files:**
- Create: `recipes/wfview/{recipe.yaml,build.sh,smoke.sh}`, `radios/icom-ic7300mk2.yaml`, `cli/src/emcomm/render/wfview.py`, `cli/src/emcomm/render/pipewire.py`
- Modify:
  - `recipes/core/recipe.yaml` (add `wfview` to `requires`, `release: 2`)
  - `cli/src/emcomm/schemas/station.schema.json` (add `control`)
  - `cli/src/emcomm/models.py` (`Station.control`)
  - `cli/src/emcomm/profiles.py` (round-trip `control`)
  - `cli/src/emcomm/render/rigctld.py` (wfview proxy)
  - `cli/src/emcomm/apply.py` (register the wfview config)
  - `cli/src/emcomm/commands/station.py` (`--control`)
  - `cli/src/emcomm/commands/use.py` (exposure warning)
  - `ansible/.../roles/radio_hw/templates/station.toml.j2` (`control`)
  - `docs/testing/m1-manual-checks.md`
- Test: `cli/tests/test_wfview.py`, `cli/tests/test_lan_station.py`; extend `cli/tests/test_ansible_station_template.py`

**Design (from upstream research):**
- wfview v2.23 is the latest stable, from gitlab.com/eliggett/wfview (tags `vX.YY`). It builds with qmake against Qt6 and links only system libraries on Linux. The IC-7300MK2 rig file first shipped in v2.22. Debian 13 ships 2.03 and Fedora ships 1.64, so we build our own.
- wfview's rigctld-compatible server (`[LAN] EnableRigCtlD`, `RigCtlPort`, default 4533) only exists in the GUI app, not in the headless `wfserver`. It binds **all interfaces with no authentication**.
- **Integration:** a station gets `control = "wfview"`. wfview then owns the radio's CAT port, and the emcomm rigctld hub becomes a NET-rigctl proxy: `rigctld -m 2 -r 127.0.0.1:4533 -T 127.0.0.1 -t 4532`. WSJT-X, JS8Call, fldigi, Direwolf, and Pat keep using `127.0.0.1:4532` unchanged. With `control = "direct"` (the default), rigctld drives the radio itself, as before.
- **IC-7300MK2:**
  - hamlib model **3094** (hamlib ≥4.7.0, so our 4.7.2 has it)
  - default CI-V address 0xB6
  - USB-C CDC-ACM serial ports (`ttyACM0` = CI-V on interface 00, `ttyACM1` = USB2 function), plus "USB Audio Codec"
  - Its USB VID:PID is **unverified**, so the definition ships without USB hints for now. Operators pass `--cat ttyACM0 --audio cardN`. The manual check records the real IDs so hints can be added.

**Interfaces:**
- Produces:
  - `Station.control: str = "direct"` (`"direct" | "wfview"`)
  - `render.rigctld.WFVIEW_RIGCTL_ADDR = "127.0.0.1:4533"`
  - `render.wfview.render_wfview(existing, ctx) -> str | None`, which sets only `[LAN] EnableRigCtlD=true` and `RigCtlPort=4533` in `~/.config/wfview/wfview.conf`
  - CLI: `emcomm station add ... --control {direct,wfview}`
  - Package `emcomm-wfview`, which provides `/opt/emcomm/bin/wfview` and `/opt/emcomm/share/wfview/rigs/*.rig`

- [ ] **Step 1: Write the failing tests**

`cli/tests/test_wfview.py`:

```python
import tomllib

from emcomm.cli import main
from emcomm.models import Operator, RadioDef, Station, UsbMatch
from emcomm.profiles import station_from_dict, station_to_dict
from emcomm.radios import load_radios
from emcomm.render.context import RenderContext
from emcomm.render.rigctld import rigctld_args
from emcomm.render.wfview import render_wfview

from sysfs import add_sound, add_tty, make_usb

MK2 = RadioDef(id="icom-ic7300mk2", vendor="Icom", model="IC-7300MK2", hamlib_model=3094,
               baud=115200, ptt="cat")
OP = Operator(callsign="K7ABC", grid="DN16bk")


def kit(control):
    return Station(name="mk2", radio="icom-ic7300mk2", cat=UsbMatch("0c26", "0000"),
                   audio=UsbMatch("08bb", "2901"), control=control)


def test_mk2_definition(paths):
    r = load_radios(paths.radios_dir)["icom-ic7300mk2"]
    assert (r.hamlib_model, r.baud, r.ptt) == (3094, 115200, "cat")


def test_direct_control_drives_radio():
    args = rigctld_args(RenderContext(OP, kit("direct"), MK2))
    assert args[:2] == ["-m", "3094"] and "/dev/emcomm/cat-mk2" in args


def test_wfview_control_proxies_hub():
    assert rigctld_args(RenderContext(OP, kit("wfview"), MK2)) == [
        "-m", "2", "-r", "127.0.0.1:4533", "-T", "127.0.0.1", "-t", "4532"]


def test_render_wfview_only_for_wfview_stations():
    assert render_wfview(None, RenderContext(OP, kit("direct"), MK2)) is None
    out = render_wfview("[General]\nTheme=dark\n", RenderContext(OP, kit("wfview"), MK2))
    assert out == "[General]\nTheme=dark\n\n[LAN]\nEnableRigCtlD=true\nRigCtlPort=4533\n"


def test_control_round_trip():
    st = kit("wfview")
    assert station_from_dict(station_to_dict(st), "t").control == "wfview"
    assert "control" not in station_to_dict(kit("direct"))


def test_station_add_and_use_with_wfview(paths, monkeypatch, capsys):
    from emcomm.commands import use as use_cmd
    monkeypatch.setattr(use_cmd, "restart_services", lambda: True)
    add_tty(paths.sysfs, make_usb(paths.sysfs, "1-1", "0c26", "0000", product="IC-7300MK2"),
            "ttyACM0")
    add_sound(paths.sysfs, make_usb(paths.sysfs, "1-2", "08bb", "2901"), "card1")
    assert main(["operator", "add", "K7ABC"], paths=paths) == 0
    assert main(["station", "add", "mk2", "--radio", "icom-ic7300mk2", "--cat", "ttyACM0",
                 "--audio", "card1", "--control", "wfview", "--no-udev"], paths=paths) == 0
    assert tomllib.loads((paths.stations_dir / "mk2.toml").read_text())["control"] == "wfview"
    capsys.readouterr()
    assert main(["use", "K7ABC", "--station", "mk2", "--yes"], paths=paths) == 0
    assert "EnableRigCtlD=true" in (paths.home / ".config/wfview/wfview.conf").read_text()
    assert "-r 127.0.0.1:4533" in (paths.home / ".config/emcomm/rigctld.env").read_text()
    assert "TCP 4533" in capsys.readouterr().err
```

Append to `cli/tests/test_ansible_station_template.py`:

```python
def test_template_control():
    st = station_from_dict(tomllib.loads(render(
        {"name": "mk2", "radio": "icom-ic7300mk2", "control": "wfview"})), "t")
    assert st.control == "wfview"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --directory cli pytest -q tests/test_wfview.py tests/test_ansible_station_template.py`
Expected: FAIL. `Station.__init__` does not accept `control`, and `emcomm.render.wfview` is missing.

- [ ] **Step 3: Add the IC-7300MK2 radio definition**

`radios/icom-ic7300mk2.yaml`:

```yaml
id: icom-ic7300mk2
vendor: Icom
model: IC-7300MK2
hamlib_model: 3094
baud: 115200
ptt: cat
notes:
  - "CI-V Address: B6h (default). CI-V USB Baud Rate: 115200 (or Auto)"
  - "CI-V USB Echo Back: OFF"
  - "USB AF/IF Output: AF; DATA OFF MOD and DATA MOD: USB; start USB MOD Level near 50%"
  - "USB SEND / USB Keying: OFF (PTT is by CAT)"
  - "USB-C shows two serial ports: ttyACM0 (CI-V) and ttyACM1 (USB2 Function). Use --cat ttyACM0"
  - "wfview control: add the kit with --control wfview, start wfview, select the radio's USB port in wfview"
```

The hamlib smoke test from Task 16 verifies that model 3094 exists in our hamlib.

- [ ] **Step 4: Add `control` to the station model, schema, and profiles**

In `station.schema.json`, add this to `properties`:

```json
    "control": {"enum": ["direct", "wfview"]},
```

In `models.py`, add the field to `Station`, after `ptt`:

```python
    control: str = "direct"
```

and add the module constant:

```python
CONTROL_MODES = ("direct", "wfview")
```

In `profiles.py`, in `station_to_dict`, after the `ptt` block:

```python
    if st.control != "direct":
        data["control"] = st.control
```

In `station_from_dict`, pass `control=data.get("control", "direct")` to `Station(...)`.

- [ ] **Step 5: Implement the rigctld proxy and the wfview renderer**

Replace `render/rigctld.py`:

```python
"""Arguments for the rigctld hub (emcomm-rigctld.service EnvironmentFile).

direct: rigctld drives the radio. wfview: wfview owns the radio and rigctld proxies its
rigctld-compatible server, so every app keeps using 127.0.0.1:4532.
"""

from __future__ import annotations

from .context import RenderContext

DUMMY_MODEL = 1
NET_RIGCTL_MODEL = 2
WFVIEW_RIGCTL_ADDR = "127.0.0.1:4533"
HUB = ["-T", "127.0.0.1", "-t", "4532"]


def rigctld_args(ctx: RenderContext) -> list[str]:
    if ctx.station.control == "wfview":
        return ["-m", str(NET_RIGCTL_MODEL), "-r", WFVIEW_RIGCTL_ADDR, *HUB]
    args = ["-m", str(ctx.radio.hamlib_model), *HUB]
    has_cat = ctx.station.cat is not None
    if ctx.radio.hamlib_model != DUMMY_MODEL and has_cat:
        args += ["-r", ctx.station.cat_link, "-s", str(ctx.radio.baud)]
    if ctx.ptt in ("rts", "dtr") and has_cat:
        args += ["-P", ctx.ptt.upper(), "-p", ctx.station.cat_link]
    if ctx.radio.set_conf:
        args.append("--set-conf=" + ",".join(f"{k}={v}" for k, v in ctx.radio.set_conf))
    return args


def render_rigctld(existing: str | None, ctx: RenderContext) -> str:
    return (
        "# Managed by emcomm: regenerated by `emcomm use`.\n"
        f'RIGCTLD_ARGS="{" ".join(rigctld_args(ctx))}"\n'
    )
```

Create `render/wfview.py`:

```python
"""wfview.conf: enable wfview's rigctld-compatible server for the emcomm hub proxy."""

from __future__ import annotations

from .context import RenderContext
from .ini import set_ini_keys
from .rigctld import WFVIEW_RIGCTL_ADDR


def render_wfview(existing: str | None, ctx: RenderContext) -> str | None:
    if ctx.station.control != "wfview":
        return None
    port = WFVIEW_RIGCTL_ADDR.rsplit(":", 1)[1]
    return set_ini_keys(existing or "", "LAN", {"EnableRigCtlD": "true", "RigCtlPort": port})
```

In `apply.py`, import `render_wfview` and add it to `APP_CONFIGS`, after the rigctld entry:

```python
    AppConfig("wfview", ".config/wfview/wfview.conf", render_wfview),
```

- [ ] **Step 6: CLI flag and exposure warning**

In `commands/station.py`, add the flag in `register` and import `CONTROL_MODES`:

```python
    add.add_argument("--control", choices=CONTROL_MODES, default="direct",
                     help="direct: rigctld drives the radio; wfview: wfview owns it")
```

Then pass `control=args.control` to `Station(...)` in `cmd_add`.

In `commands/use.py`, after the services restart in `cmd_use`:

```python
    if station.control == "wfview":
        print("warning: wfview's rigctld server listens on all interfaces without a password; "
              "block TCP 4533 in the firewall on untrusted networks. Start wfview before "
              "emcomm-rigctld.", file=sys.stderr)
```

In `roles/radio_hw/templates/station.toml.j2`, add this after the `ptt` block:

```
{% if item.control is defined %}
control = "{{ item.control }}"
{% endif %}
```

- [ ] **Step 6b: LAN kits with PipeWire virtual audio**

This is the setup you use today: the IC-7300MK2 reached over Ethernet by wfview, with no USB cable. wfview on Linux does not create audio devices, so emcomm creates a virtual pair per kit using PipeWire null sinks:
- `emcomm-<kit>-rx`: wfview plays the radio's RX audio into it, and the apps record from its monitor.
- `emcomm-<kit>-tx`: the apps play TX audio into it, and wfview records from its monitor.

Write the failing tests in `cli/tests/test_lan_station.py`:

```python
import tomllib

from emcomm.apply import plan_changes
from emcomm.cli import main
from emcomm.models import Operator, RadioDef, Station
from emcomm.render.context import RenderContext
from emcomm.render.pipewire import render_pipewire
from emcomm.render.qtini import wsjtx_values

MK2 = RadioDef(id="icom-ic7300mk2", vendor="Icom", model="IC-7300MK2", hamlib_model=3094,
               baud=115200, ptt="cat")
LAN = Station(name="mk2", radio="icom-ic7300mk2", control="wfview", virtual_audio=True)
CTX = RenderContext(Operator("K7ABC", grid="DN16bk"), LAN, MK2)


def test_pipewire_dropin():
    text = render_pipewire(None, CTX)
    assert 'node.name        = "emcomm-mk2-rx"' in text
    assert 'node.name        = "emcomm-mk2-tx"' in text
    assert text.count("support.null-audio-sink") == 2
    usb = RenderContext(CTX.operator, Station(name="b", radio="x"), MK2)
    assert render_pipewire(None, usb) is None


def test_qt_apps_use_virtual_devices():
    v = wsjtx_values(CTX)
    assert v["SoundInName"] == '"emcomm-mk2-rx.monitor"'
    assert v["SoundOutName"] == '"emcomm-mk2-tx"'


def test_plan_writes_per_kit_dropin(paths):
    paths_changes = {c.app: c.path for c in plan_changes(paths, CTX)}
    assert paths_changes["pipewire"] == paths.home / ".config/pipewire/pipewire.conf.d/60-emcomm-mk2.conf"
    assert "direwolf" not in paths_changes  # no ALSA card for LAN kits in M1


def test_add_lan_station(paths, capsys):
    assert main(["station", "add", "mk2", "--radio", "icom-ic7300mk2", "--control", "wfview",
                 "--virtual-audio", "--no-udev"], paths=paths) == 0
    data = tomllib.loads((paths.stations_dir / "mk2.toml").read_text())
    assert data["control"] == "wfview" and data["virtual_audio"] is True
    assert "warning" not in capsys.readouterr().out
```

Run: `uv run --directory cli pytest -q tests/test_lan_station.py`
Expected: FAIL (`Station` has no `virtual_audio`; `emcomm.render.pipewire` is missing).

Implement:

1. In `station.schema.json`, add to `properties`: `"virtual_audio": {"type": "boolean"}`.
2. In `models.py`, add to `Station`: `virtual_audio: bool = False`, plus:

   ```python
       @property
       def rx_sink(self) -> str:
           return f"emcomm-{self.name}-rx"

       @property
       def tx_sink(self) -> str:
           return f"emcomm-{self.name}-tx"
   ```

3. In `profiles.py`: `station_to_dict` adds `data["virtual_audio"] = True` when set, and `station_from_dict` passes `virtual_audio=data.get("virtual_audio", False)`.
4. In `render/context.py`, add to `RenderContext`:

   ```python
       @property
       def sound_in(self) -> str | None:
           if self.station.virtual_audio:
               return f"{self.station.rx_sink}.monitor"
           return self.alsa_device

       @property
       def sound_out(self) -> str | None:
           if self.station.virtual_audio:
               return self.station.tx_sink
           return self.alsa_device
   ```

5. In `render/qtini.py`, replace the `if ctx.alsa_device:` block with:

   ```python
       if ctx.sound_in:
           values["SoundInName"] = f'"{ctx.sound_in}"'
       if ctx.sound_out:
           values["SoundOutName"] = f'"{ctx.sound_out}"'
   ```

6. Create `render/pipewire.py`:

   ```python
   """Per-kit PipeWire virtual devices for LAN stations (wfview has no Linux audio devices)."""

   from __future__ import annotations

   from .context import RenderContext

   NODE = """    {{ factory = adapter
         args = {{
           factory.name     = support.null-audio-sink
           node.name        = "{name}"
           node.description = "{description}"
           media.class      = Audio/Sink
           audio.position   = [ MONO ]
           object.linger    = true
           monitor.channel-volumes = true
         }}
       }}"""


   def render_pipewire(existing: str | None, ctx: RenderContext) -> str | None:
       st = ctx.station
       if not st.virtual_audio:
           return None
       rx = NODE.format(name=st.rx_sink, description=f"emcomm {st.name} RX (radio audio from wfview)")
       tx = NODE.format(name=st.tx_sink, description=f"emcomm {st.name} TX (app audio to wfview)")
       return (f"# Managed by emcomm: virtual audio for LAN station {st.name}.\n"
               f"context.objects = [\n{rx}\n{tx}\n]\n")
   ```

7. In `apply.py`, let `relpath` contain `{station}`. In `plan_changes` use `path = paths.home / cfg.relpath.format(station=ctx.station.name)`, and register the renderer:

   ```python
       AppConfig("pipewire", ".config/pipewire/pipewire.conf.d/60-emcomm-{station}.conf",
                 render_pipewire),
   ```

8. In `commands/station.py`:
   - Add `add.add_argument("--virtual-audio", action="store_true", help="LAN kit: create PipeWire virtual RX/TX devices")` and pass `virtual_audio=args.virtual_audio` to `Station(...)`.
   - Skip the "no CAT serial port found" warning when `args.control == "wfview"`.
9. In `commands/use.py`, after the wfview warning:

   ```python
       if station.virtual_audio:
           print(f"note: restart PipeWire to create the virtual devices "
                 f"(systemctl --user restart pipewire pipewire-pulse wireplumber). In wfview, set "
                 f"audio output to '{station.rx_sink}' and input to 'Monitor of {station.tx_sink}'.",
                 file=sys.stderr)
   ```

10. In `roles/radio_hw/templates/station.toml.j2`, after the `control` block:

    ```
    {% if item.virtual_audio | default(false) %}
    virtual_audio = true
    {% endif %}
    ```

11. Append a note to `radios/icom-ic7300mk2.yaml` `notes`:
    `"LAN (no USB): sudo emcomm station add mk2 --radio icom-ic7300mk2 --control wfview --virtual-audio; connect wfview to the radio's IP"`

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check .`
Expected: PASS.

Qt's PulseAudio device naming (`<sink>.monitor` / `<sink>`) under PipeWire is unverified. Manual check 12 confirms what WSJT-X and JS8Call actually list, and the renderer gets adjusted if needed.

- [ ] **Step 7: Create the wfview recipe**

`recipes/wfview/recipe.yaml`:

```yaml
name: wfview
kind: app
summary: wfview open-source Icom/Kenwood/Yaesu rig control with waterfall and LAN remote
license: GPL-3.0-or-later
homepage: https://wfview.org/
version: "2.23"
release: 1
source:
  type: git
  url: https://gitlab.com/eliggett/wfview.git
  ref: "v{version}"
upstream:
  type: git-tags
  url: https://gitlab.com/eliggett/wfview.git
  tag_pattern: 'v(\d+\.\d+)'
deps:
  debian:
    build: [qmake6, qt6-base-dev, qt6-serialport-dev, qt6-multimedia-dev, qt6-websockets-dev,
            libqcustomplot-dev, libopus-dev, libeigen3-dev, portaudio19-dev, librtaudio-dev,
            libhidapi-dev, libudev-dev, libpulse-dev]
  fedora:
    build: [qt6-qtbase-devel, qt6-qtserialport-devel, qt6-qtmultimedia-devel,
            qt6-qtwebsockets-devel, qcustomplot-qt6-devel, opus-devel, eigen3-devel,
            portaudio-devel, rtaudio-devel, hidapi-devel, systemd-devel, pulseaudio-libs-devel]
```

`recipes/wfview/build.sh`:

```bash
#!/usr/bin/env bash
# qmake build. PREFIX is compiled in (rig files load from $PREFIX/share/wfview/rigs),
# so it must be the runtime prefix; INSTALL_ROOT stages into DESTDIR.
set -euo pipefail
QMAKE=$(command -v qmake6 || command -v qmake-qt6 || echo /usr/lib64/qt6/bin/qmake)
mkdir -p build
cd build
"$QMAKE" ../wfview.pro PREFIX="$PREFIX" VERSION="$VERSION" CONFIG+=release
# wfview.pro probes only a few qcustomplot Qt6 library names; add the distro's if it missed.
if ! grep -q -- '-lqcustomplot\|-lQCustomPlot' Makefile; then
  for name in qcustomplot-qt6 qcustomplot2.1-qt6 qcustomplotqt6 qcustomplot2qt6 QCustomPlotQt6; do
    if ldconfig -p | grep -q "lib${name}\.so "; then
      sed -i "s/^LIBS .*/& -l${name}/" Makefile
      break
    fi
  done
fi
make -j"$JOBS"
make install INSTALL_ROOT="$DESTDIR"
```

`recipes/wfview/smoke.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
test -x /opt/emcomm/bin/wfview
test -f /opt/emcomm/share/wfview/rigs/IC-7300MK2.rig
grep -q '^CIVAddress=182' /opt/emcomm/share/wfview/rigs/IC-7300MK2.rig
```

In `recipes/core/recipe.yaml`, set `requires: [hamlib, flrig, wfview, cli]` and `release: 2`.

- [ ] **Step 8: Run tests, build, smoke**

Run: `uv run --directory cli pytest -q && uv run --directory cli ruff check . && uv run --directory tools emcomm-build validate`
Expected: PASS and `ok: 3 targets, 12 recipes`.

Run: `uv run --directory tools emcomm-build build --target debian-13 --only wfview --only core && uv run --directory tools emcomm-build build --target fedora-44 --only wfview --only core`
Expected: `smoke OK` twice. If linking fails with undefined `QCustomPlot` symbols, run `ldconfig -p | grep -i qcustomplot` inside the build container and add that library name to the loop in `build.sh`.

Run: `uv run --directory tools emcomm-build build --target debian-13 --only hamlib --force`
Expected: `smoke OK`, which confirms hamlib knows model 3094.

- [ ] **Step 9: Add IC-7300MK2 checks to `docs/testing/m1-manual-checks.md`**

```markdown
11. **IC-7300MK2 (direct)**: `emcomm station detect` with the radio on USB-C. **Record the
    VID:PID, product string and interface numbers** of both ttyACM ports and the sound card
    in the PR so `radios/icom-ic7300mk2.yaml` can gain `usb_hints`.
    `sudo emcomm station add mk2 --radio icom-ic7300mk2 --cat ttyACM0 --audio cardN`;
    repeat checks 3–5 (rigctld uses hamlib model 3094).
12. **IC-7300MK2 over LAN via wfview (primary setup today)**: `sudo emcomm station add mk2
    --radio icom-ic7300mk2 --control wfview --virtual-audio`; `emcomm use <CALL> --station mk2`;
    restart PipeWire; in wfview connect to the radio's IP and set audio out/in to the
    emcomm virtual devices; record the exact device names WSJT-X and JS8Call list.
    For a USB-attached MK2 instead: `--cat ttyACM0 --audio cardN --control wfview`;
    start wfview, pick the radio's port, confirm waterfall; then
    `systemctl --user restart emcomm-rigctld` and repeat check 4 (frequency/PTT through
    127.0.0.1:4532 → wfview 4533) and check 5 (WSJT-X CAT/PTT while wfview shows the TX).
    Confirm `ss -ltn | grep 4533` and note that it listens on 0.0.0.0.
13. **IC-7300MK2 LAN (optional)**: connect wfview to the radio's Ethernet port (Network
    settings in wfview); record whether LAN control and audio work.
```

- [ ] **Step 10: Commit**

```bash
git add recipes/wfview recipes/core radios/icom-ic7300mk2.yaml cli ansible docs/testing
git commit -m "feat: wfview 2.23, IC-7300MK2, wfview-controlled and LAN stations with virtual audio"
```

---

### Task 29: Nix flake dev shell (pinned contributor tooling)

**Files:**
- Create: `flake.nix`, `flake.lock` (generated)
- Modify: `README.md` (Develop section)

**Interfaces:**
- Produces: `nix develop`, which gives every contributor the same pinned versions of `uv`, Python 3.12, `nfpm`, `shellcheck`, `actionlint`, `gnupg`, `rclone`, `git`, and `jq`. Podman comes from the host because rootless podman needs host setuid helpers. Ansible/Molecule come from `ansible/requirements-dev.txt` in a venv, matching CI. Tier-2 app outputs come in M2 (spec §4.5).

- [ ] **Step 1: Create `flake.nix`**

```nix
{
  description = "emcommOS development shell (pinned tooling)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [ python312 uv nfpm shellcheck actionlint gnupg rclone git jq ];
          shellHook = ''
            export UV_PYTHON=${pkgs.python312}/bin/python3
            command -v podman >/dev/null || echo "note: install podman from your distro for package builds"
          '';
        };
      });
    };
}
```

- [ ] **Step 2: Lock and check it**

If Nix is installed: `nix flake lock && nix flake check && nix develop -c nfpm --version`.

Without Nix, use a container:

```bash
podman run --rm -v "$PWD:/src:z" -w /src docker.io/nixos/nix sh -c \
  "nix --extra-experimental-features 'nix-command flakes' flake lock && \
   nix --extra-experimental-features 'nix-command flakes' develop -c nfpm --version"
```

Expected: `flake.lock` is created and nfpm prints its version.

- [ ] **Step 3: Document it**

Add this as the first bullet of README.md's "Develop" section:

```markdown
- Tooling: `nix develop` gives pinned uv/python/nfpm/shellcheck/actionlint/gnupg/rclone
  (optional; otherwise install them yourself). Podman comes from your distro.
```

- [ ] **Step 4: Commit**

```bash
git add flake.nix flake.lock README.md
git commit -m "build: Nix flake dev shell with pinned contributor tooling"
```
