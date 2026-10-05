#!/usr/bin/env bash
set -euo pipefail
autoreconf -fi
./configure --prefix="$PREFIX"
make -j"$JOBS"
make install DESTDIR="$DESTDIR"
