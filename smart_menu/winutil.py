"""Utilidades Win32 (ctypes): estilos de ventana por HWND (click-through, topmost, esquinas
redondeadas), información de monitores, rampa de gamma por dispositivo y auto-pegado (foco +
Ctrl+V). Centraliza las firmas para no truncar punteros/handles en 64 bits.

Las funciones de ventana reciben un **HWND** (entero); con PySide6 se obtiene de
``int(widget.winId())``.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Tuple

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

MONITOR_DEFAULTTONEAREST = 2
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

# SetWindowPos: reinsertar al frente de la banda "siempre visible" sin mover ni activar.
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

CCHDEVICENAME = 32  # longitud de szDevice en MONITORINFOEXW (p. ej. "\\.\DISPLAY1")

# Rampa de gamma de GDI: 3 canales (R, G, B) × 256 entradas de 16 bits.
GAMMA_RAMP = ctypes.c_ushort * 256 * 3

# SendInput (teclado) para el auto-pegado.
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56
ULONG_PTR = ctypes.c_size_t


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


class MONITORINFOEXW(ctypes.Structure):
    """Como MONITORINFO pero con ``szDevice`` (nombre del dispositivo del monitor)."""
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * CCHDEVICENAME)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    # El relleno garantiza sizeof(INPUT)==40 en x64 (tamaño real, requerido por SendInput).
    _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


# Firmas explícitas (imprescindible en 64 bits)
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
user32.GetMonitorInfoW.restype = wintypes.BOOL
# c_void_p admite byref de MONITORINFO y de MONITORINFOEXW (ambos se pasan por referencia).
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SendInput.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

# GDI: rampa de gamma por dispositivo (para atenuar también apps a pantalla completa).
gdi32.CreateDCW.restype = wintypes.HDC
gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.GetDeviceGammaRamp.restype = wintypes.BOOL
gdi32.GetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.restype = wintypes.BOOL
gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]


# --- monitores --------------------------------------------------------------
def _monitor_info(hmon) -> Tuple[int, tuple, tuple]:
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    full = (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom)
    work = (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
    return int(hmon), full, work


def monitor_from_point(x: int, y: int):
    """(clave, rect_monitor, rect_trabajo) del monitor que contiene el punto (x, y)."""
    return _monitor_info(user32.MonitorFromPoint(POINT(x, y), MONITOR_DEFAULTTONEAREST))


def cursor_pos() -> Tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def monitor_device_name(hmon) -> str:
    """Nombre del dispositivo del monitor (p. ej. ``\\\\.\\DISPLAY1``) a partir del HMONITOR.

    Devuelve "" si la consulta falla. Se usa para abrir un DC del monitor y ajustar su gamma.
    """
    mi = MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return ""
    return mi.szDevice


# --- estilos de ventana (reciben un HWND) -----------------------------------
def make_click_through(hwnd) -> None:
    """La ventana deja pasar el ratón y no roba el foco (para superposiciones)."""
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE,
        ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
    )


def assert_topmost(hwnd) -> None:
    """Reinserta la ventana en lo alto de la banda *topmost* sin moverla ni activarla.

    El estilo WS_EX_TOPMOST no garantiza quedar *encima de otras* ventanas topmost: la última
    en activarse gana. Llamar a esto periódicamente mantiene la superposición (y el panel) por
    delante de video/juegos a pantalla completa y otras apps siempre-visibles.
    """
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


# --- gamma por dispositivo --------------------------------------------------
def create_display_dc(device_name: str):
    """HDC del dispositivo de pantalla indicado (o 0 si falla). Liberar con :func:`delete_dc`."""
    if not device_name:
        return 0
    return gdi32.CreateDCW(device_name, None, None, None)


def delete_dc(hdc) -> None:
    if hdc:
        gdi32.DeleteDC(hdc)


def get_gamma_ramp(hdc, ramp) -> bool:
    """Lee la rampa de gamma actual del DC en ``ramp`` (un GAMMA_RAMP)."""
    return bool(gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(ramp)))


def set_gamma_ramp(hdc, ramp) -> bool:
    """Aplica ``ramp`` (un GAMMA_RAMP) al DC. Devuelve False si Windows la rechaza."""
    return bool(gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp)))


# --- auto-pegado ------------------------------------------------------------
def get_foreground_window() -> int:
    """HWND de la ventana en primer plano (0 si no hay)."""
    return user32.GetForegroundWindow() or 0


def set_foreground_window(hwnd) -> None:
    """Devuelve el primer plano a ``hwnd`` (p. ej. la app donde estaba el usuario)."""
    if hwnd:
        user32.SetForegroundWindow(hwnd)


def send_ctrl_v() -> None:
    """Simula Ctrl+V en la ventana activa (para pegar tras restaurar el foco)."""
    def _key(vk: int, up: bool) -> INPUT:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(wVk=vk, wScan=0,
                              dwFlags=KEYEVENTF_KEYUP if up else 0, time=0, dwExtraInfo=0)
        return inp

    seq = (_key(VK_CONTROL, False), _key(VK_V, False), _key(VK_V, True), _key(VK_CONTROL, True))
    arr = (INPUT * len(seq))(*seq)
    user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))
