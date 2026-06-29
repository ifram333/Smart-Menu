"""Historial de portapapeles ("aumentar el tamaño del clipboard").

:class:`ClipboardManager` escucha ``QClipboard.dataChanged`` y guarda los últimos *N* copiados
(texto e imágenes), sin duplicados consecutivos, con persistencia opcional en disco. Elegir un
ítem lo vuelve a copiar y, si ``auto_paste`` está activo, lo pega (Ctrl+V) en la ventana donde
estaba el usuario. :class:`ClipboardPopup` muestra el historial junto al cursor.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import List, Optional

from PySide6.QtCore import QEvent, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QSlider, QVBoxLayout,
                               QWidget)

from . import config
from . import winutil
from .widgets import AnimatedSwitch


def _img_hash(img: QImage) -> str:
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    return hashlib.md5(bytes(img.constBits())).hexdigest()


def _preview(item: dict) -> str:
    if item["kind"] == "text":
        text = " ".join(item["text"].split())
        return (text[:64] + "…") if len(text) > 64 else (text or "(texto vacío)")
    return "Imagen"


class ClipboardManager:
    """Historial del portapapeles. ``on_change`` se llama cuando el historial cambia."""

    def __init__(self, cfg: config.Config, on_change=None) -> None:
        self.cfg = cfg
        self._on_change = on_change
        self._items: List[dict] = []   # recientes primero
        self._img_dir = os.path.join(config.data_dir(), "clip_images")
        self._store = os.path.join(config.data_dir(), "clipboard.json")
        if self._opts().get("persist"):
            self._load()
        self._clip = QGuiApplication.clipboard()
        self._clip.dataChanged.connect(self._on_clipboard_change)
        self._on_clipboard_change()  # capturar lo que ya esté copiado

    # ---- opciones / estado ----
    def _opts(self) -> dict:
        return self.cfg.clipboard

    def items(self) -> List[dict]:
        return self._items

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()

    # ---- captura ----
    def _on_clipboard_change(self) -> None:
        opts = self._opts()
        if not opts.get("enabled", True):
            return
        md = self._clip.mimeData()
        if md is None:
            return
        item: Optional[dict] = None
        if opts.get("include_images") and md.hasImage():
            img = self._clip.image()
            if img is not None and not img.isNull():
                item = self._make_image_item(img)
        if item is None and md.hasText():
            text = self._clip.text()
            if text and text.strip():
                item = {"kind": "text", "text": text}
        if item is None:
            return
        # Sin duplicados: si ya existía (en cualquier posición) se quita y se pone al frente.
        self._items = [it for it in self._items if not self._same(it, item)]
        self._items.insert(0, item)
        del self._items[self._opts().get("max_items", 25):]
        if self._opts().get("persist"):
            self._save()
        self._notify()

    def _make_image_item(self, img: QImage) -> dict:
        digest = _img_hash(img)
        item = {"kind": "image", "hash": digest, "_image": img}
        if self._opts().get("persist"):
            os.makedirs(self._img_dir, exist_ok=True)
            path = os.path.join(self._img_dir, digest + ".png")
            if not os.path.exists(path):
                img.save(path, "PNG")
            item["path"] = path
        return item

    @staticmethod
    def _same(a: dict, b: dict) -> bool:
        if a["kind"] != b["kind"]:
            return False
        if a["kind"] == "text":
            return a["text"] == b["text"]
        return a.get("hash") == b.get("hash")

    def image_of(self, item: dict) -> Optional[QImage]:
        if item.get("_image") is not None:
            return item["_image"]
        path = item.get("path")
        if path and os.path.exists(path):
            img = QImage(path)
            if not img.isNull():
                item["_image"] = img
                return img
        return None

    # ---- acciones ----
    def use(self, index: int, paste_target: int = 0) -> None:
        if not (0 <= index < len(self._items)):
            return
        item = self._items[index]
        if item["kind"] == "text":
            self._clip.setText(item["text"])
        else:
            img = self.image_of(item)
            if img is None:
                return
            self._clip.setImage(img)
        self._items.insert(0, self._items.pop(index))  # mover al frente
        if self._opts().get("persist"):
            self._save()
        self._notify()
        if self._opts().get("auto_paste") and paste_target:
            winutil.set_foreground_window(paste_target)
            QTimer.singleShot(120, winutil.send_ctrl_v)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            if self._opts().get("persist"):
                self._save()
            self._notify()

    def clear(self) -> None:
        self._items.clear()
        if self._opts().get("persist"):
            self._save()
        self._notify()

    def set_max_items(self, n: int) -> None:
        n = max(config.CLIPBOARD_MIN_ITEMS, min(config.CLIPBOARD_MAX_ITEMS, int(n)))
        self._opts()["max_items"] = n
        del self._items[n:]
        self.cfg.save()
        if self._opts().get("persist"):
            self._save()
        self._notify()

    # ---- persistencia ----
    def _save(self) -> None:
        out = []
        for item in self._items:
            if item["kind"] == "text":
                out.append({"kind": "text", "text": item["text"]})
            elif item.get("path"):
                out.append({"kind": "image", "hash": item.get("hash", ""), "path": item["path"]})
        try:
            with open(self._store, "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False)
        except OSError:
            pass

    def _load(self) -> None:
        try:
            with open(self._store, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        for item in data if isinstance(data, list) else []:
            if item.get("kind") == "text" and item.get("text"):
                self._items.append({"kind": "text", "text": item["text"]})
            elif item.get("kind") == "image" and os.path.exists(item.get("path", "")):
                self._items.append({"kind": "image", "hash": item.get("hash", ""),
                                    "path": item["path"]})
        del self._items[self._opts().get("max_items", 25):]


class ClipboardPopup(QWidget):
    """Lista del historial junto al cursor. Clic/Enter usa un ítem; Supr lo borra; Esc cierra."""

    def __init__(self, manager: ClipboardManager) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.manager = manager
        self._guard = False
        self._prev_hwnd = 0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        self.card = QFrame(objectName="card")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 130))
        shadow.setOffset(0, 6)
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)
        root = QVBoxLayout(self.card)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel("Portapapeles", objectName="title"))
        head.addStretch(1)
        clear_btn = QPushButton("Limpiar")
        clear_btn.setObjectName("exit")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear)
        head.addWidget(clear_btn)
        root.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("cliplist")
        self.list.setIconSize(QPixmap(56, 36).size())
        self.list.setUniformItemSizes(False)
        self.list.setMaximumHeight(280)
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        root.addWidget(self.list)

        self.hint = QLabel("Enter: usar · Supr: borrar · Esc: cerrar", objectName="muted")
        root.addWidget(self.hint)

        # Opciones del portapapeles (movidas aquí desde el panel principal).
        ap_row = QHBoxLayout()
        ap_row.addWidget(QLabel("Auto-pegar al elegir"))
        ap_row.addStretch(1)
        self.autopaste_switch = AnimatedSwitch(width=40, height=23)
        self.autopaste_switch.clicked.connect(self._on_autopaste)
        ap_row.addWidget(self.autopaste_switch)
        root.addLayout(ap_row)

        self.size_lbl = QLabel("Tamaño del historial: 25", objectName="muted")
        root.addWidget(self.size_lbl)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(config.CLIPBOARD_MIN_ITEMS, config.CLIPBOARD_MAX_ITEMS)
        self.size_slider.valueChanged.connect(self._on_size_label)
        self.size_slider.sliderReleased.connect(self._on_size_apply)
        root.addWidget(self.size_slider)

        self.hide()

    # ---- opciones ----
    def _on_autopaste(self, checked: bool) -> None:
        self.manager.cfg.clipboard["auto_paste"] = checked
        self.manager.cfg.save()

    def _on_size_label(self, value: int) -> None:
        self.size_lbl.setText(f"Tamaño del historial: {value}")

    def _on_size_apply(self) -> None:
        self.manager.set_max_items(self.size_slider.value())

    def _sync_options(self) -> None:
        clip = self.manager.cfg.clipboard
        self.autopaste_switch.setChecked(clip.get("auto_paste", True))
        n = clip.get("max_items", 25)
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(n)
        self.size_slider.blockSignals(False)
        self.size_lbl.setText(f"Tamaño del historial: {n}")

    def _populate(self) -> None:
        self.list.clear()
        for idx, item in enumerate(self.manager.items()):
            entry = QListWidgetItem(_preview(item))
            entry.setData(Qt.UserRole, idx)
            if item["kind"] == "image":
                img = self.manager.image_of(item)
                if img is not None:
                    entry.setIcon(QIcon(QPixmap.fromImage(
                        img.scaled(56, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))))
                    w, h = item.get("_image").width(), item.get("_image").height()
                    entry.setText(f"Imagen {w}×{h}")
            self.list.addItem(entry)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.hint.setVisible(self.list.count() > 0)
        if not self.list.count():
            self.list.addItem(QListWidgetItem("(historial vacío)"))

    def _activate(self, entry: QListWidgetItem) -> None:
        idx = entry.data(Qt.UserRole)
        if idx is None:
            return
        self.hide()
        self.manager.use(int(idx), self._prev_hwnd)

    def _clear(self) -> None:
        self.manager.clear()
        self._populate()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.hide()
        elif e.key() == Qt.Key_Delete:
            entry = self.list.currentItem()
            idx = entry.data(Qt.UserRole) if entry else None
            if idx is not None:
                self.manager.remove(int(idx))
                self._populate()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            entry = self.list.currentItem()
            if entry:
                self._activate(entry)
        else:
            super().keyPressEvent(e)

    def popup(self, prev_hwnd: int) -> None:
        self._prev_hwnd = prev_hwnd
        self._sync_options()
        self._populate()
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
        self.move(x, y)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self.list.setFocus()
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(140)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._guard = True
        QTimer.singleShot(250, lambda: setattr(self, "_guard", False))

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.WindowDeactivate and not self._guard and self.isVisible():
            self.hide()
        return super().event(e)
