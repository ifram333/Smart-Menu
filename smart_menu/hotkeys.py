"""Hotkeys globales del sistema (Win32 ``RegisterHotKey``) integradas en el bucle de Qt.

Se registran sobre el HWND de una ventana oculta propia; el mensaje ``WM_HOTKEY`` se captura
con un ``QAbstractNativeEventFilter`` instalado en la ``QApplication``. No requiere privilegios
de administrador ni dependencias externas. Las combinaciones se describen como texto, p. ej.
``"Ctrl+Alt+K"`` o ``"Ctrl+Alt+Up"``.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication, QWidget

user32 = ctypes.windll.user32
user32.RegisterHotKey.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {
    "ALT": MOD_ALT, "CTRL": MOD_CONTROL, "CONTROL": MOD_CONTROL,
    "SHIFT": MOD_SHIFT, "WIN": MOD_WIN, "SUPER": MOD_WIN, "META": MOD_WIN,
}

# Teclas no alfanuméricas -> virtual-key. Las de flecha/función son independientes del idioma
# del teclado; las OEM (., , etc.) valen para distribuciones estándar.
_SPECIAL_VK = {
    "SPACE": 0x20, "ENTER": 0x0D, "RETURN": 0x0D, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    ".": 0xBE, "PERIOD": 0xBE, ",": 0xBC, "COMMA": 0xBC, "-": 0xBD, "MINUS": 0xBD,
    "=": 0xBB, "PLUS": 0xBB, "/": 0xBF, ";": 0xBA, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    "'": 0xDE, "`": 0xC0,
}
_SPECIAL_VK.update({f"F{i}": 0x70 + (i - 1) for i in range(1, 13)})  # F1..F12


def _vk_for(key: str) -> Optional[int]:
    key = key.strip()
    if len(key) == 1:
        ch = key.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
    return _SPECIAL_VK.get(key.upper())


def parse(combo: str) -> Tuple[int, Optional[int]]:
    """"Ctrl+Alt+K" -> (modificadores, virtual-key). vk None si no se reconoce la tecla."""
    mods, key = 0, None
    for part in (p.strip() for p in combo.split("+")):
        if not part:
            continue
        upper = part.upper()
        if upper in _MODS:
            mods |= _MODS[upper]
        else:
            key = part
    return mods, (_vk_for(key) if key else None)


class HotkeyManager(QAbstractNativeEventFilter):
    def __init__(self) -> None:
        super().__init__()
        self._win = QWidget()           # ventana oculta dueña de los hotkeys
        self._hwnd = int(self._win.winId())  # fuerza la creación del HWND nativo
        self._actions: Dict[int, Callable[[], None]] = {}
        self._next_id = 1
        QApplication.instance().installNativeEventFilter(self)

    def register(self, combo: str, callback: Callable[[], None]) -> bool:
        mods, vk = parse(combo)
        if not mods or vk is None:
            return False
        hid = self._next_id
        if not user32.RegisterHotKey(self._hwnd, hid, mods | MOD_NOREPEAT, vk):
            return False  # combinación inválida o ya tomada por otra app
        self._actions[hid] = callback
        self._next_id += 1
        return True

    def clear(self) -> None:
        for hid in list(self._actions):
            user32.UnregisterHotKey(self._hwnd, hid)
        self._actions.clear()

    def apply(self, bindings: Dict[str, Callable[[], None]]) -> None:
        """Re-registra todo a partir de ``{combo: callback}`` (ignora combos inválidos/duplicados)."""
        self.clear()
        for combo, callback in bindings.items():
            self.register(combo, callback)

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                callback = self._actions.get(int(msg.wParam))
                if callback is not None:
                    callback()
                    return True, 0
        return False, 0
