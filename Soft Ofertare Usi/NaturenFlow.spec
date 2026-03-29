# -*- mode: python ; coding: utf-8 -*-
# NaturenFlow — PRODUCȚIE: Onedir multi-exe (PyInstaller 6+)
#
# Task 3 (prompt producție):
#   • COLLECT onedir → dist/NaturenFlow/
#   • Analysis A: main.py → NaturenFlow.exe, console=False, icon assets/icon.ico
#   • Analysis B: updater.py (rădăcină) → updater.exe, console=False, uac_admin=True
#   • Datas: assets/ → assets/, version.json → ., collect_data_files("customtkinter")
#
# updater.py la rădăcină (NU ofertare/updater.py) = exe mic, fără Supabase/UI în bundle.

import os

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
spec_dir = os.path.dirname(os.path.abspath(SPEC))

# --- ('assets/*', 'assets') + ('version.json', '.') + CTk ---
_app_datas = []
_assets = os.path.join(spec_dir, "assets")
if os.path.isdir(_assets):
    _app_datas.append((_assets, "assets"))
_vjson = os.path.join(spec_dir, "version.json")
if os.path.isfile(_vjson):
    _app_datas.append((_vjson, "."))
_app_datas += collect_data_files("customtkinter")

_icon = os.path.join(spec_dir, "assets", "icon.ico")
_exe_icon = _icon if os.path.isfile(_icon) else None

# --- Analysis A (Main) ---
a = Analysis(
    ["main.py"],
    pathex=[spec_dir],
    binaries=[],
    datas=_app_datas,
    hiddenimports=[
        "ofertare.elevation",
        "customtkinter",
        "PIL",
        "PIL.Image",
        "PIL._tkinter_finder",
        "requests",
        "certifi",
        "supabase",
        "postgrest",
        "realtime",
        "storage3",
        "packaging.version",
        "packaging.specifiers",
        "CTkMessagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# --- Analysis B (Updater) ---
b = Analysis(
    ["updater.py"],
    pathex=[spec_dir],
    binaries=[],
    datas=[],
    hiddenimports=["tkinter", "_tkinter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz_a = PYZ(a.pure)
pyz_b = PYZ(b.pure)

exe_app = EXE(
    pyz_a,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NaturenFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_exe_icon,
)

exe_updater = EXE(
    pyz_b,
    b.scripts,
    [],
    exclude_binaries=True,
    name="updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    uac_admin=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_app,
    a.binaries,
    a.zipfiles,
    a.datas,
    exe_updater,
    b.binaries,
    b.zipfiles,
    b.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NaturenFlow",
)
