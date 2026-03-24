"""
Naturen Flow — punct de intrare Streamlit Cloud (repo root).

Aplicația desktop CustomTkinter rămâne în `Soft Ofertare Usi/main.py`;
varianta web importă pachetul `ofertare` din acel subfolder (Supabase + logică partajată).
"""

from __future__ import annotations

from streamlit_web.bootstrap import ensure_pkg_path

ensure_pkg_path()

from streamlit_web.main_ui import run

if __name__ == "__main__":
    run()
