#!/usr/bin/env bash
set -euo pipefail
venv=$PREFIX/lib/emcomm-cli
rm -rf "$venv"
python3 -m venv "$venv"
"$venv/bin/pip" install --quiet --no-cache-dir "$SRC/cli"
share=$DESTDIR$PREFIX/share/emcomm
mkdir -p "$DESTDIR$PREFIX/lib" "$DESTDIR$PREFIX/bin" "$share"
cp -a "$venv" "$DESTDIR$PREFIX/lib/"
ln -s ../lib/emcomm-cli/bin/emcomm "$DESTDIR$PREFIX/bin/emcomm"
cp -a "$SRC/radios" "$share/radios"
# Ship only our own collection: local dev trees also hold git-ignored third-party collections.
mkdir -p "$share/ansible/ansible_collections"
cp -aL "$SRC/ansible/ansible_collections/emcomm" "$share/ansible/ansible_collections/emcomm"
find "$share/ansible" -type d \( -name molecule -o -name __pycache__ \) -prune -exec rm -rf {} +
install -m 0644 "$SRC/bootstrap.sh" "$share/bootstrap.sh"
