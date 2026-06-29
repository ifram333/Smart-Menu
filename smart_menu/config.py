"""Ajustes persistentes de Smart Menu en ``%APPDATA%\\Smart Menu\\config.json``.

Esquema (con *defaults*): atajos globales y opciones del historial de portapapeles. ``load``
fusiona lo guardado sobre los *defaults* (así nuevas claves obtienen valor por defecto) y
``save`` escribe de forma atómica. ``data_dir`` da la carpeta de datos (historial, imágenes).
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any, Dict

APP_DIR_NAME = "Smart Menu"

DEFAULTS: Dict[str, Any] = {
    "hotkeys": {
        "toggle_awake": "Ctrl+Alt+K",   # activar/desactivar Keep Awake
        "show_panel": "Ctrl+Alt+S",     # mostrar el panel junto al cursor
        "clipboard": "Ctrl+Alt+V",      # abrir el historial de portapapeles
        "dim_up": "Ctrl+Alt+Up",        # subir atenuado (teclas independientes del teclado)
        "dim_down": "Ctrl+Alt+Down",    # bajar atenuado
    },
    "clipboard": {
        "enabled": True,
        "max_items": 25,        # profundidad del historial (configurable por el usuario)
        "include_images": True,
        "persist": True,        # conservar el historial entre reinicios
        "auto_paste": True,     # al elegir un ítem, pegarlo (Ctrl+V) en la app previa
    },
}

# Límites de la profundidad del historial expuesta en la UI.
CLIPBOARD_MIN_ITEMS = 5
CLIPBOARD_MAX_ITEMS = 200


def data_dir() -> str:
    """Carpeta de datos de la app (se crea si no existe)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def _deep_merge(base: dict, overrides: dict) -> dict:
    """Fusiona ``overrides`` sobre ``base`` recursivamente (devuelve ``base`` mutado)."""
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _read(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _atomic_write(path: str, data: dict) -> None:
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


class Config:
    """Carga los ajustes al instanciarse; modifícalos en ``.data`` y llama a ``save()``."""

    def __init__(self) -> None:
        self.path = _config_path()
        self.data = _deep_merge(copy.deepcopy(DEFAULTS), _read(self.path))

    def save(self) -> None:
        _atomic_write(self.path, self.data)

    @property
    def hotkeys(self) -> Dict[str, str]:
        return self.data["hotkeys"]

    @property
    def clipboard(self) -> Dict[str, Any]:
        return self.data["clipboard"]
