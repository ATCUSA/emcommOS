#!/usr/bin/env bash
set -euo pipefail
autoreconf -fi
./configure --prefix="$PREFIX" --with-hamlib --with-pulseaudio
make -j"$JOBS"
make install DESTDIR="$DESTDIR"
