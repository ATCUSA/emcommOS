#!/usr/bin/env bash
set -euo pipefail
rigctl=$(command -v /opt/emcomm/bin/rigctl || command -v rigctl)
[[ $("$rigctl" -m 1 f) == 145000000 ]]
models=$("$rigctl" -l | awk 'NR > 1 {print $1}')
for f in /opt/emcomm/share/emcomm/radios/*.yaml; do
  m=$(awk '/^hamlib_model:/ {print $2}' "$f")
  grep -qx "$m" <<<"$models" || { echo "$f: hamlib model $m not in rigctl -l"; exit 1; }
done
