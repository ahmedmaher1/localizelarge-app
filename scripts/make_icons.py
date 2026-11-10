"""Render the Localize Large logo to PNG files and a multi-size .ico.

Run from the repository root:

    python scripts/make_icons.py

Writes ``assets/icon.svg``, ``assets/icon_<size>.png`` for each size and
``assets/icon.ico``. Uses QSvgRenderer (PyQt6) and Pillow, both already
dependencies of the app.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

LOGO_SVG = (
    '<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="48" height="48" rx="12" fill="#0F766E"/>'
    '<path d="M15 12 V33 H27" stroke="#fff" stroke-width="5" stroke-linecap="round" '
    'stroke-linejoin="round" fill="none"/>'
    '<path d="M26 27 l4.5 4.5 L38 21" stroke="#5EEAD4" stroke-width="4.5" '
    'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    "</svg>\n"
)

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(renderer: QSvgRenderer, size: int) -> Image.Image:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def main() -> int:
    assets = Path(__file__).resolve().parent.parent / "assets"
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    (assets / "icon.svg").write_text(LOGO_SVG, encoding="utf-8")
    renderer = QSvgRenderer(QByteArray(LOGO_SVG.encode("utf-8")))
    if not renderer.isValid():
        print("The logo SVG did not load.", file=sys.stderr)
        return 1
    images = {}
    for size in SIZES:
        images[size] = render(renderer, size)
        images[size].save(assets / f"icon_{size}.png")
    images[256].save(assets / "icon.ico", format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"Wrote icon.svg, {len(SIZES)} PNG files and icon.ico to {assets}")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
