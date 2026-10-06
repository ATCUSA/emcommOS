#!/usr/bin/env bash
# M1 acceptance in a pristine container:
#   1. bootstrap.sh installs the CLI (pinned key), and emcomm bootstrap applies the playbook;
#   2. the rigctld hub answers through emcomm-run (distro or emcomm-built rigctld);
#   3. emcomm use renders WSJT-X.ini managed keys and keeps the user's own;
#   4. uninstall removes every emcomm package, repo file, pin, unit and /etc/emcomm.
# Usage: repo-install.sh <target> <repo-url> [channel]
#   target: debian-13 | fedora-44 | fedora-43;  repo-url: https://
set -euo pipefail
if [ $# -lt 2 ]; then
  echo "usage: $0 <debian-13|fedora-44|fedora-43> <repo-url> [channel]" >&2
  exit 2
fi
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
    leftovers() { dpkg-query -W -f="\${db:Status-Abbrev}\${Package}\n" "emcomm-*" 2>/dev/null | grep -E "^(ii|hi|rc)" || true; }
  else
    dnf -y -q install curl >/dev/null 2>&1 || true
    leftovers() { rpm -qa "emcomm-*"; }
  fi
  # Fail (even under `set -e`, which ignores `!`) when any of the given globs still matches.
  absent() {
    for g in "$@"; do
      if compgen -G "$g" >/dev/null; then echo "FAIL: still present: $g" >&2; exit 1; fi
    done
  }

  export PATH=/opt/emcomm/bin:$PATH
  sh /emcomm/bootstrap.sh --repo-url "$URL" --channel "$CHANNEL" --no-provision --yes
  /usr/bin/emcomm --help >/dev/null   # the sudo-visible symlink from emcomm-cli
  emcomm bootstrap --repo-url "$URL" --channel "$CHANNEL" --toolsets core --yes \
    --set emcomm_chrony_enable=false

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
  absent "/etc/apt/sources.list.d/emcomm*" "/etc/apt/preferences.d/emcomm*" "/etc/yum.repos.d/emcomm*"
  test ! -e /etc/emcomm
  absent "/usr/share/keyrings/emcomm-archive-keyring.asc" "/etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm"
  test ! -e /usr/bin/emcomm && test ! -L /usr/bin/emcomm
  test ! -e /opt/emcomm
  absent "/etc/systemd/user/emcomm-*"
  grep -qx "Font=Keep Me" ~/.config/WSJT-X.ini   # user files untouched by uninstall
  echo "M1 acceptance OK"
'
