"""Widgets reutilizables con animación para el panel (PySide6).

- :class:`AnimatedSwitch`: interruptor con knob animado (señal ``clicked`` = acción del
  usuario; ``setChecked`` solo sincroniza el estado/visual sin disparar ``clicked``).
- :class:`SegmentedControl`: fila de botones exclusivos (p. ej. la duración).
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QHBoxLayout, QPushButton,
                               QWidget)

COLOR_ON = QColor("#2f6bff")
COLOR_OFF = QColor("#3a3f4b")
COLOR_KNOB = QColor("#ffffff")


def _lerp(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class AnimatedSwitch(QAbstractButton):
    def __init__(self, parent: QWidget = None, width: int = 46, height: int = 26) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._w, self._h, self._margin = width, height, 3
        self._knob = 0.0  # 0 = apagado (izq), 1 = encendido (der)
        self._on_color = COLOR_ON
        self._off_color = COLOR_OFF
        self._knob_color = COLOR_KNOB
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(self._w, self._h)

    def set_on_color(self, color: QColor) -> None:
        self._on_color = QColor(color)
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def getKnob(self) -> float:
        return self._knob

    def setKnob(self, value: float) -> None:
        self._knob = value
        self.update()

    knobPos = Property(float, getKnob, setKnob)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(_lerp(self._off_color, self._on_color, self._knob))
        painter.drawRoundedRect(rect, radius, radius)
        diameter = rect.height() - 2 * self._margin
        travel = rect.width() - 2 * self._margin - diameter
        x = rect.left() + self._margin + self._knob * travel
        painter.setBrush(self._knob_color)
        painter.drawEllipse(QRectF(x, rect.top() + self._margin, diameter, diameter))


class SegmentedControl(QWidget):
    selected = Signal(str)  # etiqueta elegida (solo por interacción del usuario)

    def __init__(self, labels: List[str], parent: QWidget = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for label in labels:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("segment", True)  # para el QSS del panel
            button.clicked.connect(lambda _checked=False, l=label: self.selected.emit(l))
            self._group.addButton(button)
            self._buttons[label] = button
            layout.addWidget(button)

    def set_current(self, label: str) -> None:
        button = self._buttons.get(label)
        if button is not None:
            button.setChecked(True)
