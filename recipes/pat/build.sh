#!/usr/bin/env bash
set -euo pipefail
tar -xzf pat_*_linux_*.tar.gz
bin=$(find . -type f -name pat -perm -u+x | head -1)
[[ -n $bin ]] || { echo "pat binary not found in the release tarball" >&2; exit 1; }
install -D -m 0755 "$bin" "$DESTDIR$PREFIX/bin/pat"
