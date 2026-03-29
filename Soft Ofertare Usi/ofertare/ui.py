# -*- coding: utf-8 -*-
# Temă oficială UI: corporate dark (paletă flat, colțuri 4px, Segoe UI).

from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
import threading
import time
import uuid
import sqlite3
import re
import unicodedata
import json
import webbrowser
from datetime import datetime, timedelta

import customtkinter as ctk
import pandas as pd
from CTkMessagebox import CTkMessagebox
from PIL import Image, ImageSequence
import tkinter as tk
from tkinter import filedialog

from .auth_utils import hash_parola as _hash_parola
from .config import AppConfig, BNR_TIMEOUT_S, PDF_CONTACT_EMAIL, PDF_CONTACT_TEL, get_database_path
from .db_cloud import get_manere_engs_finisaje, get_manere_engs_modele, get_manere_engs_pret_lei
from .db import (
    DbHandles,
    TABLE_CLIENTI,
    TABLE_OFERTE,
    TABLE_USERS,
    get_all_clienti_telefon,
    get_categorii_distinct,
    get_client_by_id,
    get_client_by_name,
    get_client_id_by_name,
    get_clienti_with_oferte_count,
    get_colectii_parchet,
    get_colectii_produse,
    get_decor_finisaj_pairs,
    get_istoric_oferte,
    get_modele_parchet,
    get_modele_produse,
    get_offers_by_client,
    get_offer_by_id,
    get_parchet_dimensiune_pret,
    get_finisaje_tocuri,
    get_decor_finisaj_pairs_tocuri,
    get_pret_tocuri_finisaj,
    get_pret_tocuri_decor_finisaj,
    get_pret_decor_finisaj,
    get_pret_tocuri,
    get_user_contact_phone,
    get_user_for_login,
    get_user_privileges,
    get_user_can_see_all,
    get_user_full_name,
    get_approved_users_with_privileges,
    init_schema,
    insert_client,
    get_offer_snapshot,
    insert_offer,
    open_db,
    search_produse,
    update_avans,
    update_offer_detalii,
    update_offer_full,
    delete_offer,
)
from .paths import resolve_asset_path
from .pdf_export import (
    apply_majuscule_line_stoc_erkado,
    build_oferta_pret_pdf,
    discount_price_factor,
    format_nume_maner_afisare,
)
from .serialization import dumps_offer_items, get_offer_modificare_meta, loads_offer_items
from .services import fetch_bnr_eur_rate
from .updater import check_for_updates, get_local_version, install_zip_update

logger = logging.getLogger(__name__)


def _desktop_dir_candidates() -> list[str]:
    """Foldere Desktop posibile (ex. Desktop sincronizat cu OneDrive pe Windows)."""
    home = os.path.expanduser("~")
    cands = (
        os.path.join(home, "Desktop"),
        os.path.join(home, "OneDrive", "Desktop"),
    )
    return [c for c in cands if c and os.path.isdir(c)]


def _is_path_on_user_desktop(file_path: str) -> bool:
    """True dacă fișierul este salvat într-un subfolder al Desktop-ului utilizatorului."""
    file_dir = os.path.normcase(os.path.abspath(os.path.dirname(file_path)))
    for desktop in _desktop_dir_candidates():
        d = os.path.normcase(os.path.abspath(desktop))
        try:
            common = os.path.commonpath([file_dir, d])
        except ValueError:
            continue
        if common == d:
            return True
    return False


def _open_path_in_default_app(path: str) -> None:
    """Deschide fișierul cu aplicația implicită a sistemului (echivalent shell.openPath / open / xdg-open)."""
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False, timeout=120)
        else:
            subprocess.run(["xdg-open", path], check=False, timeout=120)
    except Exception:
        logger.exception("Deschidere fișier PDF eșuată: %s", path)


# Mânere Enger: prețul mânerului în DB este pe linia cu Tip Element «Măner» (CSV).
MANER_ENGER_DECOR_MANER = "Măner"

BROASCA_WC_NUME = "Broasca WC"
BROASCA_CILINDRU_NUME = "Broasca Cilindru"
BROASCA_MANER_PRET_EUR = 6.0


def _maner_broasca_tip_engs_inc(inc: str) -> str | None:
    """WC → broasca WC; OB/PZ → broasca cilindru (catalog Enger)."""
    u = (inc or "").strip().upper()
    if u == "WC":
        return "wc"
    if u in ("OB", "PZ"):
        return "cilindru"
    return None


def _maner_broasca_tip_decor_text(dec: str) -> str | None:
    """Detectează din textul decorului (Stoc/Erkado) cerința de broască."""
    if not (dec or "").strip():
        return None
    nfd = unicodedata.normalize("NFD", dec)
    s = "".join(c for c in nfd if unicodedata.category(c) != "Mn").casefold()
    if re.search(r"\bwc\b", s):
        return "wc"
    if "cilindru" in s:
        return "cilindru"
    if re.search(r"\b(ob|pz)\b", s):
        return "cilindru"
    return None


def _maner_broasca_tip_stoc_manere_fields(colectie: str, model: str, decor_display: str) -> str | None:
    """WC/Cilindru pot apărea în colecție sau model (ex. «LOFT * WC»), nu doar în decor."""
    blob = " ".join((p or "").strip() for p in (colectie, model, decor_display) if (p or "").strip())
    return _maner_broasca_tip_decor_text(blob)


def _nume_linie_maner_engs(model: str, fin: str, inc: str) -> str:
    """Denumire internă coș: «Maner (…)»; afișarea Enger normalizează din prefixul MANER dacă e cazul."""
    raw = f"{model} {fin} {inc}"
    nfd = unicodedata.normalize("NFD", raw)
    fara = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    inner = fara.upper().strip()
    return f"Maner ({inner})"
# Corporate palette (flat, muted)
CORP_WINDOW_BG = "#1E1E1E"
# Rânduri în liste scroll (Istoric / Căutare clienți) — același strat CTk + Tk
ROW_LIST_BG = "#2b2b2b"
ROW_SELECTED_BG = "#1e4620"
# Fundal „Iron Curtain” / root: același gri foarte închis, fără flash alb la sistem
IRON_CURTAIN_BG = "#1a1a1a"
CORP_FRAME_BG = "#2D2D2D"
# Fereastra de ofertare (configurator): aliniat la model vizual dark, fără margini deschise
OFERTA_WINDOW_BG = "#1F1F1F"
OFERTA_WIDGET_RADIUS = 11
CORP_MATT_GREY = "#3A3A3A"
CORP_BORDER_FINE = "#444444"
GREEN_SOFT = "#2E7D32"
GREEN_SOFT_DARK = "#256B29"
AMBER_CORP = "#F57C00"
AMBER_HOVER = "#E65100"
BORDER_GRAY = "#444444"
INPUT_BORDER_GRAY = "#444444"
RADIO_ACCENT = "#546E7A"
RADIO_ACCENT_HOVER = "#455A64"

# Decoruri cu sufix LAMINAT (nu INOVA 3D) – afișare uși Stoc.
_DECOR_STOC_AFISARE_LAMINAT = frozenset({
    "SILVER OAK",
    "ATTIC WOOD",
    "STEJAR SESIL",
    "BERGAN",
})


def _finisaj_stoc_redundant_pentru_afisare(f: str) -> bool:
    """Finisaj care nu se mai afișează separat (este deja acoperit de INOVA 3D / LAMINAT)."""
    s = (f or "").strip()
    if not s:
        return True
    return bool(re.match(r"^inova\s*,?\s*laminat\s*$", s, re.I))


def _linie_decor_usi_stoc_afisare(decor: str) -> str:
    """
    O singură etichetă pentru listă/PDF.
    Dacă decorul din BD e deja etichetat (… INOVA / … LAMINAT), îl afișăm ca atare (majuscule).
    Altfel: mapare veche din denumiri tip „… Inova Laminat”.
    """
    s = (decor or "").strip()
    if not s:
        return "—"
    u = s.upper()
    # Sincronizat cu catalogul: „ALB INOVA”, „ATTIC WOOD LAMINAT”, sau varianta „… INOVA 3D”
    if u.endswith(" LAMINAT") or u.endswith(" INOVA 3D") or u.endswith(" INOVA"):
        return u
    base = re.sub(r"\s+inova\s+laminat\s*$", "", s, flags=re.IGNORECASE).rstrip()
    if not base:
        return u
    key = re.sub(r"\s+", " ", base.upper())
    bu = base.upper()
    if key in _DECOR_STOC_AFISARE_LAMINAT:
        return f"{bu} LAMINAT"
    return f"{bu} INOVA 3D"


def _values_dropdown_usi_stoc(pairs: list[tuple[str, str]]) -> list[str]:
    """Etichete combobox uși Stoc, aliniate pe index cu pairs (preț din perechea completă)."""
    if not pairs:
        return []
    mains = [_linie_decor_usi_stoc_afisare(d) for d, f in pairs]
    freq: dict[str, int] = {}
    for lm in mains:
        freq[lm] = freq.get(lm, 0) + 1
    out: list[str] = []
    nofin: dict[str, int] = {}
    for (d, f), lm in zip(pairs, mains):
        f = (f or "").strip()
        if freq.get(lm, 0) <= 1:
            out.append(lm)
            continue
        if f and not _finisaj_stoc_redundant_pentru_afisare(f):
            cand = f"{lm} / {f}"
            k = 0
            while cand in out:
                k += 1
                cand = f"{lm} / {f} ({k})"
            out.append(cand)
            continue
        nofin[lm] = nofin.get(lm, 0) + 1
        n = nofin[lm]
        out.append(lm if n == 1 else f"{lm} ({n})")
    return out

# Texte de meniu/placeholder care nu trebuie să apară ca sugestii la căutare
# (la filtrare sunt tratați ca text gol; la click caseta se golește ca să poți tasta)
_COMBO_PLACEHOLDERS = frozenset({
    "Alege Colecție", "Alege Model", "Alege Decor",
    "Alege Colectia", "Alege Cod Produs", "Alege Tip toc", "Alege produs",
    "Nu există produse", "Nu există produse pentru acest furnizor",
    "—", "Colectia", "Cod Produs",
})

# Serviciile care NU primesc discount (conform listei fixe din UI).
_SERVICII_FARA_DISCOUNT = frozenset({
    "scurtare set usa +toc",
    "redimensionare k",
    "redimensionare sus-jos",
    "broasca wc",
    "broasca cilindru",
})

# Configurare temă (keep identical)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_ORIGINAL_CTK_TOPLEVEL_GEOMETRY = ctk.CTkToplevel.geometry


def _ensure_toplevel_content_fits(win: ctk.CTkToplevel, min_width: int, min_height: int, retries: int = 0) -> None:
    """Grow a dialog if its content requires more space than requested geometry."""
    if not win.winfo_exists():
        return
    try:
        win.update_idletasks()
        req_width = max(min_width, int(win.winfo_reqwidth()))
        req_height = max(min_height, int(win.winfo_reqheight()))
        cur_width = int(win.winfo_width())
        cur_height = int(win.winfo_height())
    except Exception:
        return

    if cur_width <= 1 or cur_height <= 1:
        if retries < 8:
            win.after(35, lambda: _ensure_toplevel_content_fits(win, min_width, min_height, retries + 1))
        return

    target_width = max(cur_width, req_width)
    target_height = max(cur_height, req_height)
    if target_width > cur_width or target_height > cur_height:
        x = max((win.winfo_screenwidth() - target_width) // 2, 0)
        y = max((win.winfo_screenheight() - target_height) // 2, 0)
        _ORIGINAL_CTK_TOPLEVEL_GEOMETRY(win, f"{target_width}x{target_height}+{x}+{y}")


def _patch_centered_toplevel_geometry() -> None:
    """Center all CTkToplevel windows when geometry is set as WIDTHxHEIGHT."""
    if getattr(ctk.CTkToplevel, "_center_geometry_patch_applied", False):
        return

    def _geometry_centered(self, new_geometry=None):
        if isinstance(new_geometry, str):
            match = re.fullmatch(r"\s*(\d+)x(\d+)\s*", new_geometry)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                x = max((self.winfo_screenwidth() - width) // 2, 0)
                y = max((self.winfo_screenheight() - height) // 2, 0)
                new_geometry = f"{width}x{height}+{x}+{y}"
                _ORIGINAL_CTK_TOPLEVEL_GEOMETRY(self, new_geometry)
                self.after(30, lambda: _ensure_toplevel_content_fits(self, width, height))
                return None
            return _ORIGINAL_CTK_TOPLEVEL_GEOMETRY(self, new_geometry)

        if new_geometry is None:
            return _ORIGINAL_CTK_TOPLEVEL_GEOMETRY(self)
        return _ORIGINAL_CTK_TOPLEVEL_GEOMETRY(self, new_geometry)

    ctk.CTkToplevel.geometry = _geometry_centered
    ctk.CTkToplevel._center_geometry_patch_applied = True


_patch_centered_toplevel_geometry()


def _apply_tk_window_chrome_dark(win: ctk.CTk | ctk.CTkToplevel, background: str | None = None) -> None:
    """Setează culoarea implicită Tk pentru widget-uri native (margins/canvas), reduce flash alb."""
    bg = background or CORP_WINDOW_BG
    try:
        win.tk_setPalette(background=bg)
    except Exception:
        pass


def _force_ctk_native_dark_bg(widget: Any, bg_hex: str = CORP_WINDOW_BG) -> None:
    """Aliniază canvas-ul / stratul Tk din spatele unui widget CTk cu fundalul întunecat (reduce flash alb)."""
    try:
        cv = getattr(widget, "_canvas", None)
        if cv is not None:
            cv.configure(bg=bg_hex, highlightthickness=0)
    except Exception:
        pass
    try:
        tk.Frame.configure(widget, bg=bg_hex)
    except Exception:
        pass


def _patch_scrollable_frame_canvas(sf, bg_hex: str | None = None) -> None:
    """Aliniază fundalul real al canvas-ului Tk din CTkScrollableFrame cu tema (marginile lăsate de grid)."""
    if sf is None:
        return
    try:
        color = bg_hex
        if not color:
            pf = getattr(sf, "_parent_frame", None)
            if pf is not None:
                try:
                    fc = pf.cget("fg_color")
                    if fc is not None and str(fc).lower() != "transparent":
                        color = str(fc)
                except Exception:
                    pass
        if not color:
            color = CORP_WINDOW_BG
        cvs = getattr(sf, "_parent_canvas", None)
        if cvs is not None:
            cvs.configure(bg=color, highlightthickness=0)
        pf = getattr(sf, "_parent_frame", None)
        if pf is not None:
            try:
                tk.Frame.configure(pf, bg=color, highlightthickness=0)
            except Exception:
                pass
        for attr in ("_scrollable_frame",):
            inner = getattr(sf, attr, None)
            if inner is not None:
                try:
                    tk.Frame.configure(inner, bg=color, highlightthickness=0)
                except Exception:
                    pass
                break
        tk.Frame.configure(sf, bg=color, highlightthickness=0)
    except Exception:
        pass


def _apply_secondary_toplevel_window_bg(win: ctk.CTkToplevel, bg: str = CORP_WINDOW_BG) -> None:
    """Fundal Tk + CTk pe Toplevel înainte de pack (margini/padding fără flash alb)."""
    try:
        win.tk_setPalette(background=bg)
    except Exception:
        pass
    try:
        win.configure(fg_color=bg)
    except Exception:
        pass
    for cfg in (
        {"bg": bg},
        {"bg_color": bg},
    ):
        try:
            win.configure(**cfg)
        except Exception:
            pass
    try:
        tk.Wm.configure(win, bg=bg, highlightthickness=0)
    except Exception:
        pass
    _apply_tk_window_chrome_dark(win, bg)
    _force_ctk_native_dark_bg(win, bg)


def _pack_secondary_window_fill_panel(win: ctk.CTkToplevel, bg: str = CORP_WINDOW_BG) -> ctk.CTkFrame:
    """Panou interior care umple Toplevel-ul: golurile din pack(padx/pady) nu expun fundalul alb al ferestrei."""
    panel = ctk.CTkFrame(win, fg_color=bg, border_width=0, corner_radius=0)
    _polish_secondary_frame_surface(panel, bg, border_width=0)
    panel.pack(fill="both", expand=True)
    return panel


def _polish_secondary_frame_surface(widget: Any, bg_hex: str, *, border_width: int | None = None) -> None:
    """fg_color + bg_color (CTk) + bg Tk — goluri între pack/grid fără flash alb."""
    if border_width is not None:
        try:
            widget.configure(border_width=border_width)
        except Exception:
            pass
    try:
        widget.configure(fg_color=bg_hex, bg_color=bg_hex)
    except Exception:
        try:
            widget.configure(fg_color=bg_hex)
        except Exception:
            pass
        try:
            widget.configure(bg_color=bg_hex)
        except Exception:
            pass
    try:
        tk.Frame.configure(widget, highlightthickness=0, bg=bg_hex)
    except Exception:
        pass
    _force_ctk_native_dark_bg(widget, bg_hex)


def _apply_list_row_frame_native_bg(row_f: Any, bg_hex: str) -> None:
    """După schimbarea culorii pe rând (select / listă): resincronizează stratul Tk dedesubt."""
    try:
        row_f.configure(fg_color=bg_hex, bg_color=bg_hex)
    except Exception:
        try:
            row_f.configure(fg_color=bg_hex)
        except Exception:
            pass
    try:
        tk.Frame.configure(row_f, highlightthickness=0, bg=bg_hex)
    except Exception:
        pass
    _force_ctk_native_dark_bg(row_f, bg_hex)


def _center_dialog_on_screen(win: ctk.CTkToplevel) -> None:
    """Reposition a small dialog to the visual center of the primary monitor."""
    try:
        if not win.winfo_exists():
            return
        win.update_idletasks()
        w = max(int(win.winfo_width()), 1)
        h = max(int(win.winfo_height()), 1)
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2, 0)
        _ORIGINAL_CTK_TOPLEVEL_GEOMETRY(win, f"{w}x{h}+{x}+{y}")
    except Exception:
        pass


_CTK_MESSAGEBOX_ORIG_INIT = CTkMessagebox.__init__


def _CTkMessagebox_init_screen_centered(self, master=None, **kwargs):
    _CTK_MESSAGEBOX_ORIG_INIT(self, master=master, **kwargs)
    self.after(25, lambda w=self: _center_dialog_on_screen(w))


CTkMessagebox.__init__ = _CTkMessagebox_init_screen_centered

_CTK_INPUT_ORIG_CREATE_WIDGETS = ctk.CTkInputDialog._create_widgets


def _CTkInputDialog_create_widgets_centered(self):
    _CTK_INPUT_ORIG_CREATE_WIDGETS(self)
    self.after(40, lambda w=self: _center_dialog_on_screen(w))


ctk.CTkInputDialog._create_widgets = _CTkInputDialog_create_widgets_centered


def _apply_fullscreen_workspace(win: ctk.CTk | ctk.CTkToplevel) -> None:
    """Fill the primary screen and maximize (Windows); geometry uses +0+0 so the centering patch is skipped."""
    try:
        win.update_idletasks()
        sw = max(win.winfo_screenwidth(), 800)
        sh = max(win.winfo_screenheight(), 600)
        win.geometry(f"{sw}x{sh}+0+0")
    except Exception:
        pass
    if os.name == "nt":
        try:
            win.state("zoomed")
        except Exception:
            pass


class Preloader(ctk.CTk):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

        # Ecran de încărcare în modul full screen (ca aplicația principală)
        try:
            self.state("zoomed")
        except Exception:
            # Fallback dacă „zoomed” nu este suportat
            self.attributes("-zoomed", True)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=CORP_WINDOW_BG)
        _apply_tk_window_chrome_dark(self)

        cale_logo = resolve_asset_path("Naturen2.png")

        try:
            img_pil = Image.open(cale_logo)
            self.img_logo = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(320, 140))
            ctk.CTkLabel(self, image=self.img_logo, text="").pack(pady=(100, 20))
        except Exception:
            logger.warning("Logo preloader nu s-a încărcat: %s", cale_logo, exc_info=True)
            ctk.CTkLabel(self, text="OFERTARE PRO", font=("Segoe UI", 22)).pack(pady=(120, 20))

        ctk.CTkLabel(self, text="Se încarcă sistemul...", font=("Segoe UI", 12), text_color="#aaaaaa").pack()

        self.progress = ctk.CTkProgressBar(
            self, width=300, height=10, mode="indeterminate", progress_color="#2E7D32"
        )
        self.progress.pack(pady=20)
        self.progress.start()

        self.after(3000, self.termina_incarcarea)

    def termina_incarcarea(self):
        self.destroy()
        self.callback()


class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._auth_user: str | None = None
        self._logged_user = None
        self._login_in_progress = False
        self.cale_logo = resolve_asset_path("Naturen2.png")
        self.withdraw()
        self.configure(fg_color=CORP_WINDOW_BG)
        _apply_tk_window_chrome_dark(self)

        self.title("Autentificare")
        # Login: fereastră mică, centrată (dimensiunea originală)
        latime, inaltime = 420, 480
        ecran_l = self.winfo_screenwidth()
        ecran_i = self.winfo_screenheight()
        x = (ecran_l // 2) - (latime // 2)
        y = (ecran_i // 2) - (inaltime // 2)
        self.geometry(f"{latime}x{inaltime}+{x}+{y}")
        self.resizable(False, False)

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(expand=True, fill="both", padx=20, pady=20)
        self.protocol("WM_DELETE_WINDOW", self._on_login_window_close)
        self._build_login_screen()
        self.after_idle(self.deiconify)

    def _on_login_window_close(self):
        self._auth_user = None
        self.quit()

    def _build_login_screen(self):
        for w in self.container.winfo_children():
            w.destroy()
        try:
            img_pil = Image.open(self.cale_logo)
            img_logo = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(280, 122))
            ctk.CTkLabel(self.container, image=img_logo, text="").pack(pady=(0, 24))
        except Exception:
            logger.warning("Logo login nu s-a încărcat: %s", self.cale_logo, exc_info=True)
            ctk.CTkLabel(
                self.container, text="OFERTARE PRO", font=("Segoe UI", 20)
            ).pack(pady=(0, 24))

        ctk.CTkLabel(
            self.container, text="Autentificare utilizator", font=("Segoe UI", 16)
        ).pack(pady=(0, 16))

        self.entry_user = ctk.CTkEntry(self.container, placeholder_text="Utilizator", width=260)
        self.entry_user.pack(pady=5)
        self.entry_parola = ctk.CTkEntry(self.container, placeholder_text="Parolă", show="*", width=260)
        self.entry_parola.pack(pady=5)

        self.lbl_error = ctk.CTkLabel(
            self.container, text="", text_color="#ff5555", font=("Segoe UI", 11)
        )
        self.lbl_error.pack(pady=(5, 5))

        self.lbl_login_status = ctk.CTkLabel(
            self.container, text="", text_color="#aaaaaa", font=("Segoe UI", 11)
        )
        self.lbl_login_status.pack(pady=(0, 2))

        self.btn_login = ctk.CTkButton(
            self.container, text="LOGIN", width=200, fg_color="#2E7D32", command=self._verifica_login
        )
        self.btn_login.pack(pady=(10, 5))

        cfg = AppConfig()
        if cfg.login_user:
            self.entry_user.insert(0, cfg.login_user)
        self.entry_parola.bind("<Return>", lambda e: self._verifica_login())
        self.entry_user.focus_set()

    def _show_preloader(self):
        for w in self.container.winfo_children():
            w.destroy()
        try:
            img_pil = Image.open(self.cale_logo)
            img_logo = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(320, 140))
            ctk.CTkLabel(self.container, image=img_logo, text="").pack(pady=(60, 20))
        except Exception:
            logger.warning("Logo preloader login nu s-a încărcat", exc_info=True)
            ctk.CTkLabel(
                self.container, text="OFERTARE PRO", font=("Segoe UI", 22)
            ).pack(pady=(80, 20))
        ctk.CTkLabel(
            self.container, text="Se încarcă sistemul...", font=("Segoe UI", 12), text_color="#aaaaaa"
        ).pack()
        self._progress = ctk.CTkProgressBar(
            self.container, width=300, height=10, mode="indeterminate", progress_color="#2E7D32"
        )
        self._progress.pack(pady=20)
        self._progress.start()
        self.after(3000, self._trece_la_app)

    def _trece_la_app(self):
        if hasattr(self, "_progress") and self._progress.winfo_exists():
            self._progress.stop()
        self._auth_user = self._logged_user
        self.quit()

    def _verifica_login(self):
        if self._login_in_progress:
            return
        user = self.entry_user.get().strip()
        parola = self.entry_parola.get().strip()
        if not user or not parola:
            self.lbl_error.configure(text="Utilizator sau parolă greșită.")
            return

        self._login_in_progress = True
        self.btn_login.configure(state="disabled")
        self.entry_user.configure(state="disabled")
        self.entry_parola.configure(state="disabled")
        self.lbl_error.configure(text="")
        self.lbl_login_status.configure(text="Verificare...")

        t = threading.Thread(target=self._verifica_login_worker, args=(user, parola), daemon=True)
        t.start()

    def _verifica_login_worker(self, user: str, parola: str) -> None:
        cfg = AppConfig()
        result: dict[str, Any] = {"ok": False, "reason": "invalid_credentials"}
        try:
            db = open_db(get_database_path())
            init_schema(db.cursor, db.conn)
            row = get_user_for_login(db.cursor, user)
            close_conn = getattr(db.conn, "close", None)
            if callable(close_conn):
                close_conn()
            if row:
                password_hash, approved, username_stocat = row[0], row[1], (row[2] if len(row) > 2 else user)
                blocked = (row[3] if len(row) > 3 else 0)
                if not approved:
                    result = {"ok": False, "reason": "not_approved"}
                elif blocked:
                    result = {"ok": False, "reason": "blocked"}
                elif _hash_parola(parola) != password_hash:
                    result = {"ok": False, "reason": "invalid_credentials"}
                else:
                    result = {"ok": True, "username": username_stocat}
            elif user == cfg.login_user and parola == cfg.login_password:
                result = {"ok": True, "username": user}
        except Exception as exc:
            logger.warning("Verificare login din DB eșuată", exc_info=True)
            result = {"ok": False, "reason": "connection_error", "error": str(exc)}
        self.after(0, lambda: self._on_login_checked(result))

    def _on_login_checked(self, result: dict[str, Any]) -> None:
        self._login_in_progress = False
        self.btn_login.configure(state="normal")
        self.entry_user.configure(state="normal")
        self.entry_parola.configure(state="normal")
        self.lbl_login_status.configure(text="")

        if result.get("ok"):
            self._logged_user = str(result.get("username") or "")
            self._show_preloader()
            return

        reason = str(result.get("reason") or "")
        if reason == "not_approved":
            self.lbl_error.configure(text="Contul tău încă nu a fost aprobat de administrator.")
            return
        if reason == "blocked":
            self.lbl_error.configure(text="Cont blocat. Contactează administratorul.")
            return
        if reason == "connection_error":
            self.lbl_error.configure(text="Eroare de conexiune la Cloud. Verifică internetul")
            return
        self.lbl_error.configure(text="Utilizator sau parolă greșită.")

class AplicatieOfertare(ctk.CTk):
    def __init__(self, config: AppConfig | None = None, utilizator_creat: str = "", on_logout=None):
        super().__init__()
        self.configure(fg_color=IRON_CURTAIN_BG)
        _force_ctk_native_dark_bg(self, IRON_CURTAIN_BG)
        _apply_tk_window_chrome_dark(self, IRON_CURTAIN_BG)
        self.withdraw()
        self._want_login_again = False

        self.config_app = config or AppConfig()
        self.APP_VERSION = get_local_version()
        self._auto_update_started = False
        self.utilizator_creat = utilizator_creat or ""
        self._on_logout = on_logout  # callback opțional: apelat după delogare pentru a redeschide login-ul

        self.title(self.config_app.title)
        # Fereastra principală: folosește întreaga rezoluție a ecranului
        ecran_l = self.winfo_screenwidth()
        ecran_i = self.winfo_screenheight()
        self.geometry(f"{ecran_l}x{ecran_i}+0+0")
        self.resizable(True, True)
        if os.name == "nt":
            try:
                self.state("zoomed")
            except Exception:
                logger.exception("Nu s-a putut seta fereastra principală în mod maximizat (zoomed).")

        self.cale_proiect = os.path.dirname(resolve_asset_path("dummy"))
        self.nume_db = get_database_path()

        self.parola_admin = self.config_app.parola_admin
        self.curs_bnr_real = self.config_app.curs_bnr_fallback
        self.curs_euro = self.config_app.curs_euro_initial
        self.tva_procent = self.config_app.tva_procent
        self.cos_cumparaturi = []
        self._last_saved_offer_id: int | None = None
        self.ultima_valoare_lei = 0
        # Servicii suplimentare fixe în LEI (TVA deja inclus): măsurători + transport
        self.masuratori_lei = 0.0
        self.transport_lei = 0.0

        self._after_id_cauta_produs = None
        self._after_id_filtreaza = None
        self._after_id_filtreaza_parchet = None
        self._after_id_istoric = None
        self._after_id_cautare_clienti = None
        self._after_id_discount_refresh = None
        self._discount_ignore_trace_writes = 0
        self._search_result_pending = None
        self._istoric_fetch_seq = 0
        self._istoric_user_map_fetch_seq = 0
        self._cautare_fetch_seq = 0
        self._main_content_frame: ctk.CTkFrame | None = None
        self._transition_frame: ctk.CTkFrame | None = None
        self._main_transition_active = False
        self._master_curtain: ctk.CTkFrame | None = None
        self._master_curtain_lbl: ctk.CTkLabel | None = None

        self.cale_logo = resolve_asset_path("Naturen2.png")
        self.cale_gif = resolve_asset_path("despre.gif")

        try:
            imagine_pil = Image.open(self.cale_logo)
            self.logo_img = ctk.CTkImage(light_image=imagine_pil, dark_image=imagine_pil, size=(240, 105))
        except Exception:
            logger.warning("Logo aplicație nu s-a încărcat: %s", self.cale_logo, exc_info=True)
            self.logo_img = None
        self.user_icon_img = None
        try:
            user_icon_pil = Image.open(resolve_asset_path("imagini/user.png"))
            self.user_icon_img = ctk.CTkImage(light_image=user_icon_pil, dark_image=user_icon_pil, size=(16, 16))
        except Exception:
            logger.warning("Icon user nu s-a încărcat", exc_info=True)
        self.customer_icon_img = None
        try:
            customer_pil = Image.open(resolve_asset_path("customer.png"))
            self.customer_icon_img = ctk.CTkImage(
                light_image=customer_pil, dark_image=customer_pil, size=(22, 22)
            )
        except Exception:
            logger.warning("Icon customer.png nu s-a încărcat (lipsește din proiect?)", exc_info=True)
        self.istoric_icon_img = None
        try:
            istoric_pil = Image.open(resolve_asset_path("istoric.png"))
            self.istoric_icon_img = ctk.CTkImage(
                light_image=istoric_pil, dark_image=istoric_pil, size=(22, 22)
            )
        except Exception:
            logger.warning("Icon istoric.png nu s-a încărcat (lipsește din proiect?)", exc_info=True)
        self.logout_icon_img = None
        try:
            logout_pil = Image.open(resolve_asset_path("logout.png"))
            self.logout_icon_img = ctk.CTkImage(
                light_image=logout_pil, dark_image=logout_pil, size=(22, 22)
            )
        except Exception:
            logger.warning("Icon logout.png nu s-a încărcat (lipsește din proiect?)", exc_info=True)

        # DB / privilegii / curs BNR se încarcă în _startup_worker (fir secundar).
        self.db: DbHandles | None = None
        self.conn = None
        self.cursor = None
        self._privileges = (1, 15, 1, 1, 0)
        self._can_see_all = False
        self._version_alert_bar = None

        self._loading_frame = ctk.CTkFrame(
            self, fg_color=IRON_CURTAIN_BG, bg_color=IRON_CURTAIN_BG, corner_radius=0
        )
        _force_ctk_native_dark_bg(self._loading_frame, IRON_CURTAIN_BG)
        self._loading_frame.pack(expand=True, fill="both")
        ctk.CTkLabel(
            self._loading_frame,
            text="Se încarcă datele...",
            font=("Segoe UI", 14),
            text_color="#cccccc",
            fg_color=IRON_CURTAIN_BG,
            bg_color=IRON_CURTAIN_BG,
            corner_radius=0,
        ).pack(expand=True)

        def _cleanup_and_destroy():
            for aid in (
                self._after_id_cauta_produs,
                self._after_id_filtreaza,
                self._after_id_filtreaza_parchet,
                self._after_id_istoric,
                self._after_id_cautare_clienti,
            ):
                if aid is not None:
                    try:
                        self.after_cancel(aid)
                    except Exception:
                        pass
            self._after_id_cauta_produs = None
            self._after_id_filtreaza = None
            self._after_id_filtreaza_parchet = None
            self._after_id_istoric = None
            self._after_id_cautare_clienti = None
            self._search_result_pending = None
            conn = getattr(self, "conn", None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    logger.exception("La închiderea conexiunii DB")
            self.destroy()

        def _on_close():
            self._want_login_again = False
            _cleanup_and_destroy()

        def _do_logout():
            self._want_login_again = True
            _cleanup_and_destroy()
            if callable(self._on_logout):
                self._on_logout()

        self._do_logout = _do_logout
        self.protocol("WM_DELETE_WINDOW", _on_close)

        threading.Thread(target=self._startup_worker, daemon=True).start()
        self.after_idle(self.deiconify)

    def _startup_worker(self) -> None:
        """Încărcare DB, schema, privilegii și curs BNR pe fir secundar (fără widget-uri Tk)."""
        payload: dict[str, Any] = {"ok": False}
        try:
            db = open_db(self.nume_db)
            init_schema(db.cursor, db.conn)

            cfg_user = (self.config_app.login_user or "").strip().lower()
            app_user = (self.utilizator_creat or "").strip().lower()
            config_dev_match = bool(cfg_user and app_user and cfg_user == app_user)

            pr = get_user_privileges(db.cursor, self.utilizator_creat) if self.utilizator_creat else None
            if pr:
                priv_list = list(pr)
                while len(priv_list) < 5:
                    priv_list.append(0)
                supabase_dev = int(priv_list[4]) == 1
                priv_list[4] = 1 if (supabase_dev or config_dev_match) else 0
                privileges = tuple(priv_list)
            else:
                can_dev = 1 if config_dev_match else 0
                privileges = (1, 15, 1, 1, can_dev)
            can_see_all = bool(get_user_can_see_all(db.cursor, self.utilizator_creat)) if self.utilizator_creat else False

            curs_bnr_real = float(self.config_app.curs_bnr_fallback)
            curs_euro = float(self.config_app.curs_euro_initial)
            rate = fetch_bnr_eur_rate(timeout_s=BNR_TIMEOUT_S)
            if rate is not None:
                curs_bnr_real = float(rate)
                curs_euro = round(curs_bnr_real * self.config_app.curs_markup_percent, 4)

            payload = {
                "ok": True,
                "db": db,
                "privileges": privileges,
                "can_see_all": can_see_all,
                "curs_bnr_real": curs_bnr_real,
                "curs_euro": curs_euro,
            }
        except Exception as exc:
            logger.exception("Startup: încărcare DB / curs eșuată")
            payload = {"ok": False, "error": str(exc)}
        self.after(0, lambda p=payload: self._apply_startup_result(p))

    def _apply_startup_result(self, payload: dict[str, Any]) -> None:
        """Aplică rezultatul încărcării pe firul UI."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        lf = getattr(self, "_loading_frame", None)
        if lf is not None:
            try:
                if lf.winfo_exists():
                    lf.destroy()
            except Exception:
                pass
            self._loading_frame = None

        if not payload.get("ok"):
            self._show_startup_error(str(payload.get("error") or "Eroare necunoscută la încărcare."))
            return

        self.db = payload["db"]
        self.conn = self.db.conn
        self.cursor = self.db.cursor
        self._privileges = payload["privileges"]
        self._can_see_all = payload["can_see_all"]
        self.curs_bnr_real = payload["curs_bnr_real"]
        self.curs_euro = payload["curs_euro"]

        self.show_ecran_start()
        self.after(100, self.check_app_version)

    def _show_startup_error(self, message: str) -> None:
        """Ecran de eroare cu posibilitate de reîncercare (rămâne pe firul UI)."""
        for w in self.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self._loading_frame = None
        self._startup_error_frame = ctk.CTkFrame(self, fg_color=CORP_WINDOW_BG)
        self._startup_error_frame.pack(expand=True, fill="both")
        ctk.CTkLabel(
            self._startup_error_frame,
            text="Nu s-au putut încărca datele aplicației.",
            font=("Segoe UI", 16, "bold"),
            text_color="#ECEFF1",
        ).pack(pady=(48, 12))
        ctk.CTkLabel(
            self._startup_error_frame,
            text=message[:800],
            font=("Segoe UI", 12),
            text_color="#ff8888",
            wraplength=520,
            justify="center",
        ).pack(pady=8, padx=24)
        ctk.CTkButton(
            self._startup_error_frame,
            text="Reîncearcă",
            width=160,
            fg_color="#2E7D32",
            command=self._retry_startup_load,
        ).pack(pady=24)

    def _retry_startup_load(self) -> None:
        try:
            ef = getattr(self, "_startup_error_frame", None)
            if ef is not None:
                try:
                    if ef.winfo_exists():
                        ef.destroy()
                except Exception:
                    pass
            self._startup_error_frame = None
        except Exception:
            pass
        self._loading_frame = ctk.CTkFrame(
            self, fg_color=IRON_CURTAIN_BG, bg_color=IRON_CURTAIN_BG, corner_radius=0
        )
        _force_ctk_native_dark_bg(self._loading_frame, IRON_CURTAIN_BG)
        self._loading_frame.pack(expand=True, fill="both")
        ctk.CTkLabel(
            self._loading_frame,
            text="Se încarcă datele...",
            font=("Segoe UI", 14),
            text_color="#cccccc",
            fg_color=IRON_CURTAIN_BG,
            bg_color=IRON_CURTAIN_BG,
            corner_radius=0,
        ).pack(expand=True)
        threading.Thread(target=self._startup_worker, daemon=True).start()

    def _get_main_transition_overlay(self) -> ctk.CTkFrame | None:
        fr = getattr(self, "_transition_frame", None)
        if fr is None:
            return None
        try:
            return fr if fr.winfo_exists() else None
        except Exception:
            return None

    def _build_main_transition_overlay_preset(self, main_content: ctk.CTkFrame) -> None:
        """Pre-randare overlay întunecat (culori + canvas Tk); rămâne ascuns până la place()."""
        fr = ctk.CTkFrame(
            main_content,
            fg_color=CORP_WINDOW_BG,
            bg_color=CORP_WINDOW_BG,
            corner_radius=0,
            border_width=0,
        )
        fr.pack_propagate(False)
        _force_ctk_native_dark_bg(fr, CORP_WINDOW_BG)
        lbl = ctk.CTkLabel(
            fr,
            text="Se încarcă...",
            font=("Segoe UI", 14),
            text_color="#aaaaaa",
            fg_color=CORP_WINDOW_BG,
            bg_color=CORP_WINDOW_BG,
            corner_radius=0,
        )
        lbl.place(relx=0.5, rely=0.5, anchor="center")
        _force_ctk_native_dark_bg(lbl, CORP_WINDOW_BG)
        self._transition_frame = fr
        self._transition_loading_lbl = lbl
        try:
            main_content.update_idletasks()
            fr.place(relx=0, rely=0, relwidth=1, relheight=1)
            fr.lift()
            main_content.update_idletasks()
            fr.place_forget()
            main_content.update_idletasks()
        except Exception:
            pass

    def _show_main_transition_overlay(self) -> None:
        fr = self._get_main_transition_overlay()
        if fr is None:
            return
        try:
            self.update_idletasks()
            fr.place(relx=0, rely=0, relwidth=1, relheight=1)
            fr.lift()
            self.update_idletasks()
        except Exception:
            pass

    def _hide_main_transition_overlay(self) -> None:
        fr = getattr(self, "_transition_frame", None)
        if fr is None:
            return
        try:
            if fr.winfo_exists():
                fr.place_forget()
        except Exception:
            pass

    def _build_master_iron_curtain_preset(self) -> None:
        """Cortină full-window pe root: pre-randare apoi ascunsă (place_forget)."""
        bg = IRON_CURTAIN_BG
        self._master_curtain = ctk.CTkFrame(
            self,
            fg_color=bg,
            bg_color=bg,
            corner_radius=0,
            border_width=0,
        )
        self._master_curtain.pack_propagate(False)
        _force_ctk_native_dark_bg(self._master_curtain, bg)
        self._master_curtain_lbl = ctk.CTkLabel(
            self._master_curtain,
            text="Se încarcă...",
            font=("Segoe UI", 14),
            text_color="#aaaaaa",
            fg_color=bg,
            bg_color=bg,
            corner_radius=0,
        )
        self._master_curtain_lbl.place(relx=0.5, rely=0.5, anchor="center")
        _force_ctk_native_dark_bg(self._master_curtain_lbl, bg)
        try:
            self.update_idletasks()
            self._master_curtain.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._master_curtain.lift()
            self.update_idletasks()
            self._master_curtain.place_forget()
            self.update_idletasks()
        except Exception:
            pass

    def _iron_curtain_show(self) -> None:
        c = getattr(self, "_master_curtain", None)
        if c is None or not c.winfo_exists():
            self._build_master_iron_curtain_preset()
            c = getattr(self, "_master_curtain", None)
        if c is None:
            return
        try:
            self.update_idletasks()
            c.place(relx=0, rely=0, relwidth=1, relheight=1)
            c.lift()
            self.update_idletasks()
        except Exception:
            pass

    def _iron_curtain_lower(self) -> None:
        c = getattr(self, "_master_curtain", None)
        if c is None:
            return
        try:
            if c.winfo_exists():
                c.lower()
        except Exception:
            pass

    def _iron_curtain_finish_open_window(self, win: ctk.CTkToplevel | None) -> None:
        """După populare date: deiconify Toplevel, apoi după 100ms coborâre cortină (timp pentru buffer video)."""
        self._hide_main_transition_overlay()
        if win is not None:
            try:
                if win.winfo_exists():
                    # 1) Desen în memorie (layout + canvas) înainte de maparea Win32
                    try:
                        win.update_idletasks()
                    except Exception:
                        pass
                    # 2) Abia apoi fereastra devine vizibilă (reduce flash alb)
                    try:
                        win.deiconify()
                    except Exception:
                        pass
                    try:
                        win.lift()
                    except Exception:
                        pass
                    try:
                        win.focus_force()
                    except Exception:
                        pass
                    if win is getattr(self, "win_istoric", None) or win is getattr(self, "win_cautare", None):
                        try:
                            win.grab_set()
                        except Exception:
                            pass
            except Exception:
                pass
        self.after(100, self._iron_curtain_lower)

    def _schedule_transition_finish(self, win: ctk.CTkToplevel | None) -> None:
        if not getattr(self, "_main_transition_active", False):
            return
        self._main_transition_active = False
        self.after_idle(lambda w=win: self._iron_curtain_finish_open_window(w))

    def _style_modern_frame(self, frame: ctk.CTkFrame) -> None:
        frame.configure(
            fg_color=CORP_FRAME_BG,
            corner_radius=4,
            border_width=1,
            border_color=BORDER_GRAY,
        )

    def _style_oferta_section_frame(self, frame: ctk.CTkFrame) -> None:
        """Colțuri rotunjite mărite doar în template-ul ferestrei de ofertă."""
        frame.configure(
            fg_color=CORP_FRAME_BG,
            corner_radius=OFERTA_WIDGET_RADIUS,
            border_width=1,
            border_color=BORDER_GRAY,
        )

    def _style_corporate_radio(self, rb: ctk.CTkRadioButton) -> None:
        rb.configure(
            fg_color=RADIO_ACCENT,
            hover_color=RADIO_ACCENT_HOVER,
            border_color=CORP_BORDER_FINE,
            text_color="#ECEFF1",
        )

    def _style_corporate_checkbox(self, cb: ctk.CTkCheckBox) -> None:
        cb.configure(
            fg_color=RADIO_ACCENT,
            hover_color=RADIO_ACCENT_HOVER,
            border_color=CORP_BORDER_FINE,
            text_color="#ECEFF1",
        )

    def _style_modern_entry(self, entry: ctk.CTkEntry) -> None:
        entry.configure(corner_radius=4, border_color=INPUT_BORDER_GRAY)

        def _focus_in(_event):
            try:
                entry.configure(border_color=GREEN_SOFT)
            except Exception:
                pass

        def _focus_out(_event):
            try:
                entry.configure(border_color=CORP_BORDER_FINE)
            except Exception:
                pass

        entry.bind("<FocusIn>", _focus_in, add="+")
        entry.bind("<FocusOut>", _focus_out, add="+")

    def _style_modern_combobox(self, combo: ctk.CTkComboBox) -> None:
        combo.configure(
            corner_radius=4,
            border_color=CORP_BORDER_FINE,
            fg_color=CORP_MATT_GREY,
            button_color="#4A4A4A",
            button_hover_color="#555555",
        )
        try:
            inner = getattr(combo, "_entry", None) or getattr(combo, "entry", None)
            if inner is not None:
                inner.bind("<FocusIn>", lambda _e: combo.configure(border_color=GREEN_SOFT), add="+")
                inner.bind("<FocusOut>", lambda _e: combo.configure(border_color=CORP_BORDER_FINE), add="+")
        except Exception:
            pass

    def _style_add_button(self, btn: ctk.CTkButton) -> None:
        btn.configure(
            corner_radius=4,
            fg_color=GREEN_SOFT,
            hover_color=GREEN_SOFT_DARK,
            text_color="white",
        )

    def _apply_modern_dark_recursive(self, root) -> None:
        def _style_widget(widget):
            try:
                if widget is getattr(self, "_master_curtain", None):
                    return
                if widget is getattr(self, "_master_curtain_lbl", None):
                    return
                if widget is getattr(self, "_transition_frame", None):
                    return
                if widget is getattr(self, "_transition_loading_lbl", None):
                    return
                if isinstance(widget, ctk.CTkRadioButton):
                    self._style_corporate_radio(widget)
                    return
                if isinstance(widget, ctk.CTkCheckBox):
                    self._style_corporate_checkbox(widget)
                    return
            except Exception:
                pass
            try:
                # Generic remap for any widget still using older bright green tones.
                try:
                    fg_any = str(widget.cget("fg_color")).lower()
                    if fg_any in {"#2E7D32", "#43A047", "#78909C"}:
                        if not isinstance(widget, ctk.CTkButton):
                            widget.configure(fg_color=CORP_FRAME_BG)
                except Exception:
                    pass
                try:
                    border_any = str(widget.cget("border_color")).lower()
                    if border_any in {"#2E7D32", "#43A047", "#78909C"}:
                        widget.configure(border_color=BORDER_GRAY)
                except Exception:
                    pass
                try:
                    text_any = str(widget.cget("text_color")).lower()
                    if text_any in {"#2E7D32", "#43A047", "#78909C"}:
                        widget.configure(text_color="#E6E6E6")
                except Exception:
                    pass
                if isinstance(widget, ctk.CTkFrame):
                    fg = str(widget.cget("fg_color")).lower()
                    if fg not in {"transparent", "#2E7D32", "#6f1d1b", "#7a1a1a"}:
                        self._style_modern_frame(widget)
                elif isinstance(widget, ctk.CTkEntry):
                    self._style_modern_entry(widget)
                    widget.configure(fg_color="#363636")
                elif isinstance(widget, ctk.CTkComboBox):
                    self._style_modern_combobox(widget)
                    widget.configure(fg_color=CORP_MATT_GREY)
                elif isinstance(widget, ctk.CTkTextbox):
                    widget.configure(
                        corner_radius=4,
                        border_width=1,
                        border_color="#3A3A3A",
                        fg_color="#363636",
                    )
                elif isinstance(widget, ctk.CTkButton):
                    text = (str(widget.cget("text") or "")).lower()
                    if "pdf" in text or "descar" in text:
                        widget.configure(corner_radius=4, fg_color="#F57C00", hover_color="#E65100", text_color="white")
                    elif any(k in text for k in ("adaug", "salveaz")):
                        self._style_add_button(widget)
                        widget.configure(font=("Segoe UI", 12))
                    elif any(k in text for k in ("istoric", "căutare clien", "cautare clien")):
                        widget.configure(
                            corner_radius=4,
                            fg_color="transparent",
                            border_width=1,
                            border_color=BORDER_GRAY,
                            text_color="white",
                            hover_color="#353535",
                        )
                    else:
                        fg = str(widget.cget("fg_color")).lower()
                        if fg in {"#2E7D32", "#43A047", "#78909C"}:
                            widget.configure(fg_color=CORP_MATT_GREY, hover_color="#454545")
                elif isinstance(widget, ctk.CTkLabel):
                    tc = str(widget.cget("text_color")).lower()
                    if tc in {"#2E7D32", "#43A047", "#78909C"}:
                        widget.configure(text_color="#E6E6E6")
            except Exception:
                pass
            for child in widget.winfo_children():
                _style_widget(child)

        _style_widget(root)

    def check_app_version(self) -> None:
        threading.Thread(target=self._check_app_version_worker, daemon=True).start()

    def _check_app_version_worker(self) -> None:
        self.APP_VERSION = get_local_version()
        result = check_for_updates(self.APP_VERSION)
        self.after(0, lambda: self._on_check_app_version_done(result))

    def _on_check_app_version_done(self, result: dict[str, Any]) -> None:
        if not self.winfo_exists():
            return
        if str(result.get("reason") or "").strip().lower() == "error":
            logger.warning("Verificarea de update a esuat: %s", result.get("error"))
            return
        if not result.get("update_available"):
            self._hide_version_alert_bar()
            return
        self._show_version_alert_bar(result)
        if not self._auto_update_started:
            self._auto_update_started = True
            self._start_auto_update_install(result)

    def _start_auto_update_install(self, result: dict[str, Any]) -> None:
        download_url = str(result.get("download_url") or "").strip()
        self._pending_update_sha256 = str(result.get("sha256") or "").strip()
        self._pending_version_cloud = str(result.get("version_cloud") or "").strip()
        if not download_url:
            self._auto_update_started = False
            self.afiseaza_mesaj("Actualizare", "Nu exista link valid pentru auto-update.", "#7a1a1a")
            return
        self.afiseaza_mesaj(
            "Actualizare",
            "S-a detectat o versiune noua. Se descarca si se instaleaza automat update-ul.",
            "#2E7D32",
        )
        threading.Thread(
            target=self._auto_update_worker,
            args=(download_url,),
            daemon=True,
        ).start()

    def _auto_update_worker(self, download_url: str) -> None:
        version_cloud = str(getattr(self, "_pending_version_cloud", "") or "").strip()
        sha256 = str(getattr(self, "_pending_update_sha256", "") or "").strip()
        result = install_zip_update(download_url, expected_sha256=sha256, new_version=version_cloud)
        self.after(0, lambda: self._on_auto_update_done(result))

    def _on_auto_update_done(self, result: dict[str, Any]) -> None:
        if result.get("ok"):
            try:
                self.destroy()
            except Exception:
                pass
            return

        self._auto_update_started = False
        error_text = str(result.get("error") or "eroare necunoscuta")
        logger.warning("Auto-update instalare esuata: %s", error_text)
        self.afiseaza_mesaj(
            "Actualizare",
            f"Auto-update a esuat: {error_text}",
            "#7a1a1a",
        )

    def _hide_version_alert_bar(self) -> None:
        if self._version_alert_bar is not None and self._version_alert_bar.winfo_exists():
            self._version_alert_bar.destroy()
        self._version_alert_bar = None

    def _open_update_link(self, url: str) -> None:
        page = str(url or "").strip()
        if not page:
            self.afiseaza_mesaj("Actualizare", "Link-ul de actualizare nu este disponibil.", "#7a1a1a")
            return
        try:
            webbrowser.open(page)
        except Exception as exc:
            logger.exception("Nu s-a putut deschide browserul pentru actualizare: %s", exc)
            self.afiseaza_mesaj(
                "Actualizare",
                "Nu s-a putut deschide browserul. Deschide manual link-ul de release GitHub.",
                "#7a1a1a",
            )
            return

        msg = (
            "Link-ul de release a fost deschis. Descarca noul kit, inchide aplicatia si ruleaza instalarea."
        )
        dialog = CTkMessagebox(
            master=self,
            title="Actualizare",
            message=msg,
            option_1="OK",
            option_2="Închide aplicația",
            icon="info",
            width=440,
            height=240,
            wraplength=400,
        )
        choice = dialog.get()
        if choice == "Închide aplicația":
            try:
                self.destroy()
            except Exception:
                pass

    def _show_version_alert_bar(self, result: dict[str, Any]) -> None:
        if self._version_alert_bar is not None and self._version_alert_bar.winfo_exists():
            self._version_alert_bar.destroy()

        version_cloud = str(result.get("version_cloud") or "").strip()
        download_url = str(result.get("download_url") or "").strip()
        self._version_alert_bar = ctk.CTkFrame(
            self,
            fg_color="#2D2D2D",
            border_width=1,
            border_color="#E65100",
            corner_radius=4,
        )
        pack_kwargs = {"fill": "x", "side": "top", "pady": (0, 2)}
        if getattr(self, "_header_frame", None) and self._header_frame.winfo_exists():
            pack_kwargs["after"] = self._header_frame
        self._version_alert_bar.pack(**pack_kwargs)

        text = (
            "⚠️ O versiune nouă este disponibilă. "
            "Vă rugăm să descărcați actualizarea pentru a vedea prețurile corecte."
        )
        if version_cloud:
            text += f" (disponibil: {version_cloud}, local: {self.APP_VERSION})"
        ctk.CTkLabel(
            self._version_alert_bar,
            text=text,
            text_color="#F5D76E",
            anchor="w",
            justify="left",
            font=("Segoe UI", 12),
        ).pack(side="left", fill="x", expand=True, padx=12, pady=8)

        ctk.CTkButton(
            self._version_alert_bar,
            text="ACTUALIZEAZĂ",
            width=190,
            fg_color="#F57C00",
            hover_color="#E65100",
            border_width=1,
            border_color="#333333",
            command=lambda: self._open_update_link(download_url),
        ).pack(side="right", padx=(8, 12), pady=6)
        ctk.CTkButton(
            self._version_alert_bar,
            text="X",
            width=28,
            fg_color="transparent",
            hover_color="#2A2A2A",
            border_width=1,
            border_color="#E65100",
            command=self._hide_version_alert_bar,
        ).pack(side="right", padx=(0, 6), pady=6)

    def obtine_curs_bnr(self):
        rate = fetch_bnr_eur_rate(timeout_s=BNR_TIMEOUT_S)
        if rate is None:
            return
        self.curs_bnr_real = float(rate)
        self.curs_euro = round(self.curs_bnr_real * self.config_app.curs_markup_percent, 4)

    def actualizeaza_curs_manual(self, valoare):
        if not valoare.strip():
            self.reseteaza_la_bnr()
            return

        dialog = ctk.CTkInputDialog(text="Introdu parola admin pentru a schimba cursul:", title="Securitate")
        parola_introdusa = dialog.get_input()

        if parola_introdusa == self.parola_admin:
            try:
                noua_valoare = float(valoare.replace(",", "."))
                self.curs_euro = noua_valoare
                self.lbl_curs_afisat.configure(text=f"CURS EURO (MANUAL): {self.curs_euro} LEI")
                self.refresh_lista_pret_produse()
            except ValueError:
                self.afiseaza_mesaj("Eroare", "Te rugăm să introduci un număr valid!", "#7a1a1a")
                self.entry_curs_manual.delete(0, "end")
        else:
            self.afiseaza_mesaj("Eroare", "Parolă incorectă!", "#7a1a1a")
            self.entry_curs_manual.delete(0, "end")

    def reseteaza_la_bnr(self, event=None):
        dialog = ctk.CTkInputDialog(text="Introdu parola admin pentru a reveni la BNR+1%:", title="Securitate")
        parola_introdusa = dialog.get_input()

        if parola_introdusa == self.parola_admin:
            self.curs_euro = round(self.curs_bnr_real * self.config_app.curs_markup_percent, 4)
            self.lbl_curs_afisat.configure(text=f"CURS EURO (BNR+1%): {self.curs_euro} LEI")
            self.refresh_lista_pret_produse()
            self.entry_curs_manual.delete(0, "end")
            self.afiseaza_mesaj("Succes", "Revenit la cursul oficial BNR + 1%")
        elif parola_introdusa is not None:
            self.afiseaza_mesaj("Eroare", "Parolă incorectă!", "#7a1a1a")

    def ruleaza_gif_despre(self):
        if not os.path.exists(self.cale_gif):
            self.afiseaza_mesaj("Eroare", "Fișierul 'despre.gif' nu a fost găsit!", "#7a1a1a")
            return
        win_gif = ctk.CTkToplevel(self)
        win_gif.title("Despre")
        win_gif.geometry("600x600")
        win_gif.attributes("-topmost", True)
        lbl_gif = ctk.CTkLabel(win_gif, text="")
        lbl_gif.pack(expand=True, fill="both")
        img = Image.open(self.cale_gif)
        frames = [
            ctk.CTkImage(light_image=f.copy().convert("RGBA"), size=(500, 500))
            for f in ImageSequence.Iterator(img)
        ]

        def update(ind):
            if not win_gif.winfo_exists():
                return
            lbl_gif.configure(image=frames[ind])
            ind = (ind + 1) % len(frames)
            win_gif.after(50, update, ind)

        update(0)

    def afiseaza_mesaj(self, titlu, mesaj, culoare="#2E7D32"):
        msg_win = ctk.CTkToplevel(self)
        msg_win.title(titlu)
        msg_win.geometry("400x200")
        msg_win.attributes("-topmost", True)
        msg_win.grab_set()
        ctk.CTkLabel(msg_win, text=mesaj, font=("Segoe UI", 14, "bold"), wraplength=350).pack(expand=True, pady=20)
        ctk.CTkButton(msg_win, text="OK", fg_color=culoare, width=120, command=msg_win.destroy).pack(pady=20)

    def show_success_toast(self, mesaj: str, style: str = "green", *, duration_ms: int = 2400) -> None:
        """Toast fără blocare UI: colț dreapta-jos, slide-up, înlocuiește toast-ul anterior."""
        themes = {
            "green": {"bg": "#14532d", "border": "#22c55e", "fg": "#ecfdf5"},
            "blue": {"bg": "#1e3a5f", "border": "#3b82f6", "fg": "#dbeafe"},
            "yellow": {"bg": "#422006", "border": "#eab308", "fg": "#fef9c3"},
            "broasca_wc": {"bg": "#1e3a5f", "border": "#3b82f6", "fg": "#dbeafe"},
            "broasca_cil": {"bg": "#422006", "border": "#ea580c", "fg": "#ffedd5"},
            "warning": {"bg": "#450a0a", "border": "#f97316", "fg": "#ffedd5"},
        }
        th = themes.get(style, themes["green"])

        close_id = getattr(self, "_toast_close_after_id", None)
        if close_id is not None:
            try:
                self.after_cancel(close_id)
            except Exception:
                pass
            self._toast_close_after_id = None

        anim_id = getattr(self, "_toast_anim_after_id", None)
        if anim_id is not None:
            try:
                self.after_cancel(anim_id)
            except Exception:
                pass
            self._toast_anim_after_id = None

        tw_old = getattr(self, "_toast_window", None)
        if tw_old is not None:
            try:
                if tw_old.winfo_exists():
                    tw_old.destroy()
            except Exception:
                pass
            self._toast_window = None

        parent = self
        try:
            if getattr(self, "win_oferta", None) and self.win_oferta.winfo_exists():
                parent = self.win_oferta
        except Exception:
            parent = self

        tw = ctk.CTkToplevel(parent)
        self._toast_window = tw
        tw.overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass

        fr = ctk.CTkFrame(
            tw,
            fg_color=th["bg"],
            corner_radius=10,
            border_width=2,
            border_color=th["border"],
        )
        fr.pack(fill="both", expand=True)
        ctk.CTkLabel(
            fr,
            text=mesaj,
            font=("Segoe UI", 13, "bold"),
            text_color=th["fg"],
            wraplength=280,
        ).pack(padx=18, pady=14)

        tw.update_idletasks()
        w = max(200, fr.winfo_reqwidth() + 16)
        h = fr.winfo_reqheight() + 16

        margin = 16
        slide_px = 48
        steps = 10
        step_ms = 18

        try:
            parent.update_idletasks()
            prx = parent.winfo_rootx()
            pry = parent.winfo_rooty()
            prw = max(parent.winfo_width(), 1)
            prh = max(parent.winfo_height(), 1)
            final_x = prx + prw - w - margin
            final_y = pry + prh - h - margin
            start_y = final_y + slide_px
        except Exception:
            final_x, final_y, start_y = 0, 0, 0

        tw.geometry(f"{w}x{h}+{final_x}+{start_y}")

        def animate(step: int) -> None:
            if not tw.winfo_exists():
                self._toast_anim_after_id = None
                return
            try:
                parent.update_idletasks()
                prx2 = parent.winfo_rootx()
                pry2 = parent.winfo_rooty()
                prw2 = max(parent.winfo_width(), 1)
                prh2 = max(parent.winfo_height(), 1)
                fy = pry2 + prh2 - h - margin
                sy = fy + slide_px
                t = (step + 1) / float(steps)
                ease = 1.0 - (1.0 - t) ** 3
                y = int(sy + (fy - sy) * ease)
                fx = prx2 + prw2 - w - margin
                tw.geometry(f"{w}x{h}+{fx}+{y}")
            except Exception:
                pass
            if step + 1 < steps:
                self._toast_anim_after_id = self.after(step_ms, lambda s=step + 1: animate(s))
            else:
                self._toast_anim_after_id = None

        self.after(1, lambda: animate(0))

        def _close_toast() -> None:
            self._toast_close_after_id = None
            anim_rem = getattr(self, "_toast_anim_after_id", None)
            if anim_rem is not None:
                try:
                    self.after_cancel(anim_rem)
                except Exception:
                    pass
                self._toast_anim_after_id = None
            try:
                if tw.winfo_exists():
                    tw.destroy()
            except Exception:
                pass
            if getattr(self, "_toast_window", None) is tw:
                self._toast_window = None

        self._toast_close_after_id = self.after(max(800, int(duration_ms)), _close_toast)

    def _afiseaza_confirmare_pdf_desktop(self, cale_pdf: str) -> None:
        """
        Dialog după salvare reușită pe Desktop: mesaj fix + Deschide (aplicație implicită) / Anulare (închide).
        """
        parent = self.win_oferta if getattr(self, "win_oferta", None) else self
        dlg = ctk.CTkToplevel(parent)
        dlg.title("Succes")
        dlg.geometry("440x210")
        dlg.grab_set()
        try:
            dlg.attributes("-topmost", True)
        except Exception:
            pass
        try:
            dlg.transient(parent)
        except Exception:
            pass
        ctk.CTkLabel(
            dlg,
            text="Oferta a fost salvată cu succes pe Desktop!",
            font=("Segoe UI", 14, "bold"),
            wraplength=400,
        ).pack(expand=True, pady=(28, 18))
        fr = ctk.CTkFrame(dlg, fg_color="transparent")
        fr.pack(pady=(0, 22))

        def _deschide() -> None:
            _open_path_in_default_app(cale_pdf)
            dlg.destroy()

        def _anulare() -> None:
            dlg.destroy()

        ctk.CTkButton(fr, text="Deschide", fg_color=GREEN_SOFT, hover_color=GREEN_SOFT_DARK, width=130, command=_deschide).pack(
            side="left", padx=10
        )
        ctk.CTkButton(fr, text="Anulare", fg_color=CORP_MATT_GREY, width=130, command=_anulare).pack(side="left", padx=10)

    def _is_safe_mode_enabled(self) -> bool:
        return bool(getattr(self, "safe_mode_enabled", True))

    def _update_safe_mode_button_ui(self) -> None:
        btn = getattr(self, "btn_safe_mode", None)
        if not btn:
            return
        if self._is_safe_mode_enabled():
            btn.configure(text="Safe Mode: ON", fg_color="#2E7D32", hover_color="#256B29")
        else:
            btn.configure(text="Safe Mode: OFF", fg_color="#7a1a1a", hover_color="#5f1414")

    def _toggle_safe_mode(self) -> None:
        self.safe_mode_enabled = not self._is_safe_mode_enabled()
        self._update_safe_mode_button_ui()

    # Nume / contact folosite ca fallback în PDF (template ca la userul 'traianc')
    _NUME_UTILIZATOR_PDF = {"_fallback": "Traian Ciubuc"}
    _CONTACT_UTILIZATOR_PDF = {
        "_universal": (PDF_CONTACT_TEL, PDF_CONTACT_EMAIL)
    }

    def _nume_utilizator_pentru_pdf(self):
        # Nume contact afișat în PDF – numele complet al userului logat (din tabela users),
        # cu fallback la șablonul de bază (ca la userul 'traianc').
        u = (self.utilizator_creat or "").strip()
        if u:
            try:
                full_name = get_user_full_name(self.cursor, u)
            except Exception:
                full_name = None
            if full_name:
                return full_name
        return self._NUME_UTILIZATOR_PDF.get("_fallback", "Traian Ciubuc")

    def _nume_utilizator_pentru_afisare_ui(self) -> str:
        """Nume complet în interfață (header, mesaje); PDF rămâne pe `_nume_utilizator_pentru_pdf`."""
        u = (self.utilizator_creat or "").strip()
        if not u:
            return ""
        try:
            fn = get_user_full_name(self.cursor, u)
        except Exception:
            fn = None
        return ((fn or "").strip() or u)

    def _parse_termen_livrare_zile(self) -> str:
        """Citește termenul de livrare din UI; acceptă valori de tip 20 sau 20-30."""
        valoare_raw = ""
        if getattr(self, "entry_termen_conditii", None) and self.entry_termen_conditii.winfo_exists():
            valoare_raw = (self.entry_termen_conditii.get() or "").strip()
        nums = re.findall(r"\d+", valoare_raw or "")
        if not nums:
            return "0"
        if len(nums) == 1:
            zile = max(0, min(200, int(nums[0])))
            return str(zile)
        st = max(0, min(200, int(nums[0])))
        dr = max(0, min(200, int(nums[1])))
        if st > dr:
            st, dr = dr, st
        return f"{st}-{dr}"

    def genereaza_pdf(self, nume_client):
        if not self.cos_cumparaturi:
            self.afiseaza_mesaj("Eroare", "Cosul este gol!", "#7a1a1a")
            return
        masuratori_val = float(getattr(self, "masuratori_lei", 0.0) or 0)
        transport_val = float(getattr(self, "transport_lei", 0.0) or 0)
        # În modul doar-citire (ofertă deschisă din istoric / regenerare PDF), folosim valorile deja în ofertă — fără dialog.
        if not getattr(self, "_win_oferta_readonly", False):
            # Dialog pentru costuri suplimentare – valorile se citesc aici ca să apară corect în PDF
            win_sup = ctk.CTkToplevel(self.win_oferta if getattr(self, "win_oferta", None) else self)
            win_sup.title("Costuri suplimentare")
            win_sup.geometry("380x200")
            win_sup.grab_set()
            try:
                win_sup.attributes("-topmost", True)
            except Exception:
                pass
            f_sup = ctk.CTkFrame(win_sup, fg_color="transparent")
            f_sup.pack(expand=True, fill="both", padx=20, pady=15)
            ctk.CTkLabel(f_sup, text="Costuri suplimentare (LEI, TVA inclus) – apar în PDF:", font=("Segoe UI", 12)).pack(anchor="w", pady=(0, 8))
            row1 = ctk.CTkFrame(f_sup, fg_color="transparent")
            row1.pack(fill="x", pady=4)
            ctk.CTkLabel(row1, text="Măsurători:", width=90, anchor="w").pack(side="left", padx=(0, 8))
            ent_mas_pdf = ctk.CTkEntry(row1, width=120)
            ent_mas_pdf.pack(side="left")
            ent_mas_pdf.insert(0, f"{masuratori_val:.2f}")
            row2 = ctk.CTkFrame(f_sup, fg_color="transparent")
            row2.pack(fill="x", pady=4)
            ctk.CTkLabel(row2, text="Transport:", width=90, anchor="w").pack(side="left", padx=(0, 8))
            ent_tr_pdf = ctk.CTkEntry(row2, width=120)
            ent_tr_pdf.pack(side="left")
            ent_tr_pdf.insert(0, f"{transport_val:.2f}")

            def _parse_sup(s: str) -> float:
                s = (s or "").strip().replace(",", ".")
                try:
                    return float(s)
                except ValueError:
                    return 0.0

            # Default 0,0 = sari peste; la "Continuă la PDF" se suprascriu cu valorile din câmpuri
            valori_ok = [0.0, 0.0]

            def _continua():
                valori_ok[0] = _parse_sup(ent_mas_pdf.get())
                valori_ok[1] = _parse_sup(ent_tr_pdf.get())
                self.masuratori_lei = valori_ok[0]
                self.transport_lei = valori_ok[1]
                win_sup.destroy()

            def _sari_peste():
                valori_ok[0] = 0.0
                valori_ok[1] = 0.0
                self.masuratori_lei = 0.0
                self.transport_lei = 0.0
                win_sup.destroy()

            btns_sup = ctk.CTkFrame(f_sup, fg_color="transparent")
            btns_sup.pack(pady=(16, 0))
            ctk.CTkButton(btns_sup, text="Continuă la PDF", fg_color="#F57C00", width=160, command=_continua).pack(side="left", padx=(0, 10))
            ctk.CTkButton(btns_sup, text="Sari peste (0 la amândoua)", fg_color="#3A3A3A", width=180, command=_sari_peste).pack(side="left")
            try:
                win_sup.protocol("WM_DELETE_WINDOW", _sari_peste)
            except Exception:
                pass
            try:
                self.wait_window(win_sup)
            except Exception:
                pass
            masuratori_val = valori_ok[0]
            transport_val = valori_ok[1]

        _fd_kw: dict = {
            "parent": self.win_oferta,
            "defaultextension": ".pdf",
            "initialfile": f"Oferta_{nume_client.replace(' ', '_')}.pdf",
            "filetypes": [("PDF", "*.pdf")],
        }
        desks = _desktop_dir_candidates()
        if desks:
            _fd_kw["initialdir"] = desks[0]
        cale_salvare = filedialog.asksaveasfilename(**_fd_kw)
        if not cale_salvare:
            return
        id_oferta = getattr(self, "id_oferta_curenta", None)
        data_oferta_pdf = (getattr(self, "data_oferta_curenta", "") or "").strip()
        if not data_oferta_pdf:
            # Fallback sigur: dacă nu avem data comenzii în context, folosim data curentă.
            data_oferta_pdf = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not id_oferta:
            # Dacă ID-ul lipsește în contextul UI, încercăm recuperarea din DB pe baza client+dată(+user).
            try:
                params = [nume_client.strip(), data_oferta_pdf]
                sql = f"SELECT id FROM {TABLE_OFERTE} WHERE nume_client_temp = ? AND data_oferta = ?"
                if (self.utilizator_creat or "").strip():
                    sql += " AND utilizator_creat = ?"
                    params.append((self.utilizator_creat or "").strip())
                sql += " ORDER BY id DESC LIMIT 1"
                self.cursor.execute(sql, tuple(params))
                row = self.cursor.fetchone()
                if row and row[0]:
                    id_oferta = row[0]
                    self.id_oferta_curenta = id_oferta
            except Exception:
                logger.exception("Recuperare id ofertă pentru PDF eșuată")
        nr_inreg = str(id_oferta).zfill(5) if id_oferta else "-"
        disc_proc = self._get_discount_proc()
        # Date de contact afișate în PDF – telefonul userului logat (din profil), altfel fallback universal
        contact = self._CONTACT_UTILIZATOR_PDF.get("_universal")
        tel_contact = get_user_contact_phone(self.cursor, (self.utilizator_creat or "").strip()) if (self.utilizator_creat or "").strip() else None
        if not tel_contact:
            tel_contact = contact[0] if contact else None
        email_contact = contact[1] if contact else None
        tel = (self.entry_tel.get() or "").strip()
        adresa = (self.entry_adresa.get() or "").strip()
        email = (self.entry_email.get() or "").strip() if getattr(self, "entry_email", None) else ""
        try:
            mentiuni = ""
            if hasattr(self, "txt_mentiuni"):
                mentiuni = self.txt_mentiuni.get("1.0", "end").strip()
                if getattr(self, "_mentiuni_placeholder_active", False):
                    mentiuni = ""
            afiseaza_mentiuni = bool(
                getattr(self, "var_afiseaza_mentiuni_pdf", None)
                and self.var_afiseaza_mentiuni_pdf.get()
                and mentiuni
            )
            conditii_pdf_activ = bool(
                getattr(self, "var_conditii_pdf", None)
                and self.var_conditii_pdf.get()
            )
            termen_livrare_zile = self._parse_termen_livrare_zile()

            build_oferta_pret_pdf(
                cale_salvare=cale_salvare,
                nr_inreg=nr_inreg,
                nume_utilizator=self._nume_utilizator_pentru_pdf(),
                contact_tel=tel_contact,
                contact_email=email_contact,
                nume_client=nume_client.strip(),
                telefon=tel,
                adresa=adresa,
                email=email,
                cos_cumparaturi=self.cos_cumparaturi,
                discount_proc=disc_proc,
                tva_procent=self.tva_procent,
                curs_euro=self.curs_euro,
                total_lei_cu_discount=self.ultima_valoare_lei,
                mentiuni=mentiuni if afiseaza_mentiuni else "",
                masuratori_lei=masuratori_val,
                transport_lei=transport_val,
                conditii_pdf=conditii_pdf_activ,
                termen_livrare_zile=termen_livrare_zile,
                aplica_adaugiri_denumire=conditii_pdf_activ,
                data_comanda=data_oferta_pdf,
            )
            # După return din fpdf2.output — scriere sincronă; verificăm că fișierul există și nu e gol.
            cale_abs = os.path.abspath(cale_salvare)
            if not os.path.isfile(cale_abs):
                raise RuntimeError("Fișierul PDF nu a fost găsit pe disc după salvare.")
            if os.path.getsize(cale_abs) == 0:
                raise RuntimeError("Fișierul PDF generat este gol.")
            if _is_path_on_user_desktop(cale_abs):
                self._afiseaza_confirmare_pdf_desktop(cale_abs)
            else:
                self.afiseaza_mesaj("Succes", "PDF generat cu succes!", "#2E7D32")
        except Exception as e:
            logger.exception("Generare PDF eșuată")
            self.afiseaza_mesaj("Eroare", f"Nu s-a putut salva PDF-ul: {e}", "#7a1a1a")

    def show_ecran_start(self):
        for widget in self.winfo_children():
            widget.destroy()
        header = ctk.CTkFrame(self, height=96, fg_color="#252525")
        header.pack(fill="x", side="top")
        self._header_frame = header
        header.pack_propagate(False)
        btn_font = ("Segoe UI", 12)

        # Zonă stânga: logo Naturen Flow.
        left_zone = ctk.CTkFrame(header, fg_color="transparent")
        left_zone.pack(side="left", padx=(22, 10), fill="y")
        if self.logo_img:
            ctk.CTkLabel(left_zone, image=self.logo_img, text="").pack(side="left", pady=10)
        else:
            ctk.CTkLabel(left_zone, text="OFERTARE USI", font=("Segoe UI", 20, "bold")).pack(
                side="left", pady=10
            )

        # Zonă centru: butoane principale.
        center_zone = ctk.CTkFrame(header, fg_color="transparent")
        center_zone.place(relx=0.5, rely=0.5, anchor="center")
        _kw_istoric = {
            "master": center_zone,
            "text": "ISTORIC",
            "font": btn_font,
            "corner_radius": 4,
            "height": 38,
            "width": 180,
            "fg_color": "transparent",
            "border_width": 1,
            "border_color": "#2E7D32",
            "text_color": "white",
            "hover_color": "#1f5a3d",
            "command": self.deschide_istoric,
        }
        if self.istoric_icon_img:
            _kw_istoric["image"] = self.istoric_icon_img
            _kw_istoric["compound"] = "left"
        ctk.CTkButton(**_kw_istoric).pack(side="left", padx=8, pady=0)
        _kw_cautare = {
            "master": center_zone,
            "text": "CĂUTARE CLIENȚI",
            "font": btn_font,
            "corner_radius": 4,
            "height": 38,
            "width": 220,
            "fg_color": "transparent",
            "border_width": 1,
            "border_color": "#2E7D32",
            "text_color": "white",
            "hover_color": "#1f5a3d",
            "command": self.deschide_cautare_client,
        }
        if self.customer_icon_img:
            _kw_cautare["image"] = self.customer_icon_img
            _kw_cautare["compound"] = "left"
        ctk.CTkButton(**_kw_cautare).pack(side="left", padx=8, pady=0)

        # Zonă dreapta: Dev Mode separat în extrema dreaptă.
        can_dev = (self._privileges[4] == 1) if (self._privileges and len(self._privileges) > 4) else False
        if can_dev:
            ctk.CTkButton(
                header,
                text="MOD DEV",
                font=btn_font,
                corner_radius=4,
                height=38,
                width=120,
                fg_color="#6f1d1b",
                hover_color="#8b2522",
                text_color="white",
                command=self._deschide_dev_mode,
            ).pack(side="right", padx=(10, 22), pady=0)

        # Zonă profil: user + ieșire.
        user_profile_frame = ctk.CTkFrame(
            header,
            fg_color="#2B2B2B",
            corner_radius=4,
            border_width=1,
            border_color="#3E3E3E",
        )
        user_profile_frame.pack(side="right", padx=10, pady=0)
        if self.user_icon_img:
            ctk.CTkLabel(
                user_profile_frame,
                text="",
                image=self.user_icon_img,
            ).pack(side="left", padx=(10, 4), pady=8)
        ctk.CTkLabel(
            user_profile_frame,
            text=f"{self._nume_utilizator_pentru_afisare_ui() or self.utilizator_creat or '—'}",
            font=("Segoe UI", 11),
            text_color="#ffffff",
        ).pack(side="left", padx=(4, 10), pady=8)
        if self.logout_icon_img:
            lbl_logout_ic = ctk.CTkLabel(
                user_profile_frame,
                text="",
                image=self.logout_icon_img,
            )
            lbl_logout_ic.pack(side="left", padx=(0, 4), pady=8)
            lbl_logout_ic.bind("<Button-1>", lambda _e: self._do_logout())
        ctk.CTkButton(
            user_profile_frame,
            text="Ieșire",
            width=74,
            height=30,
            font=("Segoe UI", 10),
            fg_color="transparent",
            border_width=1,
            border_color="#8b2522",
            text_color="#ff6b6b",
            hover_color="#5a1f1f",
            corner_radius=4,
            command=self._do_logout,
        ).pack(side="left", padx=(0, 10), pady=8)
        main_content = ctk.CTkFrame(self, fg_color=CORP_WINDOW_BG, width=1100, height=590)
        self._main_content_frame = main_content
        self._transition_frame = None
        self._master_curtain = None
        self._master_curtain_lbl = None
        main_content.place(relx=0.5, rely=0.53, anchor="center")
        main_content.grid_propagate(False)
        main_content.grid_columnconfigure(0, weight=1, uniform="grupa_casete")
        main_content.grid_columnconfigure(1, weight=1, uniform="grupa_casete")
        main_content.grid_rowconfigure(0, weight=1, uniform="grupa_casete")
        _force_ctk_native_dark_bg(main_content, CORP_WINDOW_BG)

        # Aceleași dimensiuni minime pentru ambele panouri.
        panou_latime, panou_inaltime = 500, 550

        def _style_entry_focus(ent: ctk.CTkEntry) -> None:
            ent.configure(corner_radius=4, height=35, border_color="#3A3A3A")
            ent.bind("<FocusIn>", lambda _e, x=ent: x.configure(border_color="#43A047"))
            ent.bind("<FocusOut>", lambda _e, x=ent: x.configure(border_color="#3A3A3A"))

        container = ctk.CTkFrame(
            main_content,
            fg_color="#363636",
            width=panou_latime,
            height=panou_inaltime,
            corner_radius=4,
            border_width=2,
            border_color="#43A047",
        )
        container.grid(row=0, column=0, sticky="nsew", padx=(0, 15), pady=10)
        container.grid_propagate(False)
        container_inner = ctk.CTkFrame(container, fg_color="transparent")
        container_inner.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container_inner, text="DATE CLIENT NOU", font=("Segoe UI", 20, "bold"), text_color="#43A047"
        ).pack(pady=(0, 18))
        self.entry_nume = ctk.CTkEntry(container_inner, placeholder_text="Nume Complet", width=450)
        _style_entry_focus(self.entry_nume)
        self.entry_nume.pack(pady=8, fill="x")
        f_tel = ctk.CTkFrame(container_inner, fg_color="transparent")
        f_tel.pack(pady=8, fill="x")
        self.entry_tel = ctk.CTkEntry(f_tel, placeholder_text="Telefon (ex: 07xxxxxxxx)", width=380)
        _style_entry_focus(self.entry_tel)
        self.entry_tel.pack(side="left", padx=(0, 10), fill="x", expand=True)
        self.entry_tel.bind("<FocusOut>", lambda e: self.after(150, self._verifica_telefon_existent))
        ctk.CTkButton(
            f_tel, text=" ✓ ", width=44, height=36, font=("Segoe UI", 16), fg_color="#F57C00",
            command=self._verifica_telefon_existent,
        ).pack(side="left")
        self.entry_adresa = ctk.CTkEntry(container_inner, placeholder_text="Adresă Livrare/Montaj", width=450)
        _style_entry_focus(self.entry_adresa)
        self.entry_adresa.pack(pady=8, fill="x")
        self.entry_email = ctk.CTkEntry(container_inner, placeholder_text="Email (opțional)", width=450)
        _style_entry_focus(self.entry_email)
        self.entry_email.pack(pady=8, fill="x")
        ctk.CTkLabel(container_inner, text="Data Ofertei:", font=("Segoe UI", 14, "bold"), text_color="#aaaaaa").pack(
            pady=(15, 5)
        )
        f_data = ctk.CTkFrame(container_inner, fg_color="transparent")
        f_data.pack(pady=5)
        zile = [str(i).zfill(2) for i in range(1, 32)]
        luni = [
            "Ianuarie",
            "Februarie",
            "Martie",
            "Aprilie",
            "Mai",
            "Iunie",
            "Iulie",
            "August",
            "Septembrie",
            "Octombrie",
            "Noiembrie",
            "Decembrie",
        ]
        ani = [str(i) for i in range(datetime.now().year - 1, datetime.now().year + 5)]
        self.combo_zi = ctk.CTkComboBox(f_data, values=zile, width=80)
        self.combo_zi.set(datetime.now().strftime("%d"))
        self.combo_zi.pack(side="left", padx=5)
        self.combo_luna = ctk.CTkComboBox(f_data, values=luni, width=130)
        self.combo_luna.set(luni[datetime.now().month - 1])
        self.combo_luna.pack(side="left", padx=5)
        self.combo_an = ctk.CTkComboBox(f_data, values=ani, width=100)
        self.combo_an.set(str(datetime.now().year))
        self.combo_an.pack(side="left", padx=5)

        self._bind_client_casuta_keyboard_nav()

        ctk.CTkButton(
            container_inner,
            text="DESCHIDE SISTEM OFERTARE",
            height=45,
            fg_color="#2E7D32",
            hover_color="#256B29",
            corner_radius=4,
            font=("Segoe UI", 14, "bold"),
            command=self.porneste_ofertarea,
        ).pack(pady=(28, 10), fill="x")
        ctk.CTkButton(
            container_inner,
            text="CĂUTARE CLIENT",
            width=300,
            height=50,
            fg_color="#3A3A3A",
            command=self.deschide_cautare_client,
        ).pack(pady=10)

        f_cautare_pret = ctk.CTkFrame(
            main_content,
            width=panou_latime,
            height=panou_inaltime,
            fg_color="#363636",
            corner_radius=4,
            border_width=2,
            border_color="#43A047",
        )
        f_cautare_pret.grid(row=0, column=1, sticky="nsew", padx=(15, 0), pady=10)
        f_cautare_pret.grid_propagate(False)
        f_cautare_pret_inner = ctk.CTkFrame(f_cautare_pret, fg_color="transparent")
        f_cautare_pret_inner.pack(fill="both", expand=True, padx=20, pady=20)
        f_cautare_pret_inner.grid_columnconfigure(0, weight=1)
        f_cautare_pret_inner.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(
            f_cautare_pret_inner, text="CĂUTARE PREȚ PRODUS", font=("Segoe UI", 20, "bold"), text_color="#43A047"
        ).grid(row=0, column=0, pady=(0, 12), sticky="n")
        self.ent_cauta_produs = ctk.CTkEntry(
            f_cautare_pret_inner, placeholder_text="Caută produs (model, colecție, decor...)", width=480
        )
        _style_entry_focus(self.ent_cauta_produs)
        self.ent_cauta_produs.grid(row=1, column=0, pady=(0, 10), sticky="ew")
        self.ent_cauta_produs.bind("<KeyRelease>", self._on_keyrelease_cauta_produs)
        ctk.CTkLabel(
            f_cautare_pret_inner, text="Rezultate (preț EUR / LEI la curs curent):", font=("Segoe UI", 11), text_color="#aaaaaa"
        ).grid(row=2, column=0, sticky="nw", pady=(0, 5))
        self.scroll_pret_produse = ctk.CTkScrollableFrame(f_cautare_pret_inner, fg_color=CORP_WINDOW_BG)
        self.scroll_pret_produse.grid(row=3, column=0, sticky="nsew", pady=(0, 0))
        _patch_scrollable_frame_canvas(self.scroll_pret_produse, CORP_WINDOW_BG)
        self.refresh_lista_pret_produse()

        self._build_main_transition_overlay_preset(main_content)

        _curs_panel_min_w = 300
        f_curs_container = ctk.CTkFrame(
            self,
            fg_color="#1e1e1e",
            corner_radius=8,
            border_width=1,
            border_color="#3a3a3a",
        )
        f_curs_container.place(relx=0.98, rely=0.98, anchor="se")
        f_curs_container.grid_columnconfigure(0, weight=1, minsize=_curs_panel_min_w)

        f_curs = ctk.CTkFrame(f_curs_container, fg_color="#2E7D32", corner_radius=4)
        f_curs.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        f_curs.grid_columnconfigure(0, weight=1)

        self.lbl_curs_afisat = ctk.CTkLabel(
            f_curs,
            text=f"CURS EURO (BNR+1%): {self.curs_euro} LEI",
            font=("Segoe UI", 12),
            text_color="white",
            cursor="hand2",
            anchor="center",
            justify="center",
            wraplength=_curs_panel_min_w - 36,
        )
        self.lbl_curs_afisat.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
        can_modify_curs = self._privileges[0] if self._privileges else 1
        if can_modify_curs:
            self.lbl_curs_afisat.bind("<Button-1>", self.reseteaza_la_bnr)
        self.entry_curs_manual = ctk.CTkEntry(
            f_curs_container,
            placeholder_text="Ajustează curs manual...",
            font=("Segoe UI", 11),
            height=32,
        )
        if can_modify_curs:
            self.entry_curs_manual.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
            self.entry_curs_manual.bind("<Return>", lambda e: self.actualizeaza_curs_manual(self.entry_curs_manual.get()))
        ctk.CTkButton(
            self,
            text="↻",
            width=42,
            height=34,
            fg_color="#2E7D32",
            hover_color="#256B29",
            command=self._refresh_ofertare_ui,
        ).place(relx=0.02, rely=0.98, anchor="sw")
        self._build_master_iron_curtain_preset()
        self._apply_modern_dark_recursive(self)

    def _focus_widget_casuta(self, w):
        """Pune focus pe un CTkEntry / CTkComboBox (widget intern _entry dacă există)."""
        try:
            inner = getattr(w, "_entry", None)
            if inner is not None and callable(getattr(inner, "focus_set", None)):
                inner.focus_set()
            else:
                w.focus_set()
        except Exception:
            pass

    def _bind_client_casuta_keyboard_nav(self):
        """În caseta DATE CLIENT: săgeți sus/jos și Enter între toate câmpurile (inclusiv zi/lună/an); Enter pe an = Deschide sistem ofertare."""
        if not all(
            hasattr(self, a)
            for a in (
                "entry_nume",
                "entry_tel",
                "entry_adresa",
                "entry_email",
                "combo_zi",
                "combo_luna",
                "combo_an",
            )
        ):
            return
        order = [
            self.entry_nume,
            self.entry_tel,
            self.entry_adresa,
            self.entry_email,
            self.combo_zi,
            self.combo_luna,
            self.combo_an,
        ]
        n = len(order)
        # Săgeți sus/jos pe toate câmpurile (inclusiv zi/lună/an), ca să poți ieși din dată spre email etc.
        # Lista din combobox: click pe săgeata din dreapta sau Alt+Down dacă e nevoie.
        for i, w in enumerate(order):
            def make_handlers(ii=i):
                def down(_e=None):
                    if ii < n - 1:
                        self.after_idle(lambda: self._focus_widget_casuta(order[ii + 1]))
                    return "break"

                def up(_e=None):
                    if ii > 0:
                        self.after_idle(lambda: self._focus_widget_casuta(order[ii - 1]))
                    return "break"

                def ret(_e=None):
                    if ii < n - 1:
                        self.after_idle(lambda: self._focus_widget_casuta(order[ii + 1]))
                    else:
                        self.after_idle(self.porneste_ofertarea)
                    return "break"

                return down, up, ret

            d, u, r = make_handlers()
            target = getattr(w, "_entry", None) or w
            target.bind("<Down>", d)
            target.bind("<Up>", u)
            target.bind("<Return>", r)

    def _refresh_ofertare_ui(self):
        """Reafișează ecranul principal de ofertare."""
        self.show_ecran_start()

    def _on_keyrelease_cauta_produs(self, event=None):
        """Căutare instant la tastare."""
        if self._after_id_cauta_produs is not None:
            try:
                self.after_cancel(self._after_id_cauta_produs)
            except Exception:
                pass
        self._after_id_cauta_produs = None
        self._do_refresh_lista_pret_produse()

    def _do_refresh_lista_pret_produse(self):
        """Pornește căutarea în background; rezultatul se aplică pe UI prin _apply_search_result_pending."""
        self._after_id_cauta_produs = None
        termen = self.ent_cauta_produs.get().strip() if hasattr(self, "ent_cauta_produs") else ""
        if not termen:
            self._build_lista_pret_produse_from_rows([], termen)
            return
        limit = 120
        db_path = get_database_path()
        app = self

        def run_search():
            try:
                db = open_db(db_path)
                try:
                    rows = search_produse(db.cursor, termen, limit=limit)
                    result = list(rows)
                finally:
                    try:
                        conn_obj = getattr(db, "conn", None)
                        close_fn = getattr(conn_obj, "close", None)
                        if callable(close_fn):
                            close_fn()
                    except Exception:
                        # Unele backend-uri (ex. cloud client) nu expun close() real.
                        pass
                print(f"[search_produse] termen='{termen}' rezultate={len(result)}")
                app._search_result_pending = (termen, result)
                app.after(0, app._apply_search_result_pending)
            except Exception:
                logger.exception("Căutare produse în background")

        threading.Thread(target=run_search, daemon=True).start()

    def _apply_search_result_pending(self):
        """Callback pe firul UI: aplică rezultatul din _search_result_pending dacă termenul e încă același."""
        pending = self._search_result_pending
        if pending is None:
            return
        self._search_result_pending = None
        termen, rows = pending
        if not hasattr(self, "scroll_pret_produse") or not self.scroll_pret_produse.winfo_exists():
            return
        if not hasattr(self, "ent_cauta_produs") or not self.ent_cauta_produs.winfo_exists():
            return
        if self.ent_cauta_produs.get().strip() != termen:
            return
        self._build_lista_pret_produse_from_rows(rows, termen)

    def _build_lista_pret_produse_from_rows(self, rows: list, termen: str):
        """Construiește în scroll_pret_produse lista de rânduri (pe firul UI). Cu update_idletasks în ture."""
        if not hasattr(self, "scroll_pret_produse") or not self.scroll_pret_produse.winfo_exists():
            return
        for w in self.scroll_pret_produse.winfo_children():
            w.destroy()
        if not rows:
            ctk.CTkLabel(
                self.scroll_pret_produse,
                text=(
                    "Introduceți un termen de căutare..."
                    if not termen
                    else f"Niciun produs găsit pentru: {termen}"
                ),
                font=("Segoe UI", 12),
                text_color="#888888",
                wraplength=480,
            ).pack(pady=20)
            return
        CHUNK = 20
        for i, r in enumerate(rows):
            if i > 0 and i % CHUNK == 0:
                self.scroll_pret_produse.update_idletasks()
            if len(r) >= 9:
                categorie, furnizor, colectie, model, finisaj, decor, tip_toc, dimensiune, pret = (
                    r[0],
                    r[1],
                    r[2],
                    r[3],
                    r[4],
                    r[5],
                    r[6],
                    r[7],
                    r[8],
                )
            elif len(r) == 7:
                categorie, furnizor, colectie, model, finisaj, decor, pret = r
                tip_toc, dimensiune = "", ""
            else:
                categorie, furnizor, colectie, model, decor, pret = r[0], r[1], r[2], r[3], r[4], r[5]
                finisaj, tip_toc, dimensiune = "", "", ""
            pret = pret or 0
            pret_lei = round(pret * self.curs_euro, 2)
            pret_lei_cu_tva = round(pret_lei * (1 + self.tva_procent / 100), 2)
            f = ctk.CTkFrame(self.scroll_pret_produse, fg_color="#2D2D2D", corner_radius=4)
            f.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.pack(fill="x", padx=12, pady=8)
            inner.grid_columnconfigure(0, weight=1)
            partile = []
            if categorie:
                partile.append(f"Categorie: {categorie}")
            if furnizor:
                partile.append(f"Furnizor: {furnizor}")
            if categorie == "Tocuri" and (tip_toc or dimensiune):
                partile.append(f"Tip: {tip_toc} Drept {dimensiune}".strip())
            else:
                if colectie:
                    partile.append(f"Colecție: {colectie}")
                if model:
                    if model == "Standard" and colectie:
                        partile.append(f"Denumire: {colectie}")
                    else:
                        partile.append(f"Model: {model}")
                if finisaj:
                    partile.append(f"Finisaj: {finisaj}")
                if decor:
                    partile.append(f"Decor: {decor}")
            text_produs = "\n".join(partile) if partile else "—"
            lbl_produs = ctk.CTkLabel(
                inner,
                text=text_produs,
                font=("Segoe UI", 12),
                anchor="w",
                justify="left",
                wraplength=480,
            )
            lbl_produs.grid(row=0, column=0, sticky="w")
            lbl_pret = ctk.CTkLabel(
                inner,
                text=f"{pret_lei_cu_tva:.2f} LEI (TVA inclus)",
                font=("Segoe UI", 14),
                text_color="#2E7D32",
                anchor="e",
                justify="right",
            )
            lbl_pret.grid(row=0, column=1, sticky="e", padx=(12, 0))

    def refresh_lista_pret_produse(self):
        """Reîmprospătează lista de prețuri (apel direct pe UI, ex. la schimbare curs). Folosește cursorul principal."""
        if not hasattr(self, "scroll_pret_produse") or not self.scroll_pret_produse.winfo_exists():
            return
        termen = self.ent_cauta_produs.get().strip() if hasattr(self, "ent_cauta_produs") else ""
        if not termen:
            self._build_lista_pret_produse_from_rows([], termen)
            return
        limit = 120
        rows = search_produse(self.cursor, termen, limit=limit)
        print(f"[search_produse-sync] termen='{termen}' rezultate={len(rows)}")
        self._build_lista_pret_produse_from_rows(rows, termen)

    # --- FUNCTII NOI PENTRU CAUTARE CLIENT ---
    def _inchide_fereastra_secundara(self, attr_name: str) -> None:
        """Închide Istoric / Căutare (Toplevel); datele din ecranul principal rămân neschimbate."""
        w = getattr(self, attr_name, None)
        if w is None:
            return
        try:
            w.grab_release()
        except Exception:
            pass
        try:
            if w.winfo_exists():
                w.destroy()
        except Exception:
            pass
        setattr(self, attr_name, None)

    def deschide_cautare_client(self, nume_precompletat=None):
        self._iron_curtain_show()
        self._main_transition_active = True
        self.win_cautare = ctk.CTkToplevel(self)
        self.win_cautare.withdraw()
        self.win_cautare.title("Bază de Date Clienți")
        _apply_secondary_toplevel_window_bg(self.win_cautare)
        _apply_fullscreen_workspace(self.win_cautare)
        _body_cautare = _pack_secondary_window_fill_panel(self.win_cautare)

        nav_c = ctk.CTkFrame(
            _body_cautare,
            fg_color=CORP_WINDOW_BG,
            border_width=0,
            corner_radius=0,
        )
        _polish_secondary_frame_surface(nav_c, CORP_WINDOW_BG, border_width=0)
        try:
            tk.Frame.configure(nav_c, bg=CORP_WINDOW_BG, highlightthickness=0)
        except Exception:
            pass
        nav_c.pack(fill="x", padx=20, pady=(10, 4))
        ctk.CTkButton(
            nav_c,
            text="← Înapoi la ecran principal",
            width=260,
            height=32,
            fg_color="#3A3A3A",
            hover_color="#454545",
            font=("Segoe UI", 12),
            command=lambda: self._inchide_fereastra_secundara("win_cautare"),
        ).pack(side="left")

        f_filtre = ctk.CTkFrame(
            _body_cautare,
            fg_color=CORP_WINDOW_BG,
            border_width=0,
            corner_radius=0,
        )
        _polish_secondary_frame_surface(f_filtre, CORP_WINDOW_BG, border_width=0)
        try:
            tk.Frame.configure(f_filtre, bg=CORP_WINDOW_BG, highlightthickness=0)
        except Exception:
            pass
        f_filtre.pack(fill="x", padx=20, pady=(14, 10))

        ctk.CTkLabel(f_filtre, text="Caută Client:").grid(row=0, column=0, padx=10, pady=10)
        self.ent_search_client = ctk.CTkEntry(f_filtre, width=300, placeholder_text="Introduceți nume...")
        self.ent_search_client.grid(row=0, column=1, padx=10, pady=10)
        if nume_precompletat:
            self.ent_search_client.insert(0, nume_precompletat)
        self.ent_search_client.bind("<KeyRelease>", self.update_autosuggestion)

        ctk.CTkLabel(f_filtre, text="Interval:").grid(row=0, column=2, padx=10, pady=10)
        self.combo_interval = ctk.CTkComboBox(
            f_filtre,
            values=["Toate", "Ultima Săptămână", "Ultima Lună", "Ultimul An"],
            command=lambda _x: self._refresh_tabel_clienti_immediate(),
        )
        self.combo_interval.set("Toate")
        self.combo_interval.grid(row=0, column=3, padx=10, pady=10)

        f_header = ctk.CTkFrame(
            _body_cautare,
            fg_color="#2D2D2D",
            height=38,
            corner_radius=4,
            border_width=0,
        )
        _polish_secondary_frame_surface(f_header, "#2D2D2D", border_width=0)
        try:
            tk.Frame.configure(f_header, bg="#2D2D2D", highlightthickness=0)
        except Exception:
            pass
        f_header.pack(fill="x", padx=20, pady=(0, 4))
        f_header.pack_propagate(False)
        headers = [
            ("Nume Client", 0.02, "w"),
            ("Adresă", 0.30, "w"),
            ("Telefon", 0.58, "w"),
            ("Nr. oferte", 0.96, "e"),
        ]
        for text, rel_x, anchor in headers:
            lbl = ctk.CTkLabel(f_header, text=text, font=("Segoe UI", 12), text_color="#2E7D32")
            lbl.place(relx=rel_x, rely=0.5, anchor=anchor)

        ctk.CTkLabel(
            _body_cautare,
            text="Selectați un rând, apoi «Detalii / Oferte» — dublu-click deschide direct.",
            text_color="#aaaaaa",
            font=("Segoe UI", 12),
            anchor="w",
        ).pack(fill="x", padx=24, pady=(0, 4))
        try:
            self.win_cautare.update_idletasks()
        except Exception:
            pass

        self.scroll_tabel = ctk.CTkScrollableFrame(
            _body_cautare,
            fg_color=CORP_WINDOW_BG,
            border_width=0,
            corner_radius=0,
        )
        _polish_secondary_frame_surface(self.scroll_tabel, CORP_WINDOW_BG, border_width=0)
        self.scroll_tabel.pack(fill="both", expand=True, padx=20, pady=(0, 6))
        _patch_scrollable_frame_canvas(self.scroll_tabel, CORP_WINDOW_BG)
        try:
            self.win_cautare.update_idletasks()
        except Exception:
            pass

        cautare_actions = ctk.CTkFrame(
            _body_cautare,
            fg_color="#2D2D2D",
            border_width=1,
            border_color="#333333",
            corner_radius=4,
        )
        _polish_secondary_frame_surface(cautare_actions, "#2D2D2D", border_width=1)
        try:
            tk.Frame.configure(cautare_actions, bg="#2D2D2D", highlightthickness=0)
        except Exception:
            pass
        cautare_actions.pack(fill="x", padx=20, pady=(0, 10))
        self._cautare_btn_detalii = ctk.CTkButton(
            cautare_actions,
            text="Detalii / Oferte",
            width=160,
            fg_color="#2E7D32",
            hover_color="#256B29",
            state="disabled",
            command=self._cautare_action_detalii,
        )
        self._cautare_btn_detalii.pack(side="left", padx=12, pady=10)

        def _on_cautare_destroy(event):
            if event.widget != self.win_cautare:
                return
            if self._after_id_cautare_clienti is not None:
                try:
                    self.after_cancel(self._after_id_cautare_clienti)
                except Exception:
                    pass
                self._after_id_cautare_clienti = None

        self.win_cautare.bind("<Destroy>", _on_cautare_destroy)

        self._cautare_row_pool = None
        try:
            self.win_cautare.update_idletasks()
            self.win_cautare.update()
            time.sleep(0.01)
        except Exception:
            pass
        self._refresh_tabel_clienti_immediate()

    def _refresh_tabel_clienti_immediate(self):
        if self._after_id_cautare_clienti is not None:
            try:
                self.after_cancel(self._after_id_cautare_clienti)
            except Exception:
                pass
            self._after_id_cautare_clienti = None
        self.refresh_tabel_clienti()

    def update_autosuggestion(self, event):
        if self._after_id_cautare_clienti is not None:
            try:
                self.after_cancel(self._after_id_cautare_clienti)
            except Exception:
                pass
        self._after_id_cautare_clienti = self.after(250, self._do_refresh_tabel_clienti)

    def _do_refresh_tabel_clienti(self):
        self._after_id_cautare_clienti = None
        st = getattr(self, "scroll_tabel", None)
        if st is None:
            return
        try:
            if not st.winfo_exists():
                return
        except Exception:
            return
        self.refresh_tabel_clienti()

    def _cautare_set_selected_row(self, idx: int | None) -> None:
        self._cautare_selected_idx = idx
        frames = getattr(self, "_cautare_row_frames", None) or []
        for i, f in enumerate(frames):
            try:
                if f.winfo_exists():
                    bg = ROW_SELECTED_BG if (idx is not None and i == idx) else ROW_LIST_BG
                    f.configure(fg_color=bg)
                    _apply_list_row_frame_native_bg(f, bg)
            except Exception:
                pass
        btn = getattr(self, "_cautare_btn_detalii", None)
        if btn is not None:
            try:
                if btn.winfo_exists():
                    btn.configure(state="normal" if idx is not None else "disabled")
            except Exception:
                pass

    def _cautare_current_client_id(self):
        idx = getattr(self, "_cautare_selected_idx", None)
        if idx is None:
            return None
        ids = getattr(self, "_cautare_client_ids", None) or []
        if idx < 0 or idx >= len(ids):
            return None
        return ids[idx]

    def _cautare_action_detalii(self):
        cid = self._cautare_current_client_id()
        if cid is None:
            self.afiseaza_mesaj("Atenție", "Selectați un client din listă.", "#F57C00")
            return
        self._deschide_detalii_client(cid)

    def _cautare_hide_loading_skeleton(self, st) -> None:
        sk = getattr(self, "_cautare_skeleton", None)
        if sk is not None:
            try:
                if sk.winfo_exists():
                    sk.pack_forget()
            except Exception:
                pass

    def _cautare_show_loading_skeleton(self, st) -> None:
        """Ascunde rândurile din pool și afișează un placeholder de încărcare (fără destroy pe pool)."""
        self._cautare_hide_error_label(st)
        pool = getattr(self, "_cautare_row_pool", None) or []
        for cell in pool:
            try:
                cell["frame"].pack_forget()
            except Exception:
                pass
        sk = getattr(self, "_cautare_skeleton", None)
        if sk is None or not sk.winfo_exists():
            sk = ctk.CTkFrame(
                st,
                fg_color=CORP_WINDOW_BG,
                border_width=0,
                corner_radius=0,
            )
            _polish_secondary_frame_surface(sk, CORP_WINDOW_BG, border_width=0)
            ctk.CTkLabel(
                sk,
                text="Se încarcă clienții…",
                font=("Segoe UI", 12),
                text_color="#9E9E9E",
            ).pack(pady=(12, 8))
            for _ in range(4):
                bar = ctk.CTkFrame(sk, height=10, fg_color="#333333", corner_radius=3, border_width=0)
                _polish_secondary_frame_surface(bar, "#333333", border_width=0)
                bar.pack(fill="x", padx=24, pady=5)
            self._cautare_skeleton = sk
        sk.pack(fill="x", padx=12, pady=16)

    def _cautare_ensure_error_label(self, st) -> ctk.CTkLabel:
        el = getattr(self, "_cautare_error_label", None)
        if el is None or not el.winfo_exists():
            el = ctk.CTkLabel(st, text="", font=("Segoe UI", 12), text_color="#ff8888", wraplength=480)
            self._cautare_error_label = el
        return el

    def _cautare_hide_error_label(self, st) -> None:
        el = getattr(self, "_cautare_error_label", None)
        if el is not None:
            try:
                if el.winfo_exists():
                    el.pack_forget()
            except Exception:
                pass

    def _cautare_fetch_worker(
        self,
        req_id: int,
        search_term: str,
        data_min: str | None,
    ) -> None:
        rows_out: list[dict[str, Any]] = []
        err_msg: str | None = None
        try:
            db = open_db(get_database_path())
            try:
                # Nr. oferte = total echipă (fără filtru pe utilizatorul curent).
                raw = get_clienti_with_oferte_count(
                    db.cursor, search_term, data_min, utilizator_creat=None
                )
                for t in raw:
                    rows_out.append(
                        {
                            "id": t[0],
                            "nume": t[1],
                            "adresa": t[2],
                            "telefon": t[3],
                            "nr_oferte": t[4],
                        }
                    )
            finally:
                try:
                    co = getattr(db, "conn", None)
                    fn = getattr(co, "close", None)
                    if callable(fn):
                        fn()
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("Căutare clienți (background)")
            err_msg = str(exc)
        snapshot = list(rows_out)
        self.after(
            0,
            lambda rid=req_id, data=snapshot, err=err_msg: self._apply_cautare_fetch_result(rid, data, err),
        )

    def _apply_cautare_fetch_result(
        self,
        req_id: int,
        rows_dicts: list[dict[str, Any]],
        err: str | None,
    ) -> None:
        if req_id != self._cautare_fetch_seq:
            return
        win_c = getattr(self, "win_cautare", None)
        st = getattr(self, "scroll_tabel", None)
        if st is None:
            self._schedule_transition_finish(win_c)
            return
        try:
            if not st.winfo_exists():
                self._schedule_transition_finish(win_c)
                return
        except Exception:
            self._schedule_transition_finish(win_c)
            return
        self._cautare_hide_loading_skeleton(st)
        if err is not None:
            self._cautare_client_ids = []
            self._cautare_selected_idx = None
            self._cautare_row_frames = []
            lbl = self._cautare_ensure_error_label(st)
            lbl.configure(text=f"Eroare încărcare: {err[:400]}")
            lbl.pack(anchor="w", padx=12, pady=16)
            btn = getattr(self, "_cautare_btn_detalii", None)
            if btn is not None:
                try:
                    btn.configure(state="disabled")
                except Exception:
                    pass
            self._schedule_transition_finish(win_c)
            return
        self._cautare_hide_error_label(st)
        tuples = [
            (d["id"], d["nume"], d["adresa"], d["telefon"], d["nr_oferte"]) for d in rows_dicts
        ]
        self._render_cautare_table_rows(st, tuples)
        self._schedule_transition_finish(win_c)

    def _render_cautare_table_rows(self, st, date_clienti: list[tuple[Any, ...]]) -> None:
        """Actualizează tabelul clienți pe firul UI; reutilizează frame-urile din pool (fără destroy)."""
        pool = getattr(self, "_cautare_row_pool", None)
        if pool is None:
            self._cautare_row_pool = []
            pool = self._cautare_row_pool
        for cell in pool:
            try:
                cell["frame"].pack_forget()
            except Exception:
                pass

        self._cautare_client_ids = [r[0] for r in date_clienti]
        self._cautare_selected_idx = None

        _font_row = ("Segoe UI", 12)
        _font_name = ("Segoe UI", 12, "bold")
        _muted = "#9E9E9E"

        while len(pool) < len(date_clienti):
            row_f = ctk.CTkFrame(
                st,
                height=44,
                fg_color=ROW_LIST_BG,
                corner_radius=4,
                border_width=0,
            )
            _polish_secondary_frame_surface(row_f, ROW_LIST_BG, border_width=0)
            row_f.pack_propagate(False)
            lbl_n = ctk.CTkLabel(row_f, text="", font=_font_name, anchor="w")
            lbl_n.place(relx=0.02, rely=0.5, anchor="w")
            lbl_a = ctk.CTkLabel(row_f, text="", font=_font_row, text_color=_muted, anchor="w")
            lbl_a.place(relx=0.30, rely=0.5, anchor="w")
            lbl_t = ctk.CTkLabel(row_f, text="", font=_font_row, anchor="w")
            lbl_t.place(relx=0.58, rely=0.5, anchor="w")
            lbl_no = ctk.CTkLabel(row_f, text="", font=_font_row, text_color=_muted, anchor="e")
            lbl_no.place(relx=0.98, rely=0.5, anchor="e")
            pool.append({"frame": row_f, "lbl_n": lbl_n, "lbl_a": lbl_a, "lbl_t": lbl_t, "lbl_no": lbl_no})

        self._cautare_row_frames = []
        for i, r in enumerate(date_clienti):
            _cid, nume, adresa, tel, nr_oferte = r
            cell = pool[i]
            row_f = cell["frame"]
            cell["lbl_n"].configure(text=str(nume).upper())
            cell["lbl_a"].configure(text=str(adresa or ""))
            cell["lbl_t"].configure(text=str(tel or ""))
            cell["lbl_no"].configure(text=str(nr_oferte))
            row_f.configure(fg_color=ROW_LIST_BG)
            _apply_list_row_frame_native_bg(row_f, ROW_LIST_BG)
            row_f.pack(fill="x", pady=1)
            self._cautare_row_frames.append(row_f)

            def _bind_cautare_row(idx: int):
                def _select(_event=None):
                    self._cautare_set_selected_row(idx)

                def _double(_event=None):
                    self._cautare_set_selected_row(idx)
                    self._cautare_action_detalii()

                return _select, _double

            _sel, _dbl = _bind_cautare_row(i)
            for w in (row_f, cell["lbl_n"], cell["lbl_a"], cell["lbl_t"], cell["lbl_no"]):
                w.bind("<Button-1>", _sel)
                w.bind("<Double-Button-1>", _dbl)

        btn = getattr(self, "_cautare_btn_detalii", None)
        if btn is not None:
            try:
                if btn.winfo_exists():
                    btn.configure(state="disabled")
            except Exception:
                pass

        try:
            st._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def refresh_tabel_clienti(self):
        st = getattr(self, "scroll_tabel", None)
        if st is None:
            return
        try:
            if not st.winfo_exists():
                return
        except Exception:
            return

        self._cautare_fetch_seq += 1
        req_id = self._cautare_fetch_seq

        search_term = f"%{self.ent_search_client.get()}%"
        interval = self.combo_interval.get()
        data_min = None
        if interval != "Toate":
            zile = {"Ultima Săptămână": 7, "Ultima Lună": 30, "Ultimul An": 365}
            data_min = (datetime.now() - timedelta(days=zile[interval])).strftime("%Y-%m-%d")
        self._cautare_show_loading_skeleton(st)
        threading.Thread(
            target=self._cautare_fetch_worker,
            args=(req_id, search_term, data_min),
            daemon=True,
        ).start()

    def _deschide_detalii_client(self, client_id):
        """Deschide fereastra cu toate datele clientului și lista ofertelor realizate."""
        row = get_client_by_id(self.cursor, client_id)
        if not row:
            self.afiseaza_mesaj("Eroare", "Client negăsit.", "#7a1a1a")
            return
        nume, telefon, adresa, email = row[0], row[1] or "", row[2] or "", (row[3] or "").strip()

        oferte = get_offers_by_client(self.cursor, client_id, utilizator_creat=None)

        win = ctk.CTkToplevel(self)
        win.title(f"Client: {nume}")
        win.geometry("700x550")
        win.configure(fg_color=CORP_WINDOW_BG)
        _apply_tk_window_chrome_dark(win)
        win.grab_set()
        win.transient(self)

        f_info = ctk.CTkFrame(win, fg_color="#363636")
        f_info.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(f_info, text="DATE CLIENT", font=("Segoe UI", 14, "bold"), text_color="#2E7D32").pack(anchor="w", padx=15, pady=(10, 5))
        ctk.CTkLabel(f_info, text=f"Nume: {nume}", font=("Segoe UI", 12)).pack(anchor="w", padx=15, pady=2)
        ctk.CTkLabel(f_info, text=f"Telefon: {telefon}", font=("Segoe UI", 12)).pack(anchor="w", padx=15, pady=2)
        ctk.CTkLabel(f_info, text=f"Adresă: {adresa}", font=("Segoe UI", 12)).pack(anchor="w", padx=15, pady=2)
        if email:
            ctk.CTkLabel(f_info, text=f"Email: {email}", font=("Segoe UI", 12)).pack(anchor="w", padx=15, pady=2)
        ctk.CTkLabel(f_info, text=f"Total oferte: {len(oferte)}", font=("Segoe UI", 12)).pack(anchor="w", padx=15, pady=(2, 10))

        ctk.CTkLabel(win, text="OFERTE REALIZATE", font=("Segoe UI", 14, "bold"), text_color="#2E7D32").pack(anchor="w", padx=20, pady=(10, 5))
        scroll = ctk.CTkScrollableFrame(win, fg_color=CORP_WINDOW_BG)
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        _patch_scrollable_frame_canvas(scroll, CORP_WINDOW_BG)

        for id_o, data_oferta, total_lei, detalii, avans in oferte:
            f_o = ctk.CTkFrame(scroll, fg_color="#2b2b2b")
            f_o.pack(fill="x", pady=4)
            nr = str(id_o).zfill(5)
            ctk.CTkLabel(
                f_o, text=f"Nr. {nr}  |  Data: {data_oferta}  |  Total: {total_lei:.2f} LEI",
                font=("Segoe UI", 12),
            ).pack(side="left", padx=15, pady=10)
            produse_raw = loads_offer_items(detalii) if detalii else []
            produse_payload = produse_raw if isinstance(produse_raw, dict) else {"items": produse_raw}
            ctk.CTkButton(
                f_o, text="Deschide oferta", width=120, height=28, fg_color="#2E7D32",
                command=lambda p=produse_payload, n=nume, oid=id_o, d=data_oferta, w=win: (
                    self.porneste_ofertarea({"id_oferta": oid, "data_oferta": d, "nume": n, "produse": p}),
                    w.destroy(),
                ),
            ).pack(side="right", padx=10, pady=8)

    # --- FINAL FUNCTII NOI ---

    def _normalize_telefon(self, s):
        """Returnează doar cifrele din telefon pentru comparare."""
        if not s:
            return ""
        return "".join(c for c in str(s).strip() if c.isdigit())

    def _verifica_telefon_existent(self):
        """Verifică dacă numărul introdus există în baza de date; dacă da, afișează dialog cu opțiune de deschidere date client."""
        if getattr(self, "_dialog_telefon_activ", False):
            return
        try:
            if not getattr(self, "entry_tel", None) or not self.entry_tel.winfo_exists():
                return
            tel = (self.entry_tel.get() or "").strip()
            if not tel:
                return
            tel_norm = self._normalize_telefon(tel)
            if not tel_norm:
                return
            for nume_client, tel_db in get_all_clienti_telefon(self.cursor):
                if tel_db and self._normalize_telefon(tel_db) == tel_norm:
                    self._dialog_telefon_existent(nume_client)
                    return
        except Exception:
            logger.warning("Verificare telefon existent a eșuat", exc_info=True)

    def _dialog_telefon_existent(self, nume_client):
        """Dialog: număr existent, alocat clientului X; buton pentru deschidere date client."""
        self._dialog_telefon_activ = True
        win = ctk.CTkToplevel(self)
        win.title("Număr existent")
        win.geometry("420x220")
        win.attributes("-topmost", True)
        win.grab_set()

        def la_inchidere():
            self._dialog_telefon_activ = False
            if win.winfo_exists():
                win.destroy()

        win.protocol("WM_DELETE_WINDOW", la_inchidere)
        ctk.CTkLabel(
            win, text=f"Acest număr de telefon există deja în baza de date.\nEste alocat clientului: {nume_client}.",
            font=("Segoe UI", 13), wraplength=380, justify="center",
        ).pack(expand=True, pady=(24, 12), padx=20)
        ctk.CTkButton(
            win, text="Deschide date client", width=220, height=36, fg_color="#2E7D32",
            command=lambda: self._inchide_si_deschide_date_client(win, nume_client),
        ).pack(pady=(0, 24))
        win.transient(self)

    def _inchide_si_deschide_date_client(self, dialog_win, nume_client):
        """Închide dialogul și deschide direct modulul de ofertă cu datele clientului."""
        self._dialog_telefon_activ = False
        if dialog_win.winfo_exists():
            dialog_win.destroy()
        self.after(150, lambda: self._deschide_oferta_pentru_client(nume_client))

    def _deschide_oferta_pentru_client(self, nume_client):
        """Încarcă datele clientului din DB, completează formularul și deschide direct configuratorul de ofertă."""
        try:
            row = get_client_by_name(self.cursor, nume_client)
            if not row:
                self.afiseaza_mesaj("Eroare", f"Clientul '{nume_client}' nu a fost găsit în baza de date.", "#7a1a1a")
                return
            nume, telefon, adresa = row[0], (row[1] or "").strip(), (row[2] or "").strip()
            email = (row[3] or "").strip() if len(row) > 3 else ""
            if not getattr(self, "entry_nume", None) or not self.entry_nume.winfo_exists():
                return
            self.entry_nume.delete(0, "end")
            self.entry_nume.insert(0, nume)
            self.entry_tel.delete(0, "end")
            self.entry_tel.insert(0, telefon)
            self.entry_adresa.delete(0, "end")
            self.entry_adresa.insert(0, adresa)
            if getattr(self, "entry_email", None):
                self.entry_email.delete(0, "end")
                self.entry_email.insert(0, email)
            self._dialog_telefon_activ = True
            self.porneste_ofertarea()
            self.after(2500, lambda: setattr(self, "_dialog_telefon_activ", False))
        except Exception:
            logger.exception("Încărcare date client pentru ofertă")
            self._dialog_telefon_activ = False
            self.afiseaza_mesaj("Eroare", "Nu s-au putut încărca datele clientului.", "#7a1a1a")

    def _deschide_dev_mode(self):
        """Deschide fereastra de ofertă fără date client, după verificarea parolei contului."""
        if not (self._privileges and len(self._privileges) > 4 and self._privileges[4] == 1):
            self.afiseaza_mesaj("Nu aveți permisiune", "Privilegiul „Mod Dev” nu este activat pentru contul dvs.", "#7a1a1a")
            return
        dialog = ctk.CTkInputDialog(
            text="Introdu parola contului pentru Dev Mode:",
            title="Dev Mode",
        )
        parola = dialog.get_input()
        if parola is None:
            return
        user = (self.utilizator_creat or "").strip()
        if not user:
            self.afiseaza_mesaj("Eroare", "Nu există utilizator autentificat.", "#7a1a1a")
            return
        try:
            row = get_user_for_login(self.cursor, user)
            if row:
                password_hash = row[0]
                if _hash_parola(parola) != password_hash:
                    self.afiseaza_mesaj("Eroare", "Parolă incorectă.", "#7a1a1a")
                    return
            else:
                cfg = self.config_app
                if user != (getattr(cfg, "login_user", "") or "").strip() or parola != (getattr(cfg, "login_password", "") or ""):
                    self.afiseaza_mesaj("Eroare", "Parolă incorectă.", "#7a1a1a")
                    return
        except Exception:
            logger.exception("Verificare parolă Dev Mode")
            self.afiseaza_mesaj("Eroare", "Nu s-a putut verifica parola.", "#7a1a1a")
            return
        self.porneste_ofertarea(dev_mode=True)

    def porneste_ofertarea(self, date_istoric=None, dev_mode=False, modifica=False):
        self._edit_offer_id = None
        self._last_saved_offer_id = None
        self.id_oferta_curenta = None
        self.data_oferta_curenta = ""
        mentiuni_initiale = ""
        afiseaza_mentiuni_initial = False
        conditii_pdf_initial = False
        termen_livrare_initial = 0
        if date_istoric:
            oid_hist = date_istoric.get("id_oferta")
            self.id_oferta_curenta = oid_hist
            self.data_oferta_curenta = (date_istoric.get("data_oferta") or "").strip()
            nume = date_istoric.get("nume", "")
            produse_payload = date_istoric.get("produse", [])
            self.masuratori_lei = 0.0
            self.transport_lei = 0.0
            # costs_entered în detalii: lipsă = oferte vechi (considerăm pasul costuri deja parcurs); False = încă nu s-a închis dialogul.
            self._offer_costs_entered = True
            # Suport atât pentru format vechi (listă simplă), cât și nou (dict cu items + mentiuni).
            if isinstance(produse_payload, dict):
                self.cos_cumparaturi = produse_payload.get("items", [])
                mentiuni_initiale = produse_payload.get("mentiuni", "") or ""
                afiseaza_mentiuni_initial = bool(produse_payload.get("afiseaza_mentiuni_pdf", False))
                conditii_pdf_initial = bool(produse_payload.get("conditii_pdf", False))
                termen_livrare_initial = str(produse_payload.get("termen_livrare_zile", "0") or "0").strip()
                try:
                    self.masuratori_lei = float(produse_payload.get("masuratori_lei") or 0)
                except (TypeError, ValueError):
                    self.masuratori_lei = 0.0
                try:
                    self.transport_lei = float(produse_payload.get("transport_lei") or 0)
                except (TypeError, ValueError):
                    self.transport_lei = 0.0
                if "costs_entered" in produse_payload:
                    self._offer_costs_entered = bool(produse_payload.get("costs_entered"))
            else:
                self.cos_cumparaturi = produse_payload
            if modifica and oid_hist:
                self._edit_offer_id = int(oid_hist)
            readonly = not modifica
            # Modificare / „Rescrie”: nu mai afișăm dialogul de costuri (valorile sunt deja în ofertă sau nu se re-cere pasul).
            if modifica and oid_hist:
                self._offer_costs_entered = True
        elif dev_mode:
            nume = "Dev Mode"
            self.cos_cumparaturi = []
            readonly = False
            self._offer_costs_entered = False
        else:
            nume = self.entry_nume.get().strip()
            tel = self.entry_tel.get().strip()
            if not nume:
                self.afiseaza_mesaj("Atenție", "Te rugăm să introduci numele clientului!", "#7a1a1a")
                return
            if not (len(tel) == 10 and tel.isdigit() and tel.startswith("07")):
                self.afiseaza_mesaj("Eroare Format", "Telefon invalid (10 cifre, începe cu 07)!", "#7a1a1a")
                return
            self.cos_cumparaturi = []
            readonly = False
            self._offer_costs_entered = False

        self.win_oferta = ctk.CTkToplevel(self)
        self.win_oferta.title(f"Configurator - {nume}")
        self.win_oferta.geometry("1520x850")
        self.win_oferta.minsize(1200, 700)
        self.win_oferta.configure(fg_color=OFERTA_WINDOW_BG, bg_color=OFERTA_WINDOW_BG)
        _apply_tk_window_chrome_dark(self.win_oferta, OFERTA_WINDOW_BG)
        _force_ctk_native_dark_bg(self.win_oferta, OFERTA_WINDOW_BG)
        self.win_oferta.grab_set()
        self._win_oferta_readonly = readonly
        # La deschiderea unei oferte presupunem că încă nu este salvată în sesiunea curentă
        self._oferta_salvata_recent = False
        # Safe Mode: pornit implicit la fiecare ofertă nou deschisă
        self.safe_mode_enabled = True

        main_layout = ctk.CTkFrame(
            self.win_oferta, fg_color=OFERTA_WINDOW_BG, bg_color=OFERTA_WINDOW_BG, corner_radius=0
        )
        _force_ctk_native_dark_bg(main_layout, OFERTA_WINDOW_BG)
        main_layout.pack(fill="both", expand=True, padx=8, pady=8)

        f_selectie = ctk.CTkFrame(
            main_layout,
            width=520,
            fg_color=CORP_FRAME_BG,
            bg_color=OFERTA_WINDOW_BG,
            corner_radius=OFERTA_WIDGET_RADIUS,
        )
        _force_ctk_native_dark_bg(f_selectie, CORP_FRAME_BG)
        f_selectie.pack(side="left", fill="both", padx=(0, 10))
        f_selectie.pack_propagate(False)

        f_global_filter = ctk.CTkFrame(
            f_selectie, fg_color="#2D2D2D", bg_color=CORP_FRAME_BG, height=72, corner_radius=OFERTA_WIDGET_RADIUS
        )
        f_global_filter.pack(fill="x", padx=10, pady=(20, 10))
        f_global_filter.pack_propagate(False)
        ctk.CTkLabel(
            f_global_filter,
            text="Alege furnizorul de ofertă:",
            font=("Segoe UI", 12),
            text_color="#2E7D32",
        ).pack(side="left", padx=10)
        self.var_furnizor_global = ctk.StringVar(value="Stoc")
        rb_stoc = ctk.CTkRadioButton(
            f_global_filter, text="STOC", variable=self.var_furnizor_global, value="Stoc",
            command=self.switch_catalog_global, font=("Segoe UI", 11),
        )
        rb_erkado = ctk.CTkRadioButton(
            f_global_filter, text="ERKADO", variable=self.var_furnizor_global, value="Erkado",
            command=self.switch_catalog_global, font=("Segoe UI", 11),
        )
        rb_stoc.pack(side="left", padx=5)
        rb_erkado.pack(side="left", padx=5)
        self._style_corporate_radio(rb_stoc)
        self._style_corporate_radio(rb_erkado)
        if not readonly:
            btn_parchet = ctk.CTkButton(
                f_global_filter, text="PARCHET", width=140, height=32,
                font=("Segoe UI", 11),
                fg_color=CORP_MATT_GREY,
                hover_color="#454545",
                text_color="#ECEFF1",
                corner_radius=OFERTA_WIDGET_RADIUS,
                command=self._deschide_popup_parchet,
            )
            btn_parchet.pack(side="right", padx=(6, 6))

        # Zone derulabile: categorii + servicii suplimentare (ca să fie mereu accesibile)
        scroll_selectie = ctk.CTkScrollableFrame(
            f_selectie, fg_color=CORP_FRAME_BG, bg_color=CORP_FRAME_BG
        )
        scroll_selectie.pack(fill="both", expand=True, pady=(0, 5))
        _patch_scrollable_frame_canvas(scroll_selectie, CORP_FRAME_BG)
        f_selectie_footer = ctk.CTkFrame(f_selectie, fg_color=CORP_FRAME_BG, bg_color=CORP_FRAME_BG)
        f_selectie_footer.pack(fill="x", padx=10, pady=(0, 8))
        self.btn_safe_mode = ctk.CTkButton(
            f_selectie_footer,
            text="Safe Mode: ON",
            width=130,
            height=32,
            font=("Segoe UI", 11),
            corner_radius=OFERTA_WIDGET_RADIUS,
            command=self._toggle_safe_mode,
        )
        self.btn_safe_mode.pack(side="left", anchor="w", padx=(0, 6))
        self._update_safe_mode_button_ui()

        self.config_widgets = {}
        categorii = self._get_categorii_din_db()
        for sectiune in categorii:
            self.creeaza_grup_configurare(scroll_selectie, sectiune, readonly)

        # Servicii suplimentare: prețuri fixe, fără discount
        SERVICII_SUPLIMENTARE = [
            ("Scurtare set usa +toc", 11.0),
            ("Redimensionare K", 52.0),
            ("Redimensionare sus-jos", 52.0),
        ]
        # Secțiune pliabilă pentru Servicii suplimentare
        f_servicii = ctk.CTkFrame(scroll_selectie, fg_color="#2D2D2D")
        self._style_oferta_section_frame(f_servicii)
        f_servicii.pack(fill="x", pady=5, padx=10)
        f_servicii_header = ctk.CTkFrame(f_servicii, fg_color="transparent")
        f_servicii_header.pack(fill="x", padx=10, pady=5)
        lbl_servicii_titlu = ctk.CTkLabel(
            f_servicii_header,
            text="▾ Servicii suplimentare",
            font=("Segoe UI", 13, "bold"),
            text_color="#78909C",
        )
        lbl_servicii_titlu.pack(anchor="w")
        lbl_servicii_hint = ctk.CTkLabel(
            f_servicii_header,
            text="(prețuri fixe, nu se aplică discount)",
            font=("Segoe UI", 9),
            text_color="#888888",
        )
        lbl_servicii_hint.pack(anchor="w", pady=(0, 2))

        f_servicii_content = ctk.CTkFrame(f_servicii, fg_color="transparent")
        f_servicii_content.pack(fill="x", padx=0, pady=(0, 5))

        for nume_serviciu, pret_eur in SERVICII_SUPLIMENTARE:
            r = ctk.CTkFrame(f_servicii_content, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(r, text=nume_serviciu, font=("Segoe UI", 11), anchor="w").pack(side="left", fill="x", expand=True)
            if not readonly:
                ctk.CTkButton(
                    r, text="Adaugă", width=70, height=28, fg_color="#2E7D32",
                    command=lambda n=nume_serviciu, p=pret_eur: self._adauga_serviciu_suplimentar(n, p),
                ).pack(side="right", padx=(5, 0))
                self._style_add_button(r.winfo_children()[-1])

        def _toggle_servicii():
            if f_servicii_content.winfo_ismapped():
                f_servicii_content.pack_forget()
                lbl_servicii_titlu.configure(text="▸ Servicii suplimentare")
            else:
                f_servicii_content.pack(fill="x", padx=0, pady=(0, 5))
                lbl_servicii_titlu.configure(text="▾ Servicii suplimentare")

        f_servicii_header.bind("<Button-1>", lambda e: _toggle_servicii())
        lbl_servicii_titlu.bind("<Button-1>", lambda e: _toggle_servicii())
        lbl_servicii_hint.bind("<Button-1>", lambda e: _toggle_servicii())

        # —— Produs manual (uz general): uși / tocuri / accesorii / orice ——
        f_manual = ctk.CTkFrame(scroll_selectie, fg_color="#2D2D2D")
        self._style_oferta_section_frame(f_manual)
        f_manual.pack(fill="x", pady=5, padx=10)
        f_manual_header = ctk.CTkFrame(f_manual, fg_color="transparent")
        f_manual_header.pack(fill="x", padx=10, pady=5)
        lbl_manual_titlu = ctk.CTkLabel(
            f_manual_header,
            text="▾ Adaugă produs manual (uz general)",
            font=("Segoe UI", 13, "bold"),
            text_color="#78909C",
        )
        lbl_manual_titlu.pack(anchor="w")
        lbl_manual_hint = ctk.CTkLabel(
            f_manual_header,
            text="Denumire, cantitate (buc) și preț – apare în ofertă ca o linie separată.",
            font=("Segoe UI", 9),
            text_color="#888888",
        )
        lbl_manual_hint.pack(anchor="w", pady=(0, 2))

        f_manual_content = ctk.CTkFrame(f_manual, fg_color="transparent")
        f_manual_content.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(f_manual_content, text="Denumire:", font=("Segoe UI", 11)).grid(row=0, column=0, padx=6, pady=4, sticky="e")
        entry_manual_nume = ctk.CTkEntry(f_manual_content, width=280, placeholder_text="ex: Plintă MDF, Izolație 3mm...")
        entry_manual_nume.grid(row=0, column=1, columnspan=3, padx=6, pady=4, sticky="w")
        self._style_modern_entry(entry_manual_nume)

        ctk.CTkLabel(f_manual_content, text="Cantitate (buc):", font=("Segoe UI", 11)).grid(row=1, column=0, padx=6, pady=4, sticky="e")
        entry_manual_qty = ctk.CTkEntry(f_manual_content, width=80, placeholder_text="ex: 5")
        entry_manual_qty.grid(row=1, column=1, padx=6, pady=4, sticky="w")
        self._style_modern_entry(entry_manual_qty)

        ctk.CTkLabel(f_manual_content, text="Preț/unitate (€):", font=("Segoe UI", 11)).grid(row=2, column=0, padx=6, pady=4, sticky="e")
        entry_manual_pret = ctk.CTkEntry(f_manual_content, width=100, placeholder_text="ex: 5.50")
        entry_manual_pret.grid(row=2, column=1, padx=6, pady=4, sticky="w")
        self._style_modern_entry(entry_manual_pret)

        def _adauga_produs_manual_in_cos():
            nume = (entry_manual_nume.get() or "").strip()
            try:
                qty_str = (entry_manual_qty.get() or "").strip().replace(",", ".")
                qty_val = float(qty_str) if qty_str else 0.0
            except ValueError:
                qty_val = 0.0
            try:
                pret_str = (entry_manual_pret.get() or "").strip().replace(",", ".")
                pret_val = float(pret_str) if pret_str else 0.0
            except ValueError:
                pret_val = 0.0
            if not nume or qty_val <= 0 or pret_val <= 0:
                self.afiseaza_mesaj("Atenție", "Completează denumirea, cantitatea și prețul.", "#7a1a1a")
                return
            qty_afis = int(round(qty_val)) if abs(qty_val - round(qty_val)) < 1e-6 else qty_val
            self.cos_cumparaturi.append({
                "nume": nume,
                "pret_eur": round(pret_val, 2),
                "qty": qty_afis,
                "tip": "produs_manual",
            })
            entry_manual_nume.delete(0, "end")
            entry_manual_qty.delete(0, "end")
            entry_manual_pret.delete(0, "end")
            self.refresh_cos(readonly)

        ctk.CTkButton(
            f_manual_content,
            text="Adaugă în ofertă",
            width=180,
            fg_color="#2E7D32",
            command=_adauga_produs_manual_in_cos,
        ).grid(row=3, column=0, columnspan=4, padx=6, pady=(6, 0), sticky="w")
        self._style_add_button(f_manual_content.winfo_children()[-1])

        def _toggle_manual():
            if f_manual_content.winfo_ismapped():
                f_manual_content.pack_forget()
                lbl_manual_titlu.configure(text="▸ Adaugă produs manual (uz general)")
            else:
                f_manual_content.pack(fill="x", padx=10, pady=(0, 8))
                lbl_manual_titlu.configure(text="▾ Adaugă produs manual (uz general)")

        f_manual_header.bind("<Button-1>", lambda e: _toggle_manual())
        lbl_manual_titlu.bind("<Button-1>", lambda e: _toggle_manual())
        lbl_manual_hint.bind("<Button-1>", lambda e: _toggle_manual())

        self._update_erkado_decor_text_visibility()

        self.f_cos = ctk.CTkFrame(
            main_layout,
            width=1010,
            fg_color=CORP_FRAME_BG,
            bg_color=OFERTA_WINDOW_BG,
            corner_radius=OFERTA_WIDGET_RADIUS,
            border_width=1,
            border_color=BORDER_GRAY,
        )
        _force_ctk_native_dark_bg(self.f_cos, CORP_FRAME_BG)
        self.f_cos.pack(side="right", fill="both", padx=(4, 0))
        self.tabview_cos = ctk.CTkTabview(
            self.f_cos, width=980, corner_radius=OFERTA_WIDGET_RADIUS, fg_color=CORP_FRAME_BG
        )
        self.tabview_cos.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.tabview_cos.add("Produse în ofertă")
        tab_produse = self.tabview_cos.tab("Produse în ofertă")
        ctk.CTkLabel(
            tab_produse,
            text="Coș de cumpărături",
            font=("Segoe UI", 15, "bold"),
            text_color="#2E7D32",
        ).pack(pady=(0, 6))
        self.lbl_cos_header_totals = ctk.CTkLabel(
            tab_produse,
            text="Total EUR: 0.00 | Total RON (TVA): 0.00",
            font=("Segoe UI", 12, "bold"),
            text_color="#EAB308",
        )
        self.lbl_cos_header_totals.pack(pady=(0, 6))
        frame_tabel = ctk.CTkFrame(
            tab_produse,
            fg_color="#2D2D2D",
            corner_radius=OFERTA_WIDGET_RADIUS,
            border_width=1,
            border_color=BORDER_GRAY,
        )
        frame_tabel.pack(fill="both", expand=True, padx=5)
        self.scroll_cos = ctk.CTkScrollableFrame(frame_tabel, fg_color="#2D2D2D", bg_color="#2D2D2D")
        self.scroll_cos.pack(fill="both", expand=True, padx=6, pady=6)
        _patch_scrollable_frame_canvas(self.scroll_cos, "#2D2D2D")

        self.tabview_cos.add("Rezumat ofertă")
        tab_parchet = self.tabview_cos.tab("Rezumat ofertă")
        f_parchet_header = ctk.CTkFrame(tab_parchet, fg_color="transparent")
        f_parchet_header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            f_parchet_header,
            text="REZUMAT OFERTĂ",
            font=("Segoe UI", 15, "bold"),
            anchor="center",
            justify="center",
        ).pack(pady=(0, 8))
        self.frame_rezumat_parchet = ctk.CTkFrame(tab_parchet, fg_color="transparent")
        self.frame_rezumat_parchet.pack(fill="both", expand=True, padx=5)
        self._rezumat_oferta_entry_vars = []

        self.var_conditii_pdf = ctk.BooleanVar(value=conditii_pdf_initial)
        f_conditii = ctk.CTkFrame(self.f_cos, fg_color="transparent", bg_color=CORP_FRAME_BG)
        f_conditii.pack(fill="x", padx=16, pady=(4, 8))
        cb_conditii = ctk.CTkCheckBox(
            f_conditii,
            text="Condiții",
            variable=self.var_conditii_pdf,
            width=120,
        )
        self._style_corporate_checkbox(cb_conditii)
        cb_conditii.pack(side="left")
        ctk.CTkLabel(
            f_conditii,
            text="Timp livrare:",
            font=("Segoe UI", 12),
        ).pack(side="left", padx=(14, 6))
        self.entry_termen_conditii = ctk.CTkEntry(f_conditii, width=56, placeholder_text="0")
        self._style_modern_entry(self.entry_termen_conditii)
        self.entry_termen_conditii.pack(side="left")
        ctk.CTkLabel(f_conditii, text="zile", font=("Segoe UI", 12)).pack(side="left", padx=(6, 0))
        self.entry_termen_conditii.delete(0, "end")
        self.entry_termen_conditii.insert(0, str(termen_livrare_initial))

        f_actiuni_oferta = ctk.CTkFrame(self.f_cos, fg_color="transparent", bg_color=CORP_FRAME_BG)
        f_actiuni_oferta.pack(fill="x", padx=16, pady=(0, 8))
        btn_pdf = ctk.CTkButton(
            f_actiuni_oferta,
            text="Generează PDF Ofertă",
            fg_color="#F57C00",
            hover_color="#E65100",
            corner_radius=OFERTA_WIDGET_RADIUS,
            text_color="white",
            font=("Segoe UI", 13, "bold"),
            height=40,
            command=lambda: self.genereaza_pdf(nume),
        )
        btn_pdf.pack(fill="x", pady=(0, 8))
        if not readonly:
            btn_save = ctk.CTkButton(
                f_actiuni_oferta,
                text="Salvează Ofertă",
                fg_color="#2E7D32",
                hover_color="#256B29",
                corner_radius=OFERTA_WIDGET_RADIUS,
                text_color="white",
                font=("Segoe UI", 13, "bold"),
                height=40,
                command=lambda: self.salveaza_oferta_finala(show_costs_dialog=True),
            )
            btn_save.pack(fill="x", pady=(0, 8))
            btn_goleste = ctk.CTkButton(
                f_actiuni_oferta,
                text="Golește coș",
                fg_color="transparent",
                hover_color="#353535",
                corner_radius=OFERTA_WIDGET_RADIUS,
                border_width=1,
                border_color=BORDER_GRAY,
                text_color="#ECEFF1",
                font=("Segoe UI", 12),
                height=36,
                command=lambda: self._goleste_cos_oferta(readonly),
            )
            btn_goleste.pack(fill="x")

        # Mentiuni ofertă + opțiune afișare în PDF
        self.txt_mentiuni = ctk.CTkTextbox(self.f_cos, height=55, corner_radius=OFERTA_WIDGET_RADIUS)
        self.txt_mentiuni.pack(fill="x", padx=16, pady=(4, 4))
        placeholder_text = "Mențiuni / condiții speciale (opțional). Acest text poate fi inclus sau nu în PDF."
        if mentiuni_initiale:
            self.txt_mentiuni.insert("1.0", mentiuni_initiale)
            self._mentiuni_placeholder_active = False
        else:
            self.txt_mentiuni.insert("1.0", placeholder_text)
            self._mentiuni_placeholder_active = True

        def _clear_placeholder(event=None):
            if self._mentiuni_placeholder_active:
                self.txt_mentiuni.delete("1.0", "end")
                self._mentiuni_placeholder_active = False

        def _restore_placeholder_if_empty(event=None):
            if not self.txt_mentiuni.get("1.0", "end").strip():
                self.txt_mentiuni.insert("1.0", placeholder_text)
                self._mentiuni_placeholder_active = True

        self.txt_mentiuni.bind("<FocusIn>", _clear_placeholder)
        self.txt_mentiuni.bind("<FocusOut>", _restore_placeholder_if_empty)

        self.var_afiseaza_mentiuni_pdf = ctk.BooleanVar(value=afiseaza_mentiuni_initial)
        cb_mentiuni_pdf = ctk.CTkCheckBox(
            self.f_cos,
            text="Afișează mențiunile de mai sus pe PDF",
            variable=self.var_afiseaza_mentiuni_pdf,
        )
        self._style_corporate_checkbox(cb_mentiuni_pdf)
        cb_mentiuni_pdf.pack(anchor="w", padx=20, pady=(0, 6))

        max_disc = self._privileges[1] if self._privileges else 15
        max_disc = max(0, min(50, int(max_disc) if isinstance(max_disc, (int, float)) else 15))
        discount_values = sorted(set(["0"] + [str(x) for x in range(5, max_disc + 1, 5)] + [str(max_disc)]), key=lambda x: int(x))
        state = "readonly" if readonly else "normal"
        self.discount_var = ctk.StringVar(value="0")
        f_total_area = ctk.CTkFrame(self.f_cos, fg_color="transparent", bg_color=CORP_FRAME_BG)
        f_total_area.pack(fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(f_total_area, text="Discount (%):", font=("Segoe UI", 12)).pack(side="left", padx=(0, 8))
        self.combo_discount = ctk.CTkComboBox(
            f_total_area,
            values=discount_values or ["0"],
            width=70,
            command=lambda _choice: self._on_discount_choice(readonly),
            state=state,
            variable=self.discount_var,
        )
        self._style_modern_combobox(self.combo_discount)
        try:
            self.combo_discount.configure(corner_radius=OFERTA_WIDGET_RADIUS)
        except Exception:
            pass
        self.combo_discount.set("0")
        self.combo_discount.pack(side="left", padx=(0, 12))
        self.discount_var.trace_add("write", lambda *_: self._on_discount_var_write(readonly))
        self.combo_discount.bind("<KeyRelease>", lambda e: self._on_discount_keyrelease(e, readonly))
        self.combo_discount.bind("<Return>", lambda e: self._normalize_discount_input(e, readonly))
        self.combo_discount.bind("<FocusOut>", lambda e: self._normalize_discount_input(e, readonly))
        ctk.CTkButton(
            f_total_area,
            text="Reîmprospătare catalog",
            width=160,
            height=32,
            font=("Segoe UI", 11),
            fg_color=CORP_MATT_GREY,
            hover_color="#454545",
            corner_radius=OFERTA_WIDGET_RADIUS,
            command=self._refresh_oferta_catalog,
        ).pack(side="right")

        if date_istoric and date_istoric.get("id_oferta"):
            snap = get_offer_snapshot(self.cursor, int(date_istoric["id_oferta"]), force_refresh=True)
            if snap:
                try:
                    dproc_snap = int(snap.get("discount_proc") or 0)
                except (TypeError, ValueError):
                    dproc_snap = 0
                ds = str(max(0, min(dproc_snap, max_disc)))
                if ds not in discount_values:
                    nums = sorted(int(x) for x in discount_values)
                    lower = max([n for n in nums if n <= int(ds)], default=0)
                    ds = str(lower)
                self.combo_discount.set(ds)
                try:
                    self.curs_euro = float(snap.get("curs_euro") or self.curs_euro)
                except (TypeError, ValueError):
                    pass
                self.safe_mode_enabled = bool(int(snap.get("safe_mode_enabled") or 1))
                self._update_safe_mode_button_ui()

        self.frame_rezumat_pret = ctk.CTkFrame(
            self.f_cos, fg_color="#2D2D2D", corner_radius=OFERTA_WIDGET_RADIUS, border_width=1, border_color=BORDER_GRAY
        )
        self.frame_rezumat_pret.pack(fill="x", padx=16, pady=(4, 12))
        _tva_lbl = int(round(float(self.tva_procent)))
        self.lbl_valoare_totala = ctk.CTkLabel(
            self.frame_rezumat_pret,
            text=f"Total Listă (TVA {_tva_lbl}%): 0.00 RON",
            font=("Segoe UI", 12),
            text_color="#4ADE80",
        )
        self.lbl_valoare_totala.pack(anchor="w", padx=15, pady=(12, 2))
        self.lbl_discount_aplicat = ctk.CTkLabel(
            self.frame_rezumat_pret,
            text="Valoare Discount (LEI): 0.00 RON",
            font=("Segoe UI", 12),
            text_color="#EAB308",
        )
        self.lbl_discount_aplicat.pack(anchor="w", padx=15, pady=2)
        self.lbl_total_cu_discount = ctk.CTkLabel(
            self.frame_rezumat_pret,
            text="Total Ofertat (LEI): 0.00 RON",
            font=("Segoe UI", 12),
            text_color="#86EFAC",
        )
        self.lbl_total_cu_discount.pack(anchor="w", padx=15, pady=2)
        self.lbl_avans = ctk.CTkLabel(
            self.frame_rezumat_pret,
            text="AVANS (40% din valoarea comenzii): 0.00 RON",
            font=("Segoe UI", 12),
            text_color="#7DD3FC",
        )
        self.lbl_avans.pack(anchor="w", padx=15, pady=(2, 12))

        if not readonly:
            self.switch_catalog_global()
        self.refresh_cos(readonly)

        def _la_inchidere_oferta():
            readonly = getattr(self, "_win_oferta_readonly", True)
            if readonly:
                # În modul vizualizare (ofertă deja realizată), închiderea trebuie să fie directă,
                # fără regulile de validare folosite la creare/editare.
                if getattr(self, "win_oferta", None) and self.win_oferta.winfo_exists():
                    self.win_oferta.destroy()
                return
            # Dacă oferta a fost deja salvată în această sesiune, închidem direct fără dialog
            if getattr(self, "_oferta_salvata_recent", False):
                if getattr(self, "win_oferta", None) and self.win_oferta.winfo_exists():
                    self.win_oferta.destroy()
                return
            # Mod editare: dialog „Vrei să salvezi oferta?”
            dlg = ctk.CTkToplevel(self.win_oferta)
            dlg.title("Închidere ofertă")
            dlg.geometry("400x180")
            dlg.resizable(False, False)
            dlg.transient(self.win_oferta)
            dlg.grab_set()
            ctk.CTkLabel(dlg, text="Vrei să salvezi oferta înainte de a închide?", font=("Segoe UI", 13, "bold"), wraplength=360).pack(pady=(24, 16))
            f_btns = ctk.CTkFrame(dlg, fg_color="transparent")
            f_btns.pack(pady=(0, 20))
            def _salveaza_si_inchide():
                dlg.destroy()
                ok_br, _ = self._validare_broasca_manere()
                if not ok_br:
                    self.show_success_toast(
                        "Atentie! Lipseste Broasca WC/Cilindru pentru manerul selectat! ⚠️",
                        "warning",
                        duration_ms=4000,
                    )
                    return
                ok, mesaj = self._validare_oferta_usi_tocuri()
                if not ok:
                    self.afiseaza_mesaj("Oferta nu poate fi salvată", mesaj + "\n\nOferta rămâne deschisă.", "#7a1a1a")
                    return
                self.salveaza_oferta_finala()
                if getattr(self, "win_oferta", None) and self.win_oferta.winfo_exists():
                    self.win_oferta.destroy()
            def _inchide_fara_salvare():
                dlg.destroy()
                if getattr(self, "win_oferta", None) and self.win_oferta.winfo_exists():
                    self.win_oferta.destroy()
            def _anulare():
                dlg.destroy()
            ctk.CTkButton(f_btns, text="Salvează", width=100, fg_color="#2E7D32", command=_salveaza_si_inchide).pack(side="left", padx=6)
            ctk.CTkButton(f_btns, text="Nu, închide fără salvare", width=180, fg_color="#7a1a1a", command=_inchide_fara_salvare).pack(side="left", padx=6)
            ctk.CTkButton(f_btns, text="Anulare", width=100, fg_color="#3A3A3A", command=_anulare).pack(side="left", padx=6)

        self.win_oferta.protocol("WM_DELETE_WINDOW", _la_inchidere_oferta)
        self._apply_modern_dark_recursive(self.win_oferta)

    CATEGORII_PARCHET = [
        "Parchet Laminat Stoc", "Parchet Laminat Comanda", "Parchet Spc Stoc",
        "Parchet Spc Floorify", "Parchet Triplu Stratificat",
    ]

    def _get_categorii_din_db(self):
        """Încarcă din DB toate categoriile existente (fără parchet – parchet e în meniul de sus).

        Ascunde din meniul de selecție categoriile speciale „Accesorii” (parchet)
        și „Izolatie/Izolatii parchet”, fără a afecta alte categorii (ex. Manere).
        """
        ordine = [
            "Usi Interior", "Usi intrare apartament", "Tocuri", "Manere", "Accesorii",
            "Parchet Laminat Stoc", "Parchet Laminat Comanda", "Parchet Spc Stoc",
            "Parchet Spc Floorify", "Parchet Triplu Stratificat",
        ]
        din_db = get_categorii_distinct(self.cursor)

        # Categorii care NU trebuie afișate în meniul din stânga
        exclude = {"Accesorii", "Izolatie parchet", "Izolatii parchet", "Izolatie", "Izolatii"}

        def _vizibila(cat: str) -> bool:
            c_norm = (cat or "").strip()
            if not c_norm:
                return False
            if c_norm in self.CATEGORII_PARCHET:
                return False
            if c_norm in exclude:
                return False
            return True

        result = [c for c in ordine if c in din_db and _vizibila(c)]
        for c in din_db:
            if c not in result and _vizibila(c):
                result.append(c)

        # Fallback de siguranță
        if not result:
            result = ["Usi Interior", "Tocuri", "Manere"]
        return result

    def switch_catalog_global(self):
        for titlu in self.config_widgets:
            self.populeaza_colectii(titlu)
        self._update_erkado_decor_text_visibility()

    def _refresh_oferta_catalog(self):
        """Reîncarcă catalogul din baza de date și actualizează lista de produse și cosul (fără a închide oferta)."""
        if not getattr(self, "win_oferta", None) or not self.win_oferta.winfo_exists():
            return
        if not getattr(self, "config_widgets", None):
            return
        for titlu in self.config_widgets:
            self.populeaza_colectii(titlu)
        self._update_erkado_decor_text_visibility()
        self.refresh_cos(getattr(self, "_win_oferta_readonly", False))

    def _update_erkado_decor_text_visibility(self):
        """Afișează caseta text de decor doar pentru Usi Interior atunci când furnizorul global este Erkado."""
        furn = self.var_furnizor_global.get() if hasattr(self, "var_furnizor_global") else "Stoc"
        for titlu, cfg in self.config_widgets.items():
            if titlu != "Usi Interior":
                continue
            entry = cfg.get("decor_text")
            if not entry:
                continue
            # Arătăm caseta doar la Erkado; o ascundem pentru Stoc.
            try:
                if furn == "Erkado":
                    if not entry.winfo_ismapped():
                        entry.pack(pady=(0, 4), padx=10)
                else:
                    if entry.winfo_ismapped():
                        entry.pack_forget()
            except Exception:
                continue

    def _parchet_popup_header_strip(self, parent, text: str, *, top_rounded: bool = False) -> ctk.CTkFrame:
        """Bară de titlu ca rândul de tab-uri din ofertă (CTkTabview / segmented), aceeași culoare ca main tab."""
        track_bg = "gray29"
        text_color = "#DCE4EE"
        try:
            tv = getattr(self, "tabview_cos", None)
            if tv is not None and hasattr(tv, "_segmented_button"):
                sb = tv._segmented_button
                track_bg = sb._apply_appearance_mode(sb.cget("fg_color"))
                text_color = sb._apply_appearance_mode(sb.cget("text_color"))
        except Exception:
            pass
        # CTkFrame: un singur corner_radius (fără tuplu per colț în această versiune CTk)
        bar = ctk.CTkFrame(parent, fg_color=track_bg, corner_radius=4 if top_rounded else 0)
        ctk.CTkLabel(
            bar,
            text=text.upper(),
            font=("Segoe UI", 13, "bold"),
            text_color=text_color,
        ).pack(fill="x", padx=14, pady=(11, 11))
        return bar

    def _deschide_popup_parchet(self):
        """Deschide fereastră modală: stânga = selectori, dreapta = calcul și buton Adaugă în ofertă."""
        win = ctk.CTkToplevel(self.win_oferta)
        win.title("Adaugă parchet în ofertă")
        win.geometry("800x680")
        win.minsize(760, 620)
        win.grab_set()
        win.transient(self.win_oferta)
        main = ctk.CTkFrame(win, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        # —— Stânga: opțiuni de selectie (fără scroll, tot conținutul vizibil) ——
        f_left_outer = ctk.CTkFrame(main, width=340, fg_color="#2D2D2D", corner_radius=4)
        f_left_outer.pack(side="left", fill="y", padx=(0, 15))
        f_left_outer.pack_propagate(False)
        self._parchet_popup_header_strip(f_left_outer, "Selectare produs", top_rounded=True).pack(fill="x")
        f_left = ctk.CTkFrame(f_left_outer, fg_color="transparent")
        f_left.pack(fill="both", expand=True)
        ctk.CTkLabel(f_left, text="Categorie parchet:", font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(12, 2))
        cb_cat = ctk.CTkComboBox(
            f_left, width=280, values=self.CATEGORII_PARCHET,
            command=lambda _: self._on_parchet_categorie_select(),
        )
        cb_cat.pack(pady=(0, 10), padx=12)
        cb_cat.set(self.CATEGORII_PARCHET[0] if self.CATEGORII_PARCHET else "")
        ctk.CTkLabel(f_left, text="Colectia:", font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(0, 2))
        cb_col = ctk.CTkComboBox(
            f_left, width=280, values=["Colectia"], state="disabled",
            command=lambda _: self._on_parchet_colectie_select(),
        )
        cb_col.pack(pady=(0, 10), padx=12)
        ctk.CTkLabel(f_left, text="Cod Produs:", font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(0, 2))
        cb_mod = ctk.CTkComboBox(
            f_left, width=280, values=["Cod Produs"], state="disabled",
            command=lambda _: self._on_parchet_model_select(),
        )
        cb_mod.pack(pady=(0, 10), padx=12)
        ctk.CTkLabel(f_left, text="Detalii model ales:", font=("Segoe UI", 10), text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))
        lbl_mp = ctk.CTkLabel(f_left, text="MP/cut: —", font=("Segoe UI", 11), text_color="#aaaaaa")
        lbl_mp.pack(anchor="w", padx=12, pady=2)
        lbl_pret = ctk.CTkLabel(f_left, text="Preț/mp: — €", font=("Segoe UI", 11), text_color="#aaaaaa")
        lbl_pret.pack(anchor="w", padx=12, pady=2)
        ctk.CTkLabel(
            f_left, text="Necesar client (mp):",
            font=("Segoe UI", 11),
            text_color="#2E7D32",
        ).pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            f_left, text="Introduceți metri pătrați pentru calculul cutiilor și al prețului.",
            font=("Segoe UI", 9), text_color="#888888",
        ).pack(anchor="w", padx=12, pady=(0, 2))
        entry_sup = ctk.CTkEntry(f_left, width=140, placeholder_text="ex: 25.5", state="normal")
        entry_sup.pack(anchor="w", padx=12, pady=(0, 12))
        entry_sup.bind("<KeyRelease>", lambda e: self._actualizeaza_rezumat_parchet_popup())
        # Pre-completare din tab-ul Rezumat parchet dacă utilizatorul a introdus deja mp acolo
        if getattr(self, "entry_parchet_mp_tab", None) and self.entry_parchet_mp_tab.winfo_exists():
            val = (self.entry_parchet_mp_tab.get() or "").strip()
            if val:
                entry_sup.delete(0, "end")
                entry_sup.insert(0, val)
                self._actualizeaza_rezumat_parchet_popup()

        ctk.CTkLabel(
            f_left,
            text="Adaugă parchetul (și, dacă este selectată, plinta/izolația) în oferta actuală:",
            font=("Segoe UI", 11),
            text_color="#2E7D32",
        ).pack(anchor="w", padx=12, pady=(20, 6))
        btn_adauga = ctk.CTkButton(
            f_left,
            text="Adaugă parchet în ofertă",
            width=260,
            height=40,
            font=("Segoe UI", 12),
            fg_color="#2E7D32",
            text_color="white",
            state="disabled",
            command=lambda: self._adauga_parchet_din_popup(win),
        )
        btn_adauga.pack(anchor="w", padx=12, pady=(0, 10))

        self.parchet_menu = {
            "categorie": cb_cat,
            "colectie": cb_col,
            "model": cb_mod,
            "categorie_all": list(self.CATEGORII_PARCHET),
            "colectie_all": [],
            "model_all": [],
            "lbl_mp_cut": lbl_mp,
            "pret_display": lbl_pret,
            "entry_suprafata": entry_sup,
            "buton": btn_adauga,
            "pret_val": 0.0,
            "mp_per_cut": 0.0,
            # Plintă (opțional)
            "plinta_rows": [],
            "plinta_combo": None,
            "plinta_qty": None,
            "plinta_pret_buc": 0.0,
            "plinta_lbl_total": None,
        }
        def _bind_parchet_focusout_reset(box, field):
            h = lambda e, f=field: self._reset_parchet_combobox_on_focus_out(f)
            try:
                t = getattr(box, "entry", None) or getattr(box, "_entry", None)
                if t is not None:
                    t.bind("<FocusOut>", h)
                box.bind("<FocusOut>", h)
            except Exception:
                box.bind("<FocusOut>", h)
        _bind_parchet_focusout_reset(cb_cat, "categorie")
        _bind_parchet_focusout_reset(cb_col, "colectie")
        _bind_parchet_focusout_reset(cb_mod, "model")
        self._popup_parchet_win = win
        self._popup_parchet_rezumat = {}

        # —— Dreapta: calcul și afișare (derulabil ca să fie mereu vizibil butonul) ——
        f_right_outer = ctk.CTkFrame(main, fg_color="#363636", corner_radius=4)
        f_right_outer.pack(side="right", fill="both", expand=True, padx=(0, 0))
        self._parchet_popup_header_strip(f_right_outer, "Rezumat calcul", top_rounded=True).pack(fill="x", side="top")
        f_right = ctk.CTkScrollableFrame(f_right_outer, fg_color="#363636")
        f_right.pack(fill="both", expand=True)
        _patch_scrollable_frame_canvas(f_right, "#363636")
        pad_y = 6
        ctk.CTkLabel(f_right, text="Necesar client (mp):", font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=(12, pad_y))
        lbl_necesar = ctk.CTkLabel(f_right, text="—", font=("Segoe UI", 13, "bold"))
        lbl_necesar.pack(anchor="w", padx=15, pady=(0, pad_y))
        self._popup_parchet_rezumat["lbl_necesar"] = lbl_necesar
        ctk.CTkLabel(f_right, text="Suprafață totală (mp) = cutii × mp/cutie:", font=("Segoe UI", 11), text_color="#2E7D32").pack(anchor="w", padx=15, pady=pad_y)
        lbl_sup = ctk.CTkLabel(f_right, text="—", font=("Segoe UI", 13, "bold"))
        lbl_sup.pack(anchor="w", padx=15, pady=(0, pad_y))
        self._popup_parchet_rezumat["lbl_suprafata"] = lbl_sup
        ctk.CTkLabel(f_right, text="Număr cutii:", font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=pad_y)
        lbl_cutii = ctk.CTkLabel(f_right, text="—", font=("Segoe UI", 13, "bold"))
        lbl_cutii.pack(anchor="w", padx=15, pady=(0, pad_y))
        self._popup_parchet_rezumat["lbl_cutii"] = lbl_cutii
        ctk.CTkLabel(f_right, text="Preț/mp (EUR):", font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=pad_y)
        lbl_pmp = ctk.CTkLabel(f_right, text="—", font=("Segoe UI", 13, "bold"))
        lbl_pmp.pack(anchor="w", padx=15, pady=(0, pad_y))
        self._popup_parchet_rezumat["lbl_pret_mp"] = lbl_pmp
        ctk.CTkLabel(f_right, text="Total (EUR fără TVA):", font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=pad_y)
        lbl_eur = ctk.CTkLabel(f_right, text="—", font=("Segoe UI", 13, "bold"))
        lbl_eur.pack(anchor="w", padx=15, pady=(0, pad_y))
        self._popup_parchet_rezumat["lbl_total_eur"] = lbl_eur
        ctk.CTkLabel(f_right, text="Total (LEI cu TVA):", font=("Segoe UI", 11)).pack(anchor="w", padx=15, pady=pad_y)
        lbl_lei = ctk.CTkLabel(f_right, text="—", font=("Segoe UI", 13, "bold"), text_color="#2E7D32")
        lbl_lei.pack(anchor="w", padx=15, pady=(0, pad_y))
        self._popup_parchet_rezumat["lbl_total_lei"] = lbl_lei

        # —— Linie manuală pentru accesorii parchet (plintă / izolație) ——
        ctk.CTkLabel(
            f_right,
            text="Accesorii parchet (manual): denumire, cantitate, unitate și preț.",
            font=("Segoe UI", 11),
            text_color="#2E7D32",
        ).pack(anchor="w", padx=15, pady=(18, 4))

        f_extra = ctk.CTkFrame(f_right, fg_color="#2D2D2D", corner_radius=4)
        f_extra.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(f_extra, text="Denumire:", font=("Segoe UI", 11)).grid(row=0, column=0, padx=10, pady=6, sticky="e")
        entry_extra_nume = ctk.CTkEntry(f_extra, width=260, placeholder_text="ex: Plintă MDF Sekura")
        entry_extra_nume.grid(row=0, column=1, padx=10, pady=6, sticky="w")

        ctk.CTkLabel(f_extra, text="Cantitate (buc):", font=("Segoe UI", 11)).grid(row=1, column=0, padx=10, pady=6, sticky="e")
        entry_extra_qty = ctk.CTkEntry(f_extra, width=80, placeholder_text="ex: 8")
        entry_extra_qty.grid(row=1, column=1, padx=(10, 2), pady=6, sticky="w")

        ctk.CTkLabel(f_extra, text="Preț/unitate (€):", font=("Segoe UI", 11)).grid(row=2, column=0, padx=10, pady=6, sticky="e")
        entry_extra_pret = ctk.CTkEntry(f_extra, width=100, placeholder_text="ex: 5.50")
        entry_extra_pret.grid(row=2, column=1, padx=10, pady=6, sticky="w")

        lbl_extra_total = ctk.CTkLabel(f_extra, text="Total accesoriu (EUR fără TVA): —", font=("Segoe UI", 11), text_color="#aaaaaa")
        lbl_extra_total.grid(row=3, column=0, columnspan=4, padx=10, pady=(4, 2), sticky="w")

        def _recalc_extra_total(_event=None):
            try:
                qty_str = (entry_extra_qty.get() or "").strip().replace(",", ".")
                qty = float(qty_str) if qty_str else 0.0
            except ValueError:
                qty = 0.0
            try:
                pret_str = (entry_extra_pret.get() or "").strip().replace(",", ".")
                pret_unit = float(pret_str) if pret_str else 0.0
            except ValueError:
                pret_unit = 0.0
            total = max(0.0, qty) * max(0.0, pret_unit)
            if total > 0:
                lbl_extra_total.configure(text=f"Total accesoriu (EUR fără TVA): {total:.2f} €")
            else:
                lbl_extra_total.configure(text="Total accesoriu (EUR fără TVA): —")

        entry_extra_qty.bind("<KeyRelease>", _recalc_extra_total)
        entry_extra_pret.bind("<KeyRelease>", _recalc_extra_total)

        def _adauga_accesoriu_in_cos():
            nume_extra = (entry_extra_nume.get() or "").strip()
            try:
                qty_str = (entry_extra_qty.get() or "").strip().replace(",", ".")
                qty_extra = float(qty_str) if qty_str else 0.0
            except ValueError:
                qty_extra = 0.0
            try:
                pret_str = (entry_extra_pret.get() or "").strip().replace(",", ".")
                pret_extra = float(pret_str) if pret_str else 0.0
            except ValueError:
                pret_extra = 0.0
            if not nume_extra or qty_extra <= 0 or pret_extra <= 0:
                self.afiseaza_mesaj("Atenție", "Completează denumirea, cantitatea și prețul pentru accesoriu.", "#7a1a1a")
                return
            # Cantitatea este numărul de bucăți (sau mp/role) – apare în coloana „Buc” din PDF.
            # În denumire NU mai includem unitatea, doar numele produsului.
            if abs(qty_extra - round(qty_extra)) < 1e-6:
                qty_val = int(round(qty_extra))
            else:
                qty_val = qty_extra
            total_extra = qty_extra * pret_extra
            self.cos_cumparaturi.append({
                "nume": nume_extra,
                "pret_eur": round(pret_extra, 2),
                "qty": qty_val,
                "tip": "parchet_accesoriu",
            })
            # Curăță câmpurile pentru a putea adăuga un nou accesoriu
            entry_extra_nume.delete(0, "end")
            entry_extra_qty.delete(0, "end")
            entry_extra_pret.delete(0, "end")
            combo_extra_unit.set("MP")
            lbl_extra_total.configure(text="Total accesoriu (EUR fără TVA): —")
            # Actualizează afișarea coșului dacă există metoda
            if hasattr(self, "refresh_cos"):
                try:
                    self.refresh_cos()
                except Exception:
                    pass

        btn_extra_add = ctk.CTkButton(
            f_extra,
            text="Adaugă accesoriu în ofertă",
            width=220,
            fg_color="#2E7D32",
            command=_adauga_accesoriu_in_cos,
        )
        btn_extra_add.grid(row=4, column=0, columnspan=4, padx=10, pady=(4, 8), sticky="w")

        self.parchet_menu["extra_nume"] = entry_extra_nume
        self.parchet_menu["extra_qty"] = entry_extra_qty
        self.parchet_menu["extra_unit"] = combo_extra_unit
        self.parchet_menu["extra_pret"] = entry_extra_pret
        self.parchet_menu["extra_total_lbl"] = lbl_extra_total

        ctk.CTkButton(f_right, text="Închide", width=120, fg_color="#3A3A3A", command=win.destroy).pack(pady=(16, 15))

        def la_inchidere():
            self._popup_parchet_rezumat = {}
            self._popup_parchet_win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", la_inchidere)
        self._populeaza_parchet_colectii()
        self._actualizeaza_rezumat_parchet_popup()

    def _actualizeaza_rezumat_parchet_popup(self):
        """Actualizează panoul dreapta din popup (calcul cutii, totaluri) și activează/dezactivează butonul Adaugă."""
        if not getattr(self, "_popup_parchet_rezumat", None):
            return
        w = getattr(self, "parchet_menu", None)
        if not w:
            return
        r = self._popup_parchet_rezumat
        suprafata_str = (w["entry_suprafata"].get() or "").strip().replace(",", ".")
        try:
            suprafata = float(suprafata_str)
        except (ValueError, TypeError):
            suprafata = 0.0
        mp_per_cut = w.get("mp_per_cut") or 0
        pret_per_mp = w.get("pret_val") or 0
        valid = suprafata > 0 and mp_per_cut > 0
        if valid:
            nr_cutii = math.ceil(suprafata / mp_per_cut)
            total_mp = nr_cutii * mp_per_cut
            total_eur = total_mp * pret_per_mp
            disc = self._get_discount_proc()
            total_lei = (
                total_eur * discount_price_factor(disc) * (1 + self.tva_procent / 100)
            ) * self.curs_euro
            if r.get("lbl_necesar"):
                r["lbl_necesar"].configure(text=f"{suprafata:.2f}")
            r["lbl_suprafata"].configure(text=f"{total_mp:.2f}")
            r["lbl_cutii"].configure(text=str(nr_cutii))
            r["lbl_pret_mp"].configure(text=f"{pret_per_mp:.2f} €")
            r["lbl_total_eur"].configure(text=f"{total_eur:.2f} €")
            r["lbl_total_lei"].configure(text=f"{total_lei:.2f} LEI")
        else:
            if r.get("lbl_necesar"):
                r["lbl_necesar"].configure(text="—")
            r["lbl_suprafata"].configure(text="—")
            r["lbl_cutii"].configure(text="—")
            r["lbl_pret_mp"].configure(text="—")
            r["lbl_total_eur"].configure(text="—")
            r["lbl_total_lei"].configure(text="—")
        if w.get("buton"):
            w["buton"].configure(state="normal" if valid else "disabled")

        # Accesoriu parchet manual – doar pentru afișare total în secțiunea dedicată
        extra_qty = w.get("extra_qty")
        extra_pret = w.get("extra_pret")
        extra_lbl = w.get("extra_total_lbl")
        if extra_qty and extra_pret and extra_lbl:
            try:
                q_str = (extra_qty.get() or "").strip().replace(",", ".")
                q_val = float(q_str) if q_str else 0.0
            except ValueError:
                q_val = 0.0
            try:
                p_str = (extra_pret.get() or "").strip().replace(",", ".")
                p_val = float(p_str) if p_str else 0.0
            except ValueError:
                p_val = 0.0
            total_extra = max(0.0, q_val) * max(0.0, p_val)
            if total_extra > 0:
                extra_lbl.configure(text=f"Total accesoriu (EUR fără TVA): {total_extra:.2f} €")
            else:
                extra_lbl.configure(text="Total accesoriu (EUR fără TVA): —")

    def _adauga_parchet_din_popup(self, win):
        """Adaugă linia de parchet în ofertă și actualizează cosul; închide popup-ul."""
        self._adauga_parchet_din_meniu()
        if getattr(self, "_popup_parchet_win", None) and win.winfo_exists():
            win.destroy()
        self._popup_parchet_rezumat = {}
        self._popup_parchet_win = None

    def _build_meniu_parchet(self, parent, readonly):
        """Compatibilitate: nu mai e folosit (parchet e în popup)."""
        pass

    def _populeaza_parchet_colectii(self):
        if not hasattr(self, "parchet_menu"):
            return
        w = self.parchet_menu
        cat = w["categorie"].get()
        cols = get_colectii_parchet(self.cursor, cat)
        w["colectie_all"] = list(cols) if cols else []
        w["colectie"].configure(values=cols if cols else ["—"], state="normal")
        w["colectie"].set(cols[0] if cols else "—")
        w["model_all"] = []
        w["model"].set("Cod Produs")
        w["model"].configure(state="disabled")
        w["lbl_mp_cut"].configure(text="MP/cut: —")
        w["pret_display"].configure(text="Preț/mp: —")
        w["entry_suprafata"].configure(state="disabled")
        w["buton"].configure(state="disabled")
        w["pret_val"] = 0.0
        w["mp_per_cut"] = 0.0
        self._on_parchet_colectie_select(None)

    def _on_parchet_categorie_select(self, _=None):
        self._populeaza_parchet_colectii()

    def _on_parchet_colectie_select(self, _=None):
        if not hasattr(self, "parchet_menu"):
            return
        w = self.parchet_menu
        cat = w["categorie"].get()
        col = w["colectie"].get()
        if not col or col == "—":
            return
        modele = get_modele_parchet(self.cursor, cat, col)
        w["model_all"] = list(modele) if modele else []
        w["model"].configure(values=modele if modele else ["—"], state="normal")
        w["model"].set(modele[0] if modele else "—")
        w["lbl_mp_cut"].configure(text="MP/cut: —")
        w["pret_display"].configure(text="Preț/mp: —")
        w["entry_suprafata"].configure(state="disabled")
        w["buton"].configure(state="disabled")
        w["pret_val"] = 0.0
        w["mp_per_cut"] = 0.0
        if modele:
            self._on_parchet_model_select(None)

    def _on_parchet_model_select(self, _=None):
        if not hasattr(self, "parchet_menu"):
            return
        w = self.parchet_menu
        cat = w["categorie"].get()
        col = w["colectie"].get()
        mod = (w["model"].get() or "").strip()
        if not mod or mod == "—":
            return
        mod_int = None
        mod_float = None
        try:
            mod_int = str(int(float(mod)))
        except (ValueError, TypeError):
            pass
        if mod_int == mod:
            mod_int = None
        try:
            mod_float = str(float(mod)) if "." not in mod else mod
        except (ValueError, TypeError):
            pass
        if mod_float == mod:
            mod_float = None
        res = get_parchet_dimensiune_pret(self.cursor, cat, "Stoc", col, mod, mod_int)
        if not res and mod_float:
            res = get_parchet_dimensiune_pret(self.cursor, cat, "Stoc", col, mod, mod_float)
        if res:
            try:
                mp_per_cut = float((res[0] or "0").strip().replace(",", "."))
            except (ValueError, TypeError):
                mp_per_cut = 0.0
            if mp_per_cut > 100:
                mp_per_cut = 0.0
            pret_per_mp = float(res[1]) if res[1] is not None else 0.0
            w["mp_per_cut"] = mp_per_cut
            w["pret_val"] = pret_per_mp
            w["lbl_mp_cut"].configure(text=f"MP/cut: {mp_per_cut}" if mp_per_cut else "MP/cut: —")
            w["pret_display"].configure(text=f"Preț/mp: {pret_per_mp} €" if pret_per_mp else "Preț/mp: —")
            w["entry_suprafata"].configure(state="normal")
            if w.get("buton"):
                w["buton"].configure(state="disabled")
            self._actualizeaza_rezumat_parchet_popup()

    def _adauga_parchet_din_meniu(self):
        if not hasattr(self, "parchet_menu"):
            return
        w = self.parchet_menu
        titlu = w["categorie"].get()
        suprafata_str = (w["entry_suprafata"].get() or "").strip().replace(",", ".")
        try:
            suprafata = float(suprafata_str)
        except (ValueError, TypeError):
            self.afiseaza_mesaj("Atenție", "Introdu suprafața în mp (ex: 25.5).", "#7a1a1a")
            return
        if suprafata <= 0:
            self.afiseaza_mesaj("Atenție", "Suprafața trebuie > 0.", "#7a1a1a")
            return
        mp_per_cut = w.get("mp_per_cut") or 0
        if mp_per_cut <= 0:
            self.afiseaza_mesaj("Atenție", "Selectează un produs cu MP/cut valid.", "#7a1a1a")
            return
        pret_per_mp = w.get("pret_val") or 0
        nr_cutii = math.ceil(suprafata / mp_per_cut)
        total_mp = nr_cutii * mp_per_cut
        pret_total_eur = total_mp * pret_per_mp
        col = w["colectie"].get()
        cod = w["model"].get()
        nume = f"{titlu} - Colectia {col} - Cod Produs {cod}"
        self.cos_cumparaturi.append({
            "nume": nume,
            "pret_eur": round(pret_total_eur, 2),
            "qty": 1,
            "tip": "parchet",
            "suprafata_mp": round(total_mp, 2),
            "nr_cutii": nr_cutii,
            "pret_per_mp": round(pret_per_mp, 2),
        })

        # Adaugă, dacă este selectată, și plinta ca produs separat
        cb_plinta = w.get("plinta_combo")
        entry_plinta_buc = w.get("plinta_qty")
        rows_plinta = w.get("plinta_rows") or []
        if cb_plinta and entry_plinta_buc and rows_plinta:
            sel = cb_plinta.get().strip()
            try:
                valori = list(cb_plinta.cget("values"))
            except Exception:
                valori = []
            idx = valori.index(sel) if sel in valori else -1
            if 0 <= idx < len(rows_plinta):
                denumire_p, culoare_p, model_p, dim_p, pret_buc = rows_plinta[idx]
                try:
                    qty_str = (entry_plinta_buc.get() or "").strip().replace(",", ".")
                    qty = float(qty_str) if qty_str else 0.0
                except ValueError:
                    qty = 0.0
                try:
                    pret_buc_val = float(pret_buc) if pret_buc is not None else 0.0
                except (ValueError, TypeError):
                    pret_buc_val = 0.0
                if qty > 0 and pret_buc_val > 0:
                    bucati_int = int(math.ceil(qty))
                    total_pl_eur = bucati_int * pret_buc_val
                    nume_pl = f"Plintă {denumire_p or model_p}"
                    if culoare_p:
                        nume_pl += f" – {culoare_p}"
                    if dim_p:
                        nume_pl += f" ({dim_p})"
                    nume_pl += f" – {bucati_int} buc × {pret_buc_val:.2f} €/buc"
                    # În coș păstrăm același tipar ca la parchet: qty=1, pret_eur = total linie.
                    self.cos_cumparaturi.append({
                        "nume": nume_pl,
                        "pret_eur": round(total_pl_eur, 2),
                        "qty": 1,
                        "tip": "plinta",
                    })

        # Izolație (opțional): la mp = total_mp * pret; la rolă = nr_role * pret
        cb_izolatie = w.get("izolatie_combo")
        rows_izolatie = w.get("izolatiile_rows") or []
        if cb_izolatie and rows_izolatie and total_mp > 0:
            sel = (cb_izolatie.get() or "").strip()
            try:
                valori = list(cb_izolatie.cget("values"))
            except Exception:
                valori = []
            idx = valori.index(sel) if sel and sel in valori else -1
            # Dacă selecția e goală dar avem izolații, folosim prima (combo poate nu fi sincronizat)
            if idx < 0 and rows_izolatie and valori and valori[0] != "Nu există izolații în catalog":
                idx = 0
            if 0 <= idx < len(rows_izolatie):
                r = rows_izolatie[idx]
                denumire_i = r[0] or ""
                culoare_i = r[1] or ""
                grosime_i = r[2] or ""
                dim_i = r[3] if len(r) > 3 else ""
                pret_val = 0.0
                try:
                    pret_val = float(r[4]) if r[4] is not None else 0.0
                except (ValueError, TypeError):
                    pass
                cant = (r[5] or "mp").strip().lower() if len(r) > 5 else "mp"
                if pret_val > 0:
                    if cant == "mp" or not cant:
                        total_iz_eur = total_mp * pret_val
                        nume_iz = f"Izolație {denumire_i or 'parchet'}"
                        if grosime_i:
                            nume_iz += f" – {grosime_i}"
                        if culoare_i:
                            nume_iz += f" – {culoare_i}"
                        nume_iz += f" – {total_mp:.2f} m² × {pret_val:.2f} €/m²"
                    else:
                        try:
                            mp_per_rola = float(str(cant).replace(",", "."))
                            if mp_per_rola > 0:
                                nr_role = int(math.ceil(total_mp / mp_per_rola))
                                total_iz_eur = nr_role * pret_val
                                nume_iz = f"Izolație {denumire_i or 'parchet'}"
                                if grosime_i:
                                    nume_iz += f" – {grosime_i}"
                                if culoare_i:
                                    nume_iz += f" – {culoare_i}"
                                nume_iz += f" – {nr_role} rolă × {pret_val:.2f} €/rolă (preț per rolă, {mp_per_rola:.0f} mp/rolă)"
                            else:
                                total_iz_eur = total_mp * pret_val
                                nume_iz = f"Izolație {denumire_i or 'parchet'}" + f" – {total_mp:.2f} m² × {pret_val:.2f} €/m²"
                        except (ValueError, TypeError):
                            total_iz_eur = total_mp * pret_val
                            nume_iz = f"Izolație {denumire_i or 'parchet'}" + f" – {total_mp:.2f} m² × {pret_val:.2f} €/m²"
                    self.cos_cumparaturi.append({
                        "nume": nume_iz,
                        "pret_eur": round(total_iz_eur, 2),
                        "qty": 1,
                        "tip": "izolatie",
                    })

        w["entry_suprafata"].delete(0, "end")
        if entry_plinta_buc:
            entry_plinta_buc.delete(0, "end")
        self.refresh_cos()

    def creeaza_grup_configurare(self, parent, titlu, readonly):
        f_grup = ctk.CTkFrame(parent, fg_color="#2D2D2D")
        self._style_oferta_section_frame(f_grup)
        f_grup.pack(fill="x", pady=5, padx=10)

        # Header clicabil (expand/collapse)
        f_header = ctk.CTkFrame(f_grup, fg_color="transparent")
        f_header.pack(fill="x", padx=10, pady=5)
        lbl_titlu = ctk.CTkLabel(
            f_header,
            text=f"▾ {titlu}",
            font=("Segoe UI", 13, "bold"),
            text_color="#78909C",
        )
        lbl_titlu.pack(side="left")
        is_parchet = titlu in self.CATEGORII_PARCHET
        hint_text = (
            "1. Colectia  2. Cod Produs  3. MP/cut + Pret/mp  4. Suprafață (mp) → Calculează și adaugă"
            if is_parchet
            else "1. Alege furnizorul (STOC / ERKADO)   2. Colecție + Model   3. Decor + ADĂUGĂ"
        )
        lbl_hint = ctk.CTkLabel(f_header, text=hint_text, font=("Segoe UI", 9), text_color="#888888")
        lbl_hint.pack(side="left", padx=10)

        # Container pentru conținutul secțiunii (va fi ascuns/afișat)
        f_content = ctk.CTkFrame(f_grup, fg_color="transparent")
        f_content.pack(fill="x", padx=0, pady=(0, 5))

        # Switch furnizor manere: doar pentru categoria Manere (Stoc / Enger / Erkado)
        var_furnizor_manere = None
        if titlu == "Manere":
            f_manere = ctk.CTkFrame(f_content, fg_color="transparent")
            f_manere.pack(fill="x", padx=10, pady=(2, 5))
            ctk.CTkLabel(f_manere, text="Manere:", font=("Segoe UI", 11), text_color="#2E7D32").pack(side="left", padx=(0, 8))
            var_furnizor_manere = ctk.StringVar(value="Stoc")

            def _on_manere_furnizor_change():
                self.populeaza_colectii("Manere")

            for lbl, val in [("Stoc", "Stoc"), ("Enger", "Enger"), ("Erkado", "Erkado")]:
                rb = ctk.CTkRadioButton(
                    f_manere, text=lbl, variable=var_furnizor_manere, value=val,
                    command=_on_manere_furnizor_change, font=("Segoe UI", 10),
                )
                rb.pack(side="left", padx=6)
                self._style_corporate_radio(rb)

        cb_col = ctk.CTkComboBox(
            f_content, width=380,
            values=["Alege Colectia"] if is_parchet else ["Alege Colecție"],
            command=lambda x, t=titlu: self.on_colectie_select(t),
        )
        self._style_modern_combobox(cb_col)
        cb_col.pack(pady=3, padx=10)
        cb_mod = ctk.CTkComboBox(
            f_content, width=380,
            values=["Alege Cod Produs"] if is_parchet else ["Alege Model"],
            state="disabled", command=lambda x, t=titlu: self.on_model_select(t),
        )
        self._style_modern_combobox(cb_mod)
        cb_mod.pack(pady=3, padx=10)

        if is_parchet:
            f_readonly = ctk.CTkFrame(f_content, fg_color="transparent")
            f_readonly.pack(fill="x", padx=10, pady=2)
            lbl_mp_cut = ctk.CTkLabel(f_readonly, text="MP/cut: —", font=("Segoe UI", 11), text_color="#aaaaaa")
            lbl_mp_cut.pack(anchor="w")
            lbl_pret_mp = ctk.CTkLabel(
                f_readonly, text="Pret lista eur fara TVA/mp: —", font=("Segoe UI", 11), text_color="#aaaaaa"
            )
            lbl_pret_mp.pack(anchor="w")
            ctk.CTkLabel(f_content, text="Suprafață (mp):", font=("Segoe UI", 11)).pack(anchor="w", padx=10, pady=(5, 0))
            entry_suprafata = ctk.CTkEntry(f_content, width=120, placeholder_text="ex: 25.5", state="disabled")
            self._style_modern_entry(entry_suprafata)
            entry_suprafata.pack(pady=3, padx=10, anchor="w")
            f_bottom = ctk.CTkFrame(f_content, fg_color="transparent")
            f_bottom.pack(fill="x", padx=10, pady=5)
            btn_add = ctk.CTkButton(
                f_bottom, text="Calculează și adaugă", width=180, fg_color="#2E7D32", state="disabled",
                command=lambda t=titlu: self.adauga_parchet_in_cos(t),
            )
            self._style_add_button(btn_add)
            btn_add.pack(side="left", padx=5)
            self.config_widgets[titlu] = {
                "colectie": cb_col,
                "model": cb_mod,
                "decor": None,
                "buton": btn_add,
                "pret_display": lbl_pret_mp,
                "pret_val": 0.0,
                "lbl_mp_cut": lbl_mp_cut,
                "entry_suprafata": entry_suprafata,
                "mp_per_cut": 0.0,
                "colectie_all": [],
                "model_all": [],
            }
        else:
            ph_decor_initial = "Alege Finisaj" if titlu == "Tocuri" else "Alege Decor"
            cb_dec = ctk.CTkComboBox(
                f_content, width=380, values=[ph_decor_initial], state="disabled",
                command=lambda x, t=titlu: self.on_decor_select(t),
            )
            self._style_modern_combobox(cb_dec)
            cb_dec.pack(pady=3, padx=10)

            # Câmp text pentru decor liber: îl creăm doar pentru Usi Interior,
            # dar îl vom AFIȘA doar când furnizorul selectat este Erkado.
            entry_decor_txt = None
            if titlu == "Usi Interior":
                entry_decor_txt = ctk.CTkEntry(
                    f_content,
                    width=380,
                    placeholder_text="Decor ERKADO (scrie cu MAJUSCULE, ex: CPL ALB)",
                )
                self._style_modern_entry(entry_decor_txt)
                # Inițial ascuns (furnizor implicit este Stoc)
                entry_decor_txt.pack_forget()
                entry_decor_txt.bind(
                    "<KeyRelease>",
                    lambda e, t=titlu: self._on_decor_text_change(t),
                )
            f_bottom = ctk.CTkFrame(f_content, fg_color="transparent")
            f_bottom.pack(fill="x", padx=10, pady=5)
            lbl_pret = ctk.CTkLabel(f_bottom, text="Preț: 0 €", font=("Segoe UI", 12, "italic"))
            lbl_pret.pack(side="left", padx=5)
            btn_add = ctk.CTkButton(f_bottom, text="ADĂUGĂ", width=120, fg_color="#2E7D32", state="disabled")
            self._style_add_button(btn_add)
            btn_add.pack(side="right", padx=5)
            self.config_widgets[titlu] = {
                "colectie": cb_col,
                "model": cb_mod,
                "decor": cb_dec,
                "decor_text": entry_decor_txt,
                "buton": btn_add,
                "pret_display": lbl_pret,
                "pret_val": 0,
                "colectie_all": [],
                "model_all": [],
                "decor_all": [],
                "_ph_colectie": "Alege Colecție",
                "_ph_model": "Alege Model",
                "_ph_decor": ph_decor_initial,
                "_frame_container": f_content,
                "_header_label": lbl_titlu,
            }
            if titlu == "Manere" and var_furnizor_manere is not None:
                self.config_widgets[titlu]["furnizor_manere"] = var_furnizor_manere
                self.config_widgets[titlu]["engs_pret_total_lei"] = None

        # Funcție de toggle pentru expand/collapse
        def _toggle():
            if f_content.winfo_ismapped():
                f_content.pack_forget()
                lbl_titlu.configure(text=f"▸ {titlu}")
            else:
                f_content.pack(fill="x", padx=0, pady=(0, 5))
                lbl_titlu.configure(text=f"▾ {titlu}")

        f_header.bind("<Button-1>", lambda e: _toggle())
        lbl_titlu.bind("<Button-1>", lambda e: _toggle())
        lbl_hint.bind("<Button-1>", lambda e: _toggle())

        # Reset la click în afara casetei (fără search live)
        def _bind_focusout_reset(box, field):
            h = lambda e, t=titlu, f=field: self._reset_combobox_on_focus_out(t, f)
            try:
                target = getattr(box, "entry", None) or getattr(box, "_entry", None)
                if target is not None:
                    target.bind("<FocusOut>", h)
                box.bind("<FocusOut>", h)
            except Exception:
                box.bind("<FocusOut>", h)

        _bind_focusout_reset(cb_col, "colectie")
        _bind_focusout_reset(cb_mod, "model")
        if not is_parchet:
            _bind_focusout_reset(cb_dec, "decor")

    def populeaza_colectii(self, titlu):
        furnizor = self.var_furnizor_global.get()
        w = self.config_widgets[titlu]
        is_parchet = titlu in self.CATEGORII_PARCHET
        if is_parchet:
            furnizor = "Stoc"
        # Manere: furnizorul vine din switch-ul Stoc / Enger / Erkado
        if titlu == "Manere":
            var_manere = w.get("furnizor_manere")
            furnizor = var_manere.get() if var_manere else "Stoc"
            if furnizor == "Enger":
                self._manere_engs_reset_and_populate()
                return
        use_tip_toc = titlu == "Tocuri"
        cols = get_colectii_produse(self.cursor, titlu, furnizor, use_tip_toc=use_tip_toc)
        if cols:
            valori = cols
        else:
            valori = ["Nu există produse"] if is_parchet else ["Nu există produse pentru acest furnizor"]
        # Salvăm lista completă și placeholder pentru filtrare și reset
        ph_col = "Alege Colectia" if is_parchet else ("Alege Tip toc" if titlu == "Tocuri" else "Alege Colecție")
        w["_ph_colectie"] = ph_col
        w["colectie_all"] = list(valori)
        w["colectie"].configure(values=valori)
        w["colectie"].set(ph_col)
        w["model"].set("Alege Cod Produs" if is_parchet else "Alege Model")
        w["model"].configure(state="disabled")
        if w.get("decor"):
            ph_decor = w.get("_ph_decor") or "Alege Decor"
            w["decor"].set(ph_decor)
            w["decor"].configure(state="disabled")
        w["buton"].configure(state="disabled")
        w["pret_display"].configure(text="Pret lista eur fara TVA/mp: —" if is_parchet else "Preț: 0 €")
        if is_parchet:
            w["pret_val"] = 0.0
            w["mp_per_cut"] = 0.0
            w["lbl_mp_cut"].configure(text="MP/cut: —")
            w["entry_suprafata"].delete(0, "end")
            w["entry_suprafata"].configure(state="disabled")

    def _manere_engs_reset_and_populate(self):
        """Enger: aceleași 3 combobox-uri ca la Stoc (orizontal); conținut = model / finisaj / închidere."""
        w = self.config_widgets.get("Manere")
        if not w:
            return
        modele = get_manere_engs_modele(self.cursor)
        ph_c = "Alege model"
        ph_f = "Alege finisaj"
        ph_d = "Alege închidere"
        w["_ph_colectie"] = ph_c
        w["_ph_model"] = ph_f
        w["_ph_decor"] = ph_d
        vals_c = [ph_c] + modele if modele else [ph_c]
        w["colectie_all"] = list(vals_c)
        w["colectie"].configure(values=vals_c)
        w["colectie"].set(ph_c)
        w["model_all"] = [ph_f]
        w["model"].configure(state="disabled", values=[ph_f])
        w["model"].set(ph_f)
        w["decor_all"] = [ph_d]
        w["decor"].configure(state="disabled", values=[ph_d])
        w["decor"].set(ph_d)
        w["engs_pret_total_lei"] = None
        w["pret_display"].configure(text="Total: — LEI (TVA inclus)")
        w["buton"].configure(state="disabled")

    def _manere_engs_on_colectie_select(self):
        """Enger: coloana 1 = model (colectie în DB)."""
        w = self.config_widgets["Manere"]
        ph_c = w.get("_ph_colectie") or "Alege model"
        ph_f = w.get("_ph_model") or "Alege finisaj"
        ph_d = w.get("_ph_decor") or "Alege închidere"
        col = (w["colectie"].get() or "").strip()
        if not col or col == ph_c:
            w["model_all"] = [ph_f]
            w["model"].configure(values=[ph_f], state="disabled")
            w["model"].set(ph_f)
            w["decor_all"] = [ph_d]
            w["decor"].configure(values=[ph_d], state="disabled")
            w["decor"].set(ph_d)
            self._manere_engs_refresh_total_from_w()
            return
        fins = get_manere_engs_finisaje(self.cursor, col)
        vals_f = [ph_f] + fins if fins else [ph_f]
        w["model_all"] = list(vals_f)
        w["model"].configure(state="normal", values=vals_f)
        w["model"].set(ph_f)
        w["decor_all"] = [ph_d]
        w["decor"].configure(values=[ph_d], state="disabled")
        w["decor"].set(ph_d)
        self._manere_engs_refresh_total_from_w()

    def _manere_engs_on_model_select(self):
        """Enger: coloana 2 = finisaj; coloana 3 = OB / PZ / WC."""
        w = self.config_widgets["Manere"]
        ph_f = w.get("_ph_model") or "Alege finisaj"
        ph_d = w.get("_ph_decor") or "Alege închidere"
        mod = (w["model"].get() or "").strip()
        inc_values = ["OB", "PZ", "WC"]
        if not mod or mod == ph_f:
            w["decor_all"] = [ph_d]
            w["decor"].configure(values=[ph_d], state="disabled")
            w["decor"].set(ph_d)
            self._manere_engs_refresh_total_from_w()
            return
        w["decor_all"] = list(inc_values)
        w["decor"].configure(state="normal", values=inc_values)
        w["decor"].set("OB")
        self._manere_engs_refresh_total_from_w()

    def _manere_engs_refresh_total_from_w(self):
        w = self.config_widgets.get("Manere")
        if not w:
            return
        var = w.get("furnizor_manere")
        if not var or var.get() != "Enger":
            return
        ph_c = w.get("_ph_colectie") or "Alege model"
        ph_f = w.get("_ph_model") or "Alege finisaj"
        ph_d = w.get("_ph_decor") or "Alege închidere"
        model = (w["colectie"].get() or "").strip()
        fin = (w["model"].get() or "").strip()
        inc = (w["decor"].get() or "").strip()
        w["engs_pret_total_lei"] = None
        w["pret_val"] = 0.0
        if inc == ph_d or inc not in ("OB", "PZ", "WC"):
            w["pret_display"].configure(text="Total: — LEI (TVA inclus)")
            w["buton"].configure(state="disabled")
            return
        if not model or model == ph_c or not fin or fin == ph_f:
            w["pret_display"].configure(text="Total: — LEI (TVA inclus)")
            w["buton"].configure(state="disabled")
            return
        pm = get_manere_engs_pret_lei(self.cursor, model, fin, MANER_ENGER_DECOR_MANER)
        pa = get_manere_engs_pret_lei(self.cursor, model, fin, inc)
        if pm is None or pa is None:
            w["pret_display"].configure(text="Total: — (lipsesc prețuri în catalog)")
            w["buton"].configure(state="disabled")
            return
        total = round(float(pm) + float(pa), 2)
        w["engs_pret_total_lei"] = total
        w["pret_display"].configure(text=f"Total: {total:.2f} LEI (TVA inclus)")
        w["buton"].configure(state="normal", command=lambda: self.adauga_in_cos_config("Manere"))

    def _adauga_manere_engs_in_cos(self):
        w = self.config_widgets.get("Manere")
        if not w:
            return
        total = w.get("engs_pret_total_lei")
        ph_c = w.get("_ph_colectie") or "Alege model"
        ph_f = w.get("_ph_model") or "Alege finisaj"
        model = (w["colectie"].get() or "").strip()
        fin = (w["model"].get() or "").strip()
        inc = (w["decor"].get() or "").strip()
        if total is None or not model or model == ph_c or not fin or fin == ph_f or inc not in ("OB", "PZ", "WC"):
            self.afiseaza_mesaj("Atenție", "Alege model, finisaj și tip închidere (OB / PZ / WC).", "#7a1a1a")
            return
        nume = _nume_linie_maner_engs(model, fin, inc)
        tip_b = _maner_broasca_tip_engs_inc(inc)
        self._cos_append_maner_cu_broasca_optional(
            {
                "nume": nume,
                "tip": "manere_engs",
                "pret_lei_cu_tva": round(float(total), 2),
                "pret_eur": 0.0,
                "qty": 1,
                "furnizor": "Enger",
            },
            tip_b,
        )

    def on_colectie_select(self, titlu):
        if titlu == "Manere":
            vm = self.config_widgets[titlu].get("furnizor_manere")
            if vm and vm.get() == "Enger":
                self._manere_engs_on_colectie_select()
                return
        col = self.config_widgets[titlu]["colectie"].get()
        furnizor = self.var_furnizor_global.get()
        if titlu in self.CATEGORII_PARCHET:
            furnizor = "Stoc"
        if titlu == "Manere":
            var_manere = self.config_widgets[titlu].get("furnizor_manere")
            furnizor = var_manere.get() if var_manere else "Stoc"
        if titlu == "Tocuri":
            self.config_widgets[titlu]["_tip_toc"] = col
        modele = get_modele_produse(
            self.cursor, titlu, furnizor, col,
            use_tip_toc=(titlu == "Tocuri"),
        )
        ph_mod = "Alege Cod Produs" if titlu in self.CATEGORII_PARCHET else "Alege Model"
        self.config_widgets[titlu]["_ph_model"] = ph_mod
        self.config_widgets[titlu]["model_all"] = list(modele)
        self.config_widgets[titlu]["model"].configure(state="normal", values=modele)
        self.config_widgets[titlu]["model"].set(ph_mod)
        if self.config_widgets[titlu].get("decor"):
            self.config_widgets[titlu]["decor"].configure(state="disabled")
        if titlu not in self.CATEGORII_PARCHET:
            wz = self.config_widgets[titlu]
            wz["pret_val"] = 0.0
            pd0 = wz.get("pret_display")
            if pd0:
                pd0.configure(text="Preț: —")
            wz["buton"].configure(state="disabled")
        if titlu in self.CATEGORII_PARCHET:
            w = self.config_widgets[titlu]
            w["lbl_mp_cut"].configure(text="MP/cut: —")
            w["pret_display"].configure(text="Pret lista eur fara TVA/mp: —")
            w["entry_suprafata"].configure(state="disabled")
            w["buton"].configure(state="disabled")
            w["pret_val"] = 0.0
            w["mp_per_cut"] = 0.0

    def on_model_select(self, titlu):
        col = self.config_widgets[titlu]["colectie"].get()
        mod = self.config_widgets[titlu]["model"].get()
        furnizor = self.var_furnizor_global.get()
        if titlu in self.CATEGORII_PARCHET:
            furnizor = "Stoc"
        if titlu == "Manere":
            var_manere = self.config_widgets[titlu].get("furnizor_manere")
            furnizor = var_manere.get() if var_manere else "Stoc"
            if furnizor == "Enger":
                self._manere_engs_on_model_select()
                return
        if titlu in self.CATEGORII_PARCHET:
            mod = (mod or "").strip()
            mod_int = None
            mod_float = None
            try:
                mod_int = str(int(float(mod)))
            except (ValueError, TypeError):
                pass
            if not mod_int or mod_int == mod:
                try:
                    mod_float = str(float(mod)) if "." not in mod else mod
                except (ValueError, TypeError):
                    pass
            res = get_parchet_dimensiune_pret(self.cursor, titlu, furnizor, col, mod, mod_int)
            if not res and mod_float and mod_float != mod:
                res = get_parchet_dimensiune_pret(self.cursor, titlu, furnizor, col, mod, mod_float)
            if res:
                mp_cut_str = (res[0] or "0").strip()
                try:
                    mp_per_cut = float(mp_cut_str.replace(",", "."))
                except (ValueError, TypeError):
                    mp_per_cut = 0.0
                if mp_per_cut > 100:
                    mp_per_cut = 0.0
                pret_per_mp = float(res[1]) if res[1] is not None else 0.0
                w = self.config_widgets[titlu]
                w["mp_per_cut"] = mp_per_cut
                w["pret_val"] = pret_per_mp
                w["lbl_mp_cut"].configure(text=f"MP/cut: {mp_per_cut}" if mp_per_cut else "MP/cut: —")
                w["pret_display"].configure(text=f"Pret lista eur fara TVA/mp: {pret_per_mp} €" if pret_per_mp else "Pret lista eur fara TVA/mp: —")
                w["entry_suprafata"].configure(state="normal")
                w["buton"].configure(state="normal")
            return

        if titlu == "Tocuri":
            # La Tocuri Stoc: decor/finisaj se preia automat din ușa asociată;
            # prețul se ia strict pe (tip_toc, dimensiune).
            # La Tocuri Erkado: rămâne selecție pe perechi (decor, finisaj).
            tip_toc = col
            dimensiune = mod or ""
            furnizor = self.var_furnizor_global.get()
            w = self.config_widgets[titlu]
            if furnizor == "Stoc":
                auto_label = "Automat din usa"
                w["decor_finisaj_pairs"] = []
                w["decor_all"] = [auto_label]
                w["decor"].configure(state="disabled", values=[auto_label])
                w["decor"].set(auto_label)
                res = get_pret_tocuri(self.cursor, titlu, furnizor, tip_toc, dimensiune)
                if res:
                    w["pret_val"] = res[0]
                    w["pret_display"].configure(text=f"Preț: {res[0]} €")
                    w["buton"].configure(
                        state="normal",
                        command=lambda t=titlu: self.adauga_in_cos_config(t),
                    )
                else:
                    w["pret_val"] = 0
                    w["pret_display"].configure(text="Preț: —")
                    w["buton"].configure(state="disabled")
                return

            pairs = get_decor_finisaj_pairs_tocuri(self.cursor, titlu, furnizor, tip_toc, dimensiune)
            fins = [f for _, f in pairs]
            ph_decor = w.get("_ph_decor") or "Alege Finisaj"
            if not fins:
                sample_same_dim = []
                sample_trim = []
                try:
                    self.cursor.execute(
                        """
                        SELECT COALESCE(decor,''), COALESCE(finisaj,''), COUNT(*)
                        FROM produse
                        WHERE categorie=? AND furnizor=? AND tip_toc=? AND COALESCE(dimensiune,'')=?
                        GROUP BY COALESCE(decor,''), COALESCE(finisaj,'')
                        ORDER BY COALESCE(decor,''), COALESCE(finisaj,'')
                        LIMIT 12
                        """.strip(),
                        (titlu, furnizor, tip_toc, dimensiune or ""),
                    )
                    sample_same_dim = self.cursor.fetchall()
                    self.cursor.execute(
                        """
                        SELECT DISTINCT COALESCE(finisaj,''), COALESCE(decor,'')
                        FROM produse
                        WHERE categorie=? AND furnizor=? AND tip_toc=?
                          AND TRIM(COALESCE(dimensiune,''))=TRIM(?)
                        ORDER BY COALESCE(finisaj,''), COALESCE(decor,'')
                        LIMIT 12
                        """.strip(),
                        (titlu, furnizor, tip_toc, dimensiune or ""),
                    )
                    sample_trim = self.cursor.fetchall()
                except Exception:
                    pass
            values = [f"{d} / {f}" if d else f for d, f in pairs]
            w["decor_finisaj_pairs"] = pairs
            w["decor_all"] = list(values)
            w["decor"].configure(state="normal", values=values)
            w["decor"].set(ph_decor)
            w["buton"].configure(state="disabled")
            w["pret_val"] = 0

            if values:
                w["decor"].set(values[0])
                d0, f0 = pairs[0]
                res = get_pret_tocuri_decor_finisaj(self.cursor, titlu, furnizor, tip_toc, dimensiune, d0, f0)
                if res:
                    w["pret_val"] = res[0]
                    w["pret_display"].configure(text=f"Preț: {res[0]} €")
                    w["buton"].configure(
                        state="normal",
                        command=lambda t=titlu: self.adauga_in_cos_config(t),
                    )
            return

        pairs = get_decor_finisaj_pairs(self.cursor, titlu, col, mod, furnizor)
        self.config_widgets[titlu]["decor_finisaj_pairs"] = pairs

        # Pentru ușile de interior Erkado: dropdown-ul afișează doar FINISAJ (CPL, PREMIUM, etc.)
        if titlu == "Usi Interior" and furnizor == "Erkado":
            values = [(f or (d or "—")) for d, f in pairs]
        elif titlu == "Usi Interior" and furnizor == "Stoc":
            # O linie: … LAMINAT sau … INOVA 3D (fără „/ INOVA, LAMINAT” din finisaj).
            values = _values_dropdown_usi_stoc(pairs)
        else:
            # Dacă decor lipsește și există doar finisaj, afișăm DOAR finisaj (fără „/” în față).
            # - decor și finisaj: "Decor / Finisaj"
            # - doar decor: "Decor"
            # - doar finisaj: "Finisaj"
            values = [
                f"{d} / {f}" if (d and f) else (d or f or "—")
                for d, f in pairs
            ]

        # Salvăm lista completă pentru filtrare la tastare
        self.config_widgets[titlu]["decor_all"] = list(values)
        self.config_widgets[titlu]["decor"].configure(state="normal", values=values)
        ph_decor = self.config_widgets[titlu].get("_ph_decor") or "Alege Decor"
        self.config_widgets[titlu]["decor"].set(ph_decor)

        if not (titlu == "Tocuri" and values):
            w = self.config_widgets[titlu]
            w["pret_val"] = 0.0
            w["pret_display"].configure(text="Preț: —")
            w["buton"].configure(state="disabled")

        # Pentru Tocuri: finisajul este criteriul care determină prețul.
        # Selectăm automat primul finisaj ca să se afișeze imediat prețul și să se activeze butonul.
        if titlu == "Tocuri" and values:
            self.config_widgets[titlu]["decor"].set(values[0])
            self.on_decor_select(titlu)

    def on_decor_select(self, titlu):
        col = self.config_widgets[titlu]["colectie"].get()
        mod = self.config_widgets[titlu]["model"].get()
        sel = self.config_widgets[titlu]["decor"].get()
        furnizor = self.var_furnizor_global.get()
        if titlu == "Manere":
            var_manere = self.config_widgets[titlu].get("furnizor_manere")
            furnizor = var_manere.get() if var_manere else "Stoc"
            if furnizor == "Enger":
                self._manere_engs_refresh_total_from_w()
                return

        if titlu == "Tocuri":
            w = self.config_widgets[titlu]
            tip_toc = col
            dimensiune = mod or ""
            if furnizor == "Stoc":
                res = get_pret_tocuri(self.cursor, titlu, furnizor, tip_toc, dimensiune)
                if res:
                    w["pret_val"] = res[0]
                    w["pret_display"].configure(text=f"Preț: {res[0]} €")
                    w["buton"].configure(
                        state="normal", command=lambda t=titlu: self.adauga_in_cos_config(t)
                    )
                else:
                    w["pret_val"] = 0
                    w["pret_display"].configure(text="Preț: —")
                    w["buton"].configure(state="disabled")
                return
            values = list(w["decor"].cget("values") or [])
            pairs = w.get("decor_finisaj_pairs") or []
            try:
                idx = values.index(sel)
                decor, finisaj = pairs[idx]
            except (ValueError, IndexError):
                decor, finisaj = "", sel
            ph_decor = w.get("_ph_decor") or "Alege Finisaj"
            if not sel or sel == ph_decor:
                w["buton"].configure(state="disabled")
                return

            if self._is_safe_mode_enabled():
                required = self._get_required_toc_option_for_next_toc(furnizor)
                if required and required in values and sel != required:
                    w["decor"].set(required)
                    sel = required
                    try:
                        idx = list(w["decor"].cget("values") or []).index(sel)
                        decor, finisaj = (w.get("decor_finisaj_pairs") or [("", "")])[idx]
                    except (ValueError, IndexError):
                        decor, finisaj = "", sel
                    self.afiseaza_mesaj(
                        "Atenție",
                        "Tocul trebuie să fie pe același decor/finisaj cu ușa corespunzătoare.\n"
                        f"Selecția a fost corectată automat la: {required}.",
                        "#7a1a1a",
                    )

            res = get_pret_tocuri_decor_finisaj(
                self.cursor, titlu, furnizor, tip_toc, dimensiune, decor, finisaj
            )
            if res:
                w["pret_val"] = res[0]
                w["pret_display"].configure(text=f"Preț: {res[0]} €")
                w["buton"].configure(
                    state="normal", command=lambda t=titlu: self.adauga_in_cos_config(t)
                )
            else:
                w["pret_val"] = 0
                w["pret_display"].configure(text="Preț: —")
                w["buton"].configure(state="disabled")
            return

        wcfg = self.config_widgets[titlu]
        ph_mod = wcfg.get("_ph_model") or "Alege Model"
        ph_decor = wcfg.get("_ph_decor") or "Alege Decor"
        if not mod or mod == ph_mod:
            wcfg["pret_val"] = 0.0
            wcfg["pret_display"].configure(text="Preț: —")
            wcfg["buton"].configure(state="disabled")
            return
        if not sel or sel == ph_decor:
            wcfg["pret_val"] = 0.0
            wcfg["pret_display"].configure(text="Preț: —")
            wcfg["buton"].configure(state="disabled")
            return

        pairs = wcfg.get("decor_finisaj_pairs") or []
        values = wcfg["decor"].cget("values") or []
        try:
            idx = list(values).index(sel)
            dec, fin = pairs[idx]
        except (ValueError, IndexError):
            dec, fin = sel, ""
        res = get_pret_decor_finisaj(self.cursor, titlu, col, mod, furnizor, dec, fin)
        if res:
            wcfg["pret_val"] = res[0]
            wcfg["pret_display"].configure(text=f"Preț: {res[0]} €")
            wcfg["buton"].configure(
                state="normal", command=lambda t=titlu: self.adauga_in_cos_config(t)
            )
        else:
            wcfg["pret_val"] = 0.0
            wcfg["pret_display"].configure(text="Preț: —")
            wcfg["buton"].configure(state="disabled")

    def _on_decor_text_change(self, titlu: str):
        """Transformă automat în MAJUSCULE textul introdus pentru decor liber (Erkado)."""
        cfg = self.config_widgets.get(titlu)
        if not cfg:
            return
        entry = cfg.get("decor_text")
        if not entry or not entry.winfo_exists():
            return
        cur = entry.get()
        upper = cur.upper()
        if cur != upper:
            entry.delete(0, "end")
            entry.insert(0, upper)

    def _reset_combobox_on_focus_out(self, titlu: str, field: str):
        """La click în afara casetei: restaurează lista completă și resetează la placeholder dacă nu e o opțiune validă."""
        cfg = self.config_widgets.get(titlu)
        if not cfg:
            return
        box = cfg.get(field)
        all_vals = cfg.get(f"{field}_all")
        if not box or not isinstance(all_vals, list):
            return
        box.configure(values=all_vals)
        current = (box.get() or "").strip()
        if current not in all_vals:
            ph = cfg.get(f"_ph_{field}")
            if ph is not None:
                box.set(ph)

    def _reset_parchet_combobox_on_focus_out(self, field: str):
        """La click în afara casetei (popup parchet): restaurează lista completă și resetează dacă nu e opțiune validă."""
        w = getattr(self, "parchet_menu", None)
        if not w or field not in w:
            return
        box = w.get(field)
        all_vals = w.get(f"{field}_all")
        if not all_vals and field == "categorie":
            all_vals = w.get("categorie_all") or []
        if not box or not isinstance(all_vals, list):
            return
        box.configure(values=all_vals)
        current = (box.get() or "").strip()
        if current not in all_vals and all_vals:
            box.set(all_vals[0])

    def _get_item_tip(self, item):
        """Returnează 'usi', 'tocuri' sau 'accesorii'; inferă din nume dacă lipsește tip."""
        if item.get("tip"):
            return item["tip"]
        nume = (item.get("nume") or "")
        if "Toc " in nume or "Toc Drept" in nume:
            return "tocuri"
        # Nume tip "[Furnizor] Colectie Model (Decor)" = ușă
        if "(" in nume and ")" in nume and "Toc" not in nume:
            return "usi"
        return "accesorii"

    def _total_usi(self):
        return sum(i.get("qty", 0) for i in self.cos_cumparaturi if self._get_item_tip(i) == "usi")

    def _total_tocuri(self):
        return sum(i.get("qty", 0) for i in self.cos_cumparaturi if self._get_item_tip(i) == "tocuri")

    def _get_furnizor_from_nume(self, nume: str) -> str | None:
        """Extrage furnizorul din nume când e prefix [Stoc]/[Erkado] (ex: tocuri, accesorii)."""
        if not nume or not isinstance(nume, str):
            return None
        s = nume.strip()
        if s.startswith("["):
            end = nume.find("]")
            if end == -1:
                return None
            return nume[1:end].strip()
        # Uși vechi: „Usa (colectie) …”; noi: „Usa COLECTIE …” – furnizorul e în item['furnizor'].
        if s.startswith("Usa (") or s.startswith("Ușă ("):
            return None
        return None

    def _get_furnizor_from_item(self, item: dict) -> str:
        """Furnizor din coș: cheia 'furnizor' sau parsare [Stoc]/[Erkado] din nume (compat. înapoi)."""
        f = (item.get("furnizor") or "").strip()
        if f in ("Stoc", "Erkado"):
            return f
        parsed = self._get_furnizor_from_nume(item.get("nume") or "")
        if parsed:
            return parsed
        return "Stoc"

    def _cos_row_accent_for_item(self, item: dict) -> str | None:
        """Culoare rând coș: verde DEBARA, albastru dublă/dublu, galben glisantă / toc tunel / kit glisare (vizual)."""
        nume_poz = (item.get("nume") or "").strip()
        if nume_poz in ("Sistem Glisare + Masca", "Kit Glisare Simplu Peste Perete"):
            return "yellow"
        tip = self._get_item_tip(item)
        if tip not in ("usi", "tocuri"):
            return None
        if item.get("debara") or item.get("debara_toc"):
            return "green"
        if item.get("dubla") in ("usa", "toc"):
            return "blue"
        if tip == "usi" and item.get("glisare_activ"):
            return "yellow"
        if tip == "tocuri" and item.get("toc_tunel"):
            return "yellow"
        return None

    def _cos_row_frame_kwargs(self, accent: str | None) -> dict:
        if accent == "green":
            return {
                "fg_color": "#14532d",
                "corner_radius": 8,
                "border_width": 2,
                "border_color": "#22c55e",
            }
        if accent == "yellow":
            return {
                "fg_color": "#422006",
                "corner_radius": 8,
                "border_width": 2,
                "border_color": "#eab308",
            }
        if accent == "blue":
            return {
                "fg_color": "#1e3a5f",
                "corner_radius": 8,
                "border_width": 2,
                "border_color": "#3b82f6",
            }
        return {"fg_color": "#2D2D2D", "corner_radius": 6, "border_width": 0}

    def _cos_row_title_text_color(self, accent: str | None):
        if accent == "green":
            return "#ecfdf5"
        if accent == "yellow":
            return "#fef9c3"
        if accent == "blue":
            return "#93c5fd"
        return None

    def _strip_usa_debara_state(self, idx: int) -> None:
        """Revine la preț fără DEBARA pe ușă (fără refresh)."""
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if self._get_item_tip(item) != "usi" or not item.get("debara"):
            return
        baza = float(item.get("pret_eur_fara_debara") or item.get("pret_eur") or 0)
        item["pret_eur"] = round(baza, 2)
        item.pop("debara", None)
        item.pop("pret_eur_fara_debara", None)

    def _is_stoc_usa_pt_debara(self, item: dict) -> bool:
        """True pentru ușă de interior Stoc — multiplicatorii Debară se aplică doar aici (is_stoc în specificație)."""
        return self._get_item_tip(item) == "usi" and self._get_furnizor_from_item(item) == "Stoc"

    def _stoc_pairing_index_usa(self, idx_usa: int) -> int | None:
        item = self.cos_cumparaturi[idx_usa]
        if self._get_item_tip(item) != "usi" or self._get_furnizor_from_item(item) != "Stoc":
            return None
        k = 0
        for j, it in enumerate(self.cos_cumparaturi):
            if j == idx_usa:
                return k
            if self._get_item_tip(it) == "usi" and self._get_furnizor_from_item(it) == "Stoc":
                k += 1
        return None

    def _stoc_pairing_index_toc(self, idx_toc: int) -> int | None:
        item = self.cos_cumparaturi[idx_toc]
        if self._get_item_tip(item) != "tocuri" or self._get_furnizor_from_item(item) != "Stoc":
            return None
        k = 0
        for j, it in enumerate(self.cos_cumparaturi):
            if j == idx_toc:
                return k
            if self._get_item_tip(it) == "tocuri" and self._get_furnizor_from_item(it) == "Stoc":
                k += 1
        return None

    def _find_usa_pentru_toc_stoc(self, idx_toc: int) -> int | None:
        pi = self._stoc_pairing_index_toc(idx_toc)
        if pi is None:
            return None
        k = 0
        for j, it in enumerate(self.cos_cumparaturi):
            if self._get_item_tip(it) == "usi" and self._get_furnizor_from_item(it) == "Stoc":
                if k == pi:
                    return j
                k += 1
        return None

    def _find_toc_pentru_usa_stoc(self, idx_usa: int) -> int | None:
        pi = self._stoc_pairing_index_usa(idx_usa)
        if pi is None:
            return None
        k = 0
        for j, it in enumerate(self.cos_cumparaturi):
            if self._get_item_tip(it) == "tocuri" and self._get_furnizor_from_item(it) == "Stoc":
                if k == pi:
                    return j
                k += 1
        return None

    def _toc_tip_reglabil_stoc(self, item: dict) -> bool:
        tip = (item.get("toc_tip_toc") or "").strip().lower()
        if "reglabil" in tip:
            return True
        return "reglabil" in (item.get("nume") or "").lower()

    def _factor_debara_pentru_toc_stoc(self, item: dict) -> float:
        if self._toc_tip_reglabil_stoc(item):
            return float(self.config_app.debara_toc_reglabil_factor_stoc or 1.5)
        return float(self.config_app.debara_toc_fix_factor_stoc or 2.0)

    def _toggle_debara_usa(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if not self._is_stoc_usa_pt_debara(item):
            return
        if item.get("debara"):
            baza = float(item.get("pret_eur_fara_debara") or item.get("pret_eur") or 0)
            item["pret_eur"] = round(baza, 2)
            item.pop("debara", None)
            item.pop("pret_eur_fara_debara", None)
            self.refresh_cos()
            return
        if item.get("glisare_activ"):
            pret_baza = float(item.get("pret_eur_fara_glisare") or item.get("pret_eur") or 0)
            item["pret_eur"] = round(pret_baza, 2)
            item["glisare_activ"] = False
            item["glisare_mod"] = None
            item.pop("pret_eur_fara_glisare", None)
            self._cleanup_sistem_glisare_masca()
        if item.get("dubla") == "usa":
            self._transforma_in_simpla_core(idx)
        baza = float(item.get("pret_eur") or 0)
        fac = float(self.config_app.usa_dubla_factor_stoc or 2.35)
        item["pret_eur_fara_debara"] = round(baza, 2)
        item["pret_eur"] = round(baza * fac, 2)
        item["debara"] = True
        self.show_success_toast("Optiune DEBARA activata! 👍", "green")
        self.refresh_cos()

    def _toggle_debara_toc(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if self._get_item_tip(item) != "tocuri" or self._get_furnizor_from_item(item) != "Stoc":
            return
        if item.get("dubla"):
            return
        if item.get("debara_toc"):
            baza = float(item.get("pret_eur_fara_debara_toc") or item.get("pret_eur") or 0)
            item["pret_eur"] = round(baza, 2)
            item.pop("debara_toc", None)
            item.pop("pret_eur_fara_debara_toc", None)
            self.refresh_cos()
            return
        baza = float(item.get("pret_eur") or 0)
        fac = self._factor_debara_pentru_toc_stoc(item)
        item["pret_eur_fara_debara_toc"] = round(baza, 2)
        item["pret_eur"] = round(baza * fac, 2)
        item["debara_toc"] = True
        self.show_success_toast("Optiune DEBARA activata! 👍", "green")
        self.refresh_cos()

    def transforma_in_dubla(self, idx: int) -> None:
        """
        Transformă o foaie de ușă în ușă dublă sau tocul în toc dublu.
        Stoc: ușă pret×2.35, toc pret×2. Erkado: ușă pret×2+37€, toc pret+30%.
        """
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        tip = item.get("tip")
        if tip not in ("usi", "tocuri"):
            return
        if item.get("dubla"):
            return  # deja marcat ca dublă/dublu
        furnizor = self._get_furnizor_from_item(item)
        if tip == "usi" and item.get("debara"):
            bz = float(item.get("pret_eur_fara_debara") or item.get("pret_eur") or 0)
            item["pret_eur"] = round(bz, 2)
            item.pop("debara", None)
            item.pop("pret_eur_fara_debara", None)
        if tip == "tocuri" and item.get("debara_toc"):
            bz = float(item.get("pret_eur_fara_debara_toc") or item.get("pret_eur") or 0)
            item["pret_eur"] = round(bz, 2)
            item.pop("debara_toc", None)
            item.pop("pret_eur_fara_debara_toc", None)
        pret = float(item.get("pret_eur") or 0)
        if tip == "usi":
            # UȘĂ → dublă
            # Dacă era ușă glisantă (Stoc) cu opțiuni „cu/fără închidere”, revenim întâi la prețul fără glisare
            if furnizor == "Stoc" and item.get("glisare_activ"):
                pret = float(item.get("pret_eur_fara_glisare") or pret)
                item["glisare_activ"] = False
                item["glisare_mod"] = None
            if furnizor == "Stoc":
                item["pret_eur"] = round(pret * self.config_app.usa_dubla_factor_stoc, 2)
            else:
                # Erkado: factor + adaos fix
                item["pret_eur"] = round(pret * self.config_app.usa_dubla_factor_erkado + self.config_app.usa_dubla_plus_erkado, 2)
            item["dubla"] = "usa"
            # Dacă nu mai există uși glisante Stoc active, ștergem „Sistem Glisare + Masca”
            self._cleanup_sistem_glisare_masca()
        else:
            # TOC → dublu (comportament vechi, manual, păstrat)
            if furnizor == "Stoc":
                item["pret_eur"] = round(pret * self.config_app.toc_dublu_factor_stoc, 2)
            else:
                item["pret_eur"] = round(pret * self.config_app.toc_dublu_factor_erkado, 2)
            item["dubla"] = "toc"
        if tip == "usi":
            self.show_success_toast("Usa Dubla activata! 👍", "blue")
        else:
            self.show_success_toast("Toc Dublu activat! 👍", "blue")
        self.refresh_cos()

    def _has_usa_cu_kit_glisare(self) -> bool:
        """
        True dacă există:
        - cel puțin o ușă (Stoc) cu glisare activă SAU
        - kitul de glisare Erkado („Kit Glisare Simplu Peste Perete”) în ofertă.
        """
        for i in self.cos_cumparaturi:
            if self._get_item_tip(i) == "usi" and i.get("glisare_activ"):
                return True
            if (i.get("nume") or "").strip() == "Kit Glisare Simplu Peste Perete":
                return True
        return False

    def _has_usa_glisanta_stoc(self) -> bool:
        """True dacă există cel puțin o ușă de Stoc cu glisare activă."""
        return any(
            self._get_item_tip(i) == "usi"
            and self._get_furnizor_from_item(i) == "Stoc"
            and i.get("glisare_activ")
            for i in self.cos_cumparaturi
        )

    def _cleanup_sistem_glisare_masca(self) -> None:
        """
        Elimină poziția 'Sistem Glisare + Masca' dacă nu mai există nicio ușă
        de Stoc cu kit de glisare activ.
        """
        if self._has_usa_glisanta_stoc():
            return
        self.cos_cumparaturi = [
            i for i in self.cos_cumparaturi
            if (i.get("nume") or "").strip() != "Sistem Glisare + Masca"
        ]

    def _set_toc_tunel(self, idx: int, activ: bool) -> None:
        """Toc tunel: strict vizual (marcaj + denumire); fără modificare preț."""
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if self._get_item_tip(item) != "tocuri":
            return
        if not self._has_usa_cu_kit_glisare():
            self.afiseaza_mesaj(
                "Atenție",
                "Poți seta „Toc tunel” doar dacă există în ofertă o ușă cu kit de glisare activ.",
                "#7a1a1a",
            )
            return
        if activ:
            item["toc_tunel"] = True
            if "Toc Tunel" not in (item.get("nume") or ""):
                item["nume"] = (item.get("nume") or "").replace("Toc ", "Toc Tunel ", 1)
            self.show_success_toast("Toc tunel activat! 👍", "yellow")
        else:
            item["toc_tunel"] = False
            item.pop("pret_eur_fara_tunel", None)
            nume = item.get("nume") or ""
            if "Toc Tunel" in nume:
                item["nume"] = nume.replace("Toc Tunel ", "Toc ", 1)
        self.refresh_cos()

    def _transforma_in_simpla_core(self, idx: int) -> bool:
        """Logica ușă/toc simplu fără refresh; returnează True dacă s-a modificat."""
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return False
        item = self.cos_cumparaturi[idx]
        tip = item.get("tip")
        dubla = item.get("dubla")
        if tip not in ("usi", "tocuri") or dubla not in ("usa", "toc"):
            return False
        furnizor = self._get_furnizor_from_item(item)
        pret = float(item.get("pret_eur") or 0)
        if dubla == "usa":
            if furnizor == "Stoc":
                factor = self.config_app.usa_dubla_factor_stoc or 1.0
                item["pret_eur"] = round(pret / factor, 2)
            else:
                factor = self.config_app.usa_dubla_factor_erkado or 1.0
                plus_fix = self.config_app.usa_dubla_plus_erkado
                item["pret_eur"] = round((pret - plus_fix) / factor, 2)
            item["glisare_activ"] = False
            item["glisare_mod"] = None
            self._cleanup_sistem_glisare_masca()
        else:
            if furnizor == "Stoc":
                factor = self.config_app.toc_dublu_factor_stoc or 1.0
                item["pret_eur"] = round(pret / factor, 2)
            else:
                factor = self.config_app.toc_dublu_factor_erkado or 1.0
                item["pret_eur"] = round(pret / factor, 2)
        del item["dubla"]
        return True

    def transforma_in_simpla(self, idx: int) -> None:
        """
        Revine la ușă simplă sau toc simplu (inversează formulele dublă/dublu).
        """
        if self._transforma_in_simpla_core(idx):
            self.refresh_cos()

    def _on_kit_glisare_simplu(self, idx: int) -> None:
        """La click pe Kit Glisare Simplu:
        - pentru ușile Stoc: opțiunile „Cu închidere” / „Fără închidere” și poziția suplimentară Sistem Glisare + Masca;
        - pentru ușile Erkado: comportamentul rămâne cel vechi (doar kitul, fără modificarea prețului ușii).
        """
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if self._get_item_tip(item) != "usi":
            return

        nume_kit = "Kit Glisare Simplu Peste Perete"
        nume_sistem = "Sistem Glisare + Masca"
        furnizor = self._get_furnizor_from_item(item)

        self._strip_usa_debara_state(idx)
        item = self.cos_cumparaturi[idx]
        if item.get("dubla") == "usa":
            self._transforma_in_simpla_core(idx)
            item = self.cos_cumparaturi[idx]

        # Comportament nou – DOAR pentru ușile de Stoc
        if furnizor == "Stoc":
            pret_curent = float(item.get("pret_eur") or 0)
            if "pret_eur_fara_glisare" not in item:
                item["pret_eur_fara_glisare"] = pret_curent
            item["glisare_activ"] = True
            # Implicit: Fără închidere (ușă + 26 €)
            item["glisare_mod"] = "fara"
            item["pret_eur"] = round(
                item["pret_eur_fara_glisare"] + self.config_app.glisare_plus_stoc,
                2,
            )

            # Pentru ușile Stoc: doar „Sistem Glisare + Masca” (149 €), fără „Kit Glisare Simplu Peste Perete”
            if not any((i.get("nume") or "").strip() == nume_sistem for i in self.cos_cumparaturi):
                self.cos_cumparaturi.append({
                    "nume": nume_sistem,
                    "pret_eur": 149.0,
                    "qty": 1,
                    "tip": "servicii_suplimentare",
                })
        else:
            # Comportament vechi pentru ușile Erkado: doar kitul (fără modificarea prețului ușii)
            if not self._has_erkado_usi():
                self.afiseaza_mesaj(
                    "Informație",
                    "Kitul de glisare simplu pentru Erkado este disponibil doar când aveți în ofertă cel puțin o ușă Erkado.",
                    "#7a1a1a",
                )
                return
            if any((i.get("nume") or "").strip() == nume_kit for i in self.cos_cumparaturi):
                return  # deja în coș, nu adăugăm din nou
            self.cos_cumparaturi.append({
                "nume": nume_kit,
                "pret_eur": 154.0,
                "qty": 1,
                "tip": "servicii_suplimentare",
            })
        self.show_success_toast("Usa Glisanta activata! 👍", "yellow")
        self.refresh_cos()

    def _set_glisare_mod(self, idx: int, mod: str) -> None:
        """Actualizează opțiunea de glisare pentru o ușă: 'cu' sau 'fara' închidere."""
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if self._get_item_tip(item) != "usi" or not item.get("glisare_activ"):
            return
        pret_baza = float(item.get("pret_eur_fara_glisare") or item.get("pret_eur") or 0)
        item["pret_eur_fara_glisare"] = pret_baza
        if mod == "cu":
            item["pret_eur"] = round(
                pret_baza + self.config_app.glisare_plus_cu_inchidere,
                2,
            )
            item["glisare_mod"] = "cu"
        else:
            item["pret_eur"] = round(
                pret_baza + self.config_app.glisare_plus_stoc,
                2,
            )
            item["glisare_mod"] = "fara"
        self.show_success_toast("Usa Glisanta activata! 👍", "yellow")
        self.refresh_cos()

    def _has_erkado_usi(self) -> bool:
        """True dacă în coș există cel puțin o ușă Erkado (orice decor/finisaj)."""
        return any(
            self._get_furnizor_from_item(i) == "Erkado" and self._get_item_tip(i) == "usi"
            for i in self.cos_cumparaturi
        )

    def _map_erkado_usa_finisaj_to_toc_finisaj(self, usa_finisaj: str) -> str | None:
        """Mapează finisaj ușă Erkado -> finisaj toc Erkado.

        Reguli cerute:
        - CPL -> CPL/ST PREMIUM
        - PREMIUM -> CPL/ST PREMIUM
        - GREKO -> GREKO
        """
        v = (usa_finisaj or "").strip().upper()
        if not v:
            return None
        if "GREKO" in v:
            return "GREKO"
        if "LACUIT" in v:
            return "LACUIT"
        if "0.2" in v or "0,2" in v:
            return "CPL 0.2"
        if "PREMIUM" in v:
            return "CPL/ST PREMIUM"
        if "CPL" in v:
            return "CPL/ST PREMIUM"
        return None

    def _get_mapped_toc_finisaje_from_erkado_usi_in_cos(self) -> set[str]:
        """Set de finisaje toc cerute, deduse din ușile Erkado din coș."""
        required: set[str] = set()
        for item in self.cos_cumparaturi:
            if self._get_item_tip(item) != "usi":
                continue
            furn = self._get_furnizor_from_item(item)
            if furn != "Erkado":
                continue
            usa_finisaj = item.get("usa_finisaj") or ""
            if not usa_finisaj:
                # Fallback: extragem din nume (pentru uși Erkado vechi, înainte să stocăm usa_finisaj).
                nume = item.get("nume") or ""
                if "(" in nume and ")" in nume:
                    try:
                        usa_finisaj = nume.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
                    except Exception:
                        usa_finisaj = ""
            mapped = self._map_erkado_usa_finisaj_to_toc_finisaj(usa_finisaj)
            if mapped:
                required.add(mapped)
        return required

    def _get_required_toc_option_for_next_toc(self, furnizor: str) -> str | None:
        """Opțiunea decor/finisaj cerută pentru următorul toc (pairing pe ordinea adăugării)."""
        usi_match = [
            i
            for i in self.cos_cumparaturi
            if self._get_item_tip(i) == "usi" and self._get_furnizor_from_item(i) == furnizor
        ]
        tocuri_match = [
            i
            for i in self.cos_cumparaturi
            if self._get_item_tip(i) == "tocuri" and self._get_furnizor_from_item(i) == furnizor
        ]
        idx_next = len(tocuri_match)
        if idx_next >= len(usi_match):
            return None

        usa_item = usi_match[idx_next]
        usa_decor = (usa_item.get("usa_decor") or "").strip()
        usa_finisaj = (usa_item.get("usa_finisaj") or "").strip()
        if not usa_decor:
            usa_decor = (usa_item.get("usa_decor_display") or "").strip()
        if not usa_finisaj:
            nume_usa = usa_item.get("nume") or ""
            if "(" in nume_usa and ")" in nume_usa:
                try:
                    usa_decor = nume_usa.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
                except Exception:
                    usa_decor = ""
        toc_finisaj = usa_finisaj
        if furnizor == "Erkado":
            mapped = self._map_erkado_usa_finisaj_to_toc_finisaj(usa_finisaj)
            if mapped:
                toc_finisaj = mapped
        required_raw = f"{usa_decor} / {toc_finisaj}" if (usa_decor and toc_finisaj) else (toc_finisaj or usa_decor or None)
        required = required_raw
        w = self.config_widgets.get("Tocuri") or {}
        box = w.get("decor")
        pairs = w.get("decor_finisaj_pairs") or []
        values = list(box.cget("values") or []) if box else []
        if values:
            norm = lambda s: str(s or "").strip().lower()
            target_dec = norm(usa_decor)
            target_fin = norm(toc_finisaj)
            best_idx = None
            for i, (d, f) in enumerate(pairs):
                if norm(d) == target_dec and norm(f) == target_fin:
                    best_idx = i
                    break
            if best_idx is None and target_fin:
                for i, (d, f) in enumerate(pairs):
                    if norm(f) == target_fin:
                        best_idx = i
                        break
            if best_idx is None and target_dec:
                for i, (d, f) in enumerate(pairs):
                    if norm(d) == target_dec:
                        best_idx = i
                        break
            if best_idx is not None and best_idx < len(values):
                required = values[best_idx]
            elif required_raw not in values:
                required = None
        return required

    def _get_toc_finisaj_from_item(self, item: dict) -> str | None:
        fin = item.get("toc_finisaj")
        if fin:
            return str(fin).strip()
        # Fallback: extragem din nume, ultima paranteză.
        nume = item.get("nume") or ""
        if "(" in nume and ")" in nume:
            try:
                inside = nume.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
                return inside or None
            except Exception:
                return None
        return None

    def _sync_toc_finisaj_dropdown_with_erkado_usi(self) -> None:
        """Setează automat finisajul dropdown-ului de Tocuri pentru următorul toc adăugat.

        Pairing pe ordinea adăugării: primul toc se potrivește cu prima ușă Erkado, al doilea cu a doua etc.
        """
        if not self._is_safe_mode_enabled():
            return
        furnizor = self.var_furnizor_global.get() if hasattr(self, "var_furnizor_global") else "Stoc"
        if furnizor == "Stoc":
            return
        toc_finisaj = self._get_required_toc_option_for_next_toc(furnizor)
        if not toc_finisaj:
            return
        w = self.config_widgets.get("Tocuri")
        if not w:
            return
        try:
            values = list(w["decor"].cget("values") or [])
        except Exception:
            values = []
        if values and toc_finisaj in values:
            w["decor"].set(toc_finisaj)
            try:
                self.on_decor_select("Tocuri")
            except Exception:
                pass
            # Nu modificăm tocurile existente în coș: tocurile adăugate înainte rămân aliniate cu ușile deja adăugate.

    def _on_sp1z(self, idx: int) -> None:
        """SP1Z/SP1NZ: la primul click setează opțiunea și preț 154 €; la al doilea click deselectează."""
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if (item.get("nume") or "").strip() != "Kit Glisare Simplu Peste Perete":
            return
        opt = "SP1NZ" if self._has_erkado_usi() else "SP1Z"
        if item.get("kit_glisare_option") == opt:
            item.pop("kit_glisare_option", None)
        else:
            item["kit_glisare_option"] = opt
            item["pret_eur"] = 154.0
        self.refresh_cos()

    def _on_sp1b(self, idx: int) -> None:
        """SP1B: la primul click setează opțiunea și preț 154 €; la al doilea click deselectează."""
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        if (item.get("nume") or "").strip() != "Kit Glisare Simplu Peste Perete":
            return
        if item.get("kit_glisare_option") == "SP1B":
            item.pop("kit_glisare_option", None)
        else:
            item["kit_glisare_option"] = "SP1B"
            item["pret_eur"] = 154.0
        self.refresh_cos()

    def _decor_din_paranteza_ultima(self, nume: str) -> str:
        if "(" in nume and ")" in nume:
            return nume.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
        return ""

    def _infer_maner_broasca_tip_cos_item(self, item: dict) -> str | None:
        """'wc' | 'cilindru' dacă mânerul cere broască potrivită; altfel None."""
        raw = (item.get("maner_broasca_tip") or "").strip().lower()
        if raw in ("wc", "cilindru"):
            return raw
        if item.get("tip") == "manere":
            return _maner_broasca_tip_decor_text(item.get("nume") or "")
        if item.get("tip") == "manere_engs":
            raw = (item.get("nume") or "").strip()
            mm = re.match(r"^Maner\s*\(\s*(.+)\s*\)\s*$", raw, re.IGNORECASE | re.DOTALL)
            if mm:
                toks = mm.group(1).strip().split()
                return _maner_broasca_tip_engs_inc(toks[-1]) if toks else None
            if raw.upper().startswith("MANER "):
                toks = raw.split()
                return _maner_broasca_tip_engs_inc(toks[-1]) if len(toks) >= 2 else None
            toks = raw.split()
            return _maner_broasca_tip_engs_inc(toks[-1]) if toks else None
        if item.get("tip") == "accesorii":
            nume = (item.get("nume") or "").strip()
            if nume.startswith("[") and "]" in nume:
                t = _maner_broasca_tip_decor_text(nume)
                if t:
                    return t
                dec = self._decor_din_paranteza_ultima(nume)
                return _maner_broasca_tip_decor_text(dec)
        return None

    def _cos_append_maner_cu_broasca_optional(self, maner_entry: dict, tip_b: str | None) -> None:
        """Adaugă mânerul în coș; dacă tip_b e setat, adaugă și broasca la 6 € + toast."""
        if not tip_b:
            self.cos_cumparaturi.append(maner_entry)
            self.refresh_cos()
            return
        pk = uuid.uuid4().hex[:12]
        maner_entry["broasca_pair_key"] = pk
        maner_entry["maner_broasca_tip"] = tip_b
        self.cos_cumparaturi.append(maner_entry)
        nume_b = BROASCA_WC_NUME if tip_b == "wc" else BROASCA_CILINDRU_NUME
        self.cos_cumparaturi.append({
            "nume": nume_b,
            "pret_eur": BROASCA_MANER_PRET_EUR,
            "qty": 1,
            "tip": "servicii_suplimentare",
            "fara_discount": True,
            "broasca_pair_key": pk,
            "broasca_auto": True,
        })
        et = "WC" if tip_b == "wc" else "Cilindru"
        self.show_success_toast(
            f"Broasca {et} a fost adaugata automat! 🔐",
            "broasca_wc" if tip_b == "wc" else "broasca_cil",
            duration_ms=2800,
        )
        self.refresh_cos()

    def _validare_broasca_manere(self) -> tuple[bool, str]:
        need_wc = 0
        need_cil = 0
        for it in self.cos_cumparaturi:
            bt = self._infer_maner_broasca_tip_cos_item(it)
            if not bt:
                continue
            q = int(it.get("qty") or 1)
            if bt == "wc":
                need_wc += q
            else:
                need_cil += q
        have_wc = sum(
            int(i.get("qty") or 1)
            for i in self.cos_cumparaturi
            if (i.get("nume") or "").strip() == BROASCA_WC_NUME
        )
        have_cil = sum(
            int(i.get("qty") or 1)
            for i in self.cos_cumparaturi
            if (i.get("nume") or "").strip() == BROASCA_CILINDRU_NUME
        )
        if need_wc <= have_wc and need_cil <= have_cil:
            return (True, "")
        return (False, "broasca")

    def _remove_cos_item(self, idx: int) -> None:
        """Șterge poziția din coș; pentru mâner cu broască auto, elimină și broasca cuplată."""
        if idx < 0 or idx >= len(self.cos_cumparaturi):
            return
        item = self.cos_cumparaturi[idx]
        key = item.get("broasca_pair_key")
        tip_m = item.get("maner_broasca_tip")
        is_engs = item.get("tip") == "manere_engs"
        strip_broasca = bool(key and (tip_m or is_engs) and not item.get("broasca_auto"))
        new_list: list[dict] = []
        for i, it in enumerate(self.cos_cumparaturi):
            if i == idx:
                continue
            if strip_broasca and it.get("broasca_pair_key") == key and it.get("broasca_auto"):
                continue
            new_list.append(it)
        self.cos_cumparaturi = new_list
        self.refresh_cos()

    def _validare_oferta_usi_tocuri(self) -> tuple[bool, str]:
        """
        Verifică dacă oferta e validă pentru închidere/salvare.
        Returnează (True, "") dacă e OK, (False, mesaj) dacă există probleme.
        """
        if not self._is_safe_mode_enabled():
            return (True, "")

        total_usi = self._total_usi()
        total_tocuri = self._total_tocuri()
        if (total_usi > 0 or total_tocuri > 0) and total_usi != total_tocuri:
            return (
                False,
                f"Numărul de uși trebuie să fie egal cu numărul de tocuri. Acum: {total_usi} uși, {total_tocuri} tocuri.",
            )
        has_usi_stoc = any(
            self._get_furnizor_from_item(i) == "Stoc" and self._get_item_tip(i) == "usi"
            for i in self.cos_cumparaturi
        )
        has_usi_erkado = any(
            self._get_furnizor_from_item(i) == "Erkado" and self._get_item_tip(i) == "usi"
            for i in self.cos_cumparaturi
        )
        has_toc_stoc = any(
            self._get_furnizor_from_item(i) == "Stoc" and self._get_item_tip(i) == "tocuri"
            for i in self.cos_cumparaturi
        )
        has_toc_erkado = any(
            self._get_furnizor_from_item(i) == "Erkado" and self._get_item_tip(i) == "tocuri"
            for i in self.cos_cumparaturi
        )
        if (has_usi_stoc and has_toc_erkado) or (has_usi_erkado and has_toc_stoc):
            return (
                False,
                "Nu puteți închide/salva oferta: există uși de un furnizor (Stoc/Erkado) și tocuri de alt furnizor. "
                "Toate ușile și tocurile trebuie să fie de același furnizor.",
            )

        # Potrivire finisaj uși Erkado <-> finisaj tocuri Erkado (pairing pe ordinea adăugării).
        if has_usi_erkado and has_toc_erkado:
            usi_erkado = [
                i
                for i in self.cos_cumparaturi
                if self._get_item_tip(i) == "usi" and self._get_furnizor_from_item(i) == "Erkado"
            ]
            tocuri_erkado = [
                i
                for i in self.cos_cumparaturi
                if self._get_item_tip(i) == "tocuri" and self._get_furnizor_from_item(i) == "Erkado"
            ]
            limit = min(len(usi_erkado), len(tocuri_erkado))
            for idx in range(limit):
                usa_item = usi_erkado[idx]
                usa_finisaj = usa_item.get("usa_finisaj") or ""
                if not usa_finisaj:
                    # fallback: extragem din ultima paranteză din nume (pentru uși vechi)
                    nume_usa = usa_item.get("nume") or ""
                    if "(" in nume_usa and ")" in nume_usa:
                        try:
                            usa_finisaj = nume_usa.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
                        except Exception:
                            usa_finisaj = ""

                expected_toc_finisaj = self._map_erkado_usa_finisaj_to_toc_finisaj(usa_finisaj)
                if not expected_toc_finisaj:
                    continue

                toc_item = tocuri_erkado[idx]
                actual_toc_finisaj = self._get_toc_finisaj_from_item(toc_item) or ""
                if not actual_toc_finisaj or actual_toc_finisaj != expected_toc_finisaj:
                    return (
                        False,
                        f"Nu puteți închide/salva oferta: finisajul tocului Erkado nu se potrivește cu ușa corespunzătoare. "
                        f"Indice pereche {idx + 1}: așteptat '{expected_toc_finisaj}', găsit '{actual_toc_finisaj}'.",
                    )

        # Dacă există ușă cu kit glisare activ, trebuie să existe cel puțin un toc tunel Stoc
        if self._has_usa_cu_kit_glisare():
            has_toc_tunel_stoc = any(
                self._get_item_tip(i) == "tocuri"
                and self._get_furnizor_from_item(i) == "Stoc"
                and bool(i.get("toc_tunel"))
                for i in self.cos_cumparaturi
            )
            if not has_toc_tunel_stoc:
                return (
                    False,
                    "Nu puteți închide/salva oferta: există ușă cu kit de glisare activ, dar nu este selectat niciun toc tunel de Stoc.",
                )
        return (True, "")

    def _get_decor_din_usi(self):
        """Extrage decorul din primul item tip ușă (din nume, partea din paranteze)."""
        for i in self.cos_cumparaturi:
            if self._get_item_tip(i) != "usi":
                continue
            nume = i.get("nume") or ""
            if "(" in nume and ")" in nume:
                return nume.split("(")[-1].rstrip(")").strip()
            return ""
        return ""

    def _adauga_serviciu_suplimentar(self, nume_serviciu: str, pret_eur: float):
        """Adaugă în coș un serviciu suplimentar (preț fix, fără discount)."""
        self.cos_cumparaturi.append({
            "nume": nume_serviciu,
            "pret_eur": round(pret_eur, 2),
            "qty": 1,
            "tip": "servicii_suplimentare",
            "fara_discount": True,
        })
        self.refresh_cos()

    def adauga_in_cos_config(self, titlu):
        w = self.config_widgets[titlu]
        if titlu == "Manere":
            var_m = w.get("furnizor_manere")
            if var_m and var_m.get() == "Enger":
                self._adauga_manere_engs_in_cos()
                return
        furnizor = self.var_furnizor_global.get()
        dec_display = w["decor"].get()
        # Pentru Usi Interior Erkado decorul real vine din câmpul text (obligatoriu, cu majuscule)
        if titlu == "Usi Interior" and furnizor == "Erkado":
            entry_txt = w.get("decor_text")
            decor_txt = (entry_txt.get() or "").strip() if entry_txt else ""
            if not decor_txt:
                self.afiseaza_mesaj(
                    "Atenție",
                    "Pentru ușile de interior ERKADO trebuie completat decorul în câmpul text (cu MAJUSCULE).",
                    "#7a1a1a",
                )
                return
            dec_display = decor_txt
        tip = "usi" if "Usi" in titlu else ("tocuri" if titlu == "Tocuri" else "accesorii")

        if tip == "usi":
            usa_finisaj_sel = ""
            usa_decor_sel = ""
            values = list(w["decor"].cget("values") or [])
            pairs = w.get("decor_finisaj_pairs") or []
            sel = w["decor"].get()
            try:
                idx = values.index(sel)
                usa_decor_sel, usa_finisaj_sel = pairs[idx]
            except (ValueError, IndexError):
                usa_decor_sel = dec_display
                usa_finisaj_sel = sel
            # Erkado: în listă/PDF afișăm decorul (text) + finisajul din listă (CPL, PREMIUM, GREKO, …)
            if furnizor == "Erkado":
                fin_e = (usa_finisaj_sel or "").strip()
                if fin_e:
                    nume = f"Usa {w['colectie'].get()} {w['model'].get()} ({dec_display} / {fin_e})"
                else:
                    nume = f"Usa {w['colectie'].get()} {w['model'].get()} ({dec_display})"
            else:
                nume = f"Usa {w['colectie'].get()} {w['model'].get()} ({dec_display})"
            self.cos_cumparaturi.append(
                {
                    "nume": nume,
                    "pret_eur": w["pret_val"],
                    "qty": 1,
                    "tip": tip,
                    "furnizor": furnizor,
                    "usa_decor": usa_decor_sel,
                    "usa_finisaj": usa_finisaj_sel,
                    "usa_decor_display": dec_display,
                }
            )
            self.refresh_cos()
            if self._is_safe_mode_enabled():
                self._sync_toc_finisaj_dropdown_with_erkado_usi()
            return

        if tip == "tocuri":
            tip_toc = w["colectie"].get()
            dim = w["model"].get()
            # Forțăm decor/finisaj toc conform ușii "corespunzătoare" (pairing pe ordinea adăugării).
            if self._is_safe_mode_enabled():
                required = self._get_required_toc_option_for_next_toc(furnizor)
                if required:
                    try:
                        values = list(w["decor"].cget("values") or [])
                    except Exception:
                        values = []
                    if required in values:
                        w["decor"].set(required)
                        dec_display = w["decor"].get()
                        self.on_decor_select("Tocuri")

            parte_toc = f"Toc {tip_toc} Drept {dim}" if (tip_toc and dim) else "Toc"
            toc_display = w["decor"].get()
            toc_decor = ""
            toc_finisaj = toc_display
            if furnizor == "Stoc":
                usi_match = [
                    i
                    for i in self.cos_cumparaturi
                    if self._get_item_tip(i) == "usi" and self._get_furnizor_from_item(i) == furnizor
                ]
                tocuri_match = [
                    i
                    for i in self.cos_cumparaturi
                    if self._get_item_tip(i) == "tocuri" and self._get_furnizor_from_item(i) == furnizor
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
                values = list(w["decor"].cget("values") or [])
                pairs = w.get("decor_finisaj_pairs") or []
                idx = values.index(toc_display)
                toc_decor, toc_finisaj = pairs[idx]
            except (ValueError, IndexError):
                pass
            nume = f"{parte_toc} ({toc_display})"
            # Adăugăm întotdeauna toc normal; opțiunea „Toc Tunel” se poate activa ulterior din coș
            self.cos_cumparaturi.append(
                {
                    "nume": nume,
                    "pret_eur": w["pret_val"],
                    "qty": 1,
                    "tip": tip,
                    "furnizor": furnizor,
                    "toc_decor": toc_decor,
                    "toc_finisaj": toc_finisaj,
                    "toc_tip_toc": tip_toc,
                    "toc_dimensiune": dim,
                }
            )
            self.refresh_cos()
            return

        # Accesorii (inclusiv Manere): furnizor din switch la Manere, altfel global
        if titlu == "Manere":
            var_manere = w.get("furnizor_manere")
            furnizor = var_manere.get() if var_manere else "Stoc"
            if furnizor != "Enger":
                phm = w.get("_ph_model") or "Alege Model"
                phd = w.get("_ph_decor") or "Alege Decor"
                if (w["model"].get() or "").strip() == phm.strip():
                    self.afiseaza_mesaj(
                        "Atenție",
                        "Selectează modelul mânerului (nu «Alege Model»).",
                        "#7a1a1a",
                    )
                    return
                if (w["decor"].get() or "").strip() == phd.strip():
                    self.afiseaza_mesaj(
                        "Atenție",
                        "Selectează finisajul / decorul mânerului.",
                        "#7a1a1a",
                    )
                    return
                if float(w.get("pret_val") or 0) <= 0:
                    self.afiseaza_mesaj(
                        "Atenție",
                        "Prețul mânerului nu este determinat. Verifică colecția, modelul și decorul.",
                        "#7a1a1a",
                    )
                    return
        if titlu == "Manere":
            c = (w["colectie"].get() or "").strip()
            m = (w["model"].get() or "").strip()
            dd = (dec_display or "").strip()
            segments = " ".join(x for x in (c, m) if x).strip()
            if segments and dd:
                inner = f"{segments} ({dd})"
            elif segments:
                inner = segments
            else:
                inner = dd or "—"
            nume = f"Maner ({inner})"
            entry = {
                "nume": nume,
                "pret_eur": w["pret_val"],
                "qty": 1,
                "tip": "manere",
                "furnizor": furnizor,
            }
            tip_b = _maner_broasca_tip_stoc_manere_fields(c, m, dd)
            self._cos_append_maner_cu_broasca_optional(entry, tip_b)
            return

        nume = f"[{furnizor}] {w['colectie'].get()} {w['model'].get()} ({dec_display})"
        entry = {"nume": nume, "pret_eur": w["pret_val"], "qty": 1, "tip": tip}
        self.cos_cumparaturi.append(entry)
        self.refresh_cos()

    def adauga_parchet_in_cos(self, titlu):
        w = self.config_widgets[titlu]
        suprafata_str = (w["entry_suprafata"].get() or "").strip().replace(",", ".")
        try:
            suprafata = float(suprafata_str)
        except (ValueError, TypeError):
            self.afiseaza_mesaj("Atenție", "Introdu suprafața în mp (ex: 25.5).", "#7a1a1a")
            return
        if suprafata <= 0:
            self.afiseaza_mesaj("Atenție", "Suprafața trebuie să fie mai mare decât 0.", "#7a1a1a")
            return
        mp_per_cut = w.get("mp_per_cut") or 0
        if mp_per_cut <= 0:
            self.afiseaza_mesaj("Atenție", "Selectează un produs cu MP/cut valid.", "#7a1a1a")
            return
        pret_per_mp = w.get("pret_val") or 0
        nr_cutii = math.ceil(suprafata / mp_per_cut)
        total_mp = nr_cutii * mp_per_cut
        pret_total_eur = total_mp * pret_per_mp
        col = w["colectie"].get()
        cod = w["model"].get()
        nume = f"{titlu} - Colectia {col} - Cod Produs {cod}"
        self.cos_cumparaturi.append({
            "nume": nume,
            "pret_eur": round(pret_total_eur, 2),
            "qty": 1,
            "tip": "parchet",
            "suprafata_mp": round(total_mp, 2),
            "nr_cutii": nr_cutii,
            "pret_per_mp": round(pret_per_mp, 2),
        })
        w["entry_suprafata"].delete(0, "end")
        self.refresh_cos()

    def _get_discount_proc(self) -> int:
        """
        Parsează valoarea din caseta de discount în procente (integer).
        - dacă scrii `50` => 50%
        - dacă inputul e gol/invalid => 0
        """
        raw = ""
        try:
            raw = self.combo_discount.get()
        except Exception:
            pass
        if raw is None:
            raw = ""
        s = str(raw).strip()
        if not s:
            return 0
        s = s.replace("%", "").strip()
        s = s.replace(",", ".")
        # Extrage primul număr (permite și "50%" / " 50 " / "50,0")
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        if not m:
            return 0
        try:
            val = float(m.group(0))
        except (ValueError, TypeError):
            return 0
        if math.isnan(val) or math.isinf(val):
            return 0
        val = max(0.0, val)
        # Pentru input manual acceptăm direct procentul tastat (ex: 50 => 50%).
        # Păstrăm totuși o limită de siguranță.
        val = min(100.0, val)
        parsed = int(val)
        return parsed

    def _is_item_fara_discount(self, item: dict) -> bool:
        """
        Returnează True doar pentru serviciile suplimentare din lista fixă.
        Astfel discountul se aplică pe toate produsele (Stoc/Erkado, uși/tocuri/mânere etc.),
        cu excepția serviciilor explicite de redimensionare/scurtare.
        """
        nume_norm = (item.get("nume") or "").strip().casefold()
        return nume_norm in _SERVICII_FARA_DISCOUNT

    def _schedule_discount_refresh(self, readonly: bool):
        """Debounce pentru recalcularea totalurilor la schimbarea discountului."""
        if readonly:
            return
        try:
            if self._after_id_discount_refresh is not None:
                self.after_cancel(self._after_id_discount_refresh)
        except Exception:
            pass
        self._after_id_discount_refresh = self.after(200, lambda: self.refresh_cos(readonly))

    def _on_discount_choice(self, readonly: bool):
        """Recalculează imediat la alegerea din dropdown, ca înainte."""
        if readonly:
            return
        # Ignorăm 1-2 scrieri care vin din actualizarea variabilei de text.
        self._discount_ignore_trace_writes = 2
        try:
            if self._after_id_discount_refresh is not None:
                self.after_cancel(self._after_id_discount_refresh)
        except Exception:
            pass
        self.refresh_cos(readonly)

    def _on_discount_var_write(self, readonly: bool):
        """Debounce doar pentru tastare manuală."""
        if readonly:
            return
        if self._discount_ignore_trace_writes > 0:
            self._discount_ignore_trace_writes -= 1
            return
        self._schedule_discount_refresh(readonly)

    def _on_discount_keyrelease(self, _event, readonly: bool):
        """Fallback sigur: unele versiuni CTk nu propagă mereu StringVar la tastare."""
        self._schedule_discount_refresh(readonly)

    def _normalize_discount_input(self, _event, readonly: bool):
        """La Enter/FocusOut normalizăm vizual valoarea în procente întregi."""
        if readonly:
            return
        disc = self._get_discount_proc()
        try:
            self._discount_ignore_trace_writes = 2
            self.combo_discount.set(str(disc))
        except Exception:
            pass
        self.refresh_cos(readonly)

    def _goleste_cos_oferta(self, readonly: bool) -> None:
        if readonly:
            return
        self.cos_cumparaturi.clear()
        self._last_saved_offer_id = None
        self.refresh_cos(readonly)

    def refresh_cos(self, readonly=False):
        for w in self.scroll_cos.winfo_children():
            w.destroy()
        total_eur = 0
        total_eur_fara_discount = 0.0  # servicii suplimentare
        total_eur_cu_discount = 0.0
        disc_global = self._get_discount_proc()
        sum_eng_baza = 0.0
        sum_eng_disc = 0.0
        for i, item in enumerate(self.cos_cumparaturi):
            val = float(item.get("pret_eur") or 0) * item.get("qty", 1)
            total_eur += val
            item_fara_discount = self._is_item_fara_discount(item)
            if item_fara_discount:
                total_eur_fara_discount += val
            else:
                total_eur_cu_discount += val
            is_dubla = item.get("dubla") in ("usa", "toc")
            row_accent = self._cos_row_accent_for_item(item)
            f_main = ctk.CTkFrame(self.scroll_cos, **self._cos_row_frame_kwargs(row_accent))
            f_main.pack(fill="x", pady=5, padx=2)
            f_controls = ctk.CTkFrame(f_main, fg_color="transparent")
            f_controls.pack(fill="x", padx=8, pady=(8, 6))
            # Calcul preț per linie (EUR și LEI cu TVA) pentru afișare
            pret_eur = float(item.get("pret_eur") or 0)
            qty = int(item.get("qty") or 1)
            # Nu aplicăm discount doar serviciilor suplimentare din lista fixă.
            disc_linie = 0 if item_fara_discount else disc_global
            fac_disc = discount_price_factor(disc_linie)
            if item.get("tip") == "manere_engs":
                pl = float(item.get("pret_lei_cu_tva") or 0)
                pret_total_lei_cu_tva = pl * qty * fac_disc
                sum_eng_baza += pl * qty
                sum_eng_disc += pret_total_lei_cu_tva
                pret_eur = 0.0
                pret_total_eur = 0.0
            else:
                pret_total_eur = pret_eur * qty
                pret_total_lei_cu_tva = (
                    pret_total_eur * fac_disc * (1 + self.tva_procent / 100)
                ) * self.curs_euro

            if not readonly:
                ctk.CTkButton(
                    f_controls,
                    text="-",
                    width=25,
                    height=25,
                    fg_color="#7a1a1a",
                    command=lambda idx=i: self.update_qty(idx, -1),
                ).pack(side="left", padx=4)
                qty_text = f"{item['qty']} buc" if item.get("tip") != "parchet" else "1"
                ctk.CTkLabel(
                    f_controls,
                    text=qty_text,
                    font=("Segoe UI", 12),
                    width=45,
                    fg_color="#3A3A3A",
                    corner_radius=4,
                ).pack(side="left", padx=4)
                ctk.CTkButton(
                    f_controls,
                    text="+",
                    width=25,
                    height=25,
                    fg_color="#7a1a1a",
                    command=lambda idx=i: self.update_qty(idx, 1),
                ).pack(side="left", padx=4)
                # Buton transformare: simplu ↔ dublă/dublu + Kit Glisare Simplu / Toc Tunel
                tip_item = item.get("tip")
                if tip_item in ("usi", "tocuri"):
                    btn_neutral = "#2563eb"
                    btn_green_on = "#2E7D32"
                    btn_blue_on = "#3b82f6"
                    btn_yellow_on = "#ca8a04"
                    if item.get("dubla"):
                        btn_text = "Simplă" if tip_item == "usi" else "Simplu"
                        ctk.CTkButton(
                            f_controls,
                            text=btn_text,
                            width=70,
                            height=25,
                            fg_color=btn_blue_on,
                            command=lambda idx=i: self.transforma_in_simpla(idx),
                        ).pack(side="left", padx=4)
                    else:
                        btn_dubla_text = "→ Dublu" if tip_item == "tocuri" else "→ Dublă"
                        ctk.CTkButton(
                            f_controls,
                            text=btn_dubla_text,
                            width=70,
                            height=25,
                            fg_color=btn_neutral,
                            command=lambda idx=i: self.transforma_in_dubla(idx),
                        ).pack(side="left", padx=4)
                    if tip_item == "usi":
                        if self._is_stoc_usa_pt_debara(item):
                            debara_on = bool(item.get("debara"))
                            ctk.CTkButton(
                                f_controls,
                                text="DEBARA",
                                width=88,
                                height=25,
                                fg_color=btn_green_on if debara_on else btn_neutral,
                                command=lambda idx=i: self._toggle_debara_usa(idx),
                            ).pack(side="left", padx=4)
                        ctk.CTkButton(
                            f_controls,
                            text="Kit Glisare Simplu",
                            width=120,
                            height=25,
                            fg_color=btn_yellow_on if item.get("glisare_activ") else btn_neutral,
                            command=lambda idx=i: self._on_kit_glisare_simplu(idx),
                        ).pack(side="left", padx=4)
                        if item.get("glisare_activ"):
                            mod_glis = item.get("glisare_mod") or "fara"
                            ctk.CTkButton(
                                f_controls,
                                text="Fără închidere",
                                width=120,
                                height=25,
                                fg_color=btn_yellow_on if mod_glis == "fara" else btn_neutral,
                                command=lambda idx=i: self._set_glisare_mod(idx, "fara"),
                            ).pack(side="left", padx=4)
                            ctk.CTkButton(
                                f_controls,
                                text="Cu închidere",
                                width=120,
                                height=25,
                                fg_color=btn_yellow_on if mod_glis == "cu" else btn_neutral,
                                command=lambda idx=i: self._set_glisare_mod(idx, "cu"),
                            ).pack(side="left", padx=4)
                    elif tip_item == "tocuri":
                        furnizor_toc = self._get_furnizor_from_item(item)
                        if self._has_usa_cu_kit_glisare():
                            este_tunel = bool(item.get("toc_tunel"))
                            ctk.CTkButton(
                                f_controls,
                                text="Toc tunel",
                                width=100,
                                height=25,
                                fg_color=btn_yellow_on if este_tunel else btn_neutral,
                                command=lambda idx=i, activ=not este_tunel: self._set_toc_tunel(idx, activ),
                            ).pack(side="left", padx=4)
                        if furnizor_toc == "Stoc" and not item.get("dubla"):
                            dt_on = bool(item.get("debara_toc"))
                            ctk.CTkButton(
                                f_controls,
                                text="DEBARA",
                                width=88,
                                height=25,
                                fg_color=btn_green_on if dt_on else btn_neutral,
                                command=lambda idx=i: self._toggle_debara_toc(idx),
                            ).pack(side="left", padx=4)
                # Pe rândul suplimentar "Kit Glisare Simplu Peste Perete" afișăm SP1NZ/SP1Z (Erkado/nu) și SP1B
                if not readonly and (item.get("nume") or "").strip() == "Kit Glisare Simplu Peste Perete":
                    has_erkado_usi = self._has_erkado_usi()
                    sp1z_label = "SP1NZ (cu frezare locas broasca carlig)" if has_erkado_usi else "SP1Z (cu frezare locas broasca carlig)"
                    opt_sp1z = "SP1NZ" if has_erkado_usi else "SP1Z"
                    selected_sp1z = item.get("kit_glisare_option") == opt_sp1z
                    selected_sp1b = item.get("kit_glisare_option") == "SP1B"
                    btn_yellow_kit = "#ca8a04"
                    btn_kit_off = "#3A3A3A"
                    ctk.CTkButton(
                        f_controls,
                        text=sp1z_label,
                        width=220,
                        height=25,
                        fg_color=btn_yellow_kit if selected_sp1z else btn_kit_off,
                        command=lambda idx=i: self._on_sp1z(idx),
                    ).pack(side="left", padx=4)
                    ctk.CTkButton(
                        f_controls,
                        text="SP1B (fara frezare)",
                        width=140,
                        height=25,
                        fg_color=btn_yellow_kit if selected_sp1b else btn_kit_off,
                        command=lambda idx=i: self._on_sp1b(idx),
                    ).pack(side="left", padx=4)
                # Buton ștergere (dreapta sus)
                ctk.CTkButton(
                    f_controls,
                    text="X",
                    width=25,
                    height=25,
                    fg_color="#7a1a1a",
                    command=lambda idx=i: self._remove_cos_item(idx),
                ).pack(side="right", padx=4)
                # Etichetă preț pe linie în dreapta (LEI cu TVA)
                ctk.CTkLabel(
                    f_controls,
                    text=f"{pret_total_lei_cu_tva:.2f} LEI (TVA inclus)",
                    font=("Segoe UI", 12),
                    text_color="#facc15",
                ).pack(side="right", padx=8)
            else:
                ctk.CTkLabel(f_controls, text=f"Cantitate: {item['qty']} buc", font=("Segoe UI", 12)).pack(
                    side="left", padx=5
                )
            text_color = self._cos_row_title_text_color(row_accent)
            if text_color is None and is_dubla:
                text_color = "#93c5fd"
            extra_nume = (item.get("nume_adaugire_pdf") or "").strip()
            nume_afis = item["nume"] if not extra_nume else f"{item['nume']} {extra_nume}"
            nume_afis = format_nume_maner_afisare(item, nume_afis)
            nume_afis = apply_majuscule_line_stoc_erkado(item, nume_afis)
            ctk.CTkLabel(
                f_main,
                text=nume_afis,
                font=("Segoe UI", 13, "bold"),
                wraplength=400,
                justify="left",
                anchor="w",
                text_color=text_color,
            ).pack(fill="x", padx=10, pady=(2, 2))
            if is_dubla:
                eticheta_dubla = "Usa dubla" if item.get("dubla") == "usa" else "Toc dublu"
                eticheta_dubla = apply_majuscule_line_stoc_erkado(item, eticheta_dubla)
                ctk.CTkLabel(
                    f_main,
                    text=eticheta_dubla,
                    font=("Segoe UI", 11),
                    text_color="#93c5fd",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 4))
            if item.get("debara"):
                ctk.CTkLabel(
                    f_main,
                    text="Usa DEBARA",
                    font=("Segoe UI", 11),
                    text_color="#86efac",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 4))
            if item.get("debara_toc"):
                ctk.CTkLabel(
                    f_main,
                    text="Toc DEBARA",
                    font=("Segoe UI", 11),
                    text_color="#86efac",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 4))
            if item.get("tip") == "usi" and item.get("glisare_activ"):
                ctk.CTkLabel(
                    f_main,
                    text="Usa glisanta",
                    font=("Segoe UI", 11),
                    text_color="#fde047",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 4))
            if item.get("tip") == "tocuri" and item.get("toc_tunel"):
                ctk.CTkLabel(
                    f_main,
                    text="Toc tunel (marcaj vizual)",
                    font=("Segoe UI", 11),
                    text_color="#fde047",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 4))
            nume_kit_row = (item.get("nume") or "").strip()
            if nume_kit_row == "Sistem Glisare + Masca":
                ctk.CTkLabel(
                    f_main,
                    text="Kit glisare + masca",
                    font=("Segoe UI", 11),
                    text_color="#fde047",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 4))
            elif nume_kit_row == "Kit Glisare Simplu Peste Perete":
                ctk.CTkLabel(
                    f_main,
                    text="Kit glisare simplu peste perete",
                    font=("Segoe UI", 11),
                    text_color="#fde047",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 4))
            if item.get("tip") == "parchet" and "suprafata_mp" in item:
                disc = self._get_discount_proc()
                pret_eur = item.get("pret_eur") or 0
                pret_per_mp = item.get("pret_per_mp") or 0
                pret_lei = (
                    pret_eur * discount_price_factor(disc) * (1 + self.tva_procent / 100)
                ) * self.curs_euro
                pret_mp_afis = f"{pret_per_mp:.2f} €" if pret_per_mp else "— €"
                total_eur_afis = f"{pret_eur:.2f} €" if pret_eur else "— €"
                linie = (
                    f"Suprafață acoperită: {item['suprafata_mp']} mp  |  Nr. cutii: {item['nr_cutii']}  |  "
                    f"Preț/mp: {pret_mp_afis}  |  Total: {total_eur_afis} ({pret_lei:.2f} LEI)"
                )
                ctk.CTkLabel(
                    f_main, text=linie, font=("Segoe UI", 11), text_color="#aaaaaa", wraplength=500, anchor="w"
                ).pack(fill="x", padx=10, pady=(0, 8))
        self._refresh_rezumat_parchet()
        disc = disc_global
        # Discount se aplică doar pe produse; serviciile suplimentare (fara_discount) nu se reduc
        # Mânere Enger: prețuri deja în LEI cu TVA — fără curs și fără adaos TVA.
        total_fara_disc_lei = round(
            (total_eur * (1 + self.tva_procent / 100)) * self.curs_euro + sum_eng_baza,
            2,
        )
        lei_cu_disc = round(
            (
                total_eur_cu_discount * discount_price_factor(disc) * (1 + self.tva_procent / 100)
            )
            * self.curs_euro
            + sum_eng_disc,
            2,
        )
        lei_fara_disc_servicii = round((total_eur_fara_discount * (1 + self.tva_procent / 100)) * self.curs_euro, 2)

        # Servicii suplimentare în LEI (TVA deja inclus): NU se adaugă în suma totală de pe PDF,
        # doar le memorăm separat pentru afișare ulterioară ca servicii suplimentare.
        extra_servicii_lei = float(getattr(self, "masuratori_lei", 0.0) or 0) + float(
            getattr(self, "transport_lei", 0.0) or 0
        )

        self.ultima_valoare_lei = round(lei_cu_disc + lei_fara_disc_servicii, 2)
        discount_ron = round(total_fara_disc_lei - self.ultima_valoare_lei, 2)
        avans_40 = round(self.ultima_valoare_lei * 0.40, 2)
        if getattr(self, "lbl_cos_header_totals", None) and self.lbl_cos_header_totals.winfo_exists():
            total_ron_lista_header = round(
                (total_eur * (1 + self.tva_procent / 100)) * self.curs_euro, 2
            )
            self.lbl_cos_header_totals.configure(
                text=(
                    f"Total EUR: {total_eur:.2f} | Total RON (TVA): {total_ron_lista_header:.2f}"
                )
            )
        tva_i = int(round(float(self.tva_procent)))
        if getattr(self, "lbl_valoare_totala", None) and self.lbl_valoare_totala.winfo_exists():
            self.lbl_valoare_totala.configure(
                text=f"Total Listă (TVA {tva_i}%): {total_fara_disc_lei:.2f} RON"
            )
            self.lbl_discount_aplicat.configure(text=f"Valoare Discount (LEI): {discount_ron:.2f} RON")
            self.lbl_total_cu_discount.configure(text=f"Total Ofertat (LEI): {self.ultima_valoare_lei:.2f} RON")
            self.lbl_avans.configure(text=f"AVANS (40% din valoarea comenzii): {avans_40:.2f} RON")

    def _refresh_rezumat_parchet(self):
        if not getattr(self, "frame_rezumat_parchet", None) or not self.frame_rezumat_parchet.winfo_exists():
            return
        for w in self.frame_rezumat_parchet.winfo_children():
            w.destroy()
        self._rezumat_oferta_entry_vars = []
        if not self.cos_cumparaturi:
            ctk.CTkLabel(
                self.frame_rezumat_parchet,
                text="Nu există poziții în ofertă.",
                font=("Segoe UI", 12),
                text_color="#888888",
                wraplength=600,
            ).pack(pady=30, padx=20)
            return

        ctk.CTkLabel(
            self.frame_rezumat_parchet,
            text="Poți completa cod scurt doar pentru pozițiile de tip ușă/toc. Apoi apasă ✓.",
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=8, pady=(0, 8))

        for idx, item in enumerate(self.cos_cumparaturi):
            is_dubla = item.get("dubla") in ("usa", "toc")
            f_row = ctk.CTkFrame(
                self.frame_rezumat_parchet,
                fg_color="#1e3a5f" if is_dubla else "#2D2D2D",
                corner_radius=4,
            )
            f_row.pack(fill="x", pady=5, padx=2)
            f_controls = ctk.CTkFrame(f_row, fg_color="transparent")
            f_controls.pack(fill="x", padx=8, pady=(8, 5))
            tip_item = self._get_item_tip(item)
            tip_label = "Ușă" if tip_item == "usi" else ("Toc" if tip_item == "tocuri" else "Alt produs")
            ctk.CTkLabel(
                f_controls,
                text=f"#{idx + 1} | {tip_label} | Cantitate: {item.get('qty', 1)} buc",
                font=("Segoe UI", 12),
            ).pack(side="left", padx=4)
            ctk.CTkLabel(
                f_controls,
                text="Editabil" if tip_item in ("usi", "tocuri") else "Needitabil",
                font=("Segoe UI", 10),
                text_color="#2E7D32" if tip_item in ("usi", "tocuri") else "#888888",
            ).pack(side="right", padx=6)
            ctk.CTkLabel(
                f_row,
                text=format_nume_maner_afisare(item, item.get("nume") or ""),
                font=("Segoe UI", 12),
                anchor="w",
                wraplength=700,
                justify="left",
            ).pack(fill="x", padx=10, pady=(0, 4))
            if tip_item in ("usi", "tocuri"):
                f_edit = ctk.CTkFrame(f_row, fg_color="transparent")
                f_edit.pack(fill="x", padx=10, pady=(0, 8))
                var = ctk.StringVar(value=(item.get("nume_adaugire_pdf") or "").strip())
                ctk.CTkLabel(
                    f_edit,
                    text="Adăugire denumire:",
                    font=("Segoe UI", 11),
                    text_color="#aaaaaa",
                    width=130,
                    anchor="w",
                ).pack(side="left")
                entry = ctk.CTkEntry(f_edit, width=220, textvariable=var, placeholder_text="ex: 80DR / 90ST")
                entry.pack(side="left")
                self._rezumat_oferta_entry_vars.append((idx, var))
            else:
                ctk.CTkLabel(
                    f_row,
                    text="Poziție fără editare denumire.",
                    font=("Segoe UI", 10),
                    text_color="#888888",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 8))

        f_actions = ctk.CTkFrame(self.frame_rezumat_parchet, fg_color="transparent")
        f_actions.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(
            f_actions,
            text="În PDF, adăugirile apar doar când este bifat «Condiții».",
            font=("Segoe UI", 10),
            text_color="#F57C00",
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            f_actions,
            text="Apasă ✓ ca să aplici redenumirea în ofertă.",
            font=("Segoe UI", 10),
            text_color="#aaaaaa",
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            f_actions,
            text="✓ Aplică adăugirile",
            width=180,
            height=32,
            fg_color="#2E7D32",
            command=self._aplica_adaugiri_rezumat_oferta,
        ).pack(side="right", padx=4)

    def _aplica_adaugiri_rezumat_oferta(self):
        if not getattr(self, "_rezumat_oferta_entry_vars", None):
            return
        for idx, var in self._rezumat_oferta_entry_vars:
            if idx < 0 or idx >= len(self.cos_cumparaturi):
                continue
            item = self.cos_cumparaturi[idx]
            if self._get_item_tip(item) not in ("usi", "tocuri"):
                continue
            extra = (var.get() or "").strip()
            if len(extra) > 30:
                extra = extra[:30]
            item["nume_adaugire_pdf"] = extra
        self.refresh_cos(getattr(self, "_win_oferta_readonly", False))
        self.afiseaza_mesaj("Succes", "Redenumirile au fost aplicate în ofertă.", "#2E7D32")

    def update_qty(self, idx, delta):
        item = self.cos_cumparaturi[idx]
        qty_after = item["qty"] + delta
        if qty_after <= 0:
            self._remove_cos_item(idx)
            return
        self.cos_cumparaturi[idx]["qty"] += delta
        self.refresh_cos()

    def deschide_istoric(self):
        # Cortină full-screen pe root; Toplevel rămâne pentru conținut (viitor: același container, fără recreare).
        self._iron_curtain_show()
        self._main_transition_active = True
        self.win_istoric = ctk.CTkToplevel(self)
        self.win_istoric.withdraw()
        self.win_istoric.title("Istoric")
        _apply_secondary_toplevel_window_bg(self.win_istoric)
        _apply_fullscreen_workspace(self.win_istoric)
        _body_istoric = _pack_secondary_window_fill_panel(self.win_istoric)

        nav_i = ctk.CTkFrame(
            _body_istoric,
            fg_color=CORP_WINDOW_BG,
            border_width=0,
            corner_radius=0,
        )
        _polish_secondary_frame_surface(nav_i, CORP_WINDOW_BG, border_width=0)
        try:
            tk.Frame.configure(nav_i, bg=CORP_WINDOW_BG, highlightthickness=0)
        except Exception:
            pass
        nav_i.pack(fill="x", padx=20, pady=(10, 4))
        ctk.CTkButton(
            nav_i,
            text="← Înapoi la ecran principal",
            width=260,
            height=32,
            fg_color="#3A3A3A",
            hover_color="#454545",
            font=("Segoe UI", 12),
            command=lambda: self._inchide_fereastra_secundara("win_istoric"),
        ).pack(side="left")

        search_f = ctk.CTkFrame(
            _body_istoric,
            fg_color="#2b2b2b",
            border_width=0,
            corner_radius=0,
        )
        _polish_secondary_frame_surface(search_f, "#2b2b2b", border_width=0)
        try:
            tk.Frame.configure(search_f, bg="#2b2b2b", highlightthickness=0)
        except Exception:
            pass
        search_f.pack(fill="x", padx=20, pady=5)
        self.ent_cauta_istoric = ctk.CTkEntry(
            search_f, placeholder_text="Caută după nume client...", height=40
        )
        self.ent_cauta_istoric.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        self.ent_cauta_istoric.bind("<KeyRelease>", self._on_keyrelease_cauta_istoric)
        filters_f = ctk.CTkFrame(
            _body_istoric,
            fg_color="#2D2D2D",
            border_width=1,
            border_color="#333333",
            corner_radius=4,
        )
        _polish_secondary_frame_surface(filters_f, "#2D2D2D", border_width=1)
        try:
            tk.Frame.configure(filters_f, bg="#2D2D2D", highlightthickness=0)
        except Exception:
            pass
        filters_f.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(filters_f, text="Filtre:", text_color="#aaaaaa").pack(side="left", padx=(10, 8), pady=10)

        self._istoric_user_map = {"Toți": ""}
        self.opt_user_istoric = ctk.CTkOptionMenu(
            filters_f,
            width=220,
            values=["Toți"],
            command=lambda _value: self.refresh_lista_istoric(),
        )
        self.opt_user_istoric.set("Toți")
        self.opt_user_istoric.pack(side="left", padx=(0, 10), pady=10)
        self._istoric_user_map_fetch_seq += 1
        _um_req = self._istoric_user_map_fetch_seq
        threading.Thread(target=self._istoric_user_map_worker, args=(_um_req,), daemon=True).start()

        self.ent_data_start_istoric = ctk.CTkEntry(filters_f, width=130, placeholder_text="De la (dd.mm.yyyy)")
        self.ent_data_start_istoric.pack(side="left", padx=(0, 6), pady=10)
        self.ent_data_end_istoric = ctk.CTkEntry(filters_f, width=130, placeholder_text="Până la (dd.mm.yyyy)")
        self.ent_data_end_istoric.pack(side="left", padx=(0, 10), pady=10)
        self.ent_data_start_istoric.bind("<KeyRelease>", self._on_keyrelease_cauta_istoric)
        self.ent_data_end_istoric.bind("<KeyRelease>", self._on_keyrelease_cauta_istoric)
        ctk.CTkButton(
            filters_f,
            text="FILTREAZĂ",
            width=110,
            fg_color=GREEN_SOFT,
            hover_color=GREEN_SOFT_DARK,
            command=self.refresh_lista_istoric,
        ).pack(side="left", padx=(0, 10), pady=10)

        ctk.CTkButton(
            filters_f,
            text="Ultimele 7 zile",
            width=120,
            fg_color="#3A3A3A",
            command=self._set_istoric_date_range_last_7_days,
        ).pack(side="left", padx=(0, 6), pady=10)
        ctk.CTkButton(
            filters_f,
            text="Luna curentă",
            width=120,
            fg_color="#3A3A3A",
            command=self._set_istoric_date_range_current_month,
        ).pack(side="left", padx=(0, 6), pady=10)
        ctk.CTkButton(
            filters_f,
            text="Resetează",
            width=100,
            fg_color="#2E7D32",
            command=self._reset_istoric_filters,
        ).pack(side="left", padx=(0, 10), pady=10)
        try:
            self.win_istoric.update_idletasks()
        except Exception:
            pass

        self.scroll_istoric = ctk.CTkFrame(
            _body_istoric,
            fg_color=CORP_WINDOW_BG,
            border_width=0,
            corner_radius=0,
        )
        _polish_secondary_frame_surface(self.scroll_istoric, CORP_WINDOW_BG, border_width=0)
        try:
            tk.Frame.configure(self.scroll_istoric, bg=CORP_WINDOW_BG, highlightthickness=0)
        except Exception:
            pass
        self.scroll_istoric.pack(fill="both", expand=True, padx=20, pady=10)
        self._istoric_row_pool = None
        self._istoric_empty_placeholder = None
        ctk.CTkLabel(
            self.scroll_istoric,
            text="Selectați un rând (dublu-click = Deschide), apoi folosiți butoanele de jos.",
            text_color="#aaaaaa",
            font=("Segoe UI", 12),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 6))
        _hdr_i = ctk.CTkFrame(
            self.scroll_istoric,
            fg_color="#2D2D2D",
            height=38,
            corner_radius=4,
            border_width=0,
        )
        _polish_secondary_frame_surface(_hdr_i, "#2D2D2D", border_width=0)
        _hdr_i.pack(fill="x", padx=4, pady=(0, 4))
        _hdr_i.pack_propagate(False)
        for text, rel_x, anchor in (
            ("Client", 0.02, "w"),
            ("Data", 0.28, "w"),
            ("Consultant", 0.46, "w"),
            ("Nr. înreg.", 0.62, "w"),
            ("Total", 0.72, "w"),
            ("Status", 0.98, "e"),
        ):
            ctk.CTkLabel(_hdr_i, text=text, font=("Segoe UI", 12), text_color="#2E7D32").place(
                relx=rel_x, rely=0.5, anchor=anchor
            )
        self._istoric_list_scroll = ctk.CTkScrollableFrame(
            self.scroll_istoric,
            fg_color=CORP_WINDOW_BG,
            border_width=0,
            corner_radius=0,
        )
        _polish_secondary_frame_surface(self._istoric_list_scroll, CORP_WINDOW_BG, border_width=0)
        self._istoric_list_scroll.pack(fill="both", expand=True, padx=4, pady=0)
        _patch_scrollable_frame_canvas(self._istoric_list_scroll, CORP_WINDOW_BG)
        try:
            self.win_istoric.update_idletasks()
        except Exception:
            pass
        _can_del = self._privileges[2] if self._privileges else 1
        _actions_i = ctk.CTkFrame(
            self.scroll_istoric,
            fg_color="#2D2D2D",
            border_width=1,
            border_color="#333333",
            corner_radius=4,
        )
        _polish_secondary_frame_surface(_actions_i, "#2D2D2D", border_width=1)
        try:
            tk.Frame.configure(_actions_i, bg="#2D2D2D", highlightthickness=0)
        except Exception:
            pass
        _actions_i.pack(fill="x", pady=(8, 0), padx=5)
        self._istoric_btn_open = ctk.CTkButton(
            _actions_i, text="DESCHIDE", width=100, command=self._istoric_action_deschide
        )
        self._istoric_btn_open.pack(side="left", padx=6, pady=8)
        self._istoric_btn_modifica = ctk.CTkButton(
            _actions_i,
            text="MODIFICĂ OFERTA",
            width=140,
            fg_color="#1565C0",
            hover_color="#0D47A1",
            command=self._istoric_action_modifica,
        )
        self._istoric_btn_modifica.pack(side="left", padx=6, pady=8)
        self._istoric_btn_pdf = ctk.CTkButton(
            _actions_i,
            text="DESCARCĂ PDF",
            width=130,
            fg_color=AMBER_CORP,
            hover_color=AMBER_HOVER,
            command=self._istoric_action_pdf,
        )
        self._istoric_btn_pdf.pack(side="left", padx=6, pady=8)
        self._istoric_btn_avans = ctk.CTkButton(
            _actions_i, text="Avans încasat", width=140, command=self._istoric_action_avans
        )
        self._istoric_btn_avans.pack(side="left", padx=6, pady=8)
        self._istoric_btn_del = None
        if _can_del:
            self._istoric_btn_del = ctk.CTkButton(
                _actions_i,
                text="Șterge oferta",
                width=110,
                fg_color="#7a1a1a",
                command=self._istoric_action_sterge,
            )
            self._istoric_btn_del.pack(side="left", padx=6, pady=8)
        try:
            self.win_istoric.update_idletasks()
            self.win_istoric.update()
            time.sleep(0.01)
        except Exception:
            pass
        self.refresh_lista_istoric()

    def _build_istoric_user_map_from_cursor(self, cursor) -> dict[str, str]:
        out = {"Toți": ""}
        used = {"Toți"}
        try:
            for row in get_approved_users_with_privileges(cursor):
                nume_complet = (row[1] or "").strip() if len(row) > 1 else ""
                username = (row[2] or "").strip() if len(row) > 2 else ""
                if not username:
                    continue
                label = nume_complet or username
                if label in used:
                    label = f"{nume_complet or username} ({username})"
                used.add(label)
                out[label] = username
        except Exception:
            logger.exception("Nu am putut încărca lista de useri pentru filtre istoric")
        return out

    def _istoric_user_map_worker(self, req_id: int) -> None:
        out: dict[str, str] = {"Toți": ""}
        try:
            db = open_db(get_database_path())
            try:
                out = self._build_istoric_user_map_from_cursor(db.cursor)
            finally:
                try:
                    co = getattr(db, "conn", None)
                    fn = getattr(co, "close", None)
                    if callable(fn):
                        fn()
                except Exception:
                    pass
        except Exception:
            logger.exception("Nu am putut încărca lista de useri pentru filtre istoric (background)")
            out = {"Toți": ""}
        snapshot = dict(out)
        self.after(0, lambda rid=req_id, m=snapshot: self._apply_istoric_user_map_result(rid, m))

    def _apply_istoric_user_map_result(self, req_id: int, user_map: dict[str, str]) -> None:
        if req_id != getattr(self, "_istoric_user_map_fetch_seq", 0):
            return
        w = getattr(self, "win_istoric", None)
        if w is None:
            return
        try:
            if not w.winfo_exists():
                return
        except Exception:
            return
        self._istoric_user_map = user_map
        opt = getattr(self, "opt_user_istoric", None)
        if opt is None:
            return
        try:
            if not opt.winfo_exists():
                return
        except Exception:
            return
        keys = list(user_map.keys())
        cur = (opt.get() or "").strip()
        try:
            opt.configure(values=keys)
            if cur in user_map:
                opt.set(cur)
            else:
                opt.set("Toți")
        except Exception:
            pass

    def _get_istoric_user_map(self):
        return self._build_istoric_user_map_from_cursor(self.cursor)

    def _normalize_istoric_date_input(self, raw_value: str):
        text = (raw_value or "").strip()
        if not text:
            return None
        for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        return None

    def _set_istoric_date_range_last_7_days(self):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=6)
        self.ent_data_start_istoric.delete(0, "end")
        self.ent_data_start_istoric.insert(0, start_date.strftime("%d.%m.%Y"))
        self.ent_data_end_istoric.delete(0, "end")
        self.ent_data_end_istoric.insert(0, end_date.strftime("%d.%m.%Y"))
        self.refresh_lista_istoric()

    def _set_istoric_date_range_current_month(self):
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1).date()
        end_date = now.date()
        self.ent_data_start_istoric.delete(0, "end")
        self.ent_data_start_istoric.insert(0, start_date.strftime("%d.%m.%Y"))
        self.ent_data_end_istoric.delete(0, "end")
        self.ent_data_end_istoric.insert(0, end_date.strftime("%d.%m.%Y"))
        self.refresh_lista_istoric()

    def _reset_istoric_filters(self):
        self.ent_cauta_istoric.delete(0, "end")
        self.ent_data_start_istoric.delete(0, "end")
        self.ent_data_end_istoric.delete(0, "end")
        if getattr(self, "opt_user_istoric", None):
            self.opt_user_istoric.set("Toți")
        self.refresh_lista_istoric()

    def _on_keyrelease_cauta_istoric(self, event=None):
        """Debounce 250 ms pentru căutare istoric."""
        if self._after_id_istoric is not None:
            try:
                self.after_cancel(self._after_id_istoric)
            except Exception:
                pass
        self._after_id_istoric = self.after(250, self._do_refresh_lista_istoric)

    def _do_refresh_lista_istoric(self):
        self._after_id_istoric = None
        self.refresh_lista_istoric()

    def _istoric_hide_loading_skeleton(self, list_scroll) -> None:
        sk = getattr(self, "_istoric_skeleton", None)
        if sk is not None:
            try:
                if sk.winfo_exists():
                    sk.pack_forget()
            except Exception:
                pass

    def _istoric_show_loading_skeleton(self, list_scroll) -> None:
        """Ascunde rândurile din pool și afișează skeleton / mesaj de încărcare."""
        self._istoric_hide_empty_placeholder()
        pool = getattr(self, "_istoric_row_pool", None) or []
        for cell in pool:
            try:
                cell["frame"].pack_forget()
            except Exception:
                pass
        sk = getattr(self, "_istoric_skeleton", None)
        if sk is None or not sk.winfo_exists():
            sk = ctk.CTkFrame(
                list_scroll,
                fg_color=CORP_WINDOW_BG,
                border_width=0,
                corner_radius=0,
            )
            _polish_secondary_frame_surface(sk, CORP_WINDOW_BG, border_width=0)
            ctk.CTkLabel(
                sk,
                text="Se încarcă istoricul…",
                font=("Segoe UI", 12),
                text_color="#9E9E9E",
            ).pack(pady=(12, 8))
            for _ in range(5):
                bar = ctk.CTkFrame(sk, height=10, fg_color="#333333", corner_radius=3, border_width=0)
                _polish_secondary_frame_surface(bar, "#333333", border_width=0)
                bar.pack(fill="x", padx=20, pady=4)
            self._istoric_skeleton = sk
        sk.pack(fill="x", padx=12, pady=16)

    def _istoric_ensure_empty_placeholder(self, list_scroll) -> ctk.CTkLabel:
        ph = getattr(self, "_istoric_empty_placeholder", None)
        if ph is None or not ph.winfo_exists():
            ph = ctk.CTkLabel(
                list_scroll,
                text="",
                font=("Segoe UI", 12),
                text_color="#9E9E9E",
            )
            self._istoric_empty_placeholder = ph
        return ph

    def _istoric_hide_empty_placeholder(self) -> None:
        ph = getattr(self, "_istoric_empty_placeholder", None)
        if ph is not None:
            try:
                if ph.winfo_exists():
                    ph.pack_forget()
            except Exception:
                pass

    def _istoric_fetch_worker(
        self,
        req_id: int,
        term_like: str,
        id_egal: int | None,
        data_start: str | None,
        data_end: str | None,
        utilizator_filter: str | None,
    ) -> None:
        rows_out: list[dict[str, Any]] = []
        err_msg: str | None = None
        try:
            db = open_db(get_database_path())
            try:
                raw = get_istoric_oferte(
                    db.cursor,
                    term_like,
                    id_egal,
                    utilizator_creat=None,
                    utilizator_filter=utilizator_filter,
                    data_start=data_start,
                    data_end=data_end,
                )
                for t in raw:
                    rows_out.append(
                        {
                            "id": t[0],
                            "nume_client_temp": t[1],
                            "total_lei": t[2],
                            "data_oferta": t[3],
                            "detalii_oferta": t[4],
                            "avans_incasat": t[5],
                            "utilizator_creat": t[6],
                        }
                    )
            finally:
                try:
                    co = getattr(db, "conn", None)
                    fn = getattr(co, "close", None)
                    if callable(fn):
                        fn()
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("Istoric oferte (background)")
            err_msg = str(exc)
        snapshot = list(rows_out)
        self.after(
            0,
            lambda rid=req_id, data=snapshot, err=err_msg: self._apply_istoric_fetch_result(rid, data, err),
        )

    def _apply_istoric_fetch_result(
        self,
        req_id: int,
        rows_dicts: list[dict[str, Any]],
        err: str | None,
    ) -> None:
        if req_id != self._istoric_fetch_seq:
            return
        win_ist = getattr(self, "win_istoric", None)
        list_scroll = getattr(self, "_istoric_list_scroll", None)
        if list_scroll is None:
            self._schedule_transition_finish(win_ist)
            return
        try:
            if not list_scroll.winfo_exists():
                self._schedule_transition_finish(win_ist)
                return
        except Exception:
            self._schedule_transition_finish(win_ist)
            return
        self._istoric_hide_loading_skeleton(list_scroll)
        if err is not None:
            self._istoric_row_data = []
            self._istoric_selected_idx = None
            pool = getattr(self, "_istoric_row_pool", None) or []
            for cell in pool:
                try:
                    cell["frame"].pack_forget()
                except Exception:
                    pass
            self._istoric_row_frames = []
            ph = self._istoric_ensure_empty_placeholder(list_scroll)
            ph.configure(text=f"Eroare încărcare: {err[:400]}", text_color="#ff8888")
            ph.pack(anchor="w", padx=12, pady=16)
            try:
                list_scroll._parent_canvas.yview_moveto(0)
            except Exception:
                pass
            self._on_istoric_listbox_select()
            self._schedule_transition_finish(win_ist)
            return
        tuples = [
            (
                d["id"],
                d["nume_client_temp"],
                d["total_lei"],
                d["data_oferta"],
                d["detalii_oferta"],
                d["avans_incasat"],
                d["utilizator_creat"],
            )
            for d in rows_dicts
        ]
        self._render_istoric_list_rows(list_scroll, tuples)
        self._schedule_transition_finish(win_ist)

    def _render_istoric_list_rows(self, list_scroll, istoric_rows: list[tuple[Any, ...]]) -> None:
        """Desenează rândurile de istoric pe firul UI; pool + configure, fără destroy pe rânduri."""
        self._istoric_row_data = list(istoric_rows)
        self._istoric_selected_idx = None

        self._istoric_hide_empty_placeholder()

        pool = getattr(self, "_istoric_row_pool", None)
        if pool is None:
            self._istoric_row_pool = []
            pool = self._istoric_row_pool
        for cell in pool:
            try:
                cell["frame"].pack_forget()
            except Exception:
                pass

        _font_row = ("Segoe UI", 12)
        _font_name = ("Segoe UI", 12, "bold")
        _muted = "#9E9E9E"

        if not istoric_rows:
            ph = self._istoric_ensure_empty_placeholder(list_scroll)
            ph.configure(text="Nicio ofertă găsită pentru filtrele curente.", text_color=_muted)
            ph.pack(anchor="w", padx=12, pady=16)
            self._istoric_row_frames = []
            try:
                list_scroll._parent_canvas.yview_moveto(0)
            except Exception:
                pass
            self._on_istoric_listbox_select()
            return

        while len(pool) < len(istoric_rows):
            row_f = ctk.CTkFrame(
                list_scroll,
                height=44,
                fg_color=ROW_LIST_BG,
                corner_radius=4,
                border_width=0,
            )
            _polish_secondary_frame_surface(row_f, ROW_LIST_BG, border_width=0)
            row_f.pack_propagate(False)
            lbl_nume = ctk.CTkLabel(row_f, text="", font=_font_name, anchor="w")
            lbl_nume.place(relx=0.02, rely=0.5, anchor="w")
            lbl_data = ctk.CTkLabel(row_f, text="", font=_font_row, text_color=_muted, anchor="w")
            lbl_data.place(relx=0.28, rely=0.5, anchor="w")
            lbl_cons = ctk.CTkLabel(row_f, text="", font=_font_row, text_color=_muted, anchor="w")
            lbl_cons.place(relx=0.46, rely=0.5, anchor="w")
            lbl_nr = ctk.CTkLabel(row_f, text="", font=_font_row, text_color=_muted, anchor="w")
            lbl_nr.place(relx=0.62, rely=0.5, anchor="w")
            lbl_tot = ctk.CTkLabel(row_f, text="", font=_font_row, anchor="w")
            lbl_tot.place(relx=0.72, rely=0.5, anchor="w")
            lbl_st = ctk.CTkLabel(row_f, text="", font=_font_row, text_color=_muted, anchor="e")
            lbl_st.place(relx=0.98, rely=0.5, anchor="e")
            pool.append(
                {
                    "frame": row_f,
                    "lbl_nume": lbl_nume,
                    "lbl_data": lbl_data,
                    "lbl_cons": lbl_cons,
                    "lbl_nr": lbl_nr,
                    "lbl_tot": lbl_tot,
                    "lbl_st": lbl_st,
                }
            )

        self._istoric_row_frames = []
        for i, r in enumerate(istoric_rows):
            id_o, nume, total_lei, data, det_raw = r[0], r[1], r[2], r[3], r[4]
            avans = 1 if (len(r) > 5 and r[5]) else 0
            consultant_raw = (r[6] if len(r) > 6 else "") or ""
            try:
                c_disp = (
                    get_user_full_name(self.cursor, consultant_raw.strip())
                    if consultant_raw.strip()
                    else None
                )
            except Exception:
                c_disp = None
            consultant = (c_disp or consultant_raw or "-")[:18]
            nr_inreg = str(id_o).zfill(5)
            mod_m = get_offer_modificare_meta(det_raw or "")
            if mod_m:
                mu = (mod_m[0] or "").strip()
                try:
                    m_disp = get_user_full_name(self.cursor, mu) if mu else None
                except Exception:
                    m_disp = None
                who = (m_disp or mu)[:20]
                status_text = f"Modificat: {who}" + (" · Avans" if avans else "")
            else:
                status_text = "Parțial" if avans else "Aștept."
            ds = str(data)[:20]
            cc = str(consultant)[:18]
            nm = str(nume or "").upper()
            total_txt = f"{float(total_lei or 0):,.2f} LEI".replace(",", " ")

            cell = pool[i]
            row_f = cell["frame"]
            cell["lbl_nume"].configure(text=nm[:32])
            cell["lbl_data"].configure(text=ds)
            cell["lbl_cons"].configure(text=cc)
            cell["lbl_nr"].configure(text=f"#{nr_inreg}")
            cell["lbl_tot"].configure(text=total_txt)
            cell["lbl_st"].configure(text=status_text)
            row_f.configure(fg_color=ROW_LIST_BG)
            _apply_list_row_frame_native_bg(row_f, ROW_LIST_BG)
            row_f.pack(fill="x", pady=1)
            self._istoric_row_frames.append(row_f)

            def _bind_row_select(idx: int):
                def _select(_event=None):
                    self._istoric_set_selected_row(idx)

                def _double(_event=None):
                    self._istoric_set_selected_row(idx)
                    self._istoric_action_deschide()

                return _select, _double

            _sel, _dbl = _bind_row_select(i)
            for w in (
                row_f,
                cell["lbl_nume"],
                cell["lbl_data"],
                cell["lbl_cons"],
                cell["lbl_nr"],
                cell["lbl_tot"],
                cell["lbl_st"],
            ):
                w.bind("<Button-1>", _sel)
                w.bind("<Double-Button-1>", _dbl)

        try:
            list_scroll._parent_canvas.yview_moveto(0)
        except Exception:
            pass

        self._on_istoric_listbox_select()

    def refresh_lista_istoric(self):
        list_scroll = getattr(self, "_istoric_list_scroll", None)
        if list_scroll is None:
            return
        try:
            if not list_scroll.winfo_exists():
                return
        except Exception:
            return

        self._istoric_fetch_seq += 1
        req_id = self._istoric_fetch_seq

        termen_raw = self.ent_cauta_istoric.get().strip()
        id_egal = int(termen_raw) if termen_raw.isdigit() else None
        data_start = self._normalize_istoric_date_input(
            self.ent_data_start_istoric.get() if getattr(self, "ent_data_start_istoric", None) else ""
        )
        data_end = self._normalize_istoric_date_input(
            self.ent_data_end_istoric.get() if getattr(self, "ent_data_end_istoric", None) else ""
        )
        selected_user = None
        if getattr(self, "opt_user_istoric", None):
            selected_user = self._istoric_user_map.get((self.opt_user_istoric.get() or "").strip(), "")
        utilizator_filter = (selected_user or "").strip() or None
        term_like = f"%{termen_raw}%"

        self._istoric_show_loading_skeleton(list_scroll)
        threading.Thread(
            target=self._istoric_fetch_worker,
            args=(req_id, term_like, id_egal, data_start, data_end, utilizator_filter),
            daemon=True,
        ).start()

    def _istoric_set_selected_row(self, idx: int | None) -> None:
        self._istoric_selected_idx = idx
        frames = getattr(self, "_istoric_row_frames", None) or []
        for i, f in enumerate(frames):
            try:
                if f.winfo_exists():
                    bg = ROW_SELECTED_BG if (idx is not None and i == idx) else ROW_LIST_BG
                    f.configure(fg_color=bg)
                    _apply_list_row_frame_native_bg(f, bg)
            except Exception:
                pass
        self._on_istoric_listbox_select()

    def _istoric_current_row(self):
        idx = getattr(self, "_istoric_selected_idx", None)
        if idx is None:
            return None
        rows = getattr(self, "_istoric_row_data", None) or []
        if idx < 0 or idx >= len(rows):
            return None
        return rows[idx]

    def _on_istoric_listbox_select(self, event=None):
        r = self._istoric_current_row()
        st = "normal" if r else "disabled"
        for b in (self._istoric_btn_open, self._istoric_btn_modifica, self._istoric_btn_pdf, self._istoric_btn_avans):
            if b is not None:
                b.configure(state=st)
        if getattr(self, "_istoric_btn_del", None) is not None:
            self._istoric_btn_del.configure(state=st)
        if r:
            avans = 1 if (len(r) > 5 and r[5]) else 0
            self._istoric_btn_avans.configure(
                text="✓ Avans încasat" if avans else "Marchează avans încasat",
                fg_color="#2E7D32" if avans else "#3A3A3A",
            )

    def _istoric_action_deschide(self):
        row = self._istoric_current_row()
        if not row:
            self.afiseaza_mesaj("Atenție", "Selectați o ofertă din listă.", "#F57C00")
            return
        id_o, nume, _t, data, detalii = row[0], row[1], row[2], row[3], row[4]
        self.porneste_ofertarea(self._istoric_open_data_from_row(id_o, data, nume, detalii))

    def _istoric_action_modifica(self):
        row = self._istoric_current_row()
        if not row:
            self.afiseaza_mesaj("Atenție", "Selectați o ofertă din listă.", "#F57C00")
            return
        id_o, nume, _t, data, detalii = row[0], row[1], row[2], row[3], row[4]
        snap = get_offer_snapshot(self.cursor, int(id_o), force_refresh=True)
        if snap:
            cid = int(snap.get("id_client") or 0)
            if cid:
                cr = get_client_by_id(self.cursor, cid)
                if cr:
                    self.entry_nume.delete(0, "end")
                    self.entry_nume.insert(0, str(cr[0] or ""))
                    self.entry_tel.delete(0, "end")
                    self.entry_tel.insert(0, str(cr[1] or ""))
                    self.entry_adresa.delete(0, "end")
                    self.entry_adresa.insert(0, str(cr[2] or ""))
                    if getattr(self, "entry_email", None):
                        self.entry_email.delete(0, "end")
                        self.entry_email.insert(0, str(cr[3] or "") if len(cr) > 3 else "")
        self.porneste_ofertarea(self._istoric_open_data_from_row(id_o, data, nume, detalii), modifica=True)

    def _istoric_action_pdf(self):
        row = self._istoric_current_row()
        if not row:
            self.afiseaza_mesaj("Atenție", "Selectați o ofertă din listă.", "#F57C00")
            return
        id_o, nume, _t, data, detalii = row[0], row[1], row[2], row[3], row[4]
        self._download_pdf_from_istoric(self._istoric_open_data_from_row(id_o, data, nume, detalii))

    def _istoric_action_avans(self):
        row = self._istoric_current_row()
        if not row:
            return
        self._toggle_avans_incasat(int(row[0]))

    def _istoric_action_sterge(self):
        row = self._istoric_current_row()
        if not row:
            return
        self.solicita_parola_stergere(int(row[0]))

    def _istoric_open_data_from_row(self, id_o, data, nume, detalii):
        """Payload DESCHIDE/PDF: citește mereu ultima versiune din cloud (nu rândul din listă, care poate fi învechit)."""
        try:
            snap = get_offer_snapshot(self.cursor, int(id_o), force_refresh=True)
        except Exception:
            logger.exception("Reîncărcare ofertă din cloud (istoric)")
            snap = None
        if snap:
            live = str(snap.get("detalii_oferta") or "").strip()
            if live:
                detalii = live
            d_live = str(snap.get("data_oferta") or "").strip()
            if d_live:
                data = d_live
            n_live = str(snap.get("nume_client_temp") or "").strip()
            if n_live:
                nume = n_live
        produse_raw = loads_offer_items(detalii)
        payload = produse_raw if isinstance(produse_raw, dict) else {"items": produse_raw}
        return {"id_oferta": id_o, "data_oferta": data, "nume": nume, "produse": payload}

    def fetch_history(
        self,
        user_id: str | None = None,
        client_name: str = "",
        date_range: tuple[str | None, str | None] | None = None,
        id_egal: int | None = None,
    ):
        date_start, date_end = (date_range or (None, None))
        term_like = f"%{(client_name or '').strip()}%"
        return get_istoric_oferte(
            self.cursor,
            term_like,
            id_egal,
            utilizator_creat=None,
            utilizator_filter=user_id or None,
            data_start=date_start,
            data_end=date_end,
        )

    def _download_pdf_from_istoric(self, date_istoric: dict):
        # Refolosim fluxul existent de generare PDF încărcând oferta din istoric.
        self.porneste_ofertarea(date_istoric=date_istoric)
        nume_client = (date_istoric or {}).get("nume", "")
        self.after(80, lambda: self.genereaza_pdf(nume_client))

    def _toggle_avans_incasat(self, id_oferta):
        row = get_offer_by_id(self.cursor, id_oferta)
        if not row:
            return
        current = 1 if row[0] else 0
        new_val = 0 if current else 1
        update_avans(self.conn, self.cursor, id_oferta, new_val)
        self.refresh_lista_istoric()

    def solicita_parola_stergere(self, id_oferta):
        pw_win = ctk.CTkToplevel(self)
        pw_win.geometry("400x200")
        pw_win.grab_set()
        ctk.CTkLabel(pw_win, text="Parolă ștergere:").pack(pady=20)
        entry_pw = ctk.CTkEntry(pw_win, show="*")
        entry_pw.pack(pady=5)
        entry_pw.focus_set()

        def confirma():
            if entry_pw.get() == self.parola_admin:
                delete_offer(self.conn, self.cursor, id_oferta)
                pw_win.destroy()
                self.refresh_lista_istoric()
                self.afiseaza_mesaj("Succes", "Oferta a fost ștearsă!")
            else:
                self.afiseaza_mesaj("Eroare", "Parolă incorectă!", "#7a1a1a")

        ctk.CTkButton(pw_win, text="CONFIRMĂ", fg_color="#7a1a1a", command=confirma).pack(pady=20)

    def _dialog_replace_or_new_offer(self) -> str | None:
        """Returnează 'replace', 'new' sau None. Dialog dedicat (fără CTkMessagebox.get()) pentru răspuns sigur."""
        master = self
        try:
            if getattr(self, "win_oferta", None) and self.win_oferta.winfo_exists():
                master = self.win_oferta
        except Exception:
            pass
        last_id = getattr(self, "_last_saved_offer_id", None)
        nr = str(last_id).zfill(5) if last_id is not None else "?"
        result: list[str | None] = [None]

        dlg = ctk.CTkToplevel(master)
        dlg.title("Salvare ofertă")
        dlg.geometry("540x260")
        dlg.resizable(False, False)
        try:
            dlg.transient(master)
        except Exception:
            pass
        dlg.grab_set()
        try:
            dlg.attributes("-topmost", True)
        except Exception:
            pass

        def finish(val: str | None) -> None:
            result[0] = val
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        ctk.CTkLabel(
            dlg,
            text=(
                f"Oferta #{nr} este deja salvată în această sesiune.\n\n"
                "Alege cum continui:"
            ),
            font=("Segoe UI", 14, "bold"),
            justify="center",
        ).pack(pady=(28, 18), padx=24)

        f_btns = ctk.CTkFrame(dlg, fg_color="transparent")
        f_btns.pack(pady=(0, 12))
        ctk.CTkButton(
            f_btns,
            text=f"Înlocuiește oferta #{nr} (același număr)",
            width=240,
            height=36,
            font=("Segoe UI", 12, "bold"),
            fg_color="#2E7D32",
            hover_color="#256B29",
            command=lambda: finish("replace"),
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            f_btns,
            text="Creează comandă nouă",
            width=200,
            height=36,
            font=("Segoe UI", 12),
            fg_color=CORP_MATT_GREY,
            hover_color="#454545",
            command=lambda: finish("new"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            dlg,
            text="Anulează",
            width=120,
            fg_color="#3A3A3A",
            command=lambda: finish(None),
        ).pack(pady=(8, 22))

        dlg.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        master.wait_window(dlg)
        return result[0]

    def salveaza_oferta_finala(self, *, replace_offer_id: int | None = None, force_new_offer: bool = False, show_costs_dialog: bool = False):
        ok_br, _ = self._validare_broasca_manere()
        if not ok_br:
            self.show_success_toast(
                "Atentie! Lipseste Broasca WC/Cilindru pentru manerul selectat! ⚠️",
                "warning",
                duration_ms=4000,
            )
            return
        ok, mesaj = self._validare_oferta_usi_tocuri()
        if not ok:
            self.afiseaza_mesaj("Oferta nu poate fi salvată", mesaj, "#7a1a1a")
            return

        edit_id = getattr(self, "_edit_offer_id", None)
        if force_new_offer:
            self._offer_costs_entered = False
        if (
            not edit_id
            and not force_new_offer
            and replace_offer_id is None
            and getattr(self, "_last_saved_offer_id", None) is not None
        ):
            choice = self._dialog_replace_or_new_offer()
            if choice is None:
                return
            if choice == "replace":
                self.salveaza_oferta_finala(
                    replace_offer_id=int(self._last_saved_offer_id),
                    show_costs_dialog=show_costs_dialog,
                )
                return
            self.salveaza_oferta_finala(force_new_offer=True, show_costs_dialog=show_costs_dialog)
            return

        nume, tel, adr = self.entry_nume.get(), self.entry_tel.get(), self.entry_adresa.get()
        email = (self.entry_email.get() or "").strip() if getattr(self, "entry_email", None) else ""
        if edit_id and (self.data_oferta_curenta or "").strip():
            data_s = (self.data_oferta_curenta or "").strip()
        else:
            data_s = f"{self.combo_an.get()}-{self.combo_luna.get()} {datetime.now().strftime('%H:%M')}"

        replace_save = replace_offer_id is not None

        try:
            if replace_save:
                snap = get_offer_snapshot(self.cursor, int(replace_offer_id), force_refresh=True)
                if not snap:
                    self._last_saved_offer_id = None
                    self.afiseaza_mesaj(
                        "Eroare",
                        "Oferta anterioară nu mai există în baza de date. Poți salva din nou ca ofertă nouă.",
                        "#7a1a1a",
                    )
                    return
                client_id = int(snap.get("id_client") or 0)
                if client_id <= 0:
                    self._last_saved_offer_id = None
                    self.afiseaza_mesaj(
                        "Eroare",
                        "Datele ofertei anterioare sunt incomplete. Salvează ca ofertă nouă.",
                        "#7a1a1a",
                    )
                    return
                data_s = str(snap.get("data_oferta") or "").strip() or data_s
                nume = str(snap.get("nume_client_temp") or nume)
            else:
                client_id = get_client_id_by_name(self.cursor, nume)
                if client_id is None:
                    client_id = insert_client(
                        self.conn,
                        self.cursor,
                        nume,
                        tel,
                        adr,
                        email,
                        datetime.now().strftime("%Y-%m-%d"),
                    )

            discount_salvat = self._get_discount_proc()

            mentiuni_text = ""
            if getattr(self, "txt_mentiuni", None) and self.txt_mentiuni.winfo_exists():
                mentiuni_text = (self.txt_mentiuni.get("1.0", "end").strip() or "")
                if getattr(self, "_mentiuni_placeholder_active", False):
                    mentiuni_text = ""
            afiseaza_mentiuni_pdf = bool(
                getattr(self, "var_afiseaza_mentiuni_pdf", None)
                and self.var_afiseaza_mentiuni_pdf.get()
            )
            conditii_pdf_activ = bool(
                getattr(self, "var_conditii_pdf", None)
                and self.var_conditii_pdf.get()
            )
            termen_livrare_zile = self._parse_termen_livrare_zile()

            mod_la = datetime.now().strftime("%Y-%m-%d %H:%M")
            touch_existing = bool(edit_id or replace_save)
            detalii = dumps_offer_items(
                self.cos_cumparaturi,
                mentiuni=mentiuni_text,
                afiseaza_mentiuni_pdf=afiseaza_mentiuni_pdf,
                masuratori_lei=float(getattr(self, "masuratori_lei", 0) or 0),
                transport_lei=float(getattr(self, "transport_lei", 0) or 0),
                conditii_pdf=conditii_pdf_activ,
                termen_livrare_zile=termen_livrare_zile,
                modificat_de=(self.utilizator_creat if touch_existing else None),
                modificat_la=(mod_la if touch_existing else None),
                costs_entered=bool(getattr(self, "_offer_costs_entered", False)),
            )
            try:
                print(
                    f"[SYNC][UI] Pregătesc oferta: client='{nume}', data='{data_s}', "
                    f"items={len(self.cos_cumparaturi)}, total_lei={self.ultima_valoare_lei:.2f}, "
                    f"discount={discount_salvat}, curs_euro={self.curs_euro}"
                )
                print(f"[SYNC][UI] Rânduri produse/materiale (payload detalii_oferta): {detalii}")
            except Exception:
                pass
            if replace_save:
                update_offer_full(
                    self.conn,
                    self.cursor,
                    offer_id=int(replace_offer_id),
                    id_client=client_id,
                    detalii_oferta=detalii,
                    total_lei=self.ultima_valoare_lei,
                    data_oferta=data_s,
                    nume_client_temp=nume,
                    discount_proc=discount_salvat,
                    curs_euro=self.curs_euro,
                    safe_mode_enabled=1 if self._is_safe_mode_enabled() else 0,
                )
                self.id_oferta_curenta = int(replace_offer_id)
            elif edit_id:
                update_offer_full(
                    self.conn,
                    self.cursor,
                    offer_id=int(edit_id),
                    id_client=client_id,
                    detalii_oferta=detalii,
                    total_lei=self.ultima_valoare_lei,
                    data_oferta=data_s,
                    nume_client_temp=nume,
                    discount_proc=discount_salvat,
                    curs_euro=self.curs_euro,
                    safe_mode_enabled=1 if self._is_safe_mode_enabled() else 0,
                )
                self.id_oferta_curenta = int(edit_id)
            else:
                self.id_oferta_curenta = insert_offer(
                    self.conn,
                    self.cursor,
                    id_client=client_id,
                    detalii_oferta=detalii,
                    total_lei=self.ultima_valoare_lei,
                    data_oferta=data_s,
                    nume_client_temp=nume,
                    utilizator_creat=self.utilizator_creat,
                    discount_proc=discount_salvat,
                    curs_euro=self.curs_euro,
                    safe_mode_enabled=1 if self._is_safe_mode_enabled() else 0,
                )
            self.data_oferta_curenta = data_s
            try:
                print(
                    f"[SYNC][UI] Oferta salvată: id={self.id_oferta_curenta}, "
                    f"client='{nume}', total_lei={self.ultima_valoare_lei:.2f}"
                )
            except Exception:
                pass
        except sqlite3.OperationalError as e:
            logger.exception("Eroare SQLite la salvarea ofertei")
            msg = (
                "Nu s-a putut salva oferta în baza de date.\n\n"
                "Mesaj tehnic: "
                f"{e}"
            )
            self.afiseaza_mesaj("Eroare la salvare", msg, "#7a1a1a")
            return
        except Exception as e:
            logger.exception("Eroare neașteptată la salvarea ofertei")
            self.afiseaza_mesaj(
                "Eroare la salvare",
                f"A apărut o eroare neașteptată la salvarea ofertei:\n\n{e}",
                "#7a1a1a",
            )
            return

        if self.id_oferta_curenta is not None:
            self._last_saved_offer_id = int(self.id_oferta_curenta)

        # Dialog costuri: doar la apăsarea explicită „Salvează Ofertă”, prima dată când pasul nu e încă închis (nu la închiderea ferestrei / nu la editare din istoric).
        if (
            show_costs_dialog
            and not edit_id
            and not getattr(self, "_offer_costs_entered", True)
        ):
            self._dialog_masuratori_transport()

        # Mesaj de succes cu numărul ofertei.
        nr = str(self.id_oferta_curenta).zfill(5)
        if replace_save:
            self.afiseaza_mesaj("Succes", f"Oferta #{nr} a fost actualizată cu succes.")
        elif edit_id:
            mod_ui = self._nume_utilizator_pentru_afisare_ui() or self.utilizator_creat
            self.afiseaza_mesaj(
                "Succes",
                f"Ofertă actualizată (#{nr}). Modificată de {mod_ui}. Poți descărca PDF-ul.",
            )
        else:
            self.afiseaza_mesaj(
                "Succes",
                f"Oferta salvată! Nr. înregistrare: {nr}. Poți descărca PDF-ul cu acest număr.",
            )
        if getattr(self, "win_istoric", None) and self.win_istoric.winfo_exists():
            try:
                self.refresh_lista_istoric()
            except Exception:
                pass
        # Marcăm oferta ca fiind salvată în această sesiune, pentru a nu mai cere confirmare la închidere
        self._oferta_salvata_recent = True


    def _dialog_masuratori_transport(self):
        """Dialog după salvare: întrebăm dacă se adaugă măsurători / transport în LEI (TVA inclus)."""
        try:
            win = ctk.CTkToplevel(self.win_oferta if getattr(self, "win_oferta", None) else self)
        except Exception:
            win = ctk.CTkToplevel(self)
        win.title("Servicii suplimentare")
        win.geometry("420x260")
        win.grab_set()
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        ctk.CTkLabel(
            win,
            text="Dorești să adaugi costuri pentru Măsurători și/sau Transport?\nSumele sunt în LEI, TVA deja inclus.",
            font=("Segoe UI", 13),
            wraplength=380,
            justify="center",
        ).pack(pady=(15, 10), padx=20)

        tab = ctk.CTkTabview(win, width=380, height=110, corner_radius=4)
        tab.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        tab.add("Măsurători")
        tab.add("Transport")

        # Tab Măsurători
        f_mas = tab.tab("Măsurători")
        ctk.CTkLabel(f_mas, text="Valoare Măsurători (LEI, TVA inclus):", anchor="w").pack(
            anchor="w", padx=10, pady=(10, 4)
        )
        ent_mas = ctk.CTkEntry(f_mas)
        ent_mas.pack(fill="x", padx=10, pady=(0, 10))
        if getattr(self, "masuratori_lei", 0):
            ent_mas.insert(0, f"{self.masuratori_lei:.2f}")

        # Tab Transport
        f_tr = tab.tab("Transport")
        ctk.CTkLabel(f_tr, text="Valoare Transport (LEI, TVA inclus):", anchor="w").pack(
            anchor="w", padx=10, pady=(10, 4)
        )
        ent_tr = ctk.CTkEntry(f_tr)
        ent_tr.pack(fill="x", padx=10, pady=(0, 10))
        if getattr(self, "transport_lei", 0):
            ent_tr.insert(0, f"{self.transport_lei:.2f}")

        def _parse_val_local(s: str) -> float:
            s = (s or "").strip().replace(",", ".")
            try:
                return float(s)
            except ValueError:
                return 0.0

        def _finalize_costs_dialog(*, apply_entries: bool) -> None:
            """Închide pasul costuri: marchează oferta ca având costurile definite (sau omise), persistă în detalii."""
            if apply_entries:
                self.masuratori_lei = _parse_val_local(ent_mas.get())
                self.transport_lei = _parse_val_local(ent_tr.get())
            self._offer_costs_entered = True
            try:
                win.destroy()
            except Exception:
                pass
            offer_id = getattr(self, "id_oferta_curenta", None)
            if offer_id and self.cos_cumparaturi:
                mentiuni_text = ""
                if getattr(self, "txt_mentiuni", None) and self.txt_mentiuni.winfo_exists():
                    mentiuni_text = (self.txt_mentiuni.get("1.0", "end").strip() or "")
                    if getattr(self, "_mentiuni_placeholder_active", False):
                        mentiuni_text = ""
                afiseaza_mentiuni_pdf = bool(
                    getattr(self, "var_afiseaza_mentiuni_pdf", None) and self.var_afiseaza_mentiuni_pdf.get()
                )
                conditii_pdf_activ = bool(getattr(self, "var_conditii_pdf", None) and self.var_conditii_pdf.get())
                termen_livrare_zile = self._parse_termen_livrare_zile()
                new_detalii = dumps_offer_items(
                    self.cos_cumparaturi,
                    mentiuni=mentiuni_text,
                    afiseaza_mentiuni_pdf=afiseaza_mentiuni_pdf,
                    masuratori_lei=float(self.masuratori_lei or 0),
                    transport_lei=float(self.transport_lei or 0),
                    conditii_pdf=conditii_pdf_activ,
                    termen_livrare_zile=termen_livrare_zile,
                    costs_entered=True,
                )
                try:
                    update_offer_detalii(self.conn, self.cursor, offer_id, new_detalii)
                except Exception:
                    logger.exception("Actualizare detalii ofertă (măsurători/transport) eșuată")
            try:
                self.refresh_cos(readonly=getattr(self, "_win_oferta_readonly", False))
            except Exception:
                self.refresh_cos()

        win.protocol("WM_DELETE_WINDOW", lambda: _finalize_costs_dialog(apply_entries=False))

        f_btns = ctk.CTkFrame(win, fg_color="transparent")
        f_btns.pack(fill="x", pady=(0, 12))
        ctk.CTkButton(
            f_btns,
            text="Salvează valorile",
            fg_color="#2E7D32",
            command=lambda: _finalize_costs_dialog(apply_entries=True),
        ).pack(side="left", padx=(30, 10))
        ctk.CTkButton(
            f_btns,
            text="Sari peste",
            fg_color="#3A3A3A",
            command=lambda: _finalize_costs_dialog(apply_entries=False),
        ).pack(side="right", padx=(10, 30))

        # Ținem deschis acest dialog până când utilizatorul îl închide (confirmă sau sare peste),
        # abia apoi continuă execuția funcției care a apelat acest dialog.
        try:
            self.wait_window(win)
        except Exception:
            pass


def run_app():
    while True:
        login = LoginWindow()
        login.mainloop()
        user = getattr(login, "_auth_user", None)
        try:
            login.destroy()
        except Exception:
            pass
        if not user:
            break
        app = AplicatieOfertare(utilizator_creat=user, on_logout=None)
        app.mainloop()
        if not getattr(app, "_want_login_again", False):
            break

