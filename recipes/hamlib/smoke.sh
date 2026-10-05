#!/usr/bin/env bash
# Dummy rig directly, then through the rigctld hub exactly as emcomm apps use it.
set -euo pipefail
[[ $(/opt/emcomm/bin/rigctl -m 1 f) == 145000000 ]]
/opt/emcomm/bin/rigctld --version | grep -q 'Hamlib 4\.7'
/opt/emcomm/bin/rigctld -m 1 -T 127.0.0.1 -t 4532 &
pid=$!
trap 'kill $pid' EXIT
for _ in $(seq 40); do
  rigctl -m 2 -r 127.0.0.1:4532 f >/dev/null 2>&1 && break
  sleep 0.25
done
[[ $(rigctl -m 2 -r 127.0.0.1:4532 f) == 145000000 ]]
