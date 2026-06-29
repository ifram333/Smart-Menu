"""Acceso a recursos de ``assets/`` (imágenes/íconos), compatible con la ejecución desde
fuentes y con el ejecutable de PyInstaller (``--onefile``).

Centraliza la carga del logo (a color o en gris para "inactivo"), la conversión PIL→Qt y el
recoloreado de los íconos monocromos al color del tema.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PIL import Image, ImageOps


def _assets_dir() -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "assets")
    # En fuentes: <repo>/assets, con este archivo en <repo>/src/.
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def path(name: str) -> str:
    """Ruta absoluta a un recurso de ``assets/`` (p. ej. ``"logo.png"``)."""
    return os.path.join(_assets_dir(), name)


_logo_rgba = None


def _logo_base() -> Image.Image:
    global _logo_rgba
    if _logo_rgba is None:
        _logo_rgba = Image.open(path("logo.png")).convert("RGBA")
    return _logo_rgba


def logo_image(active: bool, size: int) -> Image.Image:
    """Logo a color (activo) o en gris translúcido (inactivo)."""
    img = _logo_base().resize((size, size), Image.LANCZOS)
    if active:
        return img
    r, g, b, a = img.split()
    gray = ImageOps.grayscale(Image.merge("RGB", (r, g, b)))
    a = a.point(lambda v: int(v * 0.75))  # un poco translúcido = "apagado"
    return Image.merge("RGBA", (gray, gray, gray, a))


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())  # copy: posee su memoria tras liberar 'data'


def logo_icon(active: bool, size: int = 64) -> QIcon:
    return QIcon(pil_to_qpixmap(logo_image(active, size)))


def tinted_icon(name: str, size: int, color: str) -> QIcon:
    """Carga un PNG (forma opaca sobre fondo transparente) y lo recolorea a ``color``."""
    src = QPixmap(path(name))
    if src.isNull():
        return QIcon()
    src = src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(src.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, src)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), QColor(color))
    painter.end()
    return QIcon(out)


def export_ico() -> None:
    """Genera ``assets/icon.ico`` a partir de ``logo.png`` (lo usa build.ps1)."""
    out = path("icon.ico")
    _logo_base().resize((256, 256), Image.LANCZOS).save(
        out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print(f"{out} generado")
