import streamlit as st
from ofertare.auth_utils import hash_parola as hash_parola_fn
from ofertare.config import AppConfig, get_database_path
from ofertare.db import get_user_for_login, open_db, init_schema
from pathlib import Path
from typing import Any

_LOGO_NATUREN_PATH = Path(__file__).resolve().parent / "assets" / "naturen2.png"

LOGIN_CSS = """
<style>
    body { background: #1e1e1e; color: #eceff1; }
    .stApp { background: #1e1e1e; }
    h1, h2, h3 { color: #43a047 !important; }
    .stTextInput input {
        background-color: #2a2a2a !important;
        color: #ffffff !important;
        border: 1px solid #424242 !important;
    }
    .stButton > button {
        background-color: #43a047 !important;
        color: white !important;
        width: 100%;
        font-weight: bold;
    }
    .stButton > button:hover {
        background-color: #2e7d32 !important;
    }
</style>
"""

def _try_login(username: str, password: str, cfg: AppConfig) -> dict[str, Any]:
    """Authenticate user against database or config"""
    try:
        db = open_db(get_database_path())
        init_schema(db.cursor, db.conn)
        row = get_user_for_login(db.cursor, username)
        close_conn = getattr(db.conn, "close", None)
        if callable(close_conn):
            close_conn()
        if row:
            password_hash, approved, username_stocat = row[0], row[1], (row[2] if len(row) > 2 else username)
            blocked = row[3] if len(row) > 3 else 0
            if not approved:
                return {"ok": False, "reason": "not_approved"}
            if blocked:
                return {"ok": False, "reason": "blocked"}
            if hash_parola_fn(password) != password_hash:
                return {"ok": False, "reason": "invalid"}
            return {"ok": True, "user": str(username_stocat)}
        if username.strip().lower() == (cfg.login_user or "").strip().lower() and password == cfg.login_password:
            return {"ok": True, "user": username.strip()}
        return {"ok": False, "reason": "invalid"}
    except Exception as e:
        return {"ok": False, "reason": "error", "error": str(e)}

def render_login_custom() -> None:
    """Professional centered login UI - NO st.set_page_config() here!"""
    st.markdown(
        '<style>[data-testid="stSidebar"]{visibility:hidden;min-width:0!important;width:0!important;}</style>',
        unsafe_allow_html=True,
    )
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    
    cfg = AppConfig()
    
    # Perfect centering with custom CSS
    st.markdown("""
    <style>
    .login-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        padding: 20px;
    }
    .logo-container {
        text-align: center;
        margin-bottom: 30px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Centered container with better proportions
    col1, col2, col3 = st.columns([1.5, 2, 1.5])
    
    with col2:
        st.markdown("<div class='login-container'>", unsafe_allow_html=True)
        
        # Logo perfectly centered
        if _LOGO_NATUREN_PATH.is_file():
            st.markdown("<div class='logo-container'>", unsafe_allow_html=True)
            st.image(str(_LOGO_NATUREN_PATH), width=200)
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Title centered
        st.markdown("<h1 style='text-align: center; color: #43a047; margin-bottom: 10px;'>Naturen Flow</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; color: #eceff1; margin-bottom: 30px;'>Autentificare utilizator</h3>", unsafe_allow_html=True)
        
        # Login form
        with st.form("login_form"):
            user = st.text_input("👤 Utilizator", value=cfg.login_user or "")
            pw = st.text_input("🔒 Parolă", type="password")
            sub = st.form_submit_button("LOGIN", type="primary", use_container_width=True)
        
        if sub:
            r = _try_login(user, pw, cfg)
            if r.get("ok"):
                st.session_state.logged_user = r["user"]
                st.session_state.page = "main"
                st.success(f"✅ Bun venit, {r['user']}!")
                st.rerun()
            elif r.get("reason") == "not_approved":
                st.error("❌ Contul nu a fost aprobat de administrator.")
            elif r.get("reason") == "blocked":
                st.error("❌ Cont blocat.")
            elif r.get("reason") == "error":
                st.error(f"❌ Eroare conexiune: {r.get('error', '')}")
            else:
                st.error("❌ Utilizator sau parolă greșită.")
        
        st.markdown("</div>", unsafe_allow_html=True)