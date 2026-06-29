<p align="center">
  <img src="assets/logo.png" alt="App Icon" width="150" height="150">
</p>


# Smart Menu

Utilidades de Windows desde la **bandeja del sistema**, pensadas para ir creciendo con más
funciones. Al hacer clic en el ícono se despliega, **junto al cursor**, un panel flotante
moderno.

## Funciones

### Keep Awake
- **Mantener despierto** (switch principal: gris = inactivo, azul = activo): evita la
  suspensión / hibernación del sistema **y** que se apague la pantalla
  (API Win32 `SetThreadExecutionState`).
- **Duración**: Indefinido, 30 min, 1 h o 2 h. Al cumplirse, se desactiva solo.
- **Iniciar con Windows**: arranca al iniciar sesión (registro `Run` del usuario).
- **Salir**: restaura el comportamiento de energía normal y cierra la app.

### Atenuar pantalla
- Deslizador (0–100 %) que **oscurece el monitor donde se abre el panel**. Cada monitor
  guarda su propio nivel; el deslizador refleja/controla el del monitor actual.
- Combina dos mecanismos para cubrir el mayor número de casos:
  - una **superposición** negra semitransparente, *click-through* (deja pasar el ratón) y sin
    foco, que se **mantiene siempre al frente** (se reafirma de forma continua, así que
    también atenúa video/juegos en ventana o *borderless* y otras apps siempre-visibles);
  - una **rampa de gamma** del adaptador que oscurece además lo que una ventana no puede
    cubrir: apps a **pantalla completa** (incluida la *exclusive fullscreen* de muchos juegos).
- La atenuación persiste aunque cierres el panel; vuelve a 0 % o usa **Salir** para quitarla
  (al salir se restaura la gamma original del monitor).
- Salvedades de la parte de gamma: **no** tiene efecto con **HDR** activado, afecta al
  **color global** del monitor y su oscurecimiento es **limitado** (Windows acota la rampa).
  Por eso, con niveles altos, el propio panel y la bandeja también se ven algo más tenues.

### Hotkeys globales
- Atajos del sistema (funcionan con cualquier app en primer plano). Se reasignan desde la
  ventana de **Preferencias** (botón en el panel): clic en un atajo y pulsa la nueva
  combinación. También editables en `%APPDATA%\Smart Menu\config.json`. Por defecto:
  - **Ctrl+Alt+K** — activar/desactivar Mantener despierto.
  - **Ctrl+Alt+S** — mostrar/ocultar el panel.
  - **Ctrl+Alt+V** — abrir el historial de portapapeles.
  - **Ctrl+Alt+↑ / Ctrl+Alt+↓** — subir/bajar la atenuación del monitor bajo el cursor.

### Historial de portapapeles
- Guarda los últimos **N** elementos copiados (**texto e imágenes**), accesible desde el panel
  ("Abrir historial") o con su hotkey. Elegir un elemento lo vuelve a copiar; con **Auto-pegar**
  activado, además lo pega (Ctrl+V) en la app donde estabas.
- Dentro del propio historial puedes activar/desactivar **Auto-pegar** y ajustar la
  **profundidad** (5–200) con un deslizador.
- **Persiste** entre reinicios en `%APPDATA%\Smart Menu` (texto en JSON, imágenes en PNG). Sin
  duplicados: volver a copiar algo lo mueve arriba.

## Interacción

- **Clic izquierdo o derecho** en el ícono de la bandeja → abre el panel junto al cursor.
- El **ícono** es el logo de la app: a **color** cuando Keep Awake está activo y en **gris**
  cuando está inactivo. El tooltip también indica el estado.
- Construido con **PySide6 (Qt)**: aparece con animación (fade + slide), switches animados,
  esquinas redondeadas y sombra; sigue el tema claro/oscuro del sistema y se oculta al hacer
  clic fuera (o con `Esc`).
- Una sola instancia a la vez (mutex con nombre).

## Requisitos

- Windows 10/11 + Python 3.10 o superior (probado con 3.14).
- Dependencias (declaradas en `pyproject.toml`): `PySide6` (UI/animaciones y bandeja) y
  `Pillow` (genera el ícono); `pyinstaller` solo para empaquetar (extra `build`). Hotkeys y
  portapapeles usan solo `ctypes`/Qt, sin dependencias extra.

## Instalación y ejecución

```powershell
# Dependencias (elige una opción):
python -m pip install -r requirements.txt   # rápido (incluye PyInstaller)
python -m pip install -e ".[build]"          # desde pyproject.toml; añade el comando `smart-menu`

# Ejecutar (sin ventana de consola):
pythonw -m smart_menu

# Depuración (con logs en consola):
python -m smart_menu
```

(También: `python run.py`, o el comando `smart-menu` si instalaste con `pip install -e`.)

Los recursos viven en `assets/`: `logo.png` es la imagen de la app e `icon.ico` (generado a
partir de ella) es el ícono del ejecutable.

## Empaquetar como .exe

```powershell
./build.ps1
```

Genera `dist\Smart Menu.exe` (un solo archivo, sin consola). Internamente: instala
dependencias, crea `assets/icon.ico` desde `assets/logo.png` y ejecuta PyInstaller con
`Smart Menu.spec` (empaqueta PySide6/Qt vía sus *hooks* e incluye la carpeta `assets/`).

> Nota: al incluir Qt, el `.exe` es bastante más grande (~55 MB) y el arranque *onefile* puede
> ser algo más lento. Se desactiva UPX en el `.spec` (comprimir DLLs de Qt puede dar problemas).
> Alternativa para arrancar más rápido: pasar a `--onedir` (`COLLECT`) en el `.spec`.

## Verificación

1. Ejecuta la app, abre el panel y activa el switch **Mantener despierto**.
2. En una consola **como administrador**:

   ```powershell
   powercfg /requests
   ```

   Debe aparecer el proceso bajo **SYSTEM** y bajo **DISPLAY**. Al desactivar, desaparecen.
3. **Iniciar con Windows**: tras activar ese switch,

   ```powershell
   reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v SmartMenu
   ```

   debe mostrar el valor; al desactivarlo, desaparece.
4. **Salir** restaura la energía: después, `powercfg /requests` no lista el proceso.
5. **Hotkeys**: con otra app en primer plano, prueba **Ctrl+Alt+S** (panel), **Ctrl+Alt+K**
   (alterna Keep Awake) y **Ctrl+Alt+V** (historial de portapapeles).
6. **Portapapeles**: copia varios textos/imágenes, abre el historial y elige uno (se copia;
   con auto-pegar, se pega en la app previa). Reinicia la app: el historial persiste.

## Estructura

```
Smart Menu/
├─ smart_menu/          # paquete con el código fuente
│  ├─ __init__.py
│  ├─ __main__.py       # permite `python -m smart_menu`
│  ├─ app.py            # App PySide6 (panel animado) + cableado + main()
│  ├─ resources.py      # acceso a assets/ (logo, íconos tintados, icon.ico)
│  ├─ widgets.py        # widgets con animación (switch, control segmentado)
│  ├─ tray.py           # ícono de bandeja (QSystemTrayIcon)
│  ├─ power.py          # PowerController: energía + hilo + temporizador
│  ├─ dimmer.py         # atenuación por monitor (superposición Qt + gamma)
│  ├─ gamma.py          # rampa de gamma por dispositivo (pantalla completa)
│  ├─ winutil.py        # utilidades Win32 (estilos de ventana, gamma, auto-pegar)
│  ├─ startup.py        # iniciar con Windows (registro Run, valor SmartMenu)
│  ├─ hotkeys.py        # hotkeys globales (RegisterHotKey + filtro de eventos Qt)
│  ├─ clipboard.py      # historial de portapapeles (texto/imagen) + popup
│  ├─ preferences.py    # ventana de Preferencias (reasignar hotkeys)
│  └─ config.py         # ajustes en %APPDATA%\Smart Menu\config.json
├─ assets/              # recursos: logo.png, icon.ico e íconos de botones (PNG)
├─ run.py               # lanzador (python run.py / entrada de PyInstaller)
├─ pyproject.toml       # metadatos del paquete (nombre, versión, dependencias)
├─ LICENSE              # GNU GPL v3 (o posterior)
├─ Smart Menu.spec      # configuración de PyInstaller
├─ build.ps1            # empaquetado a .exe
└─ requirements.txt     # dependencias (reflejan pyproject, para build.ps1)
```

## Notas

- No requiere privilegios de administrador para funcionar.
- Todo corre en el hilo principal (Qt); el controlador de energía usa un hilo trabajador que
  avisa a la interfaz mediante una señal Qt.
- Tanto el clic izquierdo como el derecho abren el panel; no hay menú nativo de Windows.
- Si cierras el proceso de cualquier modo, Windows libera el bloqueo de energía (y la gamma se
  restaura al cerrar sesión).

## Autor y licencia

- Autor: **Iván Ramírez**.
- Licencia: **GNU General Public License v3.0 o posterior** (`GPL-3.0-or-later`). El texto
  completo está en [`LICENSE`](LICENSE).
