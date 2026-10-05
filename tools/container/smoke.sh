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
