"""Atenuación por rampa de gamma (Win32 GDI), complementaria a la superposición de
:mod:`dimmer`.

La rampa de gamma afecta a la salida del adaptador, así que oscurece también las
aplicaciones a **pantalla completa** (incluida la *exclusive fullscreen* de muchos juegos)
que una ventana superpuesta no puede cubrir.

Salvedades conocidas: no tiene efecto con **HDR** activado, altera el **color global** del
monitor y Windows **acota** cuánto puede oscurecer. Por eso es un refuerzo, no un sustituto
de la superposición.

El estado (la rampa original de cada dispositivo) se guarda para poder restaurarlo al
quitar la atenuación o al salir.
"""

from __future__ import annotations

from typing import Dict

from . import winutil


def _clamp_word(v: int) -> int:
    return 0 if v < 0 else (65535 if v > 65535 else v)


class GammaDimmer:
    """Atenúa por gamma, por dispositivo de pantalla (p. ej. ``\\\\.\\DISPLAY1``)."""

    def __init__(self) -> None:
        # device_name -> GAMMA_RAMP original (capturada antes del primer cambio).
        self._originals: Dict[str, object] = {}

    def _ensure_original(self, device: str) -> bool:
        """Captura (una vez) la rampa original del dispositivo. False si no se puede."""
        if device in self._originals:
            return True
        hdc = winutil.create_display_dc(device)
        if not hdc:
            return False
        try:
            ramp = winutil.GAMMA_RAMP()
            if not winutil.get_gamma_ramp(hdc, ramp):
                return False
            self._originals[device] = ramp
            return True
        finally:
            winutil.delete_dc(hdc)

    def apply(self, device: str, brightness: float) -> None:
        """Escala la rampa **original** por ``brightness`` (0..1; 1 = sin cambio).

        Escalar la rampa original (en vez de una lineal) preserva la calibración/perfil de
        color del usuario y solo reduce el brillo. Silencioso si el dispositivo no admite
        gamma o si Windows rechaza la rampa.
        """
        if not device or not self._ensure_original(device):
            return
        brightness = max(0.0, min(1.0, brightness))
        original = self._originals[device]
        ramp = winutil.GAMMA_RAMP()
        for c in range(3):
            chan = original[c]
            out = ramp[c]
            for i in range(256):
                out[i] = _clamp_word(int(chan[i] * brightness))
        hdc = winutil.create_display_dc(device)
        if not hdc:
            return
        try:
            winutil.set_gamma_ramp(hdc, ramp)
        finally:
            winutil.delete_dc(hdc)

    def restore(self, device: str) -> None:
        """Restaura la rampa original del dispositivo y olvida su estado guardado."""
        original = self._originals.pop(device, None)
        if original is None:
            return
        hdc = winutil.create_display_dc(device)
        if not hdc:
            return
        try:
            winutil.set_gamma_ramp(hdc, original)
        finally:
            winutil.delete_dc(hdc)

    def restore_all(self) -> None:
        for device in list(self._originals.keys()):
            self.restore(device)
