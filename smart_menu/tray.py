"""Ícono en la bandeja del sistema con ``QSystemTrayIcon``.

Como antes, **tanto el clic izquierdo como el derecho** abren el panel (no hay menú nativo).
Qt re-crea el ícono automáticamente cuando el shell de Windows se reinicia, así que el ícono
aparece de forma fiable también al iniciar sesión.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

# Razones de activación que abren el panel (cualquier clic sobre el ícono).
_OPEN_REASONS = (
    QSystemTrayIcon.Trigger,       # clic izquierdo
    QSystemTrayIcon.Context,       # clic derecho (sin menú asignado)
    QSystemTrayIcon.DoubleClick,
    QSystemTrayIcon.MiddleClick,
)


class Tray:
    def __init__(
        self,
        icons: Dict[str, QIcon],
        initial: str,
        tip: str,
        on_activate: Callable[[], None],
    ) -> None:
        self._icons = icons
        self._on_activate = on_activate
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(icons.get(initial, QIcon()))
        self._tray.setToolTip(tip)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in _OPEN_REASONS:
            self._on_activate()

    def update(self, key: Optional[str] = None, tip: Optional[str] = None) -> None:
        if key is not None and key in self._icons:
            self._tray.setIcon(self._icons[key])
        if tip is not None:
            self._tray.setToolTip(tip)

    def hide(self) -> None:
        self._tray.hide()
