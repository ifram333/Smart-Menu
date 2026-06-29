# build.ps1 — genera dist\Smart Menu.exe con PyInstaller (usa Smart Menu.spec).
# Uso (desde esta carpeta):  ./build.ps1
$ErrorActionPreference = "Stop"

# 1) Asegurar dependencias (PySide6, Pillow y pyinstaller, declarados en requirements.txt).
python -m pip install -r requirements.txt

# 2) Generar assets/icon.ico reutilizando el mismo diseño del ícono de la bandeja.
python run.py --make-ico

# 3) Empaquetar: un solo .exe, sin ventana de consola (config en Smart Menu.spec).
python -m PyInstaller --noconfirm "Smart Menu.spec"

Write-Host ""
Write-Host "Listo: dist\Smart Menu.exe"
