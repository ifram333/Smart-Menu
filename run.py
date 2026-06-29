"""Punto de entrada de Smart Menu (ejecución directa y empaquetado con PyInstaller).

Equivale a ``python -m smart_menu`` pero como script en la raíz: Python añade esta carpeta
a ``sys.path``, de modo que el paquete ``smart_menu`` se importa sin configuración extra.
"""

from smart_menu.app import main

if __name__ == "__main__":
    main()
