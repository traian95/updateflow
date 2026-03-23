# -*- mode: python ; coding: utf-8 -*-
# Spec pentru aplicația Ofertare (Soft_Ofertare.exe).
# Build script-ul rulează PyInstaller din rădăcina proiectului, deci getcwd() = ROOT.

import os

ROOT = os.getcwd()

# Asset-uri incluse în exe (extrase la rulare în _MEIPASS)
datas = []
for name in ('Naturen2.png', 'logo.ico', 'despre.gif'):
    p = os.path.join(ROOT, name)
    if os.path.isfile(p):
        datas.append((p, '.'))

a = Analysis(
    [os.path.join(ROOT, 'run_ofertare.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL.Image',
        'PIL.ImageSequence',
        'pandas',
        'fpdf',
        'requests',
        'ofertare',
        'ofertare.ui',
        'ofertare.config',
        'ofertare.db',
        'ofertare.auth_utils',
        'ofertare.paths',
        'ofertare.sync_service',
        'ofertare.pdf_export',
        'ofertare.serialization',
        'ofertare.services',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='Soft_Ofertare',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'logo.ico') if os.path.isfile(os.path.join(ROOT, 'logo.ico')) else None,
)
