# emcommOS — Design Spec

- **Date:** 2026-10-05 (revised same day: sourcing policy, adoption levels, LAN stations)
- **Status:** Approved
- **License:** Apache-2.0

## 1. Problem & goals

Hams run Linux on a mix of distros (mostly Debian-based, plus Fedora and Arch). Getting a
machine to a known-good loadout is manual, fragile, and usually tied to one distro release.
A known-good loadout means current hamlib, WSJT-X, JS8Call, fldigi, Pat, Direwolf, wfview,
and so on, all correctly wired to a radio. Field deployments may also have no internet.

emcommOS is for **anyone who wants a well-packaged ham station**, from an individual radio
enthusiast or a personal emcomm prepper up to clubs, ARES/RACES, AUXCOMM teams, and agencies.
Many machines are volunteers' own laptops (BYOD).

emcommOS provides:

1. **Reproducible setup** across distros and hardware models. Each package's source is
   declared and pinned per distro family.
2. **Current software.** Prefer prebuilt packages: the distro package when it is current
   enough, otherwise the upstream's binary release. Build from source only where both lag
   (e.g. hamlib and fldigi on some distros).
3. **Operator-friendly operation:** operator + station profiles, modes, and diagnostics,
   via a CLI and a TUI.
4. **Offline fallback:** an optional low-power field server (Pi / ZimaBoard) that mirrors
   everything needed to install, repair, and update machines, and hosts shared services.

### Non-goals
- Replacing distro package management for non-ham software.
- Supporting armhf / 32-bit Pis.
- Wine/VARA and SDR tooling in early milestones (later toolsets).

### Prior art (reference for ideas only — no code or data reused)
- **EmComm Tools Community (ETC)**: radio-definition files, generated device aliases,
  rigctld as a shared hub, exclusive "modes", launch-time config templating, offline
  content. Limitation: locked to Ubuntu 22.10 (EOL).
- **73Linux**: add/remove app plugin UX. Limitations: floating "latest" versions scraped at
  install time, configs written once and never managed, sudo password collected in a GUI.
- **apalrd "enterprise repo"**: repos as static files plus signed indexes.
- **modem73**, **Rhizomatica Mercury**: open-source data modems (`emcomm-modems` toolset).

## 2. Decomposition & adoption levels

Three projects, built in order:

| Project | Role |
|---|---|
| **emcommOS** (station) | The core: package sourcing and builds, repos, Ansible collection `emcomm.station`, CLI/TUI. Sole producer of artifacts. A machine running only this is fully operational. |
| **emcommOS-field** (server) | Complementary field server: mirror, netboot installers, sync hub, shared services. Never builds artifacts. |
| **emcommOS Linux** (distro) | An installable image built by running the emcommOS bootstrap at image-build time. Gets its own brainstorm/spec after the station project's M3. |

**Design rule:** the field server only ever adds *conveniences*. Anything it runs must also
run on a standalone machine.

**Adoption levels.** All levels use the same packages; each higher level is opt-in.

| Level | Who | What it adds |
|---|---|---|
| **Standalone** (default) | Enthusiasts, personal emcomm, any volunteer's own laptop | Bootstrap + CLI on the user's own machine. No accounts, no central service, no data collection. |
| **Group** (opt-in) | Clubs, ARES/RACES, AUXCOMM | Join one or more **group profiles** (a git repo or URL) providing shared station kits, settings, and recommended toolsets. The machine pulls from it, and leaving is one command. Sync folders are opt-in. |
| **Managed** | Agency- or club-owned machines | Central Ansible push, machine roles (field/base), per-model quirks, inventory/health reporting. |

**BYOD rules (all levels):**
- Bootstrap shows exactly what it will change (repo + key, packages, group membership, udev
  rules) and asks for confirmation (`--yes` for unattended use).
- Everything is **uninstallable**: `bootstrap.sh --uninstall` / `emcomm uninstall` removes
  our repo, pins, packages, units, and rules.
- emcomm never edits app settings it doesn't manage, and the confirmation lists any distro
  package a chosen toolset would replace.
- Standalone collects nothing.

## 3. Platform support

| Tier | Targets | Guarantees |
|---|---|---|
| 1 (deb and rpm, equal) | Debian 13, Ubuntu 24.04 LTS (and derivatives such as Mint 22), Fedora current + previous, Alma/Rocky 10 (EPEL + CRB; Qt5-dependent apps need the AppImage route) | Our signed repo, CI smoke tests, offline bundles, unattended installers |
| 2 | Arch and derivatives; any other distro | Same Ansible roles + CLI. Arch: official repos + AUR. Others: a pinned **Nix flake** for the apps, with Ansible handling host pieces (udev, groups, chrony/gpsd). Best effort; no offline bundle. |

Architectures: **amd64 and arm64**. Packages are per distro and architecture, never per
hardware model.

Machines never compile anything. Sources are declared per target in the repo. CI builds or
fetches everything ahead of time. Bootstrap and Ansible read `/etc/os-release` only to select
the matching repo suite or source.

## 4. Package sourcing, builds & releases

### 4.1 Sourcing policy
Each app declares a **source per distro family**, chosen in this order:

1. **Distro package** (including official backports such as Debian `trixie-backports`) when
   it is current enough. The toolset metapackage depends on it with a version floor, e.g.
   `wsjtx (>= 3.0.2)`.
2. **Upstream prebuilt binary** (static binary, release tarball, or AppImage). It is pinned
   by sha256 and repackaged into `/opt/emcomm` with nFPM; nothing is compiled.
3. **Build from source**: a pinned upstream tag, built in a clean distro container,
   installed under `/opt/emcomm` with rpath.

A `emcomm-build freshness` report compares distro versions with upstream so source changes
are deliberate, reviewed decisions. M1 sourcing (Debian 13 / Fedora 43–44):

| App | Debian 13 | Fedora 43/44 |
|---|---|---|
| hamlib (rigctld hub) | backports 4.7.2 | **build** 4.7.2 (distro 4.6.5 lacks IC-7300MK2 and the rigctld CVE fixes) |
| WSJT-X | backports 3.0.2 | distro 3.0.1 |
| Direwolf | backports 1.8.1 | distro 1.8.1 |
| fldigi, flrig | **build** (distro 4.2.06 / 2.0.05) | distro |
| flmsg, flamp | distro | distro |
| Pat | **prebuilt** upstream static binary | same |
| JS8Call (JS8Call-improved) | **prebuilt** upstream AppImage, extracted | same |
| wfview | **build** (distro 2.03; upstream Linux binary is an unsigned self-extractor) | **build** (distro 1.64) |

Because every app reaches the radio through the rigctld hub (§5.5), **only rigctld needs
current hamlib**. Distro apps may link older hamlib as plain network clients.

On Debian, `trixie-backports` is enabled with an apt pin that covers only the packages we
name.

### 4.2 Recipes
One directory per package, `recipes/<name>/recipe.yaml`, of kind `source`, `prebuilt`,
`files`, or `meta`. A recipe can be limited to certain families
(e.g. `families: [fedora]`). Meta recipes list our recipes (`requires`) and version-pinned
distro packages per family. Built and prebuilt packages install under **`/opt/emcomm`** and
never conflict with distro libraries.

### 4.3 Pipeline
1. **watch-upstream** (scheduled): resolve the newest matching upstream tag and open a PR
   bumping it (with a new sha256 for downloaded artifacts). Never scrape HTML.
2. **build**: {target} × {amd64, arm64} on native runners. Each recipe is built in a clean
   container of its target, with that target's extra repos (e.g. backports) enabled.
3. **smoke tests**: install into a fresh container and check library resolution (bundled
   AppImage trees excepted) and app-specific behaviour (e.g. `rigctl -m 1 f`).
4. **publish → `testing`**: sign, index, and upload static repos to Cloudflare R2
   (signed `InRelease`; signed RPMs plus `repomd.xml`).
5. **release set** (M3): pin all versions (ours and the distro floors), build offline
   bundles, run offline QEMU install tests, and promote to **`stable`**.

### 4.4 Signing keys
- A dedicated project key: an Ed25519 certify-only primary kept offline, plus an Ed25519
  signing subkey (3-year expiry). Only the subkey is in CI.
- Clients pin the key (deb822 `Signed-By:` / `gpgkey=`). `bootstrap.sh` pins its fingerprint.
- The field server never holds a key; it is untrusted transport.

### 4.5 Containers and Nix
- **Containers** are used only where they earn their place: clean build and test
  environments (as with sbuild and mock). Station services run as plain systemd user units.
  The field server decides its own service model in its spec.
- **Nix flake**: a dev shell pinning contributor tooling, and the tier-2 app delivery path
  (from M2). It is not used for tier-1 laptops, because Qt/audio/udev on non-NixOS Nix is
  fragile.

## 5. Station — emcommOS

### 5.1 Repository layout
```
emcommOS/
  targets.yaml                      # build targets, extra repos (e.g. backports)
  recipes/<name>/{recipe.yaml,build.sh,smoke.sh}
  release-sets/emcomm-YYYY.MM.yaml  # M3
  radios/<vendor>-<model>.yaml      # radio definitions (schema-validated)
  ansible/                          # collection emcomm.station
  cli/                              # python: emcomm CLI + emcomm-tui
  tools/                            # emcomm-build (python) + container scripts
  flake.nix                         # dev shell; tier-2 app outputs (M2)
  .github/workflows/
  bootstrap.sh
```

### 5.2 Toolsets (meta-packages)
| Toolset | Contents |
|---|---|
| `emcomm-core` | rigctld (hamlib), flrig, wfview, emcomm-cli |
| `emcomm-digital` | WSJT-X, JS8Call, fldigi, flmsg, flamp |
| `emcomm-winlink` | Pat, Direwolf (ARDOP in M2) |
| `emcomm-aprs` (M2) | Direwolf APRS configs, Xastir |
| `emcomm-modems` (M2, opt-in) | modem73, Mercury, ardopcf |
| `emcomm-logging`, `emcomm-maps` (M2) | ADIF tooling + logging app; tiles + viewer |
| `emcomm-sdr`, `emcomm-wine` (later) | SDR tools; Wine prefix for VARA / Winlink Express |

**`emcomm-standard`** is the opinionated default (core + digital + winlink in M1; aprs,
logging, and maps join in M2). Custom selection is always available.

### 5.3 Bootstrap & Ansible
`bootstrap.sh`:
1. Detect the distro.
2. Show the planned changes and confirm.
3. Verify the pinned key fingerprint.
4. Add the repo (plus Debian backports and the pin).
5. Install `emcomm-cli` and `ansible-core`.
6. Run `emcomm bootstrap`, which applies the `emcomm.station` collection locally (the same
   playbooks a managed fleet gets by push).

Roles:
- `base`: repos and pins, chrony, radio groups.
- `toolsets`: install the selected metapackages.
- `radio_hw`: station kits (local, or from a group profile in M2) and generated udev rules.
- `services`: systemd user units (rigctld hub, Direwolf, Pat). Lingering for base stations
  (managed level).

`emcomm uninstall` reverses all of it.

### 5.4 Radio definitions, stations, operators
- **Radio definition** (`radios/*.yaml`, written by us): hamlib model, baud, PTT method,
  hamlib `set-conf` options, USB hints for auto-detection, and operator notes.
- **Station kit** (`/etc/emcomm/stations/<kit>.toml`): radio + how it is reached:
  - **USB kits** match the radio interface by USB vendor/product/serial, never by port. The
    same kit definition therefore works on any machine and any port: `/dev/emcomm/cat-<kit>`
    and ALSA card `EMCOMM_<KIT>`. USB autosuspend is disabled for kit devices so laptops
    don't drop CAT or audio.
  - **LAN kits** (e.g. IC-7300MK2 over Ethernet) have no USB devices. wfview connects over
    the network, and emcomm creates a **PipeWire virtual RX/TX device pair** per kit for the
    digital apps.
- **Operator profile** (`~/.config/emcomm/operators/<call>.toml`): callsign, name, grid.
  Secrets stay in the OS keyring and are never synced.
- `emcomm use <operator> --station <kit>` renders **only managed keys** into WSJT-X.ini,
  JS8Call.ini, fldigi_def.xml, Pat config.json, wfview.conf, direwolf.conf, and the rigctld
  args. It shows a diff, backs up the previous files, and restarts running services.

### 5.5 rigctld hub & modes
- One rigctld serves `127.0.0.1:4532`, and every app uses it.
- A kit's `control` is either:
  - `direct` (rigctld drives the radio), or
  - `wfview` (wfview owns the radio, locally or over LAN, and rigctld proxies wfview's
    rigctld-compatible server on 4533 as NET rigctl).

  wfview's server binds all interfaces without authentication, so firewall TCP 4533 on
  untrusted networks.
- **Modes** (M2) are exclusive sets of user units, e.g. `ft8-js8`, `winlink-ardop`,
  `winlink-packet`, `aprs-digi`.

### 5.6 CLI & TUI
- `emcomm` (Python): `bootstrap`, `uninstall`, `use`, `operator`, `station`, `status`, plus
  `mode`, `toolset`, `group join|leave`, `source`, `update`, `rollback`, and `doctor` in later
  milestones.
- `emcomm-tui` (Textual, M2): setup wizard, operator/station, mode, toolsets, settings,
  diagnostics, status/sync, and source.

### 5.7 Source selection (with the field server)
Avahi discovery of `_emcomm-repo._tcp`. A NetworkManager dispatcher hook points package
sources at a discovered field server, otherwise at the internet, with a manual override.
Packages and signatures are identical on every source.

### 5.8 Updates, rollback & reliability
- `emcomm update` is manual; a timer only notifies.
- Snapshot before update (Btrfs/LVM or `/opt/emcomm` plus configs), with automatic rollback.
- The last two release sets stay installable offline.
- `emcomm doctor` checks groups, ModemManager, udev links, rigctld response, audio, time
  sync, key expiry, and disk space.
- A missing radio or server degrades gracefully.

### 5.9 Mixed hardware
- Nothing is model-specific.
- Machine roles `field` (services on demand) and `base` (services at boot via lingering) are
  set per machine in managed inventories.
- Per-model quirks (M2+, managed) live in `quirks/<vendor>/<model>.yml`, keyed by DMI product
  name.
- Manual hardware checks record the machine model.

## 6. Sync (opt-in)
A Syncthing mesh of machines, field server, and home node. One folder per data type
(`messages`, `logs`, `inventory`, `server-state`), each opted into separately. Inventory is a
managed-level feature. Secrets are always excluded.

## 7. Field server — emcommOS-field
- **Platform:** Debian 13 on a Pi 5 or ZimaBoard with an SSD.
- **Offline bundles:** a CI-built, signed dependency closure per target and release set,
  served statically (Caddy) or carried on USB.
- **Network services:** dnsmasq/iPXE, optional AP, Avahi, GPS-disciplined chrony.
- **Installers:** unattended installers pointed at the local bundle.
- **Optional shared services:** Pat gateway and modem hub, map tiles, Kiwix, offline lookup
  datasets, a Matrix homeserver (Conduwuit/Tuwunel), and ntfy.
- **Arch:** `pacoloco` cache.
- The service model (native vs containers) is decided in its own spec.

## 8. emcommOS Linux (distro) — future project
An installable image built by running the emcommOS bootstrap, so it never diverges from a
bootstrapped machine. Open questions:
- base distro(s)
- image tooling (mkosi, debos, live-build, Kiwi)
- live vs installed media
- atomic vs traditional updates
- branding
- serving the images from the field server

## 9. Testing strategy
| Layer | Approach |
|---|---|
| Packages | Smoke tests per target × arch in fresh containers |
| Ansible | Molecule (podman driver) on tier-1 distros (+ Arch in M2) |
| CLI/TUI | pytest against real sample configs; Textual snapshots |
| Schemas | All radio/station/operator/recipe files validated in CI |
| Release set | Offline QEMU install per tier-1 target (M3) |
| Hardware | Manual checklist recording machine model and radio. Self-hosted hardware-in-the-loop runner later. |

## 10. Milestones
1. **M1 — standalone core station** on Debian 13 + Fedora 43/44 × amd64/arm64:
   - §4.1 sourcing; signed `testing` repo
   - CLI profiles and rendering; USB and LAN (wfview) kits with PipeWire virtual audio
   - USB autosuspend off
   - roles base/toolsets/radio_hw/services
   - consent prompt and uninstall
   - Nix dev shell
2. **M2**:
   - TUI, modes, doctor
   - group profiles
   - Ubuntu 24.04 (+ Mint), EL10, Arch (official + AUR)
   - Nix tier-2 path
   - aprs/logging/maps/modems toolsets
   - Syncthing
3. **M3**: release sets, `stable` channel, offline bundles, USB sneakernet.
4. **Managed level**: push, machine roles, quirks, inventory.
5. **F1/F2** (field server). **D1** (distro spec).
6. **Later**: Ubuntu 26.04, wine/VARA, SDR, hardware-in-the-loop CI.

### M1 acceptance
- CI publishes signed `testing` repos for Debian 13 and Fedora 43/44 on both architectures.
- A fresh container can run `bootstrap.sh --no-provision --yes`, install `emcomm-core`, and
  get `145000000` back through the rigctld hub with the dummy rig.
- `emcomm use` renders WSJT-X.ini with the correct call, grid, and CAT keys and leaves
  unmanaged keys untouched.
- `emcomm uninstall` removes every emcomm package, repo file, pin, unit, rule and `/etc/emcomm`,
  and leaves the user's own files untouched.
