# emcommOS — Design Spec

- **Date:** 2026-10-05
- **Status:** Draft for review
- **License:** Apache-2.0

## 1. Problem & goals

Ham radio / emcomm groups run Linux laptops on a mix of distros (mostly Debian-based, plus
Fedora and Arch). Getting a laptop to a known-good emcomm loadout — current hamlib, WSJT-X,
JS8Call, fldigi, Pat, Direwolf, etc., correctly wired to a radio — is manual, fragile, and
usually tied to one distro release. Field deployments may have no internet.

emcommOS provides:

1. **Reproducible provisioning** of emcomm laptops across distros, for a managed group fleet
   (central push), volunteers' own laptops (self-service pull), and small teams.
2. **Current software**: latest *tagged* upstream releases, built and tested by CI, delivered
   through signed native repos.
3. **Operator-friendly operation**: operator + station profiles, mode switching, diagnostics,
   via a CLI and a TUI.
4. **Offline fallback**: an optional low-power field server (Pi / ZimaBoard) that mirrors
   everything needed to install, repair, and update laptops, and hosts shared services.

### Non-goals
- Replacing distro package management for non-emcomm software.
- Supporting armhf / 32-bit Pis.
- Wine/VARA and SDR tooling in early milestones (later toolsets).

### Prior art (reference for ideas only — no code or data reused)
- **EmComm Tools Community (ETC)** — radio-definition files, generated device aliases,
  rigctld as a shared hub, exclusive "modes", launch-time config templating, offline
  content (map tiles, Kiwix, lookup datasets). Limitation: locked to Ubuntu 22.10 (EOL).
- **73Linux** — add/remove app plugin UX. Limitations: floating "latest" scraped at install
  time, configs written once and never managed, sudo password collected in a GUI.
- **apalrd "enterprise repo"** — repos as static files + signed indexes served by any web
  server.
- **modem73**, **Rhizomatica Mercury** — open-source HF/VHF data modems (packaged in the
  opt-in `emcomm-modems` toolset).

## 2. Decomposition

Three projects, built in order:

| Project | Role |
|---|---|
| **emcommOS** (station) | The core. Recipes, packages, repos, Ansible collection `emcomm.station`, CLI/TUI. Sole producer of all artifacts. A laptop running only this is fully operational. |
| **emcommOS-field** (server) | Complementary field server. Consumes emcommOS release sets; adds mirror, registry cache, netboot installers, sync hub, shared services. Never builds artifacts. |
| **emcommOS Linux** (distro) | A packaged, installable emcommOS distribution (ISO/disk images) built on a tier-1 base, produced by running the emcommOS bootstrap at image-build time. Gets its own brainstorm/spec cycle after the station project's M3. |

**Design rule:** the field server only ever adds *conveniences*. Anything it runs (e.g. Pat)
must also run on a standalone laptop. Losing the server never removes a capability.

## 3. Platform support

| Tier | Targets | Guarantees |
|---|---|---|
| 1 (deb and rpm, equal) | Debian 13, Ubuntu 24.04 LTS (26.04 added next), Fedora current + previous, Alma/Rocky 10 (EPEL + CRB) | Native packages, CI smoke tests, offline bundles, unattended installers |
| 2 | Arch and derivatives, others | Same Ansible roles; best-effort packages; no offline bundle or installer |

Architectures: **amd64 and arm64**, built on native GitHub-hosted runners.

## 4. Package build & release pipeline

### 4.1 Recipes
One directory per app: `recipes/<app>/`.

```yaml
# recipes/hamlib/recipe.yaml
name: hamlib
upstream: { type: github-release, repo: Hamlib/Hamlib, tag_pattern: '^\d+\.\d+(\.\d+)?$' }
version: 4.6.5            # bumped by CI PRs
build: build.sh           # runs inside the target container; installs to $DESTDIR/opt/emcomm
deps:
  debian: { build: [libusb-1.0-0-dev], run: [libusb-1.0-0] }
  fedora: { build: [libusb1-devel],    run: [libusb1] }
  el:     { build: [libusb1-devel],    run: [libusb1] }
  arch:   { build: [libusb],           run: [libusb] }
depends_on: []            # e.g. wsjtx: [hamlib]
tests: tests/smoke.sh
```

- Everything installs under **`/opt/emcomm`** using rpath, so it never conflicts with
  distro libraries (e.g. `libhamlib4`) and survives distro upgrades. `/etc/profile.d/emcomm.sh`
  and `.desktop` files add it to PATH and the menus.
- **nFPM** turns each build into `.deb`, `.rpm`, and `.pkg.tar.zst` from a templated
  `nfpm.yaml`.
- Recipes that link hamlib (WSJT-X, JS8Call, fldigi, flrig, Direwolf) build against
  *our* hamlib through `depends_on`.

### 4.2 Pipeline
1. **watch-upstream** (scheduled): resolve the newest matching upstream tag. If it's newer,
   open a PR bumping `version`. Never scrape HTML for versions.
2. **build-matrix**: {debian-13, ubuntu-24.04, fedora-N, fedora-N-1, el10, arch} ×
   {amd64, arm64}, run in the matching container, in topological `depends_on` order.
3. **smoke tests**: install the packages into a fresh container and run checks: library
   resolution (`ldd` shows no "not found"), `--version`, and app-specific tests
   (e.g. `rigctl -m 1 f`).
4. **publish → `testing`**: sign, index, and upload static repos to Cloudflare R2:
   - deb: `apt-ftparchive`/aptly, signed `InRelease`, per-arch `binary-amd64`/`binary-arm64`.
   - rpm: `rpm --addsign` on each package plus `createrepo_c`, signed `repomd.xml`
     (`repo_gpgcheck=1`).
   - pacman: signed packages plus `repo-add --sign`.
5. **release set**: cutting `release-sets/emcomm-YYYY.MM.yaml` pins every package version
   and toolset composition. CI builds offline bundles (§7.2), runs an offline QEMU install
   test for each tier-1 target, then promotes the set to **`stable`**.

Channels: `stable` (release sets only; the fleet default) and `testing` (every merged build).

### 4.3 Signing keys
- A dedicated **project key** (not a personal identity), using the same layout as the
  `gpg/` tooling: an Ed25519 certify-only primary kept offline, with an Ed25519 signing
  subkey and 3-year expiry.
- Only the signing subkey goes into a GitHub Actions secret (loopback pinentry in CI).
- The primary key backup and revocation certificate live in encrypted offline storage,
  never in the repo.
- Clients pin the key with deb822 `Signed-By:` / `gpgkey=`.
- The field server never holds a signing key: it serves pre-signed static trees as
  untrusted transport.

### 4.4 Containers
Multi-arch images for headless services (rigctld, Direwolf, Pat, gpsd, modems) are built in
the same pipeline and pushed to `ghcr.io`, tagged by release set.

## 5. Station (laptop) — emcommOS

### 5.1 Repository layout
```
emcommOS/
  recipes/<app>/{recipe.yaml,build.sh,nfpm.yaml.j2,tests/}
  release-sets/emcomm-YYYY.MM.yaml
  radios/<vendor>-<model>.yaml      # radio definitions (schema-validated)
  ansible/                          # collection emcomm.station
  cli/                              # python: emcomm CLI + emcomm-tui
  quadlets/                         # Podman quadlet units per service
  schemas/                          # JSON Schemas: recipe, radio, station, operator, release-set
  .github/workflows/
  bootstrap.sh
```

### 5.2 Toolsets (meta-packages)
| Toolset | Contents |
|---|---|
| `emcomm-core` | hamlib/rigctld, flrig, gpsd, chrony config, emcomm-cli |
| `emcomm-digital` | WSJT-X, JS8Call, fldigi, flmsg, flamp |
| `emcomm-winlink` | Pat, Direwolf, ARDOP |
| `emcomm-aprs` | Direwolf APRS configs, Xastir |
| `emcomm-modems` (opt-in) | modem73, Mercury (engine) |
| `emcomm-logging` | ADIF tooling + a logging app (chosen during M2) |
| `emcomm-maps` | mbtileserver + base tiles + a map viewer (chosen during M2) |
| `emcomm-sdr` (later) | SDR++, rtl-sdr tools |
| `emcomm-wine` (later) | Wine prefix for VARA / Winlink Express |

**`emcomm-standard`** = core + digital + winlink + aprs + logging + maps. This is the
opinionated default. The installer and TUI also offer **Custom** selection.

### 5.3 Bootstrap & Ansible
`bootstrap.sh` (from `curl | sh`, USB, the field-server URL, or first boot after an
unattended install):
1. Detect the distro from `/etc/os-release`. Add the emcomm repo and key (internet, a
   discovered field server, or a USB path). Enable EPEL/CRB on EL.
2. Install `emcomm-cli` and `ansible-core`.
3. Run `emcomm bootstrap [--profile standard|custom] [--source auto|online|field|usb]`, which
   runs the `emcomm.station` collection locally (the same playbooks the managed fleet gets
   by push).

Roles:
- `base`: repos, chrony, firewall, user groups (`dialout`/`uucp`, `audio`, `plugdev`, `lock`).
- `radio_hw`: udev rules **generated from radio definitions**; stable `/dev/emcomm/*`
  links; ALSA card names `EMCOMM_AUDIO*`; ModemManager ignore rules; PipeWire defaults.
- `toolsets`: install the selected meta-packages.
- `services`: Podman plus quadlets, each disabled until a mode enables it.
- `sync`: Syncthing user service and emcomm folders.
- `desktop`: menu category, launchers, docs shortcut.

### 5.4 Radio definitions, stations, operators
- **Radio definition** (`radios/*.yaml`, written by us): vendor/model, hamlib model number,
  baud, PTT method, hamlib `set-conf` options, mixer presets *as data*, USB match keys
  (VID/PID/serial/interface), and operator notes (radio menu settings to apply by hand).
- **Station kit** (`/etc/emcomm/stations/<kit>.toml`, shared per machine): radio definition
  reference + interface (Digirig, SignaLink, built-in USB codec, AIOC…) + device serials +
  modem defaults.
- **Operator profile** (`~/.config/emcomm/operators/<call>.toml`, per user): callsign, name,
  grid (or "from GPS"), preferences. Secrets (Winlink password, APRS-IS passcode) are typed
  in locally and stored in the OS keyring (Secret Service), or in a 0600 file on headless
  systems. They are never synced or committed.
- **Active selection is per user.** `emcomm use <operator> --station <kit>` validates against
  the schemas, renders **only the keys we manage** (call, grid, rig, CAT/PTT endpoint, audio
  devices) into WSJT-X.ini, JS8Call.ini, fldigi_def.xml, Pat config.json, direwolf.conf, and
  rigctld args, shows a diff, backs up the previous files, and restarts affected services.
  The operator's other settings are preserved.

### 5.5 rigctld hub & modes
- One rigctld per active station serves `127.0.0.1:4532`. Every app uses it, so changing
  radios changes one thing. VOX-only interfaces use hamlib's dummy rig for PTT.
- **Modes** are exclusive quadlet sets: e.g. `ft8-js8`, `winlink-ardop`, `winlink-mercury`,
  `winlink-packet`, `aprs-digi`, `aprs-igate`, `packet-bbs`. `emcomm mode <name>` stops the
  current set and starts the new one, with readiness checks.

### 5.6 CLI & TUI
- `emcomm` (Python): `bootstrap`, `use`, `operator`, `station`, `mode`, `toolset add|remove`,
  `source auto|online|field|usb`, `update`, `rollback`, `doctor`, `status`.
- `emcomm-tui` (Textual): setup wizard · operator/station · mode · toolsets · settings ·
  diagnostics (CAT test, PTT test, audio level meter, GPS fix) · status/sync · source.

### 5.7 Source selection
- Avahi browses for `_emcomm-repo._tcp` / `_emcomm-registry._tcp`.
- A NetworkManager dispatcher hook (plus `emcomm source auto`) points package sources and
  the Podman `registries.conf` mirror at the field server when one is found, and otherwise
  uses the internet. `emcomm source` gives a manual override.
- Packages and signatures are identical on every source.

### 5.8 Updates, rollback & reliability
- `emcomm update` is manual. A systemd timer only notifies; nothing auto-updates during a
  deployment.
- Before an update, take a snapshot: Btrfs or LVM where available, otherwise a backup of
  `/opt/emcomm` plus managed configs. A failed update rolls back automatically.
- The last two release sets remain installable, so `emcomm rollback` works offline.
- `emcomm doctor` checks groups, ModemManager, udev links, rigctld response, audio devices,
  time sync quality, repo key validity/expiry, and disk space, and prints a fix for each
  failure.
- A missing radio or server degrades gracefully: warnings, never blocking.

## 6. Sync
Syncthing mesh: laptops ↔ field server ↔ home node (e.g. a VM at home base). It works over a
disconnected LAN and catches up when links return. One folder per data type, each with its
own sharing:
- `messages` — Pat/Winlink outboxes, ICS-213/214 forms, flmsg files
- `logs` — ADIF and net logs
- `inventory` — host facts, installed release set, last provisioning result
- `server-state` — field-server data to/from home

Secrets and keyring data are always excluded.

## 7. Field server — emcommOS-field

### 7.1 Platform
Debian 13 on a Pi 5 (arm64) or ZimaBoard (amd64) with a 256 GB+ SSD. Installed with the same
bootstrap plus the `emcomm.field` collection, which reuses station roles and images.

### 7.2 Offline bundles
- For each release set and each tier-1 target, CI performs a download-only install of the
  base system plus every toolset in a clean container. It merges those packages with ours
  into one **`emcomm-offline`** repo per target, signs it with the project key, and
  publishes it to R2 with a manifest.
- The server `rclone`s the bundles it is configured for and serves them statically with
  **Caddy**. The same bundles can be written to a **USB drive** for sites with no server.
- New bundles download automatically but are only offered to laptops after operator
  approval.
- Arch (tier 2): a `pacoloco` caching proxy.

### 7.3 Network services
- dnsmasq: DHCP, DNS, or proxy-DHCP alongside an existing router; TFTP for iPXE.
- Optional hostapd access point.
- Avahi service advertisements.
- chrony disciplined by GPS/PPS, serving the LAN.
- zot registry as a pull-through ghcr.io cache, preloaded with release-set images.

### 7.4 Installers
iPXE menu and USB installer for Debian 13 (preseed), Ubuntu 24.04 (autoinstall), Fedora and
EL10 (kickstart), all pointed at the local bundle. First boot runs
`emcomm bootstrap --source field`.

### 7.5 Optional shared services (quadlets)
- Pat gateway and Mercury/modem73 hub (same images as laptops).
- mbtileserver for map tiles; Kiwix and an offline document library.
- Offline FCC callsign, solar flux, and RMS lookup datasets.
- Matrix homeserver (Conduwuit/Tuwunel) and ntfy for LAN chat and alerts.

## 8. emcommOS Linux (distro) — future project
Goal: a ready-to-install emcommOS image so new laptops skip the "install a distro, then
bootstrap" step. Principle: the image is **built by running the emcommOS bootstrap**, so the
distro and a bootstrapped laptop never diverge. Open questions for its own brainstorm:
- Base distro(s)
- Image tooling (mkosi, debos, live-build, Kiwi)
- Live vs. installed media
- Atomic/immutable vs. traditional updates
- Branding
- Whether the field server serves the images

## 9. Testing strategy
| Layer | Approach |
|---|---|
| Recipes | Smoke tests per target × arch in fresh containers |
| Ansible | Molecule with the Podman driver across tier-1 distros + Arch |
| CLI/TUI | pytest for renderers against real sample configs; Textual snapshot tests |
| Schemas | Every radio/station/operator/recipe/release-set file validated in CI |
| Release set | Offline QEMU install from the bundle with networking disabled, per tier-1 target |
| Hardware (later) | Self-hosted runner with a dummy rig + loopback audio, then a real radio |

## 10. Milestones
1. **M1 — core station**: recipes for hamlib, flrig, WSJT-X, JS8Call, fldigi/flmsg/flamp,
   Direwolf, Pat; Debian 13 + Fedora × amd64/arm64; roles base, radio_hw, toolsets, services;
   CLI operator/station profiles and config rendering; `testing` repo on R2.
2. **M2**: TUI, modes, doctor; Ubuntu 24.04 + EL10; logging/maps/aprs/modems toolsets;
   Syncthing.
3. **M3**: release sets, `stable` channel, offline bundles, USB sneakernet.
4. **F1** (field): bundle mirror, zot, Avahi, dnsmasq/iPXE installers.
   **F2**: shared services and home node.
5. **D1** (distro): brainstorm and spec for emcommOS Linux.
6. **Later**: Arch tier-2 packages, Ubuntu 26.04, wine/VARA, SDR, hardware-in-the-loop CI.

### M1 acceptance
- CI builds hamlib into `.deb` and `.rpm` for Debian 13 and Fedora on amd64 and arm64, and
  publishes signed `testing` repos.
- A fresh Debian 13 or Fedora container can add the repo, install `emcomm-core`, and run
  `rigctl -m 1 f` successfully.
- `emcomm use <op> --station <kit>` renders a WSJT-X.ini with the correct callsign, grid,
  and rig/CAT keys and leaves unmanaged keys untouched.
