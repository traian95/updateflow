# -*- coding: utf-8 -*-
"""
Streamlit version of the main tkinter application - maintaining same layout and functionality
"""
import streamlit as st
import sys
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from typing import Dict, List, Any, Optional

# Add the Soft Ofertare Usi directory to Python path
sys.path.append(str(Path(__file__).parent.parent / "Soft Ofertare Usi"))

from ofertare.config import AppConfig, get_database_path
from ofertare.db import (
    open_db, init_schema, get_clienti_with_oferte_count, 
    get_istoric_oferte, get_offers_by_client, search_produse,
    get_categorii_distinct, get_modele_produse, insert_client, insert_offer
)
from ofertare.paths import resolve_asset_path

# Corporate colors matching tkinter version
CORP_WINDOW_BG = "#1E1E1E"
CORP_FRAME_BG = "#2D2D2D"
CORP_MATT_GREY = "#3A3A3A"
CORP_BORDER_FINE = "#444444"
GREEN_SOFT = "#2E7D32"
GREEN_SOFT_DARK = "#256B29"
AMBER_CORP = "#F57C00"
AMBER_HOVER = "#E65100"

def get_database_connection():
    """Get database connection and cursor"""
    try:
        db_path = get_database_path()
        db = open_db(db_path)
        init_schema(db.cursor, db.conn)
        return db
    except Exception as e:
        st.error(f"Eroare conexiune bază de date: {e}")
        return None

def get_categorii_list():
    """Get list of categories with error handling"""
    try:
        db = get_database_connection()
        if db:
            categorii = get_categorii_distinct(db.cursor)
            return ["Toate"] + (categorii or [])
        return ["Toate"]
    except Exception as e:
        st.error(f"Eroare la încărcarea categoriilor: {e}")
        return ["Toate"]

def apply_custom_css():
    st.markdown(f"""
    <style>
        .stApp {{
            background-color: {CORP_WINDOW_BG};
            color: #eceff1;
        }}
        div[data-testid="stHeader"] {{
            background-color: #1a1a1a;
        }}
        .main-header {{
            background-color: {CORP_FRAME_BG};
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            border: 1px solid {CORP_BORDER_FINE};
        }}
        .user-profile {{
            background-color: #2B2B2B;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            border: 1px solid #3E3E3E;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .main-content {{
            background-color: transparent;
            padding: 1rem 0;
        }}
        .panel-container {{
            background-color: #363636;
            border: 2px solid {GREEN_SOFT};
            border-radius: 4px;
            padding: 1.5rem;
            margin: 0.5rem;
        }}
        .stButton > button {{
            background-color: {GREEN_SOFT};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 0.5rem 1rem;
            font-weight: bold;
            transition: all 0.3s;
        }}
        .stButton > button:hover {{
            background-color: {GREEN_SOFT_DARK};
        }}
        .secondary-button {{
            background-color: transparent;
            border: 1px solid {GREEN_SOFT};
            color: white;
        }}
        .secondary-button:hover {{
            background-color: #1f5a3d;
        }}
        .dev-button {{
            background-color: #6f1d1b;
            border: none;
            color: white;
        }}
        .dev-button:hover {{
            background-color: #8b2522;
        }}
        .logout-button {{
            background-color: transparent;
            border: 1px solid #8b2522;
            color: #ff6b6b;
        }}
        .logout-button:hover {{
            background-color: #5a1f1f;
        }}
        .stTextInput > div > div > input {{
            background-color: {CORP_MATT_GREY};
            border: 1px solid {CORP_BORDER_FINE};
            border-radius: 4px;
            color: white;
        }}
        .stTextInput > div > div > input:focus {{
            border-color: {GREEN_SOFT};
        }}
        .stSelectbox > div > div > select {{
            background-color: {CORP_MATT_GREY};
            border: 1px solid {CORP_BORDER_FINE};
            border-radius: 4px;
            color: white;
        }}
        .panel-title {{
            color: {GREEN_SOFT};
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 1rem;
        }}
        .metric-card {{
            background-color: {CORP_FRAME_BG};
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid {CORP_BORDER_FINE};
            text-align: center;
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
            color: {GREEN_SOFT};
        }}
        .metric-label {{
            color: #aaa;
            font-size: 0.9rem;
        }}
    </style>
    """, unsafe_allow_html=True)

def render_header():
    """Render the main header with logo, navigation, and user profile"""
    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 2])
    
    with col1:
        # Logo area
        logo_path = resolve_asset_path("Naturen2.png")
        if os.path.exists(logo_path):
            st.image(logo_path, width=240)
        else:
            st.markdown("### 🌿 OFERTARE USI")
    
    with col2:
        if st.button("📋 ISTORIC", key="istoric_btn", use_container_width=True):
            st.session_state.current_page = "istoric"
            st.rerun()
    
    with col3:
        if st.button("👥 CĂUTARE CLIENȚI", key="cautare_clienti_btn", use_container_width=True):
            st.session_state.current_page = "cautare_clienti"
            st.rerun()
    
    with col4:
        # Dev mode button (if user has privileges)
        if st.session_state.get('is_dev_mode', False):
            if st.button("⚙️ MOD DEV", key="dev_mode_btn", use_container_width=True):
                st.session_state.current_page = "dev_mode"
                st.rerun()
    
    with col5:
        # User profile and logout
        user_info = f"👤 {st.session_state.logged_user}"
        st.markdown(f'<div class="user-profile">{user_info}</div>', unsafe_allow_html=True)
        
        col5_1, col5_2 = st.columns([3, 1])
        with col5_2:
            if st.button("🚪", key="logout_btn", use_container_width=True):
                st.session_state.logged_user = None
                st.session_state.current_page = "login"
                st.rerun()

def render_client_form():
    """Render the client data entry form"""
    st.markdown('<div class="panel-container">', unsafe_allow_html=True)
    st.markdown('<h2 class="panel-title">DATE CLIENT NOU</h2>', unsafe_allow_html=True)
    
    # Initialize session state for form data
    if 'client_data' not in st.session_state:
        st.session_state.client_data = {
            'nume': '',
            'telefon': '',
            'adresa': '',
            'email': '',
            'data_oferta': datetime.now()
        }
    
    # Form fields
    col1, col2 = st.columns([3, 1])
    
    with col1:
        nume = st.text_input("Nume Complet", value=st.session_state.client_data['nume'])
        telefon = st.text_input("Telefon (ex: 07xxxxxxxx)", value=st.session_state.client_data['telefon'])
        adresa = st.text_input("Adresă Livrare/Montaj", value=st.session_state.client_data['adresa'])
        email = st.text_input("Email (opțional)", value=st.session_state.client_data['email'])
    
    with col2:
        st.write("")  # Spacer
        st.write("")  # Spacer
        if st.button("✓", key="verifica_tel_btn", help="Verifică telefon existent"):
            if telefon:
                existing_client = verify_phone_number(telefon)
                if existing_client:
                    st.success(f"Client găsit: {existing_client}")
                    # Auto-fill form with existing client data
                    st.session_state.client_data.update({
                        'nume': existing_client.get('nume', ''),
                        'telefon': telefon,
                        'adresa': existing_client.get('adresa', ''),
                        'email': existing_client.get('email', '')
                    })
                    st.rerun()
                else:
                    st.info("Telefon nou - client necunoscut")
            else:
                st.error("Introduceți telefonul")
    
    # Date selection
    st.markdown("**Data Ofertei:**")
    col_zi, col_luna, col_an = st.columns(3)
    
    with col_zi:
        zile = [str(i).zfill(2) for i in range(1, 32)]
        zi = st.selectbox("Zi", zile, index=datetime.now().day - 1)
    
    with col_luna:
        luni = ["Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie", 
                "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie"]
        luna = st.selectbox("Lună", luni, index=datetime.now().month - 1)
    
    with col_an:
        ani = [str(i) for i in range(datetime.now().year - 1, datetime.now().year + 5)]
        an = st.selectbox("An", ani, index=1)
    
    # Update session state
    st.session_state.client_data.update({
        'nume': nume,
        'telefon': telefon,
        'adresa': adresa,
        'email': email,
        'zi': zi,
        'luna': luna,
        'an': an
    })
    
    st.markdown('</div>', unsafe_allow_html=True)

def perform_product_search(search_term: str, categorie: str) -> List[Dict]:
    """Perform product search with database connection"""
    try:
        db = get_database_connection()
        if db and (search_term or categorie != "Toate"):
            # Use the search_produse function from the original tkinter app
            results = search_produse(db.cursor, search_term or "", categorie if categorie != "Toate" else "")
            return results or []
        return []
    except Exception as e:
        st.error(f"Eroare la căutare: {e}")
        return []

def verify_phone_number(phone: str) -> Optional[Dict]:
    """Verify if phone number exists in database"""
    try:
        db = get_database_connection()
        if db and phone:
            # Use the get_clienti_with_oferte_count or similar function
            from ofertare.db import get_all_clienti_telefon
            clients = get_all_clienti_telefon(db.cursor)
            for client in clients:
                if phone in str(client).replace(" ", "").replace("-", ""):
                    return client
        return None
    except Exception as e:
        st.error(f"Eroare la verificare telefon: {e}")
        return None

def render_product_search():
    st.markdown('<div class="panel-container">', unsafe_allow_html=True)
    st.markdown('<h2 class="panel-title">CĂUTARE PRODUSE</h2>', unsafe_allow_html=True)
    
    # Search controls
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        search_term = st.text_input("Caută produs...", placeholder="Introduceți nume produs...")
    
    with col2:
        categorii = get_categorii_list()
        categorie = st.selectbox("Categorie", categorii)
    
    with col3:
        if st.button("🔍 Caută", use_container_width=True):
            results = perform_product_search(search_term, categorie)
            st.session_state.search_results = results
            if results:
                st.success(f"Am găsit {len(results)} produse")
            else:
                st.info("Nu am găsit produse")
    
    # Results area
    st.markdown("---")
    st.markdown("**Rezultate căutare:**")
    
    # Display search results from session state
    if 'search_results' in st.session_state and st.session_state.search_results:
        results = st.session_state.search_results
        for i, product in enumerate(results):
            with st.expander(f"{product.get('nume', 'Produs necunoscut')}"):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"**Descriere:** {product.get('descriere', 'N/A')}")
                    st.write(f"**Categorie:** {product.get('categorie', 'N/A')}")
                with col2:
                    pret = product.get('pret', 0)
                    st.write(f"**Preț:** {pret:.2f} LEI")
                with col3:
                    if st.button("Adaugă în coș", key=f"add_{i}", use_container_width=True):
                        # Add to cart
                        if 'shopping_cart' not in st.session_state:
                            st.session_state.shopping_cart = []
                        st.session_state.shopping_cart.append({
                            'nume': product.get('nume', 'Produs'),
                            'pret': pret,
                            'qty': 1,
                            'id': product.get('id', i)
                        })
                        st.success("Adăugat în coș!")
                        st.rerun()
    else:
        if search_term or categorie != "Toate":
            st.info(f"Se afișează rezultate pentru: '{search_term}' în categoria '{categorie}'")
        else:
            st.info("Introduceți termeni de căutare pentru a afișa produse")
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_shopping_cart():
    """Render the shopping cart panel"""
    st.markdown('<div class="panel-container">', unsafe_allow_html=True)
    st.markdown('<h2 class="panel-title">COȘ CUMPĂRĂTURI</h2>', unsafe_allow_html=True)
    
    # Initialize cart in session state
    if 'shopping_cart' not in st.session_state:
        st.session_state.shopping_cart = []
    
    # Cart summary
    total_items = len(st.session_state.shopping_cart)
    total_value = 0.0  # TODO: Calculate from cart items
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.metric("Produse", total_items)
    with col2:
        st.metric("Valoare", f"{total_value:.2f} LEI")
    with col3:
        if st.button("🗑️ Golește", use_container_width=True):
            st.session_state.shopping_cart = []
            st.rerun()
    
    # Cart items
    if st.session_state.shopping_cart:
        st.markdown("**Produse în coș:**")
        for i, item in enumerate(st.session_state.shopping_cart):
            col_item, col_qty, col_price, col_remove = st.columns([3, 1, 1, 1])
            with col_item:
                st.write(item.get('nume', 'Produs necunoscut'))
            with col_qty:
                st.write(f"×{item.get('qty', 1)}")
            with col_price:
                st.write(f"{item.get('pret', 0):.2f} LEI")
            with col_remove:
                if st.button("🗑️", key=f"remove_{i}", use_container_width=True):
                    st.session_state.shopping_cart.pop(i)
                    st.rerun()
    else:
        st.info("Coșul este gol")
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_main_dashboard():
    """Render the main dashboard with all panels"""
    apply_custom_css()
    
    # Header
    render_header()
    
    # Main content area - two column layout matching tkinter
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        # Client form
        render_client_form()
        
        # Product search
        render_product_search()
    
    with col_right:
        # Shopping cart
        render_shopping_cart()
        
        # Quick actions
        st.markdown('<div class="panel-container">', unsafe_allow_html=True)
        st.markdown('<h2 class="panel-title">ACȚIUNI RAPIDE</h2>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📄 Generează Ofertă PDF", use_container_width=True):
                # TODO: Implement PDF generation
                st.success("Oferta PDF va fi generată!")
        
        with col2:
            if st.button("💾 Salvează Oferta", use_container_width=True):
                # TODO: Implement offer saving
                st.success("Oferta a fost salvată!")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Statistics
        st.markdown('<div class="panel-container">', unsafe_allow_html=True)
        st.markdown('<h2 class="panel-title">STATISTICI</h2>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.markdown('<div class="metric-value">0</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">Oferte Astăzi</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.markdown('<div class="metric-value">0</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">Total Oferte</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

def render_istoric_page():
    """Render the history/offers page"""
    apply_custom_css()
    render_header()
    
    st.markdown('<div class="panel-container">', unsafe_allow_html=True)
    st.markdown('<h2 class="panel-title">ISTORIC OFERTE</h2>', unsafe_allow_html=True)
    
    # TODO: Implement history display
    st.info("Funcționalitate în dezvoltare - se vor afișa ofertele anterioare")
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_cautare_clienti_page():
    """Render the client search page"""
    apply_custom_css()
    render_header()
    
    st.markdown('<div class="panel-container">', unsafe_allow_html=True)
    st.markdown('<h2 class="panel-title">CĂUTARE CLIENȚI</h2>', unsafe_allow_html=True)
    
    # TODO: Implement client search
    st.info("Funcționalitate în dezvoltare - se vor afișa clienții existenți")
    
    st.markdown('</div>', unsafe_allow_html=True)

def render_dev_mode_page():
    """Render the developer mode page"""
    apply_custom_css()
    render_header()
    
    st.markdown('<div class="panel-container">', unsafe_allow_html=True)
    st.markdown('<h2 class="panel-title">MOD DEV</h2>', unsafe_allow_html=True)
    
    # TODO: Implement dev mode features
    st.info("Funcționalitate în dezvoltare - opțiuni pentru dezvoltatori")
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    """Main application router"""
    # Initialize session state
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'dashboard'
    
    # Route to appropriate page
    if st.session_state.current_page == 'dashboard':
        render_main_dashboard()
    elif st.session_state.current_page == 'istoric':
        render_istoric_page()
    elif st.session_state.current_page == 'cautare_clienti':
        render_cautare_clienti_page()
    elif st.session_state.current_page == 'dev_mode':
        render_dev_mode_page()
    else:
        render_main_dashboard()

if __name__ == "__main__":
    main()
