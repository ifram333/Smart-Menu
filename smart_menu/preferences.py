"""Ventana de Preferencias: reasignar los hotkeys globales a gusto.

Cada acción tiene un :class:`HotkeyCapture` (un botón que, al pulsarlo, captura la siguiente
combinación de teclas). Mientras esta ventana está abierta la app desactiva los hotkeys (para
poder capturar incluso los que ya estaban asignados) y los vuelve a registrar al cerrarla.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)

from . import config

# (clave en config.hotkeys, etiqueta visible)
ACTIONS = [
    ("toggle_awake", "Mantener despierto"),
    ("show_panel", "Mostrar el panel"),
    ("clipboard", "Historial de portapapeles"),
    ("dim_up", "Subir atenuado"),
    ("dim_down", "Bajar atenuado"),
]


def _token(key: int):
    """Tecla Qt -> token compatible con hotkeys.parse (o None si no se admite)."""
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        return chr(key)  # 'A'..'Z' / '0'..'9'
    if Qt.Key_F1 <= key <= Qt.Key_F12:
        return "F" + str(key - Qt.Key_F1 + 1)
    return {
        Qt.Key_Up: "Up", Qt.Key_Down: "Down", Qt.Key_Left: "Left", Qt.Key_Right: "Right",
        Qt.Key_Space: "Space", Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter", Qt.Key_Tab: "Tab",
        Qt.Key_Delete: "Delete", Qt.Key_Insert: "Insert", Qt.Key_Home: "Home", Qt.Key_End: "End",
        Qt.Key_PageUp: "PageUp", Qt.Key_PageDown: "PageDown",
        Qt.Key_Period: ".", Qt.Key_Comma: ",", Qt.Key_Minus: "-", Qt.Key_Plus: "+",
        Qt.Key_Slash: "/", Qt.Key_Semicolon: ";", Qt.Key_BracketLeft: "[",
        Qt.Key_BracketRight: "]", Qt.Key_Backslash: "\\", Qt.Key_Apostrophe: "'",
        Qt.Key_QuoteLeft: "`",
    }.get(key)


def _combo_from_event(event):
    """Construye "Ctrl+Alt+K" desde un evento de teclado; None si falta modificador/tecla."""
    mods = event.modifiers()
    parts = []
    if mods & Qt.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.AltModifier:
        parts.append("Alt")
    if mods & Qt.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.MetaModifier:
        parts.append("Win")
    token = _token(event.key())
    if token is None or not any(p in ("Ctrl", "Alt", "Win") for p in parts):
        return None  # se exige al menos un modificador "fuerte" + una tecla válida
    parts.append(token)
    return "+".join(parts)


class HotkeyCapture(QPushButton):
    """Botón que muestra una combinación y, al pulsarlo, captura una nueva."""

    changed = Signal(str)

    def __init__(self, combo: str = "") -> None:
        super().__init__()
        self.setObjectName("hotkeycap")
        self.setCursor(Qt.PointingHandCursor)
        self._combo = combo
        self._capturing = False
        self._refresh()
        self.clicked.connect(self._start)

    def _refresh(self) -> None:
        self.setText(self._combo or "—")

    def set_combo(self, combo: str) -> None:
        self._combo = combo
        self._capturing = False
        self._refresh()

    def _start(self) -> None:
        self._capturing = True
        self.setText("Pulsa la combinación…")
        self.grabKeyboard()

    def _cancel(self) -> None:
        self.releaseKeyboard()
        self._capturing = False
        self._refresh()

    def keyPressEvent(self, event) -> None:
        if not self._capturing:
            return super().keyPressEvent(event)
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr):
            return  # esperar la tecla principal
        if key == Qt.Key_Escape:
            self._cancel()
            return
        combo = _combo_from_event(event)
        if combo is None:
            return  # combinación inválida: seguir esperando (Esc cancela)
        self.releaseKeyboard()
        self._capturing = False
        self._combo = combo
        self._refresh()
        self.changed.emit(combo)

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._cancel()
        super().focusOutEvent(event)


class PreferencesWindow(QWidget):
    def __init__(self, cfg: config.Config, on_closed) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.cfg = cfg
        self._on_closed = on_closed
        self.setWindowTitle("Preferencias — Smart Menu")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumWidth(400)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)  # margen para la sombra
        card = QFrame(objectName="card")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 130))
        shadow.setOffset(0, 6)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)
        root.addWidget(QLabel("Atajos de teclado", objectName="title"))
        info = QLabel("Haz clic en un atajo y pulsa la combinación deseada (Esc cancela).",
                      objectName="muted")
        info.setWordWrap(True)
        root.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self._captures = {}
        for i, (action, label) in enumerate(ACTIONS):
            grid.addWidget(QLabel(label), i, 0)
            cap = HotkeyCapture(cfg.hotkeys.get(action, ""))
            cap.changed.connect(lambda combo, a=action: self._set(a, combo))
            self._captures[action] = cap
            grid.addWidget(cap, i, 1)
        grid.setColumnStretch(0, 1)
        root.addLayout(grid)

        note = QLabel("Los atajos se reactivan al cerrar esta ventana.", objectName="muted")
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.reset_btn = QPushButton("Restablecer")
        self.reset_btn.setObjectName("exit")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self._reset)
        self.close_btn = QPushButton("Cerrar")
        self.close_btn.setObjectName("exit")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        buttons.addWidget(self.reset_btn, 1)
        buttons.addWidget(self.close_btn, 1)
        root.addLayout(buttons)

    def set_icons(self, reset_icon, close_icon) -> None:
        self.reset_btn.setIcon(reset_icon)
        self.close_btn.setIcon(close_icon)

    def reload(self) -> None:
        for action, cap in self._captures.items():
            cap.set_combo(self.cfg.hotkeys.get(action, ""))

    def _set(self, action: str, combo: str) -> None:
        # Evitar duplicados: si otra acción ya usa esa combinación, revertir.
        for other, existing in self.cfg.hotkeys.items():
            if other != action and existing.lower() == combo.lower():
                self._captures[action].set_combo(self.cfg.hotkeys.get(action, ""))
                return
        self.cfg.hotkeys[action] = combo
        self.cfg.save()

    def _reset(self) -> None:
        self.cfg.data["hotkeys"] = copy.deepcopy(config.DEFAULTS["hotkeys"])
        self.cfg.save()
        self.reload()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._on_closed()
        super().closeEvent(event)
