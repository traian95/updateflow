# Updated streamlit_app.py

import streamlit as st
import sys
from pathlib import Path

# Add the Soft Ofertare Usi directory to Python path
sys.path.append(str(Path(__file__).parent / "Soft Ofertare Usi"))

# Set page configuration
st.set_page_config(
    page_title="Naturen Flow",
    page_icon="🌿",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Import and run the login UI
from streamlit_web.main_ui import render_login as run

if __name__ == "__main__":
    run()