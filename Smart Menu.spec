# -*- mode: python ; coding: utf-8 -*-
# Paquete en smart_menu/ con entrada run.py (raíz); recursos en assets/ (se empaquetan en
# assets/ del bundle). PyInstaller incluye PySide6 vía sus hooks integrados; los módulos del
# paquete se detectan siguiendo los imports de run.py -> smart_menu.app.

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'customtkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Smart Menu',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX puede corromper/retrasar DLLs de Qt; mejor desactivado aquí
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
