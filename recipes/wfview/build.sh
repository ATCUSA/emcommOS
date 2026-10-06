#!/usr/bin/env bash
# qmake build. PREFIX is compiled in (rig files load from $PREFIX/share/wfview/rigs),
# so it must be the runtime prefix; INSTALL_ROOT stages into DESTDIR.
set -euo pipefail
QMAKE=$(command -v qmake6 || command -v qmake-qt6 || echo /usr/lib64/qt6/bin/qmake)
# Qt >= 6.9 QMultiMap::remove(key, value) compares through a const reference; upstream's
# queueItem::operator== is not const (fails to compile on Fedora 44). Idempotent.
sed -i 's/bool operator==(const queueItem& lhs)$/& const/' include/cachingqueue.h
grep -q 'operator==(const queueItem& lhs) const' include/cachingqueue.h || {
  echo "wfview const patch did not apply" >&2; exit 1; }
# wfview's rigctld-compatible server binds all interfaces without authentication; the emcomm hub
# is the only client, so bind loopback only. (Other servers and the Icom LAN link are untouched.)
sed -i 's/listen(QHostAddress::Any, port)/listen(QHostAddress::LocalHost, port)/' src/rigctld.cpp
grep -q 'listen(QHostAddress::LocalHost, port)' src/rigctld.cpp || {
  echo "wfview rigctld bind patch did not apply" >&2; exit 1; }
mkdir -p build
cd build
"$QMAKE" ../wfview.pro PREFIX="$PREFIX" VERSION="$VERSION" CONFIG+=release
# wfview.pro probes only a few qcustomplot Qt6 library names; add the distro's if it missed.
if ! grep -q -- '-lqcustomplot\|-lQCustomPlot' Makefile; then
  for name in qcustomplot-qt6 qcustomplot2.1-qt6 qcustomplotqt6 qcustomplot2qt6 QCustomPlotQt6; do
    if ldconfig -p | grep -q "lib${name}\.so "; then
      sed -i "s/^LIBS .*/& -l${name}/" Makefile
      break
    fi
  done
fi
make -j"$JOBS"
make install INSTALL_ROOT="$DESTDIR"
