from __future__ import annotations

import os
import sys


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_project_dir() -> str:
    """Directorul pentru asset-uri (logo, gif). La frozen folosește _MEIPASS (bundle) sau lângă exe."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return base
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__ + os.sep + ".."))


def get_app_dir() -> str:
    """Directorul aplicației (scriibil: lângă exe). Pentru app_settings.json, baza de date (dacă nu e în APPDATA)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__ + os.sep + ".."))


def resolve_asset_path(filename: str) -> str:
    # Prefer explicit image-asset folders first, then legacy root-level locations.
    # This keeps compatibility with older installers while supporting cleaned repository layout.
    candidates = [
        resource_path(os.path.join("assets", filename)),
        resource_path(os.path.join("assets", "images", filename)),
        resource_path(os.path.join("utils", "assets", "images", filename)),
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

