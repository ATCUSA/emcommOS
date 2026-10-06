#!/usr/bin/env bash
set -euo pipefail
test -x /opt/emcomm/bin/wfview
test -f /opt/emcomm/share/wfview/rigs/IC-7300MK2.rig
grep -q '^CIVAddress=182' /opt/emcomm/share/wfview/rigs/IC-7300MK2.rig
# Starts without a display (proves all shared libraries and plugins resolve).
export QT_QPA_PLATFORM=offscreen
out=$(timeout 60 /opt/emcomm/bin/wfview --version 2>&1)
grep -q '^wfview version: ' <<<"$out"
