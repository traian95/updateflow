# -*- coding: utf-8 -*-
"""Lansare procese Windows cu elevare UAC (fără dependență de modulul `main` în .exe)."""
from __future__ import annotations

import ctypes
import os
import sys


def launch_updater_elevated(updater_path: str, parameters: str, working_dir: str) -> None:
    """
    ShellExecuteW(..., \"runas\", updater.exe, ...) → prompt UAC.
    După succes: sys.exit(0) eliberează fișierele pentru suprascriere de către updater.
    """
    if sys.platform != "win32":
        raise OSError("launch_updater_elevated is only supported on Windows")
    if not os.path.isfile(updater_path):
        raise FileNotFoundError(f"Updater not found: {updater_path}")
    params = parameters if parameters else None
    cwd = working_dir if working_dir else None
    ret = int(ctypes.windll.shell32.ShellExecuteW(None, "runas", updater_path, params, cwd, 1))
    if ret <= 32:
        raise OSError(f"ShellExecuteW failed (code {ret})")
    sys.exit(0)
