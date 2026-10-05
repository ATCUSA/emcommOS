#!/usr/bin/env bash
# Extract the upstream AppImage (runs natively on this runner's arch; no FUSE needed).
set -euo pipefail
appimage=$(ls JS8Call-*.AppImage)
chmod +x "$appimage"
"./$appimage" --appimage-extract >/dev/null
lib=$DESTDIR$PREFIX/lib/js8call
mkdir -p "$DESTDIR$PREFIX/lib" "$DESTDIR$PREFIX/bin" "$DESTDIR$PREFIX/share/applications" \
  "$DESTDIR$PREFIX/share/icons/hicolor/scalable/apps"
mv squashfs-root "$lib"
cat > "$DESTDIR$PREFIX/bin/js8call" <<'EOF'
#!/bin/sh
exec /opt/emcomm/lib/js8call/AppRun "$@"
EOF
chmod 755 "$DESTDIR$PREFIX/bin/js8call"
desktop=$(find "$lib" -maxdepth 1 -name '*.desktop' | head -1)
sed -e 's|^Exec=.*|Exec=js8call|' -e 's|^Icon=.*|Icon=js8call|' "$desktop" \
  > "$DESTDIR$PREFIX/share/applications/js8call.desktop"
# JS8Call-improved ships a scalable SVG (js8call.svg is a symlink into usr/share)
svg=$(find -L "$lib" -maxdepth 1 -name '*.svg' | head -1)
if [[ -n $svg ]]; then
  cp -L "$svg" "$DESTDIR$PREFIX/share/icons/hicolor/scalable/apps/js8call.svg"
fi
