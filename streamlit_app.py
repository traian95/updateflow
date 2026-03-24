"""
Streamlit Cloud entry point (repo root).

The main desktop offer app lives in the `Soft Ofertare Usi/` subfolder (CustomTkinter);
it is not runnable on Streamlit Cloud. Replace or extend this file with your web UI.
"""

import streamlit as st

st.set_page_config(page_title="Naturen Dashboard", page_icon="📋", layout="centered")

st.title("Naturen Flow")
st.write(
    "This repository is configured for **Streamlit Cloud** using `streamlit_app.py` at the repo root."
)
st.info(
    "**Desktop app:** run `Soft Ofertare Usi/main.py` (or the packaged `ofertare.exe`) locally — "
    "that code is not deployed here."
)
st.caption("Edit `streamlit_app.py` and root `requirements.txt` to build your web app.")
