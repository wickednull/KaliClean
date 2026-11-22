#!/usr/bin/env bash
# Build a Debian/Kali .deb package for KaliClean.
# Usage: ./packaging/build_deb.sh [version]   (default: 1.0.0)
set -euo pipefail
umask 022

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
VERSION="${1:-1.0.0}"
NAME="kaliclean"
PKG="${NAME}_${VERSION}_all"
BUILD="$(mktemp -d "${TMPDIR:-/tmp}/${NAME}-deb.XXXXXX")"
trap 'rm -rf "$BUILD"' EXIT
DEST="$ROOT/dist"

if [[ ! "$VERSION" =~ ^[0-9]+(\.[0-9]+)*([-+][A-Za-z0-9.]+)?$ ]]; then
    echo "Invalid version: $VERSION" >&2
    exit 2
fi

mkdir -p "$DEST"
APP="$BUILD/$PKG"
mkdir -p "$APP/DEBIAN"

# Application code and resources are architecture-independent.
mkdir -p "$APP/usr/share/$NAME/assets"
install -m 755 "$ROOT/kaliclean.py" "$APP/usr/share/$NAME/kaliclean.py"
install -m 644 "$ROOT/backend.py" "$APP/usr/share/$NAME/backend.py"
cp -R "$ROOT/web" "$APP/usr/share/$NAME/web"
install -m 644 "$ROOT/assets/kaliclean.svg" "$ROOT/assets/kaliclean.png" \
    "$APP/usr/share/$NAME/assets/"

# Launcher, desktop entry and icon theme.
install -D -m 755 "$HERE/kaliclean.launcher" "$APP/usr/bin/kaliclean"
install -D -m 644 "$HERE/com.github.wickednull.KaliClean.desktop" \
    "$APP/usr/share/applications/com.github.wickednull.KaliClean.desktop"
install -D -m 644 "$HERE/com.github.wickednull.KaliClean.metainfo.xml" \
    "$APP/usr/share/metainfo/com.github.wickednull.KaliClean.metainfo.xml"
for size in 16x16 22x22 24x24 32x32 48x48 64x64 96x96 128x128 256x256 512x512; do
    install -D -m 644 "$ROOT/assets/icons/$size/apps/kaliclean.png" \
        "$APP/usr/share/icons/hicolor/$size/apps/kaliclean.png"
done
install -D -m 644 "$ROOT/assets/kaliclean.svg" \
    "$APP/usr/share/icons/hicolor/scalable/apps/kaliclean.svg"

# Documentation and man page.
install -D -m 644 "$ROOT/README.md" "$APP/usr/share/doc/kaliclean/README.md"
install -D -m 644 "$ROOT/LICENSE" "$APP/usr/share/doc/kaliclean/copyright"
install -D -m 644 "$HERE/changelog" "$APP/usr/share/doc/kaliclean/changelog"
gzip -9 -n -c "$HERE/changelog" > "$APP/usr/share/doc/kaliclean/changelog.gz"
rm "$APP/usr/share/doc/kaliclean/changelog"
mkdir -p "$APP/usr/share/man/man1"
gzip -9 -n -c "$HERE/kaliclean.1" > "$APP/usr/share/man/man1/kaliclean.1.gz"

# Debian metadata. The maintainer scripts refresh menu/icon caches.
sed "s/^Version: .*/Version: $VERSION/" "$HERE/control" > "$APP/DEBIAN/control"
install -m 755 "$HERE/postinst" "$APP/DEBIAN/postinst"
install -m 755 "$HERE/postrm" "$APP/DEBIAN/postrm"

dpkg-deb --build -Zxz --root-owner-group "$APP" "$DEST/${PKG}.deb"

echo
echo "Built: $DEST/${PKG}.deb"
echo "Install with: sudo apt install ./$DEST/${PKG}.deb"
echo "Inspect with: dpkg-deb --info $DEST/${PKG}.deb"
