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
case $CHANNEL in ''|.|..|*[!a-z0-9._-]*) die "invalid channel '$CHANNEL' (allowed: a-z 0-9 . _ -)" ;; esac
case $REPO_URL in *[!A-Za-z0-9._~:/%@+-]*) die "repository URL contains unsupported characters" ;; esac

[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"
[ -r /etc/os-release ] || die "cannot read /etc/os-release; nothing was changed"
# shellcheck source=/dev/null
. /etc/os-release
ID=${ID:-}; VERSION_ID=${VERSION_ID:-}

# Install: only the distributions M1 supports (Debian 13+, Fedora), decided before any change.
require_supported() {
  ok=0
  case $ID in
    debian)
      major=${VERSION_ID%%.*}
      case $major in ''|*[!0-9]*) ;; *) [ "$major" -ge 13 ] && ok=1 ;; esac ;;
    fedora) ok=1 ;;
  esac
  [ "$ok" -eq 1 ] ||
    die "unsupported distribution '${ID:-unknown}${VERSION_ID:+ $VERSION_ID}'; M1 supports Debian 13+ and Fedora; nothing was changed"
  FAMILY=$ID
}

# Uninstall: work wherever our files can exist (derivatives included), by package tooling.
uninstall_family() {
  case " ${ID_LIKE:-} $ID " in
    *" debian "*) FAMILY=debian ;;
    *" fedora "*|*" rhel "*) FAMILY=fedora ;;
    *)
      if command -v dpkg-query >/dev/null 2>&1; then FAMILY=debian
      elif command -v rpm >/dev/null 2>&1 && command -v dnf >/dev/null 2>&1; then FAMILY=fedora
      else die "cannot tell how packages are managed on '${ID:-unknown}'; nothing was changed"
      fi ;;
  esac
}

in_set() { printf '%s\n' "$2" | grep -Fqx -- "$1"; }
# set_diff "A" "B": lines of A not in B.
set_diff() {
  printf '%s\n' "$1" | while IFS= read -r line; do
    [ -n "$line" ] || continue
    in_set "$line" "$2" || printf '%s\n' "$line"
  done
}
preview_fail() { die "could not preview the removal; nothing was changed${1:+ ($1)}"; }

# Refuse when the removal would take out a package the user installed themselves.
check_plan() {
  manual=$1; plan=$2
  for p in $plan; do
    case $p in emcomm-*) continue ;; esac
    if in_set "$p" "$manual"; then
      echo "bootstrap: removing emcomm would also remove '$p', which you installed yourself." >&2
      echo "  Remove '$p' first (it depends on emcomm), then re-run the uninstall." >&2
      echo "  Nothing was changed." >&2
      exit 1
    fi
  done
}

# Every package we asked to remove must be in the parsed plan (else the parse failed).
check_covers() {
  for p in $1; do in_set "$p" "$2" || preview_fail "$p missing from the plan"; done
}

uninstall() {
  LC_ALL=C; export LC_ALL
  echo "emcommOS uninstall will remove:"
  echo "  - the emcomm-* packages and any dependencies that only they needed (listed below)"
  echo "  - the emcommOS repository and signing key, and the Debian backports source and pin"
  echo "  - emcomm user units and udev rules, /opt/emcomm, and /etc/emcomm (including your station kits)"
  echo "Your files in ~/.config and app settings are kept; group memberships and chrony stay."
  pkgs=""; MODE="none"
  if [ "$FAMILY" = debian ]; then
    command -v dpkg-query >/dev/null 2>&1 || preview_fail "dpkg-query not found"
    rc=0; dq=$(dpkg-query -W -f='${db:Status-Abbrev}${Package}\n' 'emcomm-*' 2>/dev/null) || rc=$?
    [ "$rc" -le 1 ] || preview_fail "dpkg-query failed"
    pkgs=$(printf '%s\n' "$dq" | awk '/^(ii|hi|rc)/ {print substr($0, 4)}' | tr -d ' ')
    if [ -n "$pkgs" ]; then
      base_out=$(apt-get -s autoremove) || preview_fail "apt-get autoremove simulation"
      baseline=$(printf '%s\n' "$base_out" | awk '/^Remv / {print $2}' | sort -u)
      baseline=$(set_diff "$baseline" "$pkgs")  # our own packages are never "pre-existing"
      # shellcheck disable=SC2086
      plan_out=$(apt-get -s remove --purge --auto-remove $pkgs) || preview_fail "apt-get simulation"
      plan=$(printf '%s\n' "$plan_out" | awk '/^(Remv|Purg) / {print $2}' | sort -u)
      check_covers "$pkgs" "$plan"
      manual=$(apt-mark showmanual) || preview_fail "apt-mark"
      [ -n "$manual" ] || preview_fail "empty manual package list"
      # Packages already unneeded before we started are not ours to remove.
      todo=$(set_diff "$plan" "$baseline")
      check_covers "$pkgs" "$todo"
      check_plan "$manual" "$todo"
      if [ -n "$baseline" ]; then
        MODE="split"
      else
        MODE="auto"
      fi
      echo "Packages that will be removed (purged):"; echo "$todo" | sed 's/^/    /'
    fi
  else
    pkgs=$(rpm -qa --qf '%{NAME}\n' 'emcomm-*') || preview_fail rpm
    if [ -n "$pkgs" ]; then
      # shellcheck disable=SC2086
      plan_out=$(dnf remove --assumeno $pkgs 2>&1) || true
      plan=$(printf '%s\n' "$plan_out" | awk '
        /^Transaction Summary/ {insec=0}
        insec && /^ +[^ ]/ && $1 !~ /:$/ {print $1}
        /^Removing/ {insec=1}' | sort -u)
      check_covers "$pkgs" "$plan"
      manual=$(dnf -q repoquery --userinstalled --qf '%{name}\n') || preview_fail "dnf repoquery"
      [ -n "$manual" ] || preview_fail "empty user-installed package list"
      check_plan "$manual" "$plan"
      MODE="dnf"
      echo "Packages that will be removed:"; echo "$plan" | sed 's/^/    /'
    fi
  fi
  confirm "Remove emcommOS?"
  if [ "$FAMILY" = debian ]; then
    case $MODE in
      auto)
        # shellcheck disable=SC2086
        apt-get remove --purge --auto-remove -y $pkgs ;;
      split)
        # shellcheck disable=SC2086
        apt-get remove --purge -y $pkgs
        after_out=$(apt-get -s autoremove) || die "emcomm packages were already removed, but the follow-up list of unneeded dependencies failed; run apt-get autoremove yourself if wanted"
        after=$(printf '%s\n' "$after_out" | awk '/^Remv / {print $2}' | sort -u)
        new=$(set_diff "$after" "$baseline")
        extra=$(set_diff "$new" "$todo")
        mine=$(set_diff "$new" "$extra")
        if [ -n "$extra" ]; then
          echo "warning: these packages became unneeded but were not in the confirmed list;" >&2
          echo "  leaving them installed (run 'apt-get autoremove' if you want them gone):" >&2
          printf '%s\n' "$extra" | sed 's/^/    /' >&2
        fi
        # shellcheck disable=SC2086
        [ -z "$mine" ] || apt-get purge -y $mine ;;
    esac
    rm -f /etc/apt/sources.list.d/emcomm.sources /etc/apt/sources.list.d/emcomm-backports.sources \
          /etc/apt/preferences.d/emcomm-backports.pref /usr/share/keyrings/emcomm-archive-keyring.asc
    apt-get update -qq || true
  else
    if [ "$MODE" = dnf ]; then
      # shellcheck disable=SC2086
      dnf -y remove $pkgs
    fi
    rm -f /etc/yum.repos.d/emcomm-*.repo /etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm
  fi
  rm -f /etc/systemd/user/emcomm-*.service /etc/udev/rules.d/70-emcomm-*.rules
  rm -rf /etc/emcomm /opt/emcomm
  udevadm control --reload 2>/dev/null || true
  echo "emcommOS removed. Group memberships (dialout, audio) and chrony were left in place."
}

if [ "$UNINSTALL" -eq 1 ]; then
  uninstall_family
  uninstall
  exit 0
fi

require_supported
[ -n "$REPO_URL" ] || die "set EMCOMM_REPO_URL or pass --repo-url"
case $REPO_URL in https://*|file://*) ;; *) die "refusing non-HTTPS repository URL: $REPO_URL" ;; esac
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
curl -fsSL --proto '=https,file' --proto-redir '=https,file' "$REPO_URL/$CHANNEL/emcomm-archive-keyring.asc" -o "$tmp/key.asc"
keys=$(GNUPGHOME="$tmp" gpg --batch --show-keys --with-colons "$tmp/key.asc")
npub=$(printf '%s\n' "$keys" | grep -c '^pub:' || true)
[ "$npub" -eq 1 ] ||
  die "the repository key file contains $npub keys; exactly one is allowed. Refusing to trust it."
fpr=$(printf '%s\n' "$keys" | awk -F: '/^fpr/ {print $10; exit}')
[ "$fpr" = "$EMCOMM_KEY_FINGERPRINT" ] ||
  die "repository key $fpr does not match the pinned emcommOS key $EMCOMM_KEY_FINGERPRINT"
# Install only a re-export of the pinned key, never the downloaded file itself.
GNUPGHOME="$tmp" gpg --batch --import "$tmp/key.asc" 2>/dev/null
GNUPGHOME="$tmp" gpg --batch --armor --export "$EMCOMM_KEY_FINGERPRINT" > "$tmp/pinned.asc"
[ -s "$tmp/pinned.asc" ] || die "could not export the pinned key"
[ "$(GNUPGHOME="$tmp" gpg --batch --show-keys --with-colons "$tmp/pinned.asc" 2>/dev/null | grep -c '^pub:')" -eq 1 ] ||
  die "exported key file does not contain exactly one key"

if [ "$FAMILY" = debian ]; then
  install -m 0644 "$tmp/pinned.asc" /usr/share/keyrings/emcomm-archive-keyring.asc
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
  install -m 0644 "$tmp/pinned.asc" /etc/pki/rpm-gpg/RPM-GPG-KEY-emcomm
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
  if [ "$YES" -eq 1 ]; then
    exec /opt/emcomm/bin/emcomm bootstrap "$@"
  fi
  # Under curl | sh stdin is the script; confirm() already proved /dev/tty opens.
  exec /opt/emcomm/bin/emcomm bootstrap "$@" < /dev/tty
fi
echo "emcomm CLI installed; run 'sudo emcomm bootstrap' to finish setting up this machine."
