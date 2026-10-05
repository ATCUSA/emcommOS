#!/usr/bin/env bash
set -euo pipefail
test -x /opt/emcomm/lib/js8call/AppRun
test -x /opt/emcomm/bin/js8call
grep -q '^Exec=js8call' /opt/emcomm/share/applications/js8call.desktop
