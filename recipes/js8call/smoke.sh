#!/usr/bin/env bash
set -euo pipefail
test -x /opt/emcomm/lib/js8call/AppRun
test -x /opt/emcomm/bin/js8call
grep -q '^Exec=js8call' /opt/emcomm/share/applications/js8call.desktop
out=$(QT_QPA_PLATFORM=offscreen /opt/emcomm/bin/js8call --version 2>&1)
grep -q 'JS8Call' <<<"$out" || { echo "js8call --version failed: $out" >&2; exit 1; }
