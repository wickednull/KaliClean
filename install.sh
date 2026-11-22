#!/usr/bin/env bash
# Lightweight system install (alternative to the .deb package).
# Usage: sudo ./install.sh
set -euo pipefail
umask 022

if [ "$(id -u)" -ne 0 ]; then
    echo "This installer needs root privileges: sudo ./install.sh" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="kaliclean"

install -d "/usr/share/$NAME/assets"
install -m 755 "$ROOT/kaliclean.py" "/usr/share/$NAME/kaliclean.py"
install -m 644 "$ROOT/backend.py" "/usr/share/$NAME/backend.py"
cp -R "$ROOT/web" "/usr/share/$NAME/web"
install -m 644 "$ROOT/assets/kaliclean.svg" "$ROOT/assets/kaliclean.png" \
    "/usr/share/$NAME/assets/"

install -D -m 755 "$ROOT/packaging/kaliclean.launcher" "/usr/bin/kaliclean"
install -D -m 644 "$ROOT/packaging/com.github.wickednull.KaliClean.desktop" \
    "/usr/share/applications/com.github.wickednull.KaliClean.desktop"
install -D -m 644 "$ROOT/packaging/com.github.wickednull.KaliClean.metainfo.xml" \
    "/usr/share/metainfo/com.github.wickednull.KaliClean.metainfo.xml"
for size in 16x16 22x22 24x24 32x32 48x48 64x64 96x96 128x128 256x256 512x512; do
    install -D -m 644 "$ROOT/assets/icons/$size/apps/kaliclean.png" \
        "/usr/share/icons/hicolor/$size/apps/kaliclean.png"
done
install -D -m 644 "$ROOT/assets/kaliclean.svg" \
    "/usr/share/icons/hicolor/scalable/apps/kaliclean.svg"

install -D -m 644 "$ROOT/README.md" "/usr/share/doc/kaliclean/README.md"
install -D -m 644 "$ROOT/LICENSE" "/usr/share/doc/kaliclean/copyright"
install -D -m 644 "$ROOT/packaging/kaliclean.1" "/usr/share/man/man1/kaliclean.1"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
fi

echo "KaliClean installed. Launch it from the applications menu or with: kaliclean"
