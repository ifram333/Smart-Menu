"""Smart Menu — utilidades de Windows desde la bandeja del sistema (PySide6).

Funciones: **Keep Awake** (evita suspensión y que se apague la pantalla), **Atenuar pantalla**
(superposición + gamma por monitor), **Iniciar con Windows**, **hotkeys globales** e
**historial de portapapeles**.

Interfaz: un ícono en la bandeja (el logo). Cualquier clic abre, junto al cursor, un panel
flotante moderno con animación. Todo corre en el hilo principal (Qt); el controlador de energía
usa un hilo trabajador que notifica a la interfaz mediante una señal Qt.

Ejecutar (desde la raíz del repo):
    pythonw src\\app.py            # uso normal, sin consola
    python  src\\app.py            # con logs (depuración)
    python  src\\app.py --make-ico # solo genera assets/icon.ico (lo usa build.ps1)
"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

from . import clipboard
from . import hotkeys
from . import preferences
from . import resources
from . import startup
from . import winutil
from .config import Config
from .dimmer import Dimmer
from .power import PowerController
from .tray import Tray
from .widgets import AnimatedSwitch, SegmentedControl

APP_NAME = "Smart Menu"
_MUTEX_NAME = "SmartMenu_SingleInstance_Mutex"
ACCENT = "#2f6bff"
MUTED_DARK = "#9aa4b2"    # texto/ícono secundario (tema oscuro)
MUTED_LIGHT = "#6b7280"   # texto/ícono secundario (tema claro)

# Selector de duración: (etiqueta, segundos | None = indefinido)
DURATIONS = [("Indefinido", None), ("30 min", 30 * 60), ("1 h", 60 * 60), ("2 h", 7200)]
_DURATION_LABELS = [d[0] for d in DURATIONS]
_LABEL_TO_SECONDS = {label: secs for label, secs in DURATIONS}
_SECONDS_TO_LABEL = {secs: label for label, secs in DURATIONS}

PANEL_W = 320
_mutex_handle = None  # se conserva para que el mutex viva mientras corra el proceso


# --- utilidades --------------------------------------------------------------
def _single_instance_or_exit() -> None:
    """Crea un mutex con nombre; si ya hay otra instancia, termina en silencio."""
    global _mutex_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
    _mutex_handle = handle


def _format_remaining(seconds: int) -> str:
    minutes = seconds // 60
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        return f"{h} h {m:02d} min"
    if minutes >= 1:
        return f"{minutes} min"
    return f"{seconds} s"


def _qss(dark: bool) -> str:
    if dark:
        card, text, muted = "#23262e", "#e6e8ec", MUTED_DARK
        border, seg, hover = "#3a3f4b", "#2b2f38", "#2b2f38"
    else:
        card, text, muted = "#ffffff", "#1b1d22", MUTED_LIGHT
        border, seg, hover = "#d4d7dd", "#eceef2", "#e6e8ec"
    return f"""
    #card {{ background: {card}; border-radius: 16px; }}
    QLabel {{ color: {text}; background: transparent; }}
    QLabel#title {{ font-size: 17px; font-weight: 700; }}
    QLabel#muted {{ color: {muted}; font-size: 12px; }}
    QLabel#section {{ color: {muted}; font-size: 11px; font-weight: 700; }}
    QPushButton[segment="true"] {{
        background: {seg}; color: {text}; border: none; border-radius: 8px;
        padding: 7px 4px; font-size: 12px;
    }}
    QPushButton[segment="true"]:checked {{ background: {ACCENT}; color: white; }}
    QPushButton#exit {{
        background: transparent; color: {muted}; border: 1px solid {border};
        border-radius: 10px; padding: 9px; font-size: 13px;
    }}
    QPushButton#exit:hover {{ background: {hover}; }}
    QSlider::groove:horizontal {{ height: 6px; background: {seg}; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
    QSlider::handle:horizontal {{
        background: {ACCENT}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    }}
    QListWidget#cliplist {{
        background: {seg}; border: none; border-radius: 8px; padding: 4px; color: {text};
        outline: none;
    }}
    QListWidget#cliplist::item {{ padding: 6px 8px; border-radius: 6px; }}
    QListWidget#cliplist::item:selected {{ background: {ACCENT}; color: white; }}
    QPushButton#hotkeycap {{
        background: {seg}; color: {text}; border: 1px solid {border};
        border-radius: 8px; padding: 6px 12px; font-weight: 600;
    }}
    QPushButton#hotkeycap:hover {{ border-color: {ACCENT}; }}
    """


# --- panel flotante ----------------------------------------------------------
class Panel(QWidget):
    def __init__(self, app: "App") -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.app = app
        self.controller = app.controller
        self._updating = False
        self._guard = False
        self._screen = None
        self._device = ""
        self._dim_key = ""

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(PANEL_W)
        self._build()
        self.hide()

    # ---- construcción ----
    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section")
        return lbl

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)  # margen para la sombra

        self.card = QFrame()
        self.card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 130))
        shadow.setOffset(0, 6)
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(8)

        # Encabezado: logo + nombre + estado
        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(resources.pil_to_qpixmap(resources.logo_image(True, 44)))
        logo.setFixedSize(44, 44)
        logo.setScaledContents(True)
        header.addWidget(logo)
        titlebox = QVBoxLayout()
        titlebox.setSpacing(0)
        titlebox.addWidget(QLabel(APP_NAME, objectName="title"))
        self.status_lbl = QLabel("Inactivo", objectName="muted")
        titlebox.addWidget(self.status_lbl)
        header.addSpacing(12)
        header.addLayout(titlebox)
        header.addStretch(1)
        root.addLayout(header)
        root.addSpacing(8)

        # Mantener despierto
        ka_row = QHBoxLayout()
        ka_lbl = QLabel("Mantener despierto")
        ka_lbl.setStyleSheet("font-size: 14px; font-weight: 600;")
        ka_row.addWidget(ka_lbl)
        ka_row.addStretch(1)
        self.ka_switch = AnimatedSwitch()
        self.ka_switch.clicked.connect(self._on_keepawake)
        ka_row.addWidget(self.ka_switch)
        root.addLayout(ka_row)

        # Duración
        root.addSpacing(6)
        root.addWidget(self._section("DURACIÓN"))
        self.segment = SegmentedControl(_DURATION_LABELS)
        self.segment.selected.connect(self._on_duration)
        root.addWidget(self.segment)

        # Atenuar pantalla
        root.addSpacing(8)
        root.addWidget(self._section("ATENUAR PANTALLA"))
        dim_row = QHBoxLayout()
        self.dim_slider = QSlider(Qt.Horizontal)
        self.dim_slider.setRange(0, 100)
        self.dim_slider.setSingleStep(5)
        self.dim_slider.valueChanged.connect(self._on_dim)
        dim_row.addWidget(self.dim_slider, 1)
        self.dim_pct = QLabel("0%", objectName="muted")
        self.dim_pct.setFixedWidth(40)
        self.dim_pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        dim_row.addSpacing(8)
        dim_row.addWidget(self.dim_pct)
        root.addLayout(dim_row)

        # Portapapeles
        root.addSpacing(8)
        root.addWidget(self._section("PORTAPAPELES"))
        self.clip_btn = QPushButton("Abrir historial")
        self.clip_btn.setObjectName("exit")
        self.clip_btn.setCursor(Qt.PointingHandCursor)
        self.clip_btn.clicked.connect(self.app.open_clipboard)
        root.addWidget(self.clip_btn)

        # Iniciar con Windows
        root.addSpacing(10)
        start_row = QHBoxLayout()
        start_row.addWidget(QLabel("Iniciar con Windows"))
        start_row.addStretch(1)
        self.start_switch = AnimatedSwitch(width=40, height=23)
        self.start_switch.clicked.connect(self._on_startup)
        start_row.addWidget(self.start_switch)
        root.addLayout(start_row)

        # Preferencias + Salir (misma fila, al mismo nivel)
        root.addSpacing(12)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        self.prefs_btn = QPushButton("Preferencias")
        self.prefs_btn.setObjectName("exit")
        self.prefs_btn.setCursor(Qt.PointingHandCursor)
        self.prefs_btn.clicked.connect(self.app.open_preferences)
        self.exit_btn = QPushButton("Salir")
        self.exit_btn.setObjectName("exit")
        self.exit_btn.setCursor(Qt.PointingHandCursor)
        self.exit_btn.clicked.connect(self.app.quit)
        actions_row.addWidget(self.prefs_btn, 1)
        actions_row.addWidget(self.exit_btn, 1)
        root.addLayout(actions_row)

    def set_action_icons(self, color: str) -> None:
        self.clip_btn.setIcon(resources.tinted_icon("track.png", 16, color))
        self.prefs_btn.setIcon(resources.tinted_icon("tool.png", 16, color))
        self.exit_btn.setIcon(resources.tinted_icon("exit.png", 16, color))

    # ---- callbacks ----
    def _on_keepawake(self, checked: bool) -> None:
        if self._updating:
            return
        self.controller.enable() if checked else self.controller.disable()
        self.refresh()

    def _on_duration(self, label: str) -> None:
        if self._updating:
            return
        self.controller.set_duration(_LABEL_TO_SECONDS.get(label))
        self.refresh()

    def _on_dim(self, value: int) -> None:
        if self._updating or self._screen is None:
            return
        level = int(value)
        self.dim_pct.setText(f"{level}%")
        self._guard = True  # la overlay no debería robar foco, pero evitamos autocierre
        self.app.dimmer.set(self._screen, self._device, level)
        self.raise_()
        self.activateWindow()
        winutil.assert_topmost(int(self.winId()))
        QTimer.singleShot(300, lambda: setattr(self, "_guard", False))

    def _on_startup(self, checked: bool) -> None:
        if self._updating:
            return
        startup.enable() if checked else startup.disable()

    # ---- estado ----
    def _status_text(self) -> str:
        if not self.controller.active:
            return "Inactivo"
        rem = self.controller.remaining()
        return "Activo" if rem is None else f"Activo · {_format_remaining(rem)} restantes"

    def refresh(self) -> None:
        self._updating = True
        try:
            self.ka_switch.setChecked(self.controller.active)
            self.status_lbl.setText(self._status_text())
            self.segment.set_current(_SECONDS_TO_LABEL.get(self.controller.duration, "Indefinido"))
            self.start_switch.setChecked(startup.is_enabled())
            level = self.app.dimmer.level(self._dim_key)
            self.dim_slider.setValue(level)
            self.dim_pct.setText(f"{level}%")
        finally:
            self._updating = False

    # ---- mostrar/ocultar ----
    def popup(self) -> None:
        self.adjustSize()
        w, h = self.width(), self.height()
        cpos = QCursor.pos()
        screen = QGuiApplication.screenAt(cpos) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        m = 8
        x = cpos.x() + 12 if (cpos.x() + 12 + w + m) <= avail.right() else cpos.x() - w - 12
        y = cpos.y() + 12 if (cpos.y() + 12 + h + m) <= avail.bottom() else cpos.y() - h - 12
        x = max(avail.left() + m, min(int(x), avail.right() - w - m))
        y = max(avail.top() + m, min(int(y), avail.bottom() - h - m))

        # Monitor donde se abre (para el atenuado y su gamma).
        self._screen = screen
        px, py = winutil.cursor_pos()
        mon_key, _full, _work = winutil.monitor_from_point(px, py)
        self._device = winutil.monitor_device_name(mon_key)
        self._dim_key = self._device or screen.name()

        self.refresh()
        self.move(x, y)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self._animate_in(QPoint(x, y))

        self._guard = True
        QTimer.singleShot(250, lambda: setattr(self, "_guard", False))

    def _animate_in(self, target: QPoint) -> None:
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(160)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)
        self._slide.setStartValue(QPoint(target.x(), target.y() + 8))
        self._slide.setEndValue(target)
        self._fade.start()
        self._slide.start()

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.WindowDeactivate and not self._guard and self.isVisible():
            self.app.hide_panel()
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.app.hide_panel()
        else:
            super().keyPressEvent(e)


# --- aplicación --------------------------------------------------------------
class _PowerSignals(QObject):
    changed = Signal()


class App:
    def __init__(self) -> None:
        self.config = Config()
        self._signals = _PowerSignals()
        self._signals.changed.connect(self._on_power_change)
        self.controller = PowerController(on_change=self._signals.changed.emit)

        self.dimmer = Dimmer()
        self.clipboard = clipboard.ClipboardManager(self.config, on_change=self._on_clip_change)
        self.clip_popup = clipboard.ClipboardPopup(self.clipboard)
        self.panel = Panel(self)
        self._visible = False
        self._last_hide = 0.0
        self.prefs = None

        self._icons = {"on": resources.logo_icon(True), "off": resources.logo_icon(False)}
        self.tray = Tray(self._icons, "off", self._tip(), on_activate=self.toggle_panel)

        self.hotkeys = hotkeys.HotkeyManager()
        self._apply_hotkeys()

        self._apply_theme()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _s: self._apply_theme())

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tip(self) -> str:
        return f"{APP_NAME} — Keep Awake: {'activo' if self.controller.active else 'inactivo'}"

    def _apply_theme(self) -> None:
        dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        self._qss = _qss(dark)
        self._muted = MUTED_DARK if dark else MUTED_LIGHT
        self.panel.setStyleSheet(self._qss)
        self.clip_popup.setStyleSheet(self._qss)
        self.panel.set_action_icons(self._muted)
        if self.prefs is not None:
            self.prefs.setStyleSheet(self._qss)
            self.prefs.set_icons(resources.tinted_icon("reset.png", 16, self._muted),
                                 resources.tinted_icon("close.png", 16, self._muted))

    def open_preferences(self) -> None:
        if self.prefs is None:
            self.prefs = preferences.PreferencesWindow(self.config, on_closed=self._on_prefs_closed)
            self.prefs.setStyleSheet(self._qss)
            self.prefs.set_icons(resources.tinted_icon("reset.png", 16, self._muted),
                                 resources.tinted_icon("close.png", 16, self._muted))
        self.hotkeys.clear()   # desactivar mientras se editan (para poder capturarlos)
        self.prefs.reload()
        self.prefs.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        frame = self.prefs.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.prefs.move(frame.topLeft())
        self.prefs.show()
        self.prefs.raise_()
        self.prefs.activateWindow()

    def _on_prefs_closed(self) -> None:
        self._apply_hotkeys()  # re-registrar con la config (posiblemente nueva)

    def _apply_hotkeys(self) -> None:
        hk = self.config.hotkeys
        self.hotkeys.apply({
            hk["toggle_awake"]: self.controller.toggle,
            hk["show_panel"]: self.show_panel,
            hk["clipboard"]: self.open_clipboard,
            hk["dim_up"]: lambda: self._dim_step(+10),
            hk["dim_down"]: lambda: self._dim_step(-10),
        })

    def open_clipboard(self) -> None:
        self.clip_popup.popup(winutil.get_foreground_window())

    def _dim_step(self, delta: int) -> None:
        cpos = QCursor.pos()
        screen = QGuiApplication.screenAt(cpos) or QGuiApplication.primaryScreen()
        px, py = winutil.cursor_pos()
        mon_key, _full, _work = winutil.monitor_from_point(px, py)
        device = winutil.monitor_device_name(mon_key)
        dim_key = device or screen.name()
        level = max(0, min(100, self.dimmer.level(dim_key) + delta))
        self.dimmer.set(screen, device, level)
        if self._visible:
            self.panel.refresh()

    def _on_clip_change(self) -> None:
        # El manager captura el portapapeles ya en su __init__ (antes de existir clip_popup).
        popup = getattr(self, "clip_popup", None)
        if popup is not None and popup.isVisible():
            popup._populate()

    # ---- acciones ----
    def toggle_panel(self) -> None:
        import time
        # Si el panel se ocultó hace muy poco (clic en la bandeja que lo desactivó), no reabrir.
        if self._visible or (time.monotonic() - self._last_hide) < 0.25:
            self.hide_panel()
        else:
            self.show_panel()

    def show_panel(self) -> None:
        self._visible = True
        self.panel.popup()

    def hide_panel(self) -> None:
        import time
        if not self._visible:
            return
        self._visible = False
        self._last_hide = time.monotonic()
        self.panel.hide()

    def _on_power_change(self) -> None:
        self.tray.update(key="on" if self.controller.active else "off", tip=self._tip())
        if self._visible:
            self.panel.refresh()

    def _tick(self) -> None:
        self.dimmer.reassert()
        if self._visible:
            try:
                winutil.assert_topmost(int(self.panel.winId()))
            except Exception:
                pass
            if self.controller.active and self.controller.remaining() is not None:
                self.panel.status_lbl.setText(self.panel._status_text())

    def quit(self) -> None:
        try:
            self.controller.shutdown()
            self.dimmer.clear_all()
        finally:
            self.clip_popup.hide()
            self.tray.hide()
            QApplication.instance().quit()


def main() -> None:
    if "--make-ico" in sys.argv:
        resources.export_ico()
        return
    _single_instance_or_exit()
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)
    App()
    sys.exit(qapp.exec())
