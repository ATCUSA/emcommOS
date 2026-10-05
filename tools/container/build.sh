#!/usr/bin/env bash
# Runs inside the target distro container. Installs build dependencies and any
# already-built emcomm packages from /work/deps, then runs the recipe's build.sh
# so that it installs into /work/destdir/opt/emcomm.
set -euo pipefail

# Under rootless podman, container root is the invoking host user, but files owned by any
# other uid/gid (e.g. restored by `tar -x` as root from an archive made by uid 501) map to
# unmapped sub-UIDs the host user cannot delete. Normalise ownership on every exit.
normalize_ownership() {
  local p
  for p in /work/src /work/destdir /work/runtime-deps.txt; do
    if [[ -e $p ]]; then chown -R -h 0:0 "$p" 2>/dev/null || true; fi
  done
}
trap normalize_ownership EXIT

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
