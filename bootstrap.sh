#!/bin/sh
# emcommOS bootstrap: shows what it will change, asks first, trusts the emcommOS signing key
# (pinned below), adds the package repository, installs the emcomm CLI, then sets the machine
# up with Ansible. Everything can be undone with --uninstall.
#
#   curl -fsSL "$EMCOMM_REPO_URL/bootstrap.sh" | sudo EMCOMM_REPO_URL="$EMCOMM_REPO_URL" sh
#   sudo sh bootstrap.sh --repo-url URL [--channel testing] [--toolsets standard]
#                        [--no-provision] [--yes] [--uninstall]
set -eu

EMCOMM_KEY_FINGERPRINT="7F78527F54EA22280FD664748AA729513E77A41A"
REPO_URL=${EMCOMM_REPO_URL:-}
CHANNEL=${EMCOMM_CHANNEL:-testing}
TOOLSETS=${EMCOMM_TOOLSETS:-standard}
PROVISION=1
YES=0
UNINSTALL=0

die() { echo "bootstrap: $*" >&2; exit 1; }

confirm() {
  [ "$YES" -eq 1 ] && return 0
  ( : < /dev/tty ) 2>/dev/null || die "no terminal to confirm on; re-run with --yes"
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
