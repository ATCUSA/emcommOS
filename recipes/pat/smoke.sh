#!/usr/bin/env bash
set -euo pipefail
out=$(pat version 2>&1)
grep -qi pat <<<"$out"
