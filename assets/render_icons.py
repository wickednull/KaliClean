#!/usr/bin/env python3
"""Render kaliclean.svg into the PNG sizes used by freedesktop icon themes.

Requires PySide6 (already a KaliClean dependency). Run from anywhere:
    python3 assets/render_icons.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "kaliclean.svg"
ICON_DIR = ROOT / "icons"
SIZES = (16, 22, 24, 32, 48, 64, 96, 128, 256, 512)


def render(size: int, destination: Path) -> None:
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    svg = QSvgRenderer(str(SOURCE))
    if not svg.isValid():
        raise RuntimeError(f"Could not parse {SOURCE}")
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    svg.render(painter, QRectF(0, 0, size, size))
    painter.end()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(destination), "PNG"):
        raise RuntimeError(f"Could not write {destination}")


def main() -> None:
    app = QGuiApplication(sys.argv)  # needed for a paint device in some builds
    del app
    for size in SIZES:
        target = ICON_DIR / f"{size}x{size}" / "apps" / "kaliclean.png"
        render(size, target)
        print(f"wrote {target.relative_to(ROOT.parent)}")
    render(256, ROOT / "kaliclean.png")


if __name__ == "__main__":
    main()
