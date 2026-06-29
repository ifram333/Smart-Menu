"""Iniciar con Windows mediante la clave de registro ``Run`` del usuario actual (HKCU).

No requiere privilegios de administrador. Soporta tanto la app empaquetada (.exe) como
la ejecución del script con ``pythonw.exe`` (para que no aparezca ventana de consola).
"""

from __future__ import annotations

import os
import sys
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "SmartMenu"


def _pythonw_path() -> str:
    """Ruta a pythonw.exe junto al intérprete actual (cae a python.exe si no existe)."""
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return pythonw if os.path.exists(pythonw) else sys.executable


def _launch_command() -> str:
    """Comando que Windows ejecutará al iniciar sesión, con comillas adecuadas."""
    if getattr(sys, "frozen", False):
        # Empaquetado con PyInstaller: el propio ejecutable.
        return f'"{sys.executable}"'
    # Script: pythonw.exe (sin consola) + el lanzador run.py de la raíz del repo.
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "run.py"))
    return f'"{_pythonw_path()}" "{script}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def enable() -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        pass  # ya no existe: nada que hacer


def toggle() -> bool:
    """Alterna el inicio con Windows y devuelve el nuevo estado."""
    if is_enabled():
        disable()
        return False
    enable()
    return True
