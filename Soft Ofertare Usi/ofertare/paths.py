from __future__ import annotations

import os
import sys


def get_resource_path(relative_path: str) -> str:
    """
    Cale absolută către o resursă din proiect (assets/, version.json lângă exe etc.).

    - Script: rădăcina aplicației (folderul care conține `main.py` și `ofertare/`).
    - PyInstaller onedir: întâi `os.path.dirname(sys.executable)` (resurse distribuite
      lângă .exe), apoi `sys._MEIPASS` dacă fișierul e doar în bundle intern.
    """
    rel = relative_path.replace("/", os.sep).strip(os.sep)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        p_exe = os.path.normpath(os.path.join(exe_dir, rel))
        if os.path.exists(p_exe):
            return p_exe
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p_me = os.path.normpath(os.path.join(meipass, rel))
            if os.path.exists(p_me):
                return p_me
        return p_exe
    # Dezvoltare: `ofertare/paths.py` → părinte = rădăcina proiectului
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.normpath(os.path.join(root, rel))


def resource_path(relative_path: str) -> str:
    """Alias compatibil cu cod vechi; folosește aceeași logică ca `get_resource_path`."""
    return get_resource_path(relative_path)


def get_project_dir() -> str:
    """Directorul rădăcină al aplicației pentru resurse împachetate (bundle / proiect)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_app_dir() -> str:
    """Director lângă executabil (scriibil): app_settings.json, logs, version.json la runtime."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_asset_path(filename: str) -> str:
    # Prefer explicit image-asset folders first, then legacy root-level locations.
    candidates = [
        get_resource_path(os.path.join("assets", filename)),
        get_resource_path(os.path.join("assets", "images", filename)),
        get_resource_path(os.path.join("utils", "assets", "images", filename)),
        os.path.join(get_app_dir(), "utils", "assets", "images", filename),
        os.path.join(get_app_dir(), "assets", "images", filename),
        os.path.join(get_app_dir(), "assets", filename),
        os.path.join(get_project_dir(), "utils", "assets", "images", filename),
        os.path.join(get_project_dir(), "assets", "images", filename),
        os.path.join(get_project_dir(), "assets", filename),
        os.path.join(get_app_dir(), filename),
        os.path.join(get_project_dir(), filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]
