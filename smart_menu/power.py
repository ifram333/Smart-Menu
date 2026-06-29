"""Control de energía: evita la suspensión/hibernación del sistema y que se apague la
pantalla usando la API Win32 ``SetThreadExecutionState``.

El estado de ejecución es **por hilo** y se libera si ese hilo termina, por lo que aquí
se reafirma desde un hilo trabajador persistente que vive durante toda la sesión. Ese
mismo hilo gestiona el modo temporizado (cuenta atrás y autoapagado).
"""

from __future__ import annotations

import ctypes
import threading
import time
from typing import Callable, Optional

# Banderas de SetThreadExecutionState (winbase.h)
ES_CONTINUOUS = 0x80000000        # mantiene el estado hasta el siguiente cambio
ES_SYSTEM_REQUIRED = 0x00000001   # evita suspensión/hibernación del sistema
ES_DISPLAY_REQUIRED = 0x00000002  # evita además que se apague la pantalla

# Cada cuánto reafirma el estado el hilo trabajador (segundos).
_REASSERT_INTERVAL = 30.0

_kernel32 = ctypes.windll.kernel32
# Firma explícita: el valor de retorno es un EXECUTION_STATE (DWORD).
_kernel32.SetThreadExecutionState.restype = ctypes.c_uint
_kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint]


def _set_execution_state(flags: int) -> bool:
    """Llama a SetThreadExecutionState. Devuelve False si la API falla (retorna 0)."""
    return _kernel32.SetThreadExecutionState(ctypes.c_uint(flags)) != 0


class PowerController:
    """Mantiene el equipo despierto mientras está activo.

    Toda mutación del estado pasa por un lock y despierta al hilo trabajador, que es el
    único que llama a ``SetThreadExecutionState`` (la API es por hilo). ``on_change`` se
    invoca tras cada cambio para que la interfaz refresque ícono/menú; también se llama
    cuando el temporizador expira y la app se autodesactiva.
    """

    def __init__(self, on_change: Optional[Callable[[], None]] = None) -> None:
        self._on_change = on_change
        self._lock = threading.RLock()
        self._wake = threading.Event()   # señala cambios al hilo trabajador
        self._stop = threading.Event()   # solicita el cierre del hilo

        self._active = False
        self._duration: Optional[int] = None    # segundos; None = indefinido
        self._deadline: Optional[float] = None   # time.monotonic() de expiración

        self._thread = threading.Thread(
            target=self._run, name="keepawake-worker", daemon=True
        )
        self._thread.start()

    # --- propiedades de solo lectura para la interfaz ---
    @property
    def active(self) -> bool:
        return self._active

    @property
    def duration(self) -> Optional[int]:
        return self._duration

    def remaining(self) -> Optional[int]:
        """Segundos restantes del temporizador, o None si está inactivo/indefinido."""
        with self._lock:
            if not self._active or self._deadline is None:
                return None
            return max(0, int(round(self._deadline - time.monotonic())))

    # --- mutaciones ---
    def enable(self) -> None:
        with self._lock:
            self._active = True
            self._arm_deadline_locked()
        self._notify_and_wake()

    def disable(self) -> None:
        with self._lock:
            self._active = False
            self._deadline = None
        self._notify_and_wake()

    def toggle(self) -> None:
        with self._lock:
            should_enable = not self._active
        self.enable() if should_enable else self.disable()

    def set_duration(self, seconds: Optional[int]) -> None:
        """Fija la duración del temporizador (None = indefinido). Si ya está activo,
        reinicia la cuenta atrás desde ahora."""
        with self._lock:
            self._duration = seconds
            if self._active:
                self._arm_deadline_locked()
        self._notify_and_wake()

    def shutdown(self) -> None:
        """Restaura la energía normal y detiene el hilo trabajador."""
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=2.0)
        _set_execution_state(ES_CONTINUOUS)  # garantía de limpieza aunque expire el join

    # --- internos ---
    def _arm_deadline_locked(self) -> None:
        self._deadline = None if self._duration is None else time.monotonic() + self._duration

    def _flags_locked(self) -> int:
        # "Mantener despierto" implica mantener también la pantalla encendida.
        if self._active:
            return ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        return ES_CONTINUOUS

    def _notify(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                pass  # la interfaz nunca debe tumbar al controlador

    def _notify_and_wake(self) -> None:
        self._wake.set()
        self._notify()

    def _run(self) -> None:
        _set_execution_state(ES_CONTINUOUS)  # estado conocido al arrancar
        while not self._stop.is_set():
            with self._lock:
                flags = self._flags_locked()
                deadline = self._deadline
                active = self._active

            _set_execution_state(flags)

            # Dormir hasta el reafirmado periódico o la expiración del temporizador.
            timeout = _REASSERT_INTERVAL
            if active and deadline is not None:
                timeout = min(timeout, max(0.0, deadline - time.monotonic()))

            if self._wake.wait(timeout):
                self._wake.clear()
                continue

            # Venció el wait sin cambios: comprobar expiración del temporizador.
            expired = False
            with self._lock:
                if (
                    self._active
                    and self._deadline is not None
                    and time.monotonic() >= self._deadline
                ):
                    self._active = False
                    self._deadline = None
                    expired = True
            if expired:
                _set_execution_state(ES_CONTINUOUS)
                self._notify()

        _set_execution_state(ES_CONTINUOUS)  # salida: restaurar energía normal
