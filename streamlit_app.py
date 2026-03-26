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

# Initialize session state
if "logged_user" not in st.session_state:
    st.session_state.logged_user = None
if "page" not in st.session_state:
    st.session_state.page = "login"

def render_main_app():
    """Render the main application after login"""
    st.markdown("# 🌿 Welcome to Naturen Flow")
    st.markdown(f"**Logged in as:** {st.session_state.logged_user}")
    
    # Add a simple logout button
    if st.button("Logout", type="primary"):
        st.session_state.logged_user = None
        st.session_state.page = "login"
        st.rerun()
    
    st.markdown("---")
    st.markdown("## Dashboard")
    st.markdown("Your main application content would go here.")
    
    # Placeholder for future features
    st.markdown("### Features coming soon:")
    st.markdown("- Order management")
    st.markdown("- Inventory tracking")
    st.markdown("- Reporting dashboard")

def render_login():
    """Render login page"""
    from streamlit_web.main_ui import render_login as run_login
    run_login()

# Main routing logic
if st.session_state.logged_user:
    render_main_app()
else:
    render_login()

if __name__ == "__main__":
    pass  # Routing handled above