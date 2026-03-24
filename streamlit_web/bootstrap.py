"""Ensure the packaged app folder is on sys.path so `import ofertare` works on Streamlit Cloud."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_pkg_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    app_dir = root / "Soft Ofertare Usi"
    s = str(app_dir)
    if s not in sys.path:
        sys.path.insert(0, s)
    return app_dir
