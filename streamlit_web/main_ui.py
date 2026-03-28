"""
Interfață Streamlit — fluxuri aliniate cu `AplicatieOfertare` (ecran start + configurator).
"""

from __future__ import annotations

import math
import re
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from ofertare.auth_utils import hash_parola as hash_parola_fn
from ofertare.config import AppConfig, BNR_TIMEOUT_S, get_database_path
from ofertare.db import (
    get_all_clienti_telefon,
    get_categorii_distinct,
    get_client_by_id,
    get_client_by_name,
    get_client_id_by_name,
    get_clienti_with_oferte_count,
    get_colectii_produse,
    get_decor_finisaj_pairs,
    get_istoric_oferte,
    get_manere_engs_finisaje,
    get_manere_engs_modele,
    get_manere_engs_pret_lei,
    get_modele_produse,
    get_offers_by_client,
    get_parchet_dimensiune_pret,
    get_pret_decor_finisaj,
    get_pret_tocuri,
    get_pret_tocuri_decor_finisaj,
    get_user_can_see_all,
    get_user_contact_phone,
    get_user_for_login,
    get_user_full_name,
    get_user_privileges,
    init_schema,
    insert_client,
    insert_offer,
    open_db,
    search_produse,
)
from ofertare.pdf_export import apply_majuscule_line_stoc_erkado
from ofertare.serialization import dumps_offer_items, loads_offer_items
from ofertare.services import fetch_bnr_eur_rate

from streamlit_web.offer_math import (
    compute_cart_totals,
    estimate_parchet_line_lei_tva,
    get_furnizor_from_item,
    get_item_tip,
    parse_discount_percent,
    validate_offer_usi_toc,
)
from streamlit_web.pdf_helper import build_offer_pdf_bytes
from streamlit_web.stoc_decor_labels import values_dropdown_usi_stoc
from streamlit_web.toc_pairing import required_toc_decor_option

MANER_ENGER_DECOR_MANER = "Măner"

_LOGO_NATUREN_PATH = Path(__file__).resolve().parent / "assets" / "naturen2.png"

CATEGORII_PARCHET = [
    "Parchet Laminat Stoc",
    "Parchet Laminat Comanda",
    "Parchet Spc Stoc",
    "Parchet Spc Floorify",
    "Parchet Triplu Stratificat",
]

CORP_CSS = """
<style>
    .block-container { padding-top: 0.65rem; padding-bottom: 1.25rem; max-width: 1440px; }
    div[data-testid="stHeader"] { background: #1a1a1a; }
    .stApp { background: #1e1e1e; color: #eceff1; }
    h1, h2, h3 { color: #43a047 !important; }
    .nf-page-head {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem 1rem;
        margin-bottom: 0.35rem;
    }
    .nf-page-head h2 { margin: 0 !important; font-size: 1.35rem !important; line-height: 1.2 !important; }
    .nf-dev-pill {
        font-size: 0.8rem;
        padding: 0.25rem 0.65rem;
        border-radius: 4px;
        background: #2a3f2e;
        border: 1px solid #43a047;
        color: #c8e6c9;
    }
    /* Card titles inside bordered containers */
    .nf-card-title {
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #81c784;
        margin: -4px 0 10px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid #3d4a3f;
    }
    .nf-fin-block {
        background: #1a231c;
        border-radius: 6px;
        padding: 12px 14px;
        border: 1px solid #2d4a32;
        margin: 4px 0 2px 0;
        font-size: 0.95rem;
        line-height: 1.65;
    }
    .nf-fin-block strong { color: #c8e6c9 !important; }
    .nf-fin-total { font-size: 1.08rem; margin-top: 6px; padding-top: 8px; border-top: 1px solid #3d4a3f; }
    .nf-actions-row { margin-top: 0.35rem; }
</style>
"""

# Configurator: dashboard compact, fără scroll pe pagină; scroll doar în coloane / zone interne
CONFIGURATOR_PAGE_CSS = """
<style>
    /* Zona principală: încape în viewport; scroll doar în coloane, nu pe pagină */
    section.main {
        overflow: hidden !important;
        max-height: 100vh !important;
        box-sizing: border-box !important;
    }
    section.main > div.block-container {
        max-width: 100% !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding: 1rem clamp(0.35rem, 0.9vw, 0.75rem) !important;
        max-height: 100vh !important;
        box-sizing: border-box !important;
    }
    section.main [data-testid="stVerticalBlock"] { gap: 0.35rem !important; }
    section.main h4 { font-size: 0.95rem !important; margin-top: 0.15rem !important; margin-bottom: 0.25rem !important; }
    section.main h5 { font-size: 0.82rem !important; margin-top: 0.1rem !important; margin-bottom: 0.2rem !important; }
    section.main [data-testid="stTabs"] { margin-top: 0 !important; }
    section.main [data-testid="stTabs"] [role="tablist"] { min-height: 2.1rem !important; gap: 0.25rem !important; }
    section.main [data-testid="stTabs"] button { padding: 0.2rem 0.5rem !important; font-size: 0.82rem !important; }
    /* Grilă 3 coloane ~36% / 36% / 28% — fără scroll pe pagină, scroll în coloană */
    section.main div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3)) {
        align-items: stretch !important;
        flex-wrap: nowrap !important;
        max-height: calc(100vh - 4.75rem) !important;
        min-height: 0 !important;
    }
    section.main div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3)) > div[data-testid="column"]:nth-child(1) {
        flex: 0 1 36% !important;
        min-width: 240px !important;
        max-width: 40% !important;
        max-height: calc(100vh - 4.75rem) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding-right: 2px !important;
    }
    section.main div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3)) > div[data-testid="column"]:nth-child(2) {
        flex: 1 1 36% !important;
        min-width: 280px !important;
        max-height: calc(100vh - 4.75rem) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding-right: 2px !important;
    }
    section.main div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3)) > div[data-testid="column"]:nth-child(3) {
        flex: 0 1 28% !important;
        min-width: 220px !important;
        max-width: 32% !important;
        max-height: calc(100vh - 4.75rem) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding-right: 2px !important;
    }
    section.main [data-testid="column"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3)) > div[data-testid="column"] {
        flex: 1 1 0% !important;
        min-width: 0 !important;
        max-width: none !important;
        width: auto !important;
        max-height: none !important;
        overflow: visible !important;
    }
    /* Carduri compacte — mai puțin spațiu vertical între secțiuni */
    section.main [data-testid="column"] [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 6px !important;
        border: 1px solid #424242 !important;
        background: #252525 !important;
        padding: 0.4rem 0.5rem 0.45rem 0.5rem !important;
        margin-bottom: 0.22rem !important;
    }
    section.main [data-testid="column"] .nf-card-title {
        font-size: 0.72rem !important;
        margin: -2px 0 6px 0 !important;
        padding-bottom: 4px !important;
    }
    section.main [data-testid="column"] .nf-fin-block {
        padding: 6px 8px !important;
        font-size: 0.82rem !important;
        line-height: 1.4 !important;
        margin: 0 !important;
        background: #1a231c !important;
        border: 1px solid #2d4a32 !important;
        border-radius: 6px !important;
    }
    section.main [data-testid="column"] .nf-fin-total { font-size: 0.9rem !important; margin-top: 2px !important; padding-top: 4px !important; }
    /* Scroll doar în zona listei produse (tab „Produse în ofertă”) */
    section.main div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(3)) > div[data-testid="column"]:nth-child(2) [role="tabpanel"] {
        max-height: min(42vh, 380px) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }
    div[data-testid="stDialog"] > div {
        max-width: min(520px, 94vw) !important;
    }
</style>
"""

# Taburi verticale în sidebar (similar meniului orizontal din desktop)
SIDEBAR_NAV_CSS = """
<style>
    /* Radio ca „taburi” întunecate, colțuri rotunjite */
    [data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 0.35rem;
        flex-direction: column;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        display: flex !important;
        align-items: center;
        background: #2d2d2d !important;
        border: 1px solid #5a5a5a !important;
        border-radius: 4px !important;
        padding: 0.55rem 0.75rem !important;
        margin: 0 !important;
        width: 100%;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] {
        border-radius: 4px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        border-color: #2e7d32 !important;
        background: #1e3a24 !important;
        box-shadow: inset 0 0 0 1px #43a047;
    }
</style>
"""


def _slug(titlu: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in titlu)


def _visible_categories(cursor) -> list[str]:
    ordine = [
        "Usi Interior",
        "Usi intrare apartament",
        "Tocuri",
        "Manere",
        "Accesorii",
        "Parchet Laminat Stoc",
        "Parchet Laminat Comanda",
        "Parchet Spc Stoc",
        "Parchet Spc Floorify",
        "Parchet Triplu Stratificat",
    ]
    din_db = get_categorii_distinct(cursor)
    exclude = {"Accesorii", "Izolatie parchet", "Izolatii parchet", "Izolatie", "Izolatii"}

    def viz(cat: str) -> bool:
        c = (cat or "").strip()
        if not c or c in CATEGORII_PARCHET:
            return False
        if c in exclude:
            return False
        return True

    result = [c for c in ordine if c in din_db and viz(c)]
    for c in din_db:
        if c not in result and viz(c):
            result.append(c)
    return result or ["Usi Interior", "Tocuri", "Manere"]


def _privileges_tuple(username: str, cursor, cfg: AppConfig) -> tuple[int, int, int, int, int]:
    cfg_u = (cfg.login_user or "").strip().lower()
    app_u = (username or "").strip().lower()
    config_dev_match = bool(cfg_u and app_u and cfg_u == app_u)
    pr = get_user_privileges(cursor, username) if username else None
    if pr:
        priv_list = list(pr)
        while len(priv_list) < 5:
            priv_list.append(0)
        supabase_dev = int(priv_list[4]) == 1
        priv_list[4] = 1 if (supabase_dev or config_dev_match) else 0
        return tuple(priv_list)  # type: ignore[return-value]
    can_dev = 1 if config_dev_match else 0
    return (1, 15, 1, 1, can_dev)


def _init_state() -> None:
    if "logged_user" not in st.session_state:
        st.session_state.logged_user = ""
    if "page" not in st.session_state:
        st.session_state.page = "login"
    if "cos" not in st.session_state:
        st.session_state.cos = []
    if "curs_euro" not in st.session_state:
        cfg = AppConfig()
        st.session_state.curs_euro = float(cfg.curs_euro_initial)
        st.session_state.curs_bnr_real = float(cfg.curs_bnr_fallback)
    if "tva" not in st.session_state:
        st.session_state.tva = float(AppConfig().tva_procent)
    if "client" not in st.session_state:
        st.session_state.client = {
            "nume": "",
            "tel": "",
            "adresa": "",
            "email": "",
            "zi": datetime.now().strftime("%d"),
            "luna": [
                "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
                "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
            ][datetime.now().month - 1],
            "an": str(datetime.now().year),
        }
    if "furnizor_global" not in st.session_state:
        st.session_state.furnizor_global = "Stoc"
    if "safe_mode" not in st.session_state:
        st.session_state.safe_mode = True
    if "discount" not in st.session_state:
        st.session_state.discount = "0"
    if "readonly_offer" not in st.session_state:
        st.session_state.readonly_offer = False
    if "dev_mode" not in st.session_state:
        st.session_state.dev_mode = False
    if "id_oferta_curenta" not in st.session_state:
        st.session_state.id_oferta_curenta = None
    if "data_oferta_curenta" not in st.session_state:
        st.session_state.data_oferta_curenta = ""
    if "masuratori_lei" not in st.session_state:
        st.session_state.masuratori_lei = 0.0
    if "transport_lei" not in st.session_state:
        st.session_state.transport_lei = 0.0
    if "mentiuni" not in st.session_state:
        st.session_state.mentiuni = ""
    if "afiseaza_mentiuni_pdf" not in st.session_state:
        st.session_state.afiseaza_mentiuni_pdf = False
    if "conditii_pdf" not in st.session_state:
        st.session_state.conditii_pdf = False
    if "termen_livrare" not in st.session_state:
        st.session_state.termen_livrare = "0"
    if "sidebar_view" not in st.session_state:
        st.session_state.sidebar_view = "main"
    if "parchet_calculator_open" not in st.session_state:
        st.session_state.parchet_calculator_open = False
    if "configurator_right_panel" not in st.session_state:
        st.session_state.configurator_right_panel = "ajustari"


def _db():
    db = open_db(get_database_path())
    init_schema(db.cursor, db.conn)
    return db


def _try_login(username: str, password: str, cfg: AppConfig) -> dict[str, Any]:
    try:
        db = _db()
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


def _parse_termen_livrare_zile(raw: str) -> str:
    nums = re.findall(r"\d+", raw or "")
    if not nums:
        return "0"
    if len(nums) == 1:
        return str(max(0, min(200, int(nums[0]))))
    st_ = max(0, min(200, int(nums[0])))
    dr = max(0, min(200, int(nums[1])))
    if st_ > dr:
        st_, dr = dr, st_
    return f"{st_}-{dr}"


def _add_usa_to_cos(
    cursor,
    titlu: str,
    furnizor: str,
    colectie: str,
    model: str,
    decor_display: str,
    pairs: list[tuple[str, str]],
    decor_labels: list[str],
    sel_decor: str,
    pret_val: float,
) -> None:
    dec_display = decor_display
    if titlu == "Usi Interior" and furnizor == "Erkado":
        dec_display = decor_display.strip()
    usa_finisaj_sel = ""
    usa_decor_sel = ""
    try:
        idx = decor_labels.index(sel_decor)
        usa_decor_sel, usa_finisaj_sel = pairs[idx]
    except (ValueError, IndexError):
        usa_decor_sel = dec_display
        usa_finisaj_sel = sel_decor
    if furnizor == "Erkado":
        fin_e = (usa_finisaj_sel or "").strip()
        if fin_e:
            nume = f"Usa {colectie} {model} ({dec_display} / {fin_e})"
        else:
            nume = f"Usa {colectie} {model} ({dec_display})"
    else:
        nume = f"Usa {colectie} {model} ({dec_display})"
    st.session_state.cos.append(
        {
            "nume": nume,
            "pret_eur": pret_val,
            "qty": 1,
            "tip": "usi",
            "furnizor": furnizor,
            "usa_decor": usa_decor_sel,
            "usa_finisaj": usa_finisaj_sel,
            "usa_decor_display": dec_display,
        }
    )


def _add_toc_to_cos(
    cursor,
    furnizor: str,
    tip_toc: str,
    dim: str,
    toc_display: str,
    pairs: list[tuple[str, str]],
    decor_labels: list[str],
    pret_val: float,
) -> None:
    toc_decor = ""
    toc_finisaj = toc_display
    if furnizor == "Stoc":
        usi_match = [i for i in st.session_state.cos if get_item_tip(i) == "usi" and get_furnizor_from_item(i) == furnizor]
        tocuri_match = [
            i for i in st.session_state.cos if get_item_tip(i) == "tocuri" and get_furnizor_from_item(i) == furnizor
        ]
        idx_next = len(tocuri_match)
        if idx_next < len(usi_match):
            usa_item = usi_match[idx_next]
            toc_decor = (usa_item.get("usa_decor") or usa_item.get("usa_decor_display") or "").strip()
            toc_finisaj = (usa_item.get("usa_finisaj") or "").strip()
            if toc_decor and toc_finisaj:
                toc_display = f"{toc_decor} / {toc_finisaj}"
            else:
                toc_display = toc_decor or toc_finisaj or "Automat din usa"
    try:
        idx = decor_labels.index(toc_display)
        toc_decor, toc_finisaj = pairs[idx]
    except (ValueError, IndexError):
        pass
    parte = f"Toc {tip_toc} Drept {dim}" if (tip_toc and dim) else "Toc"
    nume = f"{parte} ({toc_display})"
    st.session_state.cos.append(
        {
            "nume": nume,
            "pret_eur": pret_val,
            "qty": 1,
            "tip": "tocuri",
            "furnizor": furnizor,
            "toc_decor": toc_decor,
            "toc_finisaj": toc_finisaj,
            "toc_tip_toc": tip_toc,
            "toc_dimensiune": dim,
        }
    )


def render_login() -> None:
    st.markdown(
        '<style>[data-testid="stSidebar"]{visibility:hidden;min-width:0!important;width:0!important;}</style>',
        unsafe_allow_html=True,
    )
    st.markdown(CORP_CSS, unsafe_allow_html=True)
    cfg = AppConfig()
    st.title("Naturen Flow")
    st.subheader("Autentificare utilizator")
    with st.form("login_form"):
        user = st.text_input("Utilizator", value=cfg.login_user or "")
        pw = st.text_input("Parolă", type="password")
        sub = st.form_submit_button("LOGIN", type="primary")
    if sub:
        r = _try_login(user, pw, cfg)
        if r.get("ok"):
            st.session_state.logged_user = r["user"]
            st.session_state.page = "start"
            st.session_state.sidebar_view = "main"
            st.session_state["nav_radio"] = "Acasă"
            st.rerun()
        elif r.get("reason") == "not_approved":
            st.error("Contul nu a fost aprobat de administrator.")
        elif r.get("reason") == "blocked":
            st.error("Cont blocat.")
        elif r.get("reason") == "error":
            st.error(f"Eroare conexiune: {r.get('error', '')}")
        else:
            st.error("Utilizator sau parolă greșită.")


def render_sidebar_nav() -> None:
    """Meniuri (ISTORIC, CĂUTARE, MOD DEV) în sidebar, ca taburi verticale."""
    st.markdown(SIDEBAR_NAV_CSS, unsafe_allow_html=True)
    cfg = AppConfig()
    db = _db()
    priv = _privileges_tuple(st.session_state.logged_user, db.cursor, cfg)
    can_dev = priv[4] == 1
    close_conn = getattr(db.conn, "close", None)
    if callable(close_conn):
        close_conn()

    with st.sidebar:
        if _LOGO_NATUREN_PATH.is_file():
            st.image(str(_LOGO_NATUREN_PATH), use_container_width=True)
        st.markdown("### Naturen Flow")
        st.caption("Navigare")
        choice = st.radio(
            "Meniu",
            options=["Acasă", "Istoric", "Căutare clienți"],
            key="nav_radio",
            label_visibility="collapsed",
        )
        if choice == "Acasă":
            st.session_state.sidebar_view = "main"
        elif choice == "Istoric":
            st.session_state.sidebar_view = "istoric"
        else:
            st.session_state.sidebar_view = "cautare"

        if can_dev:
            st.markdown("---")
            if st.button("MOD DEV", use_container_width=True, type="secondary", key="sidebar_mod_dev"):
                st.session_state.page = "dev_pw"
                st.rerun()

        st.divider()
        st.caption(f"👤 {st.session_state.logged_user}")
        if st.button("Ieșire", use_container_width=True, key="sidebar_logout"):
            st.session_state.logged_user = ""
            st.session_state.page = "login"
            st.session_state.cos = []
            st.rerun()


def _render_istoric_panel(db) -> None:
    pk = st.session_state.page
    st.markdown("## Istoric oferte")
    q = st.text_input("Caută după nume client", key=f"istoric_q_{pk}")
    uf = st.selectbox("Utilizator", ["(toți)"] + [st.session_state.logged_user], key=f"istoric_u_{pk}")
    rows = get_istoric_oferte(
        db.cursor,
        f"%{q}%",
        utilizator_creat=st.session_state.logged_user,
        utilizator_filter=None if uf == "(toți)" else uf.replace("(toți)", "").strip() or None,
    )
    for rid, nume, total, data_o, detalii, avans, ucreate in rows[:80]:
        with st.container():
            st.write(f"**#{rid}** {nume} — {data_o} — {total:.2f} LEI — {ucreate}")
            if st.button(f"Deschide #{rid}", key=f"opn_{pk}_{rid}"):
                data = loads_offer_items(detalii) if detalii else []
                items = data.get("items", []) if isinstance(data, dict) else data
                st.session_state.cos = list(items or [])
                st.session_state.readonly_offer = True
                st.session_state.id_oferta_curenta = rid
                st.session_state.data_oferta_curenta = data_o or ""
                st.session_state.client["nume"] = nume or ""
                st.session_state["nav_radio"] = "Acasă"
                st.session_state.sidebar_view = "main"
                st.session_state.page = "configurator"
                st.rerun()


def _render_cautare_panel(db) -> None:
    pk = st.session_state.page
    st.markdown("## Căutare clienți")
    term = st.text_input("Nume", key=f"cl_q_{pk}")
    interval = st.selectbox(
        "Interval", ["Toate", "Ultima Săptămână", "Ultima Lună", "Ultimul An"], key=f"cl_int_{pk}"
    )
    data_min = None
    if interval != "Toate":
        zile = {"Ultima Săptămână": 7, "Ultima Lună": 30, "Ultimul An": 365}
        data_min = (datetime.now() - timedelta(days=zile[interval])).strftime("%Y-%m-%d")
    cli = get_clienti_with_oferte_count(
        db.cursor, f"%{term}%", data_min, utilizator_creat=st.session_state.logged_user or None
    )
    for client_id, nume, adresa, tel, nr_o in cli[:100]:
        st.write(f"**{nume}** — {tel} — oferte: {nr_o}")
        if st.button("Detalii", key=f"det_{pk}_{client_id}"):
            row = get_client_by_id(db.cursor, client_id)
            if row:
                st.session_state.client["nume"] = row[0]
                st.session_state.client["tel"] = (row[1] or "").strip()
                st.session_state.client["adresa"] = (row[2] or "").strip()
                st.session_state.client["email"] = (row[3] or "").strip() if len(row) > 3 else ""
            st.session_state["nav_radio"] = "Acasă"
            st.session_state.sidebar_view = "main"
            st.rerun()


def render_start() -> None:
    _init_state()
    st.markdown(CORP_CSS, unsafe_allow_html=True)
    render_sidebar_nav()
    cfg = AppConfig()
    db = _db()
    priv = _privileges_tuple(st.session_state.logged_user, db.cursor, cfg)
    can_modify_curs = priv[0] == 1

    if st.session_state.sidebar_view == "istoric":
        _render_istoric_panel(db)
        close_conn = getattr(db.conn, "close", None)
        if callable(close_conn):
            close_conn()
        return
    if st.session_state.sidebar_view == "cautare":
        _render_cautare_panel(db)
        close_conn = getattr(db.conn, "close", None)
        if callable(close_conn):
            close_conn()
        return

    close_conn = getattr(db.conn, "close", None)
    if callable(close_conn):
        close_conn()

    st.markdown("---")
    left, right = st.columns(2)

    with left:
        st.markdown("### DATE CLIENT NOU")
        c = st.session_state.client
        c["nume"] = st.text_input("Nume Complet", value=c["nume"], key="cl_nume")
        t1, t2 = st.columns([4, 1])
        with t1:
            c["tel"] = st.text_input("Telefon (07xxxxxxxx)", value=c["tel"], key="cl_tel")
        with t2:
            if st.button("✓"):
                norm = lambda s: "".join(x for x in s if x.isdigit())
                tel_n = norm(c["tel"])
                for nume_client, tel_db in get_all_clienti_telefon(_db().cursor):
                    if tel_db and norm(tel_db) == tel_n:
                        st.warning(f"Număr existent la client: {nume_client}")
                        break
        c["adresa"] = st.text_input("Adresă Livrare/Montaj", value=c["adresa"], key="cl_adr")
        c["email"] = st.text_input("Email (opțional)", value=c["email"], key="cl_em")
        st.markdown("**Data Ofertei:**")
        d1, d2, d3 = st.columns(3)
        luni = [
            "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
            "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
        ]
        ani = [str(y) for y in range(datetime.now().year - 1, datetime.now().year + 5)]
        c["zi"] = d1.selectbox("Zi", [str(i).zfill(2) for i in range(1, 32)], index=max(0, int(c["zi"]) - 1) if c["zi"].isdigit() else 0, key="cl_zi")
        c["luna"] = d2.selectbox("Lună", luni, index=luni.index(c["luna"]) if c["luna"] in luni else 0, key="cl_luna")
        c["an"] = d3.selectbox("An", ani, index=ani.index(c["an"]) if c["an"] in ani else 1, key="cl_an")

        if st.button("DESCHIDE SISTEM OFERTARE", type="primary", use_container_width=True):
            tel = (c["tel"] or "").strip()
            if not (c["nume"] or "").strip():
                st.error("Introduceți numele clientului.")
            elif not (len(tel) == 10 and tel.isdigit() and tel.startswith("07")):
                st.error("Telefon invalid (10 cifre, începe cu 07).")
            else:
                st.session_state.readonly_offer = False
                st.session_state.dev_mode = False
                st.session_state.cos = []
                st.session_state.id_oferta_curenta = None
                st.session_state.data_oferta_curenta = ""
                st.session_state.page = "configurator"
                st.rerun()
        if st.button("CĂUTARE CLIENT", use_container_width=True):
            st.session_state["nav_radio"] = "Căutare clienți"
            st.session_state.sidebar_view = "cautare"
            st.rerun()

    with right:
        st.markdown("### CĂUTARE PREȚ PRODUS")
        qprod = st.text_input("Caută produs (model, colecție, decor...)", key="qprod")
        if not qprod.strip():
            st.caption("Introduceți un termen de căutare...")
        else:
            cur = _db().cursor
            rows = list(search_produse(cur, qprod.strip(), limit=120))
            close_conn = getattr(_db().conn, "close", None)
            if callable(close_conn):
                close_conn()
            if not rows:
                st.info("Niciun produs găsit.")
            else:
                for r in rows[:80]:
                    if len(r) >= 9:
                        categorie, furnizor, colectie, model, finisaj, decor, tip_toc, dimensiune, pret = r[:9]
                        pret_f = float(pret or 0)
                        lei = pret_f * (1 + st.session_state.tva / 100.0) * st.session_state.curs_euro
                        st.write(
                            f"**{categorie}** [{furnizor}] {colectie} / {model} — **{pret_f:.2f} EUR** (~ **{lei:.2f} LEI**)"
                        )

    st.markdown("---")
    fc1, fc2, fc3 = st.columns([1, 2, 1])
    with fc2:
        st.success(f"CURS EURO (BNR+1%): {st.session_state.curs_euro:.4f} LEI")
        if can_modify_curs:
            manual = st.text_input("Ajustează curs manual", key="curs_manual")
            if st.button("Aplică curs manual"):
                try:
                    v = float((manual or "").replace(",", "."))
                    if v > 0:
                        st.session_state.curs_euro = v
                        st.rerun()
                except ValueError:
                    st.error("Curs invalid")
            if st.button("Reset la BNR (+1%)"):
                r = fetch_bnr_eur_rate(timeout_s=BNR_TIMEOUT_S)
                if r:
                    st.session_state.curs_bnr_real = r
                    st.session_state.curs_euro = round(r * AppConfig().curs_markup_percent, 4)
                st.rerun()
    with fc1:
        if st.button("↻ Reîmprospătare UI"):
            st.rerun()


def render_category_block(cursor, titlu: str, furnizor: str, readonly: bool, *, compact: bool = False) -> None:
    if readonly:
        return
    sl = _slug(titlu)
    is_parchet = titlu in CATEGORII_PARCHET
    ph_col = "Alege Colectia" if is_parchet else ("Alege Tip toc" if titlu == "Tocuri" else "Alege Colecție")
    ph_mod = "Alege Cod Produs" if is_parchet else "Alege Model"
    ph_dec = "Alege Finisaj" if titlu == "Tocuri" else "Alege Decor"

    open_default = titlu in ("Usi Interior", "Usi intrare apartament", "Tocuri", "Manere")
    with (st.expander(f"▾ {titlu}", expanded=open_default) if not compact else nullcontext()):
        if titlu == "Manere":
            man_f = st.radio("Manere furnizor", ["Stoc", "Enger", "Erkado"], horizontal=True, key=f"man_f_{sl}")
        else:
            man_f = "Stoc"

        use_furn = furnizor
        if titlu in CATEGORII_PARCHET:
            use_furn = "Stoc"
        if titlu == "Manere":
            use_furn = man_f

        if titlu == "Manere" and man_f == "Enger":
            modele = get_manere_engs_modele(cursor)
            if compact:
                em1, em2 = st.columns(2)
                with em1:
                    m_sel = st.selectbox("Model", ["Alege model"] + modele, key=f"eng_m_{sl}")
                fins = get_manere_engs_finisaje(cursor, m_sel) if m_sel != "Alege model" else []
                with em2:
                    f_sel = st.selectbox("Finisaj", ["Alege finisaj"] + fins, key=f"eng_f_{sl}")
            else:
                m_sel = st.selectbox("Model", ["Alege model"] + modele, key=f"eng_m_{sl}")
                fins = get_manere_engs_finisaje(cursor, m_sel) if m_sel != "Alege model" else []
                f_sel = st.selectbox("Finisaj", ["Alege finisaj"] + fins, key=f"eng_f_{sl}")
            inc_opts = ["OB", "PZ", "WC"]
            i_sel = st.selectbox("Închidere", ["Alege închidere"] + inc_opts, key=f"eng_i_{sl}")
            total = None
            if m_sel != "Alege model" and f_sel != "Alege finisaj" and i_sel in inc_opts:
                pm = get_manere_engs_pret_lei(cursor, m_sel, f_sel, MANER_ENGER_DECOR_MANER)
                pa = get_manere_engs_pret_lei(cursor, m_sel, f_sel, i_sel)
                if pm is not None and pa is not None:
                    total = round(float(pm) + float(pa), 2)
                    st.info(f"Total: **{total:.2f} LEI (TVA inclus)**")
            if compact:
                eb1, _ = st.columns([1, 4])
                with eb1:
                    eng_add = st.button("Adaugă (Enger)", key=f"add_eng_{sl}", use_container_width=False)
            else:
                eng_add = st.button("Adaugă (Enger)", key=f"add_eng_{sl}")
            if eng_add:
                if total is None:
                    st.error("Alege model, finisaj și închidere.")
                else:
                    nume = f"Maner ENGS {m_sel} {f_sel} ({i_sel})"
                    st.session_state.cos.append(
                        {
                            "nume": nume,
                            "tip": "manere_engs",
                            "pret_lei_cu_tva": total,
                            "pret_eur": 0.0,
                            "qty": 1,
                            "furnizor": "Enger",
                        }
                    )
                    st.rerun()
            return

        use_tip_toc = titlu == "Tocuri"
        cols = get_colectii_produse(cursor, titlu, use_furn, use_tip_toc=use_tip_toc)
        if not cols:
            cols = ["Nu există produse"] if is_parchet else ["Nu există produse pentru acest furnizor"]
        if compact:
            ccol, cmod = st.columns(2)
            with ccol:
                col_sel = st.selectbox(ph_col, [ph_col] + [x for x in cols if x != ph_col], key=f"sb_col_{sl}")
            mod_opts = []
            if col_sel and col_sel != ph_col:
                mod_opts = get_modele_produse(cursor, titlu, use_furn, col_sel, use_tip_toc=use_tip_toc)
            with cmod:
                mod_sel = st.selectbox(ph_mod, [ph_mod] + mod_opts, key=f"sb_mod_{sl}")
        else:
            col_sel = st.selectbox(ph_col, [ph_col] + [x for x in cols if x != ph_col], key=f"sb_col_{sl}")

            mod_opts = []
            if col_sel and col_sel != ph_col:
                mod_opts = get_modele_produse(cursor, titlu, use_furn, col_sel, use_tip_toc=use_tip_toc)
            mod_sel = st.selectbox(ph_mod, [ph_mod] + mod_opts, key=f"sb_mod_{sl}")

        pret_val = 0.0
        decor_sel = ph_dec
        pairs: list[tuple[str, str]] = []
        decor_labels: list[str] = []

        if is_parchet:
            mp_per_cut = 0.0
            pret_mp = 0.0
            if col_sel != ph_col and mod_sel != ph_mod:
                mod_int = None
                mod_float = None
                try:
                    mod_int = str(int(float(mod_sel)))
                except (ValueError, TypeError):
                    pass
                try:
                    mod_float = str(float(mod_sel)) if "." not in str(mod_sel) else mod_sel
                except (ValueError, TypeError):
                    pass
                res = get_parchet_dimensiune_pret(cursor, titlu, "Stoc", col_sel, mod_sel, mod_int)
                if not res and mod_float and mod_float != mod_sel:
                    res = get_parchet_dimensiune_pret(cursor, titlu, "Stoc", col_sel, mod_sel, mod_float)
                if res:
                    try:
                        mp_per_cut = float(str(res[0] or "0").replace(",", "."))
                    except (ValueError, TypeError):
                        mp_per_cut = 0.0
                    if mp_per_cut > 100:
                        mp_per_cut = 0.0
                    pret_mp = float(res[1] or 0)
                    st.caption(f"MP/cut: {mp_per_cut} | Preț listă EUR/mp (fără TVA): {pret_mp}")
            sup = st.text_input("Suprafață (mp)", key=f"sup_{sl}")
            if compact:
                pp1, _ = st.columns([1, 4])
                with pp1:
                    parch_add = st.button("Calculează și adaugă", key=f"add_parchet_cat_{sl}", use_container_width=False)
            else:
                parch_add = st.button("Calculează și adaugă", key=f"add_parchet_cat_{sl}")
            if parch_add:
                try:
                    supf = float((sup or "").replace(",", "."))
                except ValueError:
                    supf = 0.0
                if supf <= 0 or mp_per_cut <= 0 or pret_mp <= 0:
                    st.error("Selectați produs valid și suprafață > 0.")
                else:
                    nr_cutii = math.ceil(supf / mp_per_cut)
                    total_mp = nr_cutii * mp_per_cut
                    pret_total_eur = total_mp * pret_mp
                    nume = f"{titlu} - Colectia {col_sel} - Cod Produs {mod_sel}"
                    st.session_state.cos.append(
                        {
                            "nume": nume,
                            "pret_eur": round(pret_total_eur, 2),
                            "qty": 1,
                            "tip": "parchet",
                            "suprafata_mp": round(total_mp, 2),
                            "nr_cutii": nr_cutii,
                            "pret_per_mp": round(pret_mp, 2),
                        }
                    )
                    st.rerun()
            return

        if col_sel != ph_col and mod_sel != ph_mod:
            if titlu == "Tocuri":
                if use_furn == "Stoc":
                    res = get_pret_tocuri(cursor, titlu, use_furn, col_sel, mod_sel)
                    if res:
                        pret_val = float(res[0])
                    decor_sel = "Automat din usa"
                else:
                    pairs = get_decor_finisaj_pairs_tocuri(cursor, titlu, use_furn, col_sel, mod_sel)
                    vals = [f"{d} / {f}" if d else f for d, f in pairs]
                    req = None
                    if st.session_state.safe_mode and use_furn == "Erkado":
                        req = required_toc_decor_option(
                            st.session_state.cos, use_furn, vals, pairs
                        )
                    default_i = 0
                    if req and req in vals:
                        default_i = vals.index(req)
                    decor_sel = st.selectbox(
                        ph_dec,
                        [ph_dec] + vals,
                        index=default_i + 1 if vals else 0,
                        key=f"sb_dec_{sl}",
                    )
                    if decor_sel != ph_dec and pairs:
                        try:
                            ix = vals.index(decor_sel)
                            d0, f0 = pairs[ix]
                            res = get_pret_tocuri_decor_finisaj(cursor, titlu, use_furn, col_sel, mod_sel, d0, f0)
                            if res:
                                pret_val = float(res[0])
                        except Exception:
                            pret_val = 0.0
            else:
                pairs = get_decor_finisaj_pairs(cursor, titlu, col_sel, mod_sel, use_furn)
                if titlu == "Usi Interior" and use_furn == "Erkado":
                    decor_labels = [(f or (d or "—")) for d, f in pairs]
                elif titlu == "Usi Interior" and use_furn == "Stoc":
                    decor_labels = values_dropdown_usi_stoc(pairs)
                else:
                    decor_labels = [f"{d} / {f}" if (d and f) else (d or f or "—") for d, f in pairs]

                if titlu == "Usi Interior" and use_furn == "Erkado":
                    st.text_input("Decor ERKADO (MAJUSCULE)", key=f"erk_txt_{sl}")

                decor_sel = st.selectbox(
                    ph_dec,
                    [ph_dec] + decor_labels,
                    key=f"sb_dec_{sl}",
                )
                if decor_sel != ph_dec and pairs:
                    try:
                        idx = decor_labels.index(decor_sel)
                        dec, fin = pairs[idx]
                    except (ValueError, IndexError):
                        dec, fin = decor_sel, ""
                    res = get_pret_decor_finisaj(cursor, titlu, col_sel, mod_sel, use_furn, dec, fin)
                    if res:
                        pret_val = float(res[0])

        st.write(f"**Preț calculat:** {pret_val:.2f} €" if pret_val else "**Preț:** —")

        if compact:
            ab1, _ = st.columns([1, 5])
            with ab1:
                do_add = st.button("ADĂUGĂ", key=f"add_cat_{sl}", use_container_width=False)
        else:
            do_add = st.button("ADĂUGĂ", key=f"add_cat_{sl}")
        if do_add:
            if pret_val <= 0:
                st.error("Selectați opțiuni valide.")
                return
            if titlu == "Tocuri":
                pairs = get_decor_finisaj_pairs_tocuri(cursor, titlu, use_furn, col_sel, mod_sel)
                vals = [f"{d} / {f}" if d else f for d, f in pairs]
                td = st.session_state.get(f"sb_dec_{sl}", ph_dec)
                if use_furn == "Stoc":
                    _add_toc_to_cos(cursor, use_furn, col_sel, mod_sel, "Automat din usa", pairs, vals, pret_val)
                else:
                    _add_toc_to_cos(cursor, use_furn, col_sel, mod_sel, td, pairs, vals, pret_val)
            elif "Usi" in titlu:
                dt = (
                    (st.session_state.get(f"erk_txt_{sl}") or "").strip().upper()
                    if (titlu == "Usi Interior" and use_furn == "Erkado")
                    else decor_sel
                )
                if titlu == "Usi Interior" and use_furn == "Erkado" and not (dt or "").strip():
                    st.error("Completați decorul ERKADO (text).")
                    return
                pairs = get_decor_finisaj_pairs(cursor, titlu, col_sel, mod_sel, use_furn)
                if titlu == "Usi Interior" and use_furn == "Erkado":
                    dlab = [(f or (d or "—")) for d, f in pairs]
                elif titlu == "Usi Interior" and use_furn == "Stoc":
                    dlab = values_dropdown_usi_stoc(pairs)
                else:
                    dlab = [f"{d} / {f}" if (d and f) else (d or f or "—") for d, f in pairs]
                sel = st.session_state.get(f"sb_dec_{sl}", ph_dec)
                _add_usa_to_cos(cursor, titlu, use_furn, col_sel, mod_sel, dt, pairs, dlab, sel, pret_val)
            else:
                nume = f"[{use_furn}] {col_sel} {mod_sel} ({decor_sel})"
                st.session_state.cos.append({"nume": nume, "pret_eur": pret_val, "qty": 1, "tip": "accesorii"})
            st.rerun()


def _render_parchet_calculator_window(cursor) -> None:
    """Fereastră dedicată: categorie → colecție → model, calcul ca în catalog (MP/cut, EUR/mp), preview LEI ca în coș."""
    st.markdown("### Calculator PARCHET")
    if st.button("← Înapoi la catalog", key="pc_back"):
        st.session_state.parchet_calculator_open = False
        st.rerun()

    _fg = (st.session_state.get("furnizor_global") or "Stoc").strip()
    pf = _fg if _fg in ("Stoc", "Erkado") else "Stoc"
    st.caption(f"Furnizor parchet = furnizor ofertă din catalog (**{pf}**).")
    cat = st.selectbox("Categorie parchet", CATEGORII_PARCHET, key="pc_cat")
    col_opts = get_colectii_produse(cursor, cat, pf, use_tip_toc=False)
    col_sel: str | None = None
    if not col_opts:
        st.warning("Nu există colecții pentru această categorie și furnizor.")
    else:
        col_sel = st.selectbox("Colectia", col_opts, key="pc_col")

    mod_opts: list[str] = []
    if col_sel:
        mod_opts = get_modele_produse(cursor, cat, pf, col_sel, use_tip_toc=False)
    mod_sel: str | None = None
    if col_sel and mod_opts:
        mod_sel = st.selectbox("Cod Produs", mod_opts, key="pc_mod")
    elif col_sel and not mod_opts:
        st.caption("Nu există modele pentru această colecție.")

    st.text_input("Necesar client (mp)", key="pc_sup")

    mp_per_cut = 0.0
    pret_mp = 0.0
    res = None
    if col_sel and mod_sel:
        mod_int = None
        mod_float = None
        try:
            mod_int = str(int(float(mod_sel)))
        except (ValueError, TypeError):
            pass
        try:
            mod_float = str(float(mod_sel)) if "." not in str(mod_sel) else mod_sel
        except (ValueError, TypeError):
            pass
        res = get_parchet_dimensiune_pret(cursor, cat, pf, col_sel, mod_sel, mod_int)
        if not res and mod_float and mod_float != mod_sel:
            res = get_parchet_dimensiune_pret(cursor, cat, pf, col_sel, mod_sel, mod_float)
        if res:
            try:
                mp_per_cut = float(str(res[0] or "0").replace(",", "."))
            except (ValueError, TypeError):
                mp_per_cut = 0.0
            pret_mp = float(res[1] or 0)
            if mp_per_cut > 100:
                mp_per_cut = 0.0

    sup_raw = (st.session_state.get("pc_sup") or "").strip()
    try:
        supf = float(sup_raw.replace(",", "."))
    except ValueError:
        supf = 0.0

    if mp_per_cut > 0 and pret_mp > 0:
        st.caption(f"MP/cut: **{mp_per_cut}** | Preț EUR/mp (fără TVA): **{pret_mp:.2f}**")
        if supf > 0:
            nr_cutii = math.ceil(supf / mp_per_cut)
            total_mp = nr_cutii * mp_per_cut
            pret_total_eur = total_mp * pret_mp
            dproc = parse_discount_percent(st.session_state.discount)
            lei_linie = estimate_parchet_line_lei_tva(
                pret_total_eur,
                discount_proc=dproc,
                tva_procent=st.session_state.tva,
                curs_euro=st.session_state.curs_euro,
            )
            st.info(
                f"**{nr_cutii}** cutii → **{total_mp:.2f}** mp acoperit | **{pret_total_eur:.2f}** EUR (fără TVA)\n\n"
                f"Estimativ linie (discount {dproc}%, TVA {st.session_state.tva}%, curs {st.session_state.curs_euro:.4f}): **{lei_linie:.2f} RON**"
            )
        else:
            st.caption("Introduceți suprafața (mp) pentru calcul complet.")
    elif col_sel and mod_sel:
        st.warning(
            "Nu s-au găsit dimensiune/preț pentru acest model (schimbați furnizorul ofertei din catalog sau verificați codul)."
        )

    if st.button("Adaugă parchet în ofertă", key="pc_add", type="primary"):
        if not col_sel or not mod_sel or not res or supf <= 0 or mp_per_cut <= 0 or pret_mp <= 0:
            st.error("Completați categoria, colecția, codul și suprafața validă.")
            return
        nr_cutii = math.ceil(supf / mp_per_cut)
        total_mp = nr_cutii * mp_per_cut
        pret_total_eur = total_mp * pret_mp
        nume = f"{cat} - Colectia {col_sel} - Cod Produs {mod_sel}"
        st.session_state.cos.append(
            {
                "nume": nume,
                "pret_eur": round(pret_total_eur, 2),
                "qty": 1,
                "tip": "parchet",
                "suprafata_mp": round(total_mp, 2),
                "nr_cutii": nr_cutii,
                "pret_per_mp": round(pret_mp, 2),
                "furnizor": pf,
            }
        )
        st.rerun()


def render_configurator() -> None:
    _init_state()
    st.markdown(CORP_CSS, unsafe_allow_html=True)
    st.markdown(CONFIGURATOR_PAGE_CSS, unsafe_allow_html=True)
    cfg = AppConfig()
    db = _db()
    cursor = db.cursor
    priv = _privileges_tuple(st.session_state.logged_user, cursor, cfg)
    max_disc = max(0, min(50, int(priv[1] or 15)))
    readonly = st.session_state.readonly_offer

    render_sidebar_nav()

    if st.session_state.sidebar_view == "istoric":
        _render_istoric_panel(db)
        close_conn = getattr(db.conn, "close", None)
        if callable(close_conn):
            close_conn()
        return
    if st.session_state.sidebar_view == "cautare":
        _render_cautare_panel(db)
        close_conn = getattr(db.conn, "close", None)
        if callable(close_conn):
            close_conn()
        return

    data_comanda_pdf = (st.session_state.data_oferta_curenta or "").strip() or (
        f"{st.session_state.client['an']}-{st.session_state.client['luna']} {datetime.now().strftime('%H:%M')}"
    )

    disc_opts = sorted(set(["0"] + [str(x) for x in range(5, max_disc + 1, 5)] + [str(max_disc)]))

    left, mid, right = st.columns([36, 36, 28], gap="small")

    with left:
        if st.session_state.dev_mode:
            st.markdown(
                '<div class="nf-page-head" style="margin-bottom:0.25rem;">'
                '<span class="nf-dev-pill">Mod Dev — fără validare client.</span>'
                "</div>",
                unsafe_allow_html=True,
            )
        show_parchet_win = bool(st.session_state.parchet_calculator_open) and not readonly
        if show_parchet_win:
            with st.container(border=True):
                st.markdown('<p class="nf-card-title">Configurare</p>', unsafe_allow_html=True)
                st.session_state.safe_mode = st.toggle("Safe Mode", value=st.session_state.safe_mode)
            with st.container(border=True):
                _render_parchet_calculator_window(cursor)
        else:
            with st.container(border=True):
                st.markdown('<p class="nf-card-title">Configurare</p>', unsafe_allow_html=True)
                row_top = st.columns([5, 1])
                with row_top[0]:
                    fg = st.radio(
                        "Alege furnizorul de ofertă:",
                        ["Stoc", "Erkado"],
                        horizontal=True,
                        index=0 if st.session_state.furnizor_global == "Stoc" else 1,
                        key="fglob",
                    )
                with row_top[1]:
                    if not readonly:
                        st.caption("")
                        if st.button(
                            "PARCHET",
                            key="btn_parchet_win",
                            use_container_width=True,
                            help="Calculator parchet (categorie, colecție, cod)",
                        ):
                            st.session_state.parchet_calculator_open = True
                            st.rerun()
                st.session_state.furnizor_global = fg
                st.session_state.safe_mode = st.toggle("Safe Mode", value=st.session_state.safe_mode)
            with st.container(border=True):
                st.markdown('<p class="nf-card-title">Catalog produse</p>', unsafe_allow_html=True)
                cat_seg = st.radio(
                    "Categorie Produs",
                    ["Uși", "Tocuri", "Mânere", "Servicii", "Manual"],
                    horizontal=True,
                    key="cfg_cat_segment",
                    label_visibility="visible",
                )
                if cat_seg == "Uși":
                    ua = st.radio(
                        "Tip ușă",
                        ["Usi Interior", "Usi intrare apartament"],
                        horizontal=True,
                        key="cfg_cat_usi_sub",
                    )
                    render_category_block(cursor, ua, st.session_state.furnizor_global, readonly, compact=True)
                elif cat_seg == "Tocuri":
                    render_category_block(cursor, "Tocuri", st.session_state.furnizor_global, readonly, compact=True)
                elif cat_seg == "Mânere":
                    render_category_block(cursor, "Manere", st.session_state.furnizor_global, readonly, compact=True)
                elif cat_seg == "Servicii":
                    SERVICII = [
                        ("Scurtare set usa +toc", 11.0),
                        ("Redimensionare K", 52.0),
                        ("Redimensionare sus-jos", 52.0),
                    ]
                    st.caption("Servicii suplimentare (prețuri fixe, nu se aplică discount)")
                    for nume, pret in SERVICII:
                        if st.button(f"Adaugă — {nume} ({pret} €)", key=f"svc_{hash(nume)}"):
                            st.session_state.cos.append(
                                {
                                    "nume": nume,
                                    "pret_eur": pret,
                                    "qty": 1,
                                    "tip": "servicii_suplimentare",
                                    "fara_discount": True,
                                }
                            )
                            st.rerun()
                    cats_rest = _visible_categories(cursor)
                    if "Accesorii" in cats_rest:
                        render_category_block(cursor, "Accesorii", st.session_state.furnizor_global, readonly, compact=True)
                    _known_cat = {
                        "Usi Interior",
                        "Usi intrare apartament",
                        "Tocuri",
                        "Manere",
                        "Accesorii",
                    }
                    for titlu_extra in [c for c in cats_rest if c not in _known_cat]:
                        render_category_block(
                            cursor, titlu_extra, st.session_state.furnizor_global, readonly, compact=True
                        )
                else:
                    st.caption("Produs manual (uz general)")
                    mn = st.text_input("Denumire", key="man_n")
                    mq = st.text_input("Cantitate (buc)", key="man_q")
                    mp = st.text_input("Preț/unitate (€)", key="man_p")
                    if st.button("Adaugă în ofertă", key="man_add"):
                        try:
                            qv = float((mq or "").replace(",", "."))
                            pv = float((mp or "").replace(",", "."))
                        except ValueError:
                            qv, pv = 0.0, 0.0
                        if not (mn or "").strip() or qv <= 0 or pv <= 0:
                            st.error("Completează denumirea, cantitatea și prețul.")
                        else:
                            st.session_state.cos.append(
                                {"nume": mn.strip(), "pret_eur": round(pv, 2), "qty": qv, "tip": "produs_manual"}
                            )
                            st.rerun()

        if st.button("Înapoi la ecran start", key="cfg_back_left", use_container_width=True):
            st.session_state.parchet_calculator_open = False
            st.session_state.page = "start"
            st.rerun()

    with right:
        aj_active = st.session_state.configurator_right_panel == "ajustari"
        sb_active = st.session_state.configurator_right_panel == "setari"
        br1, br2 = st.columns(2)
        with br1:
            if st.button(
                "Ajustări ofertă",
                use_container_width=True,
                type="primary" if aj_active else "secondary",
                disabled=readonly,
                key="btn_right_ajustari",
            ):
                st.session_state.configurator_right_panel = "ajustari"
                st.rerun()
        with br2:
            if st.button(
                "Setări document",
                use_container_width=True,
                type="primary" if sb_active else "secondary",
                key="btn_right_setari",
            ):
                st.session_state.configurator_right_panel = "setari"
                st.rerun()

        with st.container(border=True):
            if aj_active:
                st.markdown('<p class="nf-card-title">Ajustări ofertă</p>', unsafe_allow_html=True)
                st.session_state.discount = st.selectbox(
                    "Discount %",
                    disc_opts,
                    index=min(disc_opts.index(st.session_state.discount), len(disc_opts) - 1)
                    if st.session_state.discount in disc_opts
                    else 0,
                    disabled=readonly,
                    key="cfg_disc_sel",
                )
                st.session_state.masuratori_lei = float(
                    st.number_input(
                        "Măsurători (LEI, PDF)",
                        value=float(st.session_state.masuratori_lei),
                        key="cfg_masuratori",
                    )
                )
                st.session_state.transport_lei = float(
                    st.number_input(
                        "Transport (LEI, PDF)",
                        value=float(st.session_state.transport_lei),
                        key="cfg_transport",
                    )
                )
            else:
                st.markdown('<p class="nf-card-title">Setări document</p>', unsafe_allow_html=True)
                st.session_state.mentiuni = st.text_area(
                    "Mentiuni", value=st.session_state.mentiuni, key="cfg_mentiuni"
                )
                st.session_state.afiseaza_mentiuni_pdf = st.checkbox(
                    "Afișează mentiunile în PDF",
                    value=st.session_state.afiseaza_mentiuni_pdf,
                    key="cfg_afis_ment",
                )
                st.session_state.conditii_pdf = st.checkbox(
                    "Condiții (PDF)", value=st.session_state.conditii_pdf, key="cfg_cond_pdf"
                )
                st.session_state.termen_livrare = st.text_input(
                    "Termen livrare (zile)",
                    value=st.session_state.termen_livrare,
                    key="cfg_termen",
                )

        dproc = parse_discount_percent(st.session_state.discount)
        totals = compute_cart_totals(
            st.session_state.cos,
            discount_proc=dproc,
            tva_procent=st.session_state.tva,
            curs_euro=st.session_state.curs_euro,
        )

    with mid:
        with st.container(border=True):
            st.markdown('<p class="nf-card-title">Ofertă curentă</p>', unsafe_allow_html=True)
            tab1, tab2 = st.tabs(["Produse în ofertă", "Rezumat ofertă"])
            with tab1:
                st.markdown("#### PRODUSE ÎN OFERTĂ")
                if not st.session_state.cos:
                    st.caption("Coșul este gol.")
                for i, item in enumerate(list(st.session_state.cos)):
                    extra = (item.get("nume_adaugire_pdf") or "").strip()
                    nume_afis = item["nume"] if not extra else f"{item['nume']} {extra}"
                    nume_afis = apply_majuscule_line_stoc_erkado(item, nume_afis)
                    cc1, cc2, cc3 = st.columns([1, 4, 2])
                    with cc1:
                        if not readonly:
                            if st.button("−", key=f"dq_{i}"):
                                q = int(item.get("qty") or 1) - 1
                                if q <= 0:
                                    st.session_state.cos.pop(i)
                                else:
                                    st.session_state.cos[i]["qty"] = q
                                st.rerun()
                    with cc2:
                        st.write(nume_afis)
                    with cc3:
                        if not readonly:
                            if st.button("+", key=f"iq_{i}"):
                                st.session_state.cos[i]["qty"] = int(item.get("qty") or 1) + 1
                                st.rerun()
                            if st.button("✕", key=f"rm_{i}"):
                                st.session_state.cos.pop(i)
                                st.rerun()

                if st.button("🔄 Reîmprospătare catalog", key="ref_cat"):
                    st.rerun()
            with tab2:
                st.markdown("#### REZUMAT OFERTĂ")
                for i, item in enumerate(st.session_state.cos):
                    if get_item_tip(item) in ("usi", "tocuri"):
                        nv = st.text_input(
                            f"Adăugire denumire #{i+1}",
                            value=(item.get("nume_adaugire_pdf") or ""),
                            key=f"rez_{i}",
                        )
                        item["nume_adaugire_pdf"] = (nv or "").strip()[:30]
                st.caption("În PDF, adăugirile apar când este bifat «Condiții».")

        with st.container(border=True):
            st.markdown('<p class="nf-card-title">Acțiuni finale</p>', unsafe_allow_html=True)
            btn_save, btn_pdf = st.columns(2, gap="small")
            with btn_save:
                if not readonly:
                    if st.button("SALVEAZĂ OFERTA", type="primary", use_container_width=True, key="btn_save_offer_mid"):
                        ok, msg = validate_offer_usi_toc(st.session_state.cos, st.session_state.safe_mode)
                        if not ok:
                            st.error(msg)
                        else:
                            c = st.session_state.client
                            data_s = f"{c['an']}-{c['luna']} {datetime.now().strftime('%H:%M')}"
                            try:
                                cid = get_client_id_by_name(cursor, c["nume"])
                                if cid is None:
                                    cid = insert_client(
                                        db.conn,
                                        cursor,
                                        c["nume"],
                                        c["tel"],
                                        c["adresa"],
                                        c["email"],
                                        datetime.now().strftime("%Y-%m-%d"),
                                    )
                                detalii = dumps_offer_items(
                                    st.session_state.cos,
                                    mentiuni=st.session_state.mentiuni,
                                    afiseaza_mentiuni_pdf=st.session_state.afiseaza_mentiuni_pdf,
                                    conditii_pdf=st.session_state.conditii_pdf,
                                    termen_livrare_zile=_parse_termen_livrare_zile(st.session_state.termen_livrare),
                                )
                                oid = insert_offer(
                                    db.conn,
                                    cursor,
                                    id_client=cid,
                                    detalii_oferta=detalii,
                                    total_lei=totals["ultima_valoare_lei"],
                                    data_oferta=data_s,
                                    nume_client_temp=c["nume"],
                                    utilizator_creat=st.session_state.logged_user,
                                    discount_proc=dproc,
                                    curs_euro=st.session_state.curs_euro,
                                    safe_mode_enabled=1 if st.session_state.safe_mode else 0,
                                )
                                st.session_state.id_oferta_curenta = oid
                                st.session_state.data_oferta_curenta = data_s
                                st.success(f"Ofertă salvată (#{oid}).")
                            except Exception as e:
                                st.error(f"Eroare salvare: {e}")
            with btn_pdf:
                if st.button("📥 Generează PDF (descarcă)", use_container_width=True, key="btn_gen_pdf"):
                    if not st.session_state.cos:
                        st.error("Coșul este gol.")
                    else:
                        tel_c = get_user_contact_phone(cursor, st.session_state.logged_user) or None
                        nume_u = get_user_full_name(cursor, st.session_state.logged_user) or st.session_state.logged_user
                        oid = st.session_state.id_oferta_curenta
                        nr = str(oid).zfill(5) if oid else "-"
                        try:
                            pdf_bytes = build_offer_pdf_bytes(
                                nr_inreg=nr,
                                nume_utilizator=nume_u,
                                contact_tel=tel_c,
                                contact_email=None,
                                nume_client=st.session_state.client["nume"],
                                telefon=st.session_state.client["tel"],
                                adresa=st.session_state.client["adresa"],
                                email=st.session_state.client.get("email") or "",
                                cos_cumparaturi=st.session_state.cos,
                                discount_proc=dproc,
                                tva_procent=st.session_state.tva,
                                curs_euro=st.session_state.curs_euro,
                                total_lei_cu_discount=totals["ultima_valoare_lei"],
                                mentiuni=st.session_state.mentiuni if st.session_state.afiseaza_mentiuni_pdf else "",
                                masuratori_lei=st.session_state.masuratori_lei,
                                transport_lei=st.session_state.transport_lei,
                                conditii_pdf=st.session_state.conditii_pdf,
                                termen_livrare_zile=_parse_termen_livrare_zile(st.session_state.termen_livrare),
                                aplica_adaugiri_denumire=st.session_state.conditii_pdf,
                                data_comanda=data_comanda_pdf,
                            )
                            st.session_state["_pdf_bytes"] = pdf_bytes
                        except Exception as ex:
                            st.error(f"Eroare PDF: {ex}")
            pb = st.session_state.get("_pdf_bytes")
            if pb:
                st.download_button(
                    label="Descarcă fișierul PDF generat",
                    data=pb,
                    file_name=f"Oferta_{(st.session_state.client['nume'] or 'client').replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    key="dl_pdf",
                )

        with st.container(border=True):
            st.markdown('<p class="nf-card-title">Rezumat financiar</p>', unsafe_allow_html=True)
            st.markdown(
                f"""<div class="nf-fin-block">
<div>Valoare totală (TVA INCLUS): <strong>{totals["total_fara_disc_lei"]:.2f} RON</strong></div>
<div>Discount aplicat (RON): <strong>{totals["discount_ron"]:.2f} RON</strong></div>
<div>Valoare cu discount (TVA INCLUS): <strong>{totals["ultima_valoare_lei"]:.2f} RON</strong></div>
<div class="nf-fin-total">AVANS (40%): <strong>{totals["avans_40"]:.2f} RON</strong></div>
</div>""",
                unsafe_allow_html=True,
            )

    close_conn = getattr(db.conn, "close", None)
    if callable(close_conn):
        close_conn()


def render_dev_pw() -> None:
    st.markdown(
        '<style>[data-testid="stSidebar"]{visibility:hidden;min-width:0!important;width:0!important;}</style>',
        unsafe_allow_html=True,
    )
    st.title("Dev Mode")
    pw = st.text_input("Parola contului", type="password")
    if st.button("Continuă"):
        cfg = AppConfig()
        db = _db()
        row = get_user_for_login(db.cursor, st.session_state.logged_user)
        ok = False
        if row and hash_parola_fn(pw) == row[0]:
            ok = True
        elif (st.session_state.logged_user or "").strip().lower() == (cfg.login_user or "").strip().lower() and pw == cfg.login_password:
            ok = True
        close_conn = getattr(db.conn, "close", None)
        if callable(close_conn):
            close_conn()
        if ok:
            st.session_state.dev_mode = True
            st.session_state.readonly_offer = False
            st.session_state.cos = []
            st.session_state.client["nume"] = "Dev Mode"
            st.session_state.client["tel"] = "0712345678"
            st.session_state.page = "configurator"
            st.rerun()
        else:
            st.error("Parolă incorectă.")
    if st.button("Renunță"):
        st.session_state.page = "start"
        st.rerun()


def run() -> None:
    st.set_page_config(page_title="Naturen Flow", layout="wide", initial_sidebar_state="expanded")
    _init_state()
    p = st.session_state.page
    if p == "login":
        render_login()
    elif p == "start":
        render_start()
    elif p == "configurator":
        render_configurator()
    elif p == "dev_pw":
        render_dev_pw()
    else:
        st.session_state.page = "login"
        render_login()
