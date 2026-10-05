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
