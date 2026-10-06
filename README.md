# emcommOS

Distro-agnostic provisioning for ham radio / emergency-communications laptops:
current builds of hamlib, WSJT-X, JS8Call, fldigi, Direwolf, Pat and friends from signed
deb/rpm repositories, an Ansible collection to set the station up, and an `emcomm` CLI that
wires every app to your radio from operator + station profiles.

Status: **M1 (core station)**: Debian 13 and Fedora 43/44 on amd64 and arm64; the only
channel is `testing`. Design: `docs/superpowers/specs/2026-10-05-emcommos-design.md`.
Source: https://github.com/ATCUSA/emcommOS (public). Licensed under Apache-2.0.

## Where the software comes from

For each application family, in order:

1. the **distro package** (or the official Debian backports, pinned to just the packages we
   need) when it is current enough;
2. an **upstream prebuilt binary**, pinned by sha256;
3. a **source build** in a clean container.

The decision for each family is recorded in `recipes/` and reviewed with
`emcomm-build freshness`. Everything we package installs under `/opt/emcomm`; outside it,
only `/etc/profile.d/emcomm.sh` and `/usr/lib/environment.d/50-emcomm.conf` are added.
Packages are signed with a dedicated project key whose fingerprint is pinned in `bootstrap.sh`.

rigctld comes from hamlib 4.7.2 or newer (Debian: backports; Fedora: our build) for the CVE
fixes. It listens only on `127.0.0.1:4532`, and apps reach the radio only through it.

## Install a station

The repository URL is configuration, not hardcoded: set `EMCOMM_REPO_URL` to the base URL
the maintainers publish (https:// only; no trailing slash).

```bash
curl -fsSL "$EMCOMM_REPO_URL/bootstrap.sh" | sudo EMCOMM_REPO_URL="$EMCOMM_REPO_URL" sh
```

`bootstrap.sh --no-provision` only installs the `emcomm` CLI. On Debian it does not yet add
the trixie-backports source and pin that hamlib/WSJT-X/Direwolf come from, so run
`sudo emcomm bootstrap` to finish before installing toolsets yourself (a manual
`apt install emcomm-core` needs that step first).

Then:

```bash
emcomm operator add K7ABC --grid DN16bk --name "Your Name"
sudo emcomm station add kita --radio icom-ic7300     # auto-detects the plugged-in radio
emcomm use K7ABC --station kita                       # shows a diff, then updates app configs
systemctl --user daemon-reload                        # once, so systemd sees the new user units
systemctl --user enable --now emcomm-rigctld          # CAT/PTT hub on 127.0.0.1:4532
```

`emcomm bootstrap` installs the emcomm user units in `/etc/systemd/user`; a running user
session does not see them until `systemctl --user daemon-reload` (or a fresh login).

`emcomm radios` lists supported radios. Every app talks to the radio through rigctld on
127.0.0.1:4532, so switching radios or operators is one command.

Dire Wolf (for Pat packet) has no bind-address option: its AGW port 8000 listens on all
interfaces without authentication, so block TCP 8000 in your firewall on untrusted networks.
emcomm turns Dire Wolf's KISS TCP port off (`KISSPORT 0`); Pat uses AGW on localhost:8000.

### IC-7300MK2 over LAN with wfview

wfview (installed with `emcomm-core`) can own an Icom radio reached over Ethernet; emcomm then
proxies its rigctld-compatible server so WSJT-X, JS8Call, fldigi, Direwolf and Pat keep using
127.0.0.1:4532.

```bash
sudo emcomm station add mk2 --radio icom-ic7300mk2 --control wfview --virtual-audio
emcomm use K7ABC --station mk2
systemctl --user restart pipewire pipewire-pulse wireplumber   # creates emcomm-mk2-rx / -tx
/opt/emcomm/bin/wfview     # connect to the radio's IP; audio out emcomm-mk2-rx, in Monitor of emcomm-mk2-tx
systemctl --user restart emcomm-rigctld                        # start wfview first
```

emcomm's wfview build serves rigctld on localhost only. A wfview from elsewhere (distro package,
upstream binary) binds all interfaces without a password: block TCP 4533 in your firewall on
untrusted networks. Start or restart wfview after `emcomm use`; it overwrites wfview.conf on exit.

### Your own machine (BYOD)

emcommOS never changes a machine without showing what it will do and asking first
(`--yes` for unattended runs). Standalone installs collect no data, and emcomm never writes
operator secrets such as a Winlink password or APRS-IS passcode. App configs get managed
keys only; your own settings in them are kept.

Everything can be removed again:

```bash
sudo sh bootstrap.sh --uninstall     # or: sudo emcomm uninstall
```

It lists the packages it will remove (and refuses if that would take out something you
installed yourself), then removes the emcomm packages, repository and key (on Fedora also from
the RPM database), the Debian backports source and pin, emcomm user units and udev rules,
`/opt/emcomm` and `/etc/emcomm`. Stop running services first, as each user:
`systemctl --user disable --now emcomm-rigctld emcomm-direwolf emcomm-pat`.

Kept, per user: `~/.config/emcomm`, the settings in app configs,
`~/.config/pipewire/pipewire.conf.d/60-emcomm-*.conf`, and enabled user-unit symlinks;
group memberships (`dialout`, `audio`) and chrony are left alone too.

## Develop

- Tooling: `nix develop` gives pinned uv/python/nfpm/shellcheck/actionlint/gnupg/rclone
  (optional; otherwise install them yourself). Podman comes from your distro.
- Build tooling (Python, uv): `uv run --directory tools pytest -q`; build packages with
  `uv run --directory tools emcomm-build build --target debian-13` (needs podman and nfpm;
  `nix develop` provides nfpm, and CI gets podman and the same nfpm version from the
  `.github/actions/setup-build-host` composite action).
- CLI: `uv run --directory cli pytest -q`.
- Ansible: see `ansible/requirements-dev.txt`; `molecule test` in the collection directory.
- Acceptance (needs podman, network and a published repo):
  `tests/integration/repo-install.sh <debian-13|fedora-43|fedora-44> "$EMCOMM_REPO_URL"`.
  Manual hardware checks: `docs/testing/m1-manual-checks.md`.
- Maintainers: `docs/maintainer/setup.md`.

Prior art that inspired ideas (no code reused): EmComm Tools Community, 73Linux.
