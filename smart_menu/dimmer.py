"""Atenuación (dimming) por monitor combinando dos mecanismos:

1. **Superposición** Qt translúcida negra (un ``QWidget`` sin borde, *topmost*, *click-through*
   y sin foco): oscurece el monitor sin estorbar, con niveles profundos en apps normales.
2. **Rampa de gamma** del adaptador (ver :mod:`gamma`): oscurece también lo que la
   superposición no puede cubrir (video/juegos a **pantalla completa**, incluida la exclusiva).

Para un mismo nivel, el oscurecimiento se reparte entre ambos de modo que las apps *normales*
mantienen el brillo de siempre (superposición × gamma) y las de pantalla completa quedan
atenuadas por la gamma (hasta ``GAMMA_FLOOR``). La superposición pierde el frente cuando otra
ventana topmost/fullscreen pasa delante, así que :meth:`Dimmer.reassert` debe llamarse
periódicamente (también reafirma la gamma, que algunos juegos reescriben).

Se identifica cada monitor por su **nombre de dispositivo** (``\\\\.\\DISPLAY1``, el que usa la
gamma); el ``QScreen`` asociado da la geometría de la superposición.
"""

from __future__ import annotations

from typing import Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QScreen
from PySide6.QtWidgets import QWidget

from . import gamma
from . import winutil

# Tope de opacidad de la superposición: el 100% del control = 85% de oscuridad (nunca negro
# total, para no perder de vista la bandeja).
MAX_ALPHA = 0.85

# Brillo mínimo al que puede bajar la gamma (en el nivel 100%). Se mantiene relativamente alto:
# suficiente para que Windows acepte la rampa y no "lave" el color, y es el dim que verán las
# apps a pantalla completa (las normales se oscurecen además con la capa).
GAMMA_FLOOR = 0.5


def _split_levels(level: int) -> Tuple[float, float]:
    """Reparte un nivel (1-100) en (alpha de la superposición, brillo de gamma 0..1).

    Resultado en apps normales: ``gamma * (1 - alpha) == 1 - MAX_ALPHA*level/100`` (idéntico al
    comportamiento clásico). En pantalla completa (solo gamma): brillo == ``gamma``.
    """
    target_brightness = 1.0 - MAX_ALPHA * level / 100.0
    gamma_brightness = 1.0 - (level / 100.0) * (1.0 - GAMMA_FLOOR)
    overlay_alpha = 1.0 - target_brightness / gamma_brightness
    return max(0.0, min(MAX_ALPHA, overlay_alpha)), gamma_brightness


class _Overlay(QWidget):
    """Ventana negra translúcida que cubre un monitor (sin foco ni captura del ratón)."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        # Fondo negro sólido; la translucidez se logra con setWindowOpacity.
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.setPalette(palette)


class Dimmer:
    def __init__(self) -> None:
        self._overlays: Dict[str, _Overlay] = {}
        self._levels: Dict[str, int] = {}
        self._devices: Dict[str, str] = {}   # clave -> nombre de dispositivo ("" si no se pudo)
        self._gamma = gamma.GammaDimmer()

    def level(self, key: str) -> int:
        return self._levels.get(key, 0)

    def set(self, screen: QScreen, device: str, level: int) -> None:
        """Atenúa ``screen`` (geometría de la capa) usando ``device`` para la gamma.

        ``device`` es el nombre del dispositivo (``\\\\.\\DISPLAY1``) o "" si no se resolvió.
        La clave del monitor es ``device`` (o el nombre del ``QScreen`` como respaldo).
        """
        level = max(0, min(100, int(level)))
        key = device or screen.name()
        self._levels[key] = level
        self._devices[key] = device
        overlay = self._overlays.get(key)

        if level <= 0:
            if overlay is not None:
                overlay.hide()
            if device:
                self._gamma.restore(device)
            return

        overlay_alpha, gamma_brightness = _split_levels(level)

        if overlay is None:
            overlay = _Overlay()
            self._overlays[key] = overlay

        overlay.setGeometry(screen.geometry())
        overlay.setWindowOpacity(overlay_alpha)
        overlay.show()
        hwnd = int(overlay.winId())
        winutil.make_click_through(hwnd)
        winutil.assert_topmost(hwnd)

        if device:
            self._gamma.apply(device, gamma_brightness)

    def reassert(self) -> None:
        """Reafirma superposición (z-order) y gamma de los monitores atenuados (~1 vez/s)."""
        for key, level in list(self._levels.items()):
            if level <= 0:
                continue
            overlay = self._overlays.get(key)
            if overlay is not None and overlay.isVisible():
                winutil.assert_topmost(int(overlay.winId()))
            device = self._devices.get(key, "")
            if device:
                _, gamma_brightness = _split_levels(level)
                self._gamma.apply(device, gamma_brightness)

    def clear_all(self) -> None:
        for overlay in self._overlays.values():
            overlay.hide()
            overlay.deleteLater()
        self._overlays.clear()
        self._levels.clear()
        self._devices.clear()
        self._gamma.restore_all()
