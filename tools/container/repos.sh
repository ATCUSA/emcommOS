#!/usr/bin/env bash
# Install the target's extra repos and apt pins written by the build tool into /work/repos.
set -euo pipefail
shopt -s nullglob
case "$FAMILY" in
  debian)
    for f in /work/repos/*.sources; do cp "$f" "/etc/apt/sources.list.d/emcomm-$(basename "$f")"; done
    for f in /work/repos/*.pref; do cp "$f" "/etc/apt/preferences.d/emcomm-$(basename "$f")"; done
    ;;
esac
