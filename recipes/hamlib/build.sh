#!/usr/bin/env bash
set -euo pipefail
./configure --prefix="$PREFIX" --libdir="$PREFIX/lib" --disable-static \
  --with-libusb --without-cxx-binding --disable-winradio
make -j"$JOBS"
make install DESTDIR="$DESTDIR"
