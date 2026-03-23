from __future__ import annotations

import logging
import re
from datetime import datetime
import threading

import customtkinter as ctk
import pandas as pd
from PIL import Image
from tkinter import filedialog

from .config import AppConfig, BNR_TIMEOUT_S, PDF_CONTACT_EMAIL, PDF_CONTACT_TEL, get_database_path, get_settings_path
from .auth_utils import hash_parola, username_din_nume_complet
from .db import (
    DbHandles,
    get_istoric_oferte_admin,
    get_istoric_oferte_by_user,
    get_activity_users_with_counts,
    get_approved_users_with_privileges,
    get_produse_for_admin_list,
    get_user_contact_phone,
    insert_produs,
    delete_produs,
    delete_offer,
    insert_user,
    user_exists_by_username,
    delete_user,
    set_user_blocked,
    update_user_privileges,
    init_schema,
    open_db,
    get_oferte_by_date,
)
from .paths import resolve_asset_path
from .pdf_export import build_oferta_pret_pdf
from .serialization import loads_offer_items
from .db import get_user_full_name
from .services import fetch_bnr_eur_rate
from .updater import list_updates_for_admin, upload_new_version

logger = logging.getLogger(__name__)
# Temă corporate (aceeași paletă ca ofertare/ui.py)
CORP_WINDOW_BG = "#363636"
CORP_FRAME_BG = "#2D2D2D"
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


class AdminLoginWindow(ctk.CTk):
    """Fereastră de autentificare pentru programul admin – același design ca la Ofertare (logo + login + preloader)."""
    def __init__(self, on_success):
        super().__init__()
        self.on_success = on_success
        self.cale_logo = resolve_asset_path("Naturen2.png")
        self.configure(fg_color=CORP_WINDOW_BG)
        self.title("Admin – Autentificare")
        # Login admin: fereastră mică, centrată (dimensiunea originală)
        latime, inaltime = 420, 480
        ecran_l = self.winfo_screenwidth()
        ecran_i = self.winfo_screenheight()
        x = (ecran_l // 2) - (latime // 2)
        y = (ecran_i // 2) - (inaltime // 2)
        self.geometry(f"{latime}x{inaltime}+{x}+{y}")
        self.resizable(False, False)
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(expand=True, fill="both", padx=20, pady=20)
        self._build_login_screen()

    def _build_login_screen(self):
        for w in self.container.winfo_children():
            w.destroy()
        try:
            img_pil = Image.open(self.cale_logo)
            img_logo = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(280, 122))
            ctk.CTkLabel(self.container, image=img_logo, text="").pack(pady=(0, 24))
        except Exception:
            logger.warning("Logo login admin nu s-a încărcat: %s", self.cale_logo, exc_info=True)
            ctk.CTkLabel(
                self.container, text="ADMIN", font=("Segoe UI", 20)
            ).pack(pady=(0, 24))
        ctk.CTkLabel(
            self.container, text="Autentificare Admin", font=("Segoe UI", 16)
        ).pack(pady=(0, 16))
        self.entry_user = ctk.CTkEntry(self.container, placeholder_text="Utilizator", width=260)
        self.entry_user.pack(pady=5)
        self.entry_parola = ctk.CTkEntry(self.container, placeholder_text="Parolă", show="*", width=260)
        self.entry_parola.pack(pady=5)
        self.lbl_error = ctk.CTkLabel(
            self.container, text="", text_color="#ff5555", font=("Segoe UI", 11)
        )
        self.lbl_error.pack(pady=(5, 5))
        ctk.CTkButton(
            self.container, text="INTRARE", width=200, height=40, fg_color=GREEN_SOFT, hover_color=GREEN_SOFT_DARK, corner_radius=4, command=self._verifica
        ).pack(pady=(12, 8))
        cfg = AppConfig()
        if cfg.admin_user:
            self.entry_user.insert(0, cfg.admin_user)
        self.entry_parola.bind("<Return>", lambda e: self._verifica())
        self.entry_user.focus_set()

    def _show_preloader(self):
        for w in self.container.winfo_children():
            w.destroy()
        try:
            img_pil = Image.open(self.cale_logo)
            img_logo = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(320, 140))
            ctk.CTkLabel(self.container, image=img_logo, text="").pack(pady=(60, 20))
        except Exception:
            logger.warning("Logo preloader admin nu s-a încărcat", exc_info=True)
            ctk.CTkLabel(
                self.container, text="ADMIN", font=("Segoe UI", 22)
            ).pack(pady=(80, 20))
        ctk.CTkLabel(
            self.container, text="Se încarcă sistemul...", font=("Segoe UI", 12), text_color="#aaaaaa"
        ).pack()
        self._progress = ctk.CTkProgressBar(
            self.container, width=300, height=10, mode="indeterminate", progress_color=GREEN_SOFT
        )
        self._progress.pack(pady=20)
        self._progress.start()
        self.after(3000, self._trece_la_app)

    def _trece_la_app(self):
        if hasattr(self, "_progress") and self._progress.winfo_exists():
            self._progress.stop()
        self.destroy()
        self.on_success()

    def _verifica(self):
        u, p = self.entry_user.get().strip(), self.entry_parola.get().strip()
        cfg = AppConfig()
        if u == cfg.admin_user and p == cfg.admin_password:
            self._show_preloader()
        else:
            self.lbl_error.configure(text="Utilizator sau parolă incorectă.")


class AdminApp(ctk.CTk):
    """
    Aplicație separată de administrare: catalog produse + istoric oferte.

    - Catalog: tip produs (Uși, Tocuri, Mânere, Accesorii, Parchet), adăugare manuală, import Excel.
    - Istoric oferte: vizualizare oferte (client, dată, total), detaliu ofertă, descărcare PDF.
    """

    CATEGORII_STOC = [
        "Usi Interior", "Usi intrare apartament", "Tocuri", "Manere", "Accesorii",
        "Izolatii parchet", "Plinta parchet",
        "Parchet Laminat Stoc", "Parchet Laminat Comanda", "Parchet Spc Stoc",
        "Parchet Spc Floorify", "Parchet Triplu Stratificat",
    ]
    CATEGORII_ERKADO = ["Usi Interior", "Tocuri", "Accesorii"]
    CATEGORII_PARCHET = [
        "Parchet Laminat Stoc", "Parchet Laminat Comanda", "Parchet Spc Stoc",
        "Parchet Spc Floorify", "Parchet Triplu Stratificat",
    ]
    # Finisaje / decoruri comune la uși și tocuri (multi-select la introducere uși)
    DECORURI_USI = [
        "Alb", "Nuc", "Stejar Riviera", "Stejar Gotic", "Stejar Pastel",
        "Wenge Alb", "Silver Oak", "Kasmir", "Attic Wood",
    ]

    def __init__(self):
        super().__init__()
        self.configure(fg_color=CORP_WINDOW_BG)

        self.title("Admin Catalog Produse")
        # Fereastra principală admin: ocupă toată rezoluția ecranului
        ecran_l = self.winfo_screenwidth()
        ecran_i = self.winfo_screenheight()
        self.geometry(f"{ecran_l}x{ecran_i}+0+0")
        self.minsize(1020, 620)
        self.resizable(True, True)

        db_path = get_database_path()
        self.db: DbHandles = open_db(db_path)
        self.conn = self.db.conn
        self.cursor = self.db.cursor
        init_schema(self.cursor, self.conn)

        self.cat_selectata = self.CATEGORII_STOC[0]
        self.furnizor_selectat = "Stoc"
        self.inputs = {}
        self.cale_logo = resolve_asset_path("Naturen2.png")
        self.config_app = AppConfig()
        self.curs_euro = self.config_app.curs_euro_initial
        self._obtine_curs_bnr()

        self._nav_stack = []  # stivă pentru butonul Înapoi: ecran anterior
        self._current_screen = "meniu"
        self._update_upload_in_progress: bool = False
        self.update_mandatory_var = ctk.BooleanVar(value=False)
        self._catalog_list_refresh_id: int = 0
        self._build_ui()
        self._show_meniu()

    def _style_modern_frame(self, frame: ctk.CTkFrame) -> None:
        frame.configure(
            fg_color=CORP_FRAME_BG,
            corner_radius=4,
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

    def _style_modern_combo(self, combo: ctk.CTkComboBox) -> None:
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

    def _style_modern_button(self, btn: ctk.CTkButton) -> None:
        txt = (str(btn.cget("text") or "")).lower()
        if "pdf" in txt or "descar" in txt:
            btn.configure(corner_radius=4, fg_color=AMBER_CORP, hover_color=AMBER_HOVER, text_color="white")
        elif any(k in txt for k in ("adaug", "salveaz", "confirm", "ok")):
            btn.configure(
                corner_radius=4,
                fg_color=GREEN_SOFT,
                hover_color=GREEN_SOFT_DARK,
                text_color="white",
                font=("Segoe UI", 12),
            )
        elif any(k in txt for k in ("istoric", "căutare clien", "cautare clien", "meniu", "înapoi", "inapoi")):
            btn.configure(
                corner_radius=4,
                fg_color="transparent",
                border_width=1,
                border_color=BORDER_GRAY,
                text_color="white",
                hover_color="#353535",
            )
        else:
            fg = str(btn.cget("fg_color")).lower()
            if fg not in {"#7a1a1a", "#6f1d1b", "#f57c00"}:
                btn.configure(corner_radius=4, fg_color=CORP_MATT_GREY, hover_color="#454545")

    def _apply_modern_dark_recursive(self, root) -> None:
        def _walk(widget):
            try:
                if isinstance(widget, ctk.CTkRadioButton):
                    self._style_corporate_radio(widget)
                    return
                if isinstance(widget, ctk.CTkCheckBox):
                    self._style_corporate_checkbox(widget)
                    return
            except Exception:
                pass
            try:
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
                    if fg not in {"transparent", "#2E7D32", "#6f1d1b", "#7a1a1a", "#f57c00"}:
                        self._style_modern_frame(widget)
                elif isinstance(widget, ctk.CTkEntry):
                    self._style_modern_entry(widget)
                    widget.configure(fg_color="#363636")
                elif isinstance(widget, ctk.CTkComboBox):
                    self._style_modern_combo(widget)
                    widget.configure(fg_color=CORP_MATT_GREY)
                elif isinstance(widget, ctk.CTkTextbox):
                    widget.configure(
                        corner_radius=4,
                        border_width=1,
                        border_color="#3A3A3A",
                        fg_color="#363636",
                    )
                elif isinstance(widget, ctk.CTkButton):
                    self._style_modern_button(widget)
                elif isinstance(widget, ctk.CTkLabel):
                    txt = (str(widget.cget("text") or "")).strip()
                    if txt and len(txt) < 40 and txt.upper() == txt:
                        widget.configure(text_color="#E6E6E6", font=("Segoe UI", 14))
            except Exception:
                pass
            for child in widget.winfo_children():
                _walk(child)

        _walk(root)

    # ---------- Parametri calcul (usi duble / glisante) ----------

    def _build_parametri_form(self, frame: ctk.CTkFrame) -> None:
        self._param_entries: dict[str, ctk.CTkEntry] = {}
        grid = ctk.CTkFrame(frame, fg_color="#2D2D2D")
        grid.pack(fill="x", padx=20, pady=10)
        grid.grid_columnconfigure(1, weight=1)

        def add_row(row: int, label: str, key: str, value: float) -> None:
            ctk.CTkLabel(grid, text=label, anchor="w", font=("Segoe UI", 12)).grid(
                row=row, column=0, padx=12, pady=6, sticky="w"
            )
            ent = ctk.CTkEntry(grid, width=120)
            ent.insert(0, str(value))
            ent.grid(row=row, column=1, padx=12, pady=6, sticky="w")
            self._param_entries[key] = ent

        cfg = self.config_app
        add_row(0, "Ușă dublă Stoc – factor multiplicare", "usa_dubla_factor_stoc", cfg.usa_dubla_factor_stoc)
        add_row(1, "Ușă dublă Erkado – factor multiplicare", "usa_dubla_factor_erkado", cfg.usa_dubla_factor_erkado)
        add_row(2, "Ușă dublă Erkado – adaos fix (€)", "usa_dubla_plus_erkado", cfg.usa_dubla_plus_erkado)
        add_row(3, "Toc dublu Stoc – factor multiplicare", "toc_dublu_factor_stoc", cfg.toc_dublu_factor_stoc)
        add_row(4, "Toc dublu Erkado – factor multiplicare", "toc_dublu_factor_erkado", cfg.toc_dublu_factor_erkado)
        add_row(5, "Glisare fără închidere – adaos (€)", "glisare_plus_stoc", cfg.glisare_plus_stoc)
        add_row(6, "Glisare cu închidere – adaos (€)", "glisare_plus_cu_inchidere", cfg.glisare_plus_cu_inchidere)

        ctk.CTkButton(
            frame,
            text="Salvează parametrii",
            width=180,
            height=36,
            fg_color="#2E7D32",
            command=self._salveaza_parametri_calcul,
        ).pack(pady=(14, 8), padx=4)

    def _salveaza_parametri_calcul(self) -> None:
        from .config import AppConfig  # pentru reîncărcare locală

        # 1) Confirmare parolă admin înainte de modificare
        win = ctk.CTkToplevel(self)
        win.title("Confirmare parolă admin")
        win.geometry("420x200")
        win.grab_set()
        win.transient(self)
        f = ctk.CTkFrame(win, fg_color="transparent")
        f.pack(expand=True, fill="both", padx=24, pady=20)
        ctk.CTkLabel(
            f,
            text="Pentru a modifica parametrii de calcul, introduce parola de admin:",
            font=("Segoe UI", 12),
            wraplength=360,
        ).pack(pady=(0, 12), anchor="w")
        entry_parola = ctk.CTkEntry(f, show="*", width=260)
        entry_parola.pack(pady=(0, 8))
        lbl_err = ctk.CTkLabel(f, text="", text_color="#ff5555", font=("Segoe UI", 11))
        lbl_err.pack(pady=(0, 8))

        def _continua():
            parola = entry_parola.get()
            if not parola or parola != self.config_app.parola_admin:
                lbl_err.configure(text="Parolă admin incorectă.")
                return
            win.destroy()
            self._salveaza_parametri_calcul_confirmat(AppConfig)

        ctk.CTkButton(
            f,
            text="Confirmă",
            width=160,
            height=36,
            fg_color="#2E7D32",
            command=_continua,
        ).pack(pady=(10, 0), padx=4)
        entry_parola.bind("<Return>", lambda e: _continua())

    def _salveaza_parametri_calcul_confirmat(self, AppConfig_cls) -> None:
        errors: list[str] = []
        valori_noi: dict[str, float] = {}
        for key, entry in self._param_entries.items():
            text = (entry.get() or "").replace(",", ".").strip()
            try:
                valori_noi[key] = float(text)
            except ValueError:
                errors.append(f"{key} trebuie să fie număr (ai introdus: {text!r})")
        if errors:
            self._afiseaza_mesaj("Eroare", "\n".join(errors))
            return

        # Citim eventualul fișier existent și îl actualizăm cu valorile noi
        import json, os

        settings_path = get_settings_path()
        data: dict[str, object] = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    data = raw
            except Exception:
                data = {}
        data.update(valori_noi)
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Reîncarcă în config-ul curent pentru sesiunea de admin
            self.config_app = AppConfig_cls()
            self._afiseaza_mesaj(
                "Succes",
                "Parametrii au fost salvați. Redeschide aplicația de ofertare pentru a aplica noile valori."
            )
        except Exception:
            logger.exception("Salvare parametri calcul eșuată")
            self._afiseaza_mesaj("Eroare", "Nu s-au putut salva parametrii. Verifică drepturile pe folder.")

    def _show_parametri_calcul(self, from_back=False) -> None:
        """Toggle: dacă suntem deja în tab-ul de parametri (și nu venim din Back), revenim la MENIU."""
        if not from_back and self.frame_parametri.winfo_ismapped():
            self._show_meniu(from_back=False)
            return
        if not from_back:
            self._nav_stack.append(self._current_screen)
        self._current_screen = "parametri"
        self.frame_meniu.pack_forget()
        self.frame_catalog.pack_forget()
        self.frame_istoric.pack_forget()
        self.frame_privilegii.pack_forget()
        self.frame_monitorizare.pack_forget()
        if hasattr(self, "frame_statistica"):
            self.frame_statistica.pack_forget()
        if hasattr(self, "frame_update_software"):
            self.frame_update_software.pack_forget()
        self.frame_parametri.pack(fill="both", expand=True)
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back.pack(side="left", padx=5, pady=4)
        self._apply_modern_dark_recursive(self.frame_parametri)

    def _obtine_curs_bnr(self):
        rate = fetch_bnr_eur_rate(timeout_s=BNR_TIMEOUT_S)
        if rate is not None:
            self.curs_euro = round(rate * self.config_app.curs_markup_percent, 4)

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="#2D2D2D", corner_radius=4)
        top.pack(fill="x", padx=20, pady=(15, 10))
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=0)

        left_top = ctk.CTkFrame(top, fg_color="transparent")
        left_top.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            left_top,
            text="ADMINISTRARE",
            font=("Segoe UI", 20, "bold"),
        ).pack(side="left", padx=14, pady=12)

        self.btns_nav = ctk.CTkFrame(left_top, fg_color="transparent")
        self.btns_nav.pack(side="left", padx=(10, 14), pady=10)
        self.btn_meniu = ctk.CTkButton(
            self.btns_nav,
            text="MENIU",
            width=120,
            height=36,
            fg_color="#3A3A3A",
            command=lambda: self._show_meniu(from_back=False),
        )
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back = ctk.CTkButton(
            self.btns_nav,
            text="ÎNAPOI",
            width=100,
            height=36,
            fg_color="#3A3A3A",
            command=self._go_back,
        )
        # btn_back se afișează doar când suntem într-un ecran secundar (în _show_*)

        self.btn_parametri = ctk.CTkButton(
            self.btns_nav,
            text="Parametri calcul",
            width=160,
            height=36,
            fg_color="#3A3A3A",
            command=self._show_parametri_calcul,
        )
        self.btn_parametri.pack(side="left", padx=5, pady=4)

        right_top = ctk.CTkFrame(top, fg_color="transparent")
        right_top.grid(row=0, column=1, sticky="e", padx=(8, 14), pady=8)
        try:
            logo_pil = Image.open(self.cale_logo)
            self.logo_header_img = ctk.CTkImage(
                light_image=logo_pil,
                dark_image=logo_pil,
                size=(300, 120),
            )
            ctk.CTkLabel(right_top, image=self.logo_header_img, text="").pack(side="right")
        except Exception:
            logger.warning("Logo header admin nu s-a încărcat: %s", self.cale_logo, exc_info=True)

        self.btns_cat_frame = ctk.CTkFrame(top, fg_color="transparent")
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=20, pady=(5, 20))

        # ---------- Meniu principal (3 casute centrate) ----------
        self.frame_meniu = ctk.CTkFrame(self.main_container, fg_color="transparent")
        meniu_centru = ctk.CTkFrame(self.frame_meniu, fg_color="transparent")
        meniu_centru.place(relx=0.5, rely=0.5, anchor="center")
        marime_casuta = 200
        self._meniu_cards = []
        for i, (titlu, cmd) in enumerate([
            ("Introducere produse", self._show_catalog),
            ("Oferte", self._show_istoric),
            ("Privilegii useri", self._show_privilegii),
            ("Monitorizare activitate", self._show_monitorizare),
            ("Statistica", self._show_statistica),
            ("Update Software", self._show_update_software),
        ]):
            casuta = ctk.CTkFrame(meniu_centru, width=marime_casuta, height=marime_casuta, fg_color="#2D2D2D", corner_radius=4)
            casuta.pack(side="left", padx=25, pady=20)
            casuta.pack_propagate(False)
            lbl = ctk.CTkLabel(casuta, text=titlu, font=("Segoe UI", 16, "bold"), text_color="#2E7D32" if cmd else "#666666")
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            self._meniu_cards.append((casuta, lbl, titlu, cmd))
            if cmd:
                casuta.bind("<Button-1>", lambda e, c=cmd: c())
                lbl.bind("<Button-1>", lambda e, c=cmd: c())
                casuta.configure(cursor="hand2")
                lbl.configure(cursor="hand2")

        # ---------- Panou Privilegii useri ----------
        self.frame_privilegii = ctk.CTkFrame(self.main_container, fg_color="transparent")
        ctk.CTkLabel(
            self.frame_privilegii,
            text="Privilegii conturi (useri aprobați)",
            font=("Segoe UI", 18, "bold"),
            text_color="#2E7D32",
        ).pack(pady=(15, 10))
        ctk.CTkLabel(
            self.frame_privilegii,
            text="Creează useri noi sau modifică privilegii pentru userii existenți: modificare curs EUR, discount maxim, ștergere oferte, ștergere clienți.",
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            wraplength=700,
        ).pack(pady=(0, 10))
        f_btn_add = ctk.CTkFrame(self.frame_privilegii, fg_color="transparent")
        f_btn_add.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(
            f_btn_add, text="Adaugă user nou", width=160, height=36, fg_color="#2E7D32",
            command=self._deschide_creare_user,
        ).pack(side="left", padx=(0, 8), pady=4)
        self.scroll_privilegii = ctk.CTkScrollableFrame(
            self.frame_privilegii, label_text="Useri"
        )
        self.scroll_privilegii.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # ---------- Panou Monitorizare activitate ----------
        self.frame_monitorizare = ctk.CTkFrame(self.main_container, fg_color="transparent")
        ctk.CTkLabel(
            self.frame_monitorizare,
            text="Monitorizare activitate",
            font=("Segoe UI", 18, "bold"),
            text_color="#2E7D32",
        ).pack(pady=(15, 10))
        ctk.CTkLabel(
            self.frame_monitorizare,
            text="Useri și număr de oferte create. Poți folosi lista din stânga sau meniul derulant de mai jos pentru a selecta un user și a vedea detaliile ofertelor și statusul acestora.",
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            wraplength=700,
        ).pack(pady=(0, 8))
        # Meniu derulant cu toți userii (pentru filtrare rapidă a ofertelor)
        f_select_user = ctk.CTkFrame(self.frame_monitorizare, fg_color="transparent")
        f_select_user.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(
            f_select_user,
            text="Selectează user:",
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(0, 8))
        self.combo_monitorizare_user = ctk.CTkComboBox(
            f_select_user,
            values=[],
            state="readonly",
            width=260,
            command=lambda u: self._on_select_monitorizare_user(u),
        )
        self.combo_monitorizare_user.pack(side="left", padx=(0, 10), pady=4)

        self.f_monitorizare_content = ctk.CTkFrame(self.frame_monitorizare, fg_color="transparent")
        self.f_monitorizare_content.pack(fill="both", expand=True)
        self.scroll_monitorizare_useri = ctk.CTkScrollableFrame(
            self.f_monitorizare_content, label_text="Useri (nr. oferte)", width=320
        )
        self.scroll_monitorizare_useri.pack(side="left", fill="y", padx=(10, 5), pady=(0, 10))
        self.scroll_monitorizare_oferte = ctk.CTkScrollableFrame(
            self.f_monitorizare_content, label_text="Oferte ale userului selectat", fg_color="transparent"
        )
        self.scroll_monitorizare_oferte.pack(side="right", fill="both", expand=True, padx=(5, 10), pady=(0, 10))

        # ---------- Panou Update Software ----------
        self.frame_update_software = ctk.CTkFrame(self.main_container, fg_color="transparent")
        ctk.CTkLabel(
            self.frame_update_software,
            text="Update Software",
            font=("Segoe UI", 18, "bold"),
            text_color="#2E7D32",
        ).pack(pady=(15, 8))
        ctk.CTkLabel(
            self.frame_update_software,
            text=(
                "Publică o nouă versiune în cloud. Toate stațiile Ofertare vor detecta update-ul\n"
                "și îl vor instala automat la următoarea pornire."
            ),
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            wraplength=780,
        ).pack(pady=(0, 16))

        self.frame_update_card = ctk.CTkFrame(self.frame_update_software, fg_color="#2D2D2D", corner_radius=4)
        self.frame_update_card.pack(fill="x", padx=20, pady=(0, 12))
        self.frame_update_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.frame_update_card,
            text="Versiune:",
            font=("Segoe UI", 12),
        ).grid(row=0, column=0, padx=(18, 10), pady=(16, 8), sticky="w")
        self.entry_update_version = ctk.CTkEntry(
            self.frame_update_card,
            width=220,
            placeholder_text="ex: 1.0.5",
        )
        self.entry_update_version.grid(row=0, column=1, padx=(0, 18), pady=(16, 8), sticky="we")

        ctk.CTkLabel(
            self.frame_update_card,
            text="Link download (https://...):",
            font=("Segoe UI", 12),
        ).grid(row=1, column=0, padx=(18, 10), pady=(8, 6), sticky="w")

        self.entry_update_drive_link = ctk.CTkEntry(
            self.frame_update_card,
            placeholder_text="ex: https://github.com/.../releases/download/.../naturen_flow_update.zip",
        )
        self.entry_update_drive_link.grid(row=1, column=1, padx=(0, 18), pady=(8, 6), sticky="we")

        ctk.CTkLabel(
            self.frame_update_card,
            text="SHA256 (opțional, dar recomandat):",
            font=("Segoe UI", 12),
        ).grid(row=2, column=0, padx=(18, 10), pady=(6, 4), sticky="w")

        self.entry_update_sha256 = ctk.CTkEntry(
            self.frame_update_card,
            placeholder_text="hash SHA256 (64 caractere hex)",
        )
        self.entry_update_sha256.grid(row=2, column=1, padx=(0, 18), pady=(6, 4), sticky="we")

        ctk.CTkLabel(
            self.frame_update_card,
            text="Note release (opțional):",
            font=("Segoe UI", 12),
        ).grid(row=3, column=0, padx=(18, 10), pady=(6, 4), sticky="nw")
        self.txt_update_notes = ctk.CTkTextbox(self.frame_update_card, height=80)
        self.txt_update_notes.grid(row=3, column=1, padx=(0, 18), pady=(6, 4), sticky="we")

        self.chk_update_mandatory = ctk.CTkCheckBox(
            self.frame_update_card,
            text="Update obligatoriu (mandatory)",
            variable=self.update_mandatory_var,
        )
        self.chk_update_mandatory.grid(row=4, column=1, padx=(0, 18), pady=(4, 4), sticky="w")

        self.lbl_update_file_path = ctk.CTkLabel(
            self.frame_update_card,
            text="Se publică metadata standard: version, download_url, sha256, mandatory, notes, is_active.",
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.lbl_update_file_path.grid(row=5, column=0, columnspan=2, padx=18, pady=(4, 8), sticky="we")

        self.btn_publish_update = ctk.CTkButton(
            self.frame_update_card,
            text="Lansează Update în Cloud",
            width=320,
            height=46,
            fg_color="#2E7D32",
            font=("Segoe UI", 14, "bold"),
            command=self._launch_update_upload,
        )
        self.btn_publish_update.grid(row=6, column=0, columnspan=2, padx=18, pady=(10, 8), sticky="w")

        self.progress_update_upload = ctk.CTkProgressBar(
            self.frame_update_card,
            mode="indeterminate",
            width=320,
        )
        self.lbl_update_status = ctk.CTkLabel(
            self.frame_update_card,
            text="",
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.lbl_update_status.grid(row=8, column=0, columnspan=2, padx=18, pady=(4, 16), sticky="we")

        self.frame_update_list = ctk.CTkFrame(self.frame_update_software, fg_color="#2D2D2D", corner_radius=4)
        self.frame_update_list.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        ctk.CTkLabel(
            self.frame_update_list,
            text="Update-uri existente (ultimele 20)",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 6))
        self.scroll_update_rows = ctk.CTkScrollableFrame(self.frame_update_list, fg_color="transparent")
        self.scroll_update_rows.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        # ---------- Panou Statistica ----------
        self.frame_statistica = ctk.CTkFrame(self.main_container, fg_color="transparent")
        ctk.CTkLabel(
            self.frame_statistica,
            text="Statistica oferte pe zile",
            font=("Segoe UI", 18, "bold"),
            text_color="#2E7D32",
        ).pack(pady=(15, 10))
        ctk.CTkLabel(
            self.frame_statistica,
            text="Selectează data pentru care vrei să vezi numărul de oferte, produsele cele mai ofertate și totalul valoric.",
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            wraplength=760,
        ).pack(pady=(0, 10))

        f_date = ctk.CTkFrame(self.frame_statistica, fg_color="transparent")
        f_date.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(f_date, text="Data (YYYY-MM-DD):", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
        from datetime import datetime

        self.entry_data_stat = ctk.CTkEntry(f_date, width=140)
        self.entry_data_stat.pack(side="left", padx=(0, 8))
        try:
            azi = datetime.now().date().isoformat()
            self.entry_data_stat.insert(0, azi)
        except Exception:
            pass

        ctk.CTkButton(
            f_date,
            text="Calculează",
            width=120,
            height=32,
            fg_color="#2E7D32",
            command=self._calculeaza_statistica_zi,
        ).pack(side="left", padx=(8, 0), pady=4)

        self.lbl_rezumat_stat = ctk.CTkLabel(
            self.frame_statistica,
            text="Nu a fost selectată nicio zi.",
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
        )
        self.lbl_rezumat_stat.pack(pady=(5, 10), padx=10, anchor="w")

        f_stat_split = ctk.CTkFrame(self.frame_statistica, fg_color="transparent")
        f_stat_split.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.scroll_stat_oferte = ctk.CTkScrollableFrame(
            f_stat_split, label_text="Oferte în ziua selectată"
        )
        self.scroll_stat_oferte.pack(side="left", fill="both", expand=True, padx=(0, 5), pady=(0, 10))
        self.scroll_stat_produse = ctk.CTkScrollableFrame(
            f_stat_split, label_text="Produse cele mai ofertate (uși / mânere / parchet)"
        )
        self.scroll_stat_produse.pack(side="right", fill="both", expand=True, padx=(5, 0), pady=(0, 10))

        # ---------- Panou Parametri calcul ----------
        self.frame_parametri = ctk.CTkFrame(self.main_container, fg_color="transparent")
        ctk.CTkLabel(
            self.frame_parametri,
            text="Parametri calcul uși duble și glisante",
            font=("Segoe UI", 18, "bold"),
            text_color="#2E7D32",
        ).pack(pady=(15, 10))
        ctk.CTkLabel(
            self.frame_parametri,
            text=(
                "Aici poți modifica factorii de calcul folosiți în aplicația de ofertare pentru uși duble și glisante.\n"
                "Modificările se aplică după ce repornești aplicația de ofertare."
            ),
            font=("Segoe UI", 11),
            text_color="#aaaaaa",
            wraplength=760,
        ).pack(pady=(0, 15))
        self._build_parametri_form(self.frame_parametri)

        # ---------- Panou Catalog produse ----------
        self.frame_catalog = ctk.CTkFrame(self.main_container, fg_color="transparent")
        form_frame = ctk.CTkFrame(self.frame_catalog, width=620)
        form_frame.pack(side="left", fill="y", padx=(10, 15), pady=10)
        ctk.CTkLabel(
            form_frame,
            text="Adăugare / Import produse",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 15), sticky="w")
        self._build_form(form_frame)
        self.list_frame = ctk.CTkScrollableFrame(
            self.frame_catalog, label_text="Produse în catalog"
        )
        self.list_frame.pack(side="right", fill="both", expand=True, padx=(0, 10), pady=10)

        # ---------- Panou Istoric oferte ----------
        self.frame_istoric = ctk.CTkFrame(self.main_container, fg_color="transparent")
        f_filtre = ctk.CTkFrame(self.frame_istoric, fg_color="transparent")
        f_filtre.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(f_filtre, text="Caută client sau nr. înreg.:").pack(side="left", padx=(0, 10))
        self.ent_cauta_oferte = ctk.CTkEntry(
            f_filtre, width=300, placeholder_text="Nume client sau nr. (ex: 1, 00012)..."
        )
        self.ent_cauta_oferte.pack(side="left", padx=5)
        self.ent_cauta_oferte.bind("<KeyRelease>", lambda e: self._refresh_istoric())
        self.scroll_oferte = ctk.CTkScrollableFrame(
            self.frame_istoric, label_text="Oferte salvate (client, dată, total)"
        )
        self.scroll_oferte.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Curs EUR doar în Istoric oferte, colț dreapta sus (zona marcată cu chenar roșu)
        self.f_curs_istoric = ctk.CTkFrame(
            self.frame_istoric, fg_color="#2E7D32", corner_radius=4, height=44, width=280
        )
        self.f_curs_istoric.place(relx=1.0, rely=0.0, anchor="ne", x=-15, y=10)
        self.f_curs_istoric.pack_propagate(False)
        self.lbl_curs_admin = ctk.CTkLabel(
            self.f_curs_istoric,
            text=f"CURS EURO (BNR+1%): {self.curs_euro} LEI",
            font=("Segoe UI", 12),
            text_color="white",
        )
        self.lbl_curs_admin.pack(expand=True, padx=14, pady=10)
        self._apply_modern_dark_recursive(self)

    def _build_form(self, frame):
        row = 1

        # --- Câmpuri pentru categorii standard (ascunse la Tocuri) ---
        self._lbl_furnizor = ctk.CTkLabel(frame, text="Furnizor:")
        self._lbl_furnizor.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["furnizor"] = ctk.CTkComboBox(
            frame, values=["Stoc", "Erkado"], command=self._on_furnizor_change
        )
        self.inputs["furnizor"].set("Stoc")
        self.inputs["furnizor"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        row += 1

        self._lbl_categorie = ctk.CTkLabel(frame, text="Categorie:")
        self._lbl_categorie.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["categorie"] = ctk.CTkComboBox(
            frame, values=self.CATEGORII_STOC.copy(), command=self._on_categorie_change
        )
        self.inputs["categorie"].set(self.CATEGORII_STOC[0])
        self.inputs["categorie"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        row += 1

        self._lbl_colectie = ctk.CTkLabel(frame, text="Colecție:")
        self._lbl_colectie.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["colectie"] = ctk.CTkEntry(frame, width=300)
        self.inputs["colectie"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        row += 1

        self._lbl_model = ctk.CTkLabel(frame, text="Model:")
        self._lbl_model.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["model"] = ctk.CTkEntry(frame, width=300)
        self.inputs["model"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        row += 1

        self._lbl_finisaj = ctk.CTkLabel(frame, text="Finisaj:")
        self._lbl_finisaj.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["finisaj"] = ctk.CTkEntry(frame, width=300)
        self.inputs["finisaj"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        row += 1

        self._lbl_decor = ctk.CTkLabel(frame, text="Decor:")
        self._lbl_decor.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["decor"] = ctk.CTkEntry(frame, width=300)
        self.inputs["decor"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        row += 1

        # --- Multi-select Finisaj / Decor pentru categorii Uși (ordine în catalog: Finisaj apoi Decor) ---
        self._lbl_finisaj_usi = ctk.CTkLabel(frame, text="Finisaj, apoi decor:")
        self._lbl_finisaj_usi.grid(row=row, column=0, padx=10, pady=5, sticky="ne")
        self._frame_finisaj_usi = ctk.CTkScrollableFrame(frame, width=320, height=110, fg_color="#2b2b2b")
        self._frame_finisaj_usi.grid(row=row, column=1, padx=10, pady=5, sticky="nwe")
        self._check_finisaj_usi = {}
        for i, fin in enumerate(self.DECORURI_USI):
            cb = ctk.CTkCheckBox(self._frame_finisaj_usi, text=fin, width=200, font=("Segoe UI", 12))
            cb.grid(row=i // 3, column=i % 3, padx=8, pady=4, sticky="w")
            self._check_finisaj_usi[fin] = cb
        row += 1

        # --- Câmpuri doar pentru Tocuri (ascunse la celelalte categorii) ---
        self._lbl_tip_toc = ctk.CTkLabel(frame, text="Tipul tocului:")
        self._lbl_tip_toc.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["tip_toc"] = ctk.CTkComboBox(frame, values=["Fix", "Reglabil"], width=300)
        self.inputs["tip_toc"].set("Fix")
        self.inputs["tip_toc"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        row += 1

        self._lbl_reglaj = ctk.CTkLabel(frame, text="Reglajul:")
        self._lbl_reglaj.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["reglaj"] = ctk.CTkEntry(frame, width=300, placeholder_text="ex: 100-120 (se adaugă MM)")
        self.inputs["reglaj"].grid(row=row, column=1, padx=10, pady=5, sticky="we")
        self.inputs["reglaj"].bind("<KeyRelease>", self._validare_reglaj)
        self.inputs["reglaj"].bind("<FocusOut>", self._adauga_mm_reglaj)
        row += 1

        # --- Preț listă (mereu vizibil; eticheta se ajustează pe categorie) ---
        self._lbl_pret = ctk.CTkLabel(frame, text="Preț listă (€):")
        self._lbl_pret.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        self.inputs["pret"] = ctk.CTkEntry(frame, width=120)
        self.inputs["pret"].grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1

        self._btn_add = ctk.CTkButton(
            frame,
            text="Salvează produs",
            width=200,
            height=36,
            fg_color="#2E7D32",
            command=self._salveaza_produs_manual,
        )
        self._btn_add.grid(row=row, column=0, columnspan=2, padx=10, pady=(15, 10), sticky="we")
        row += 1

        self._btn_import = ctk.CTkButton(
            frame,
            text="Importă produse din Excel",
            width=220,
            height=36,
            fg_color="#F57C00",
            command=self._incarca_excel,
        )
        self._btn_import.grid(row=row, column=0, columnspan=2, padx=10, pady=(8, 10), sticky="we")
        row += 1

        self._lbl_hint = ctk.CTkLabel(
            frame,
            text="Excel: Categorie, Furnizor, Colectie, Model, Finisaj, Decor, Preț listă (€). Opțional: categorie/furnizor din formular. Tocuri: tip_toc, reglaj. Importul în cloud necesită cheia Supabase service role (.env, SUPABASE_SERVICE_ROLE_KEY sau fișier supabase_service_role.key lângă exe / în %APPDATA%\\Soft Ofertare Usi).",
            wraplength=560,
            font=("Segoe UI", 10),
            text_color="#aaaaaa",
        )
        self._lbl_hint.grid(row=row, column=0, columnspan=4, padx=10, pady=(5, 10), sticky="w")

        frame.columnconfigure(1, weight=1)
        self._vizibilitate_form_categorie()

    def _validare_reglaj(self, event=None):
        """Permite doar cifre și simbolul '-' (Reglajul); păstrează ' MM' la final dacă există."""
        w = self.inputs.get("reglaj")
        if not w:
            return
        val = w.get()
        avea_mm = val.rstrip().endswith(" MM")
        permis = re.sub(r"[^0-9\-]", "", val)
        if avea_mm and permis:
            permis = permis + " MM"
        if permis != val:
            w.delete(0, "end")
            w.insert(0, permis)

    def _adauga_mm_reglaj(self, event=None):
        """La ieșirea din câmp, adaugă ' MM' la final dacă există valoare numerică."""
        w = self.inputs.get("reglaj")
        if not w:
            return
        val = (w.get() or "").strip()
        if not val:
            return
        if val.endswith(" MM"):
            return
        # Păstrăm doar cifre și '-' pentru partea numerică
        numeric = re.sub(r"[^0-9\-]", "", val)
        if numeric:
            w.delete(0, "end")
            w.insert(0, numeric + " MM")

    def _on_furnizor_change(self, furnizor: str):
        self.furnizor_selectat = furnizor
        categorii = self.CATEGORII_STOC if furnizor == "Stoc" else self.CATEGORII_ERKADO
        self.inputs["categorie"].configure(values=categorii)
        self.inputs["categorie"].set(categorii[0])
        self.cat_selectata = categorii[0]
        self._vizibilitate_form_categorie()
        self._refresh_list()

    def _sync_ui_furnizor_categorie(self, furnizor: str, categorie: str | None) -> None:
        """Setează Furnizor + Categorie în formular fără a reseta categoria dacă e validă pentru furnizor (ex. după import Excel)."""
        furn = (furnizor or "").strip()
        if furn not in ("Stoc", "Erkado"):
            furn = "Stoc"
        self.furnizor_selectat = furn
        if self.inputs.get("furnizor"):
            self.inputs["furnizor"].set(furn)
        categorii = self.CATEGORII_STOC if furn == "Stoc" else self.CATEGORII_ERKADO
        if self.inputs.get("categorie"):
            self.inputs["categorie"].configure(values=categorii)
            cat = (categorie or "").strip()
            if cat in categorii:
                self.inputs["categorie"].set(cat)
                self.cat_selectata = cat
            else:
                self.inputs["categorie"].set(categorii[0])
                self.cat_selectata = categorii[0]
        self._vizibilitate_form_categorie()
        self._refresh_list()

    def _on_categorie_change(self, cat: str):
        self.cat_selectata = cat
        self._vizibilitate_form_categorie()
        self._refresh_list()

    def _vizibilitate_form_categorie(self):
        """Afișează doar câmpurile relevante pentru categoria selectată și reordonează rândurile fără goluri."""
        este_tocuri = self.cat_selectata == "Tocuri"
        este_parchet = self.cat_selectata in self.CATEGORII_PARCHET
        pad = {"padx": 10, "pady": 5, "sticky": "we"}
        pad_e = {"padx": 10, "pady": 5, "sticky": "e"}
        pad_w = {"padx": 10, "pady": 5, "sticky": "w"}
        if este_parchet:
            # Parchet: Categorie, Colectia, Cod produs, MP/cut, Pret lista eur fara TVA/mp
            self._lbl_furnizor.grid_remove()
            self.inputs["furnizor"].grid_remove()
            self._lbl_categorie.grid(row=1, column=0, **pad_e)
            self.inputs["categorie"].grid(row=1, column=1, **pad)
            self._lbl_colectie.configure(text="Colectia")
            self._lbl_colectie.grid(row=2, column=0, **pad_e)
            self.inputs["colectie"].grid(row=2, column=1, **pad)
            self._lbl_model.configure(text="Cod produs")
            self._lbl_model.grid(row=3, column=0, **pad_e)
            self.inputs["model"].grid(row=3, column=1, **pad)
            self._lbl_reglaj.configure(text="MP/cut")
            self._lbl_reglaj.grid(row=4, column=0, **pad_e)
            self.inputs["reglaj"].grid(row=4, column=1, **pad)
            self._lbl_pret.configure(text="Preț listă EUR fără TVA/mp")
            self._lbl_pret.grid(row=5, column=0, **pad_e)
            self.inputs["pret"].grid(row=5, column=1, **pad_w)
            self._lbl_decor.grid_remove()
            self.inputs["decor"].grid_remove()
            self._lbl_finisaj.grid_remove()
            self.inputs["finisaj"].grid_remove()
            self._lbl_finisaj_usi.grid_remove()
            self._frame_finisaj_usi.grid_remove()
            self._lbl_tip_toc.grid_remove()
            self.inputs["tip_toc"].grid_remove()
            self._btn_add.grid(row=6, column=0, columnspan=2, padx=10, pady=(15, 8), sticky="we")
            self._btn_import.grid(row=7, column=0, columnspan=2, padx=10, pady=(5, 8), sticky="we")
            self._lbl_hint.grid(row=8, column=0, columnspan=4, padx=10, pady=(5, 10), sticky="w")
        elif este_tocuri:
            # Tocuri: Furnizor (Stoc / Erkado), Categorie, Tip toc, Reglaj, Preț listă, butoane, hint (rânduri 1–8)
            self._lbl_pret.configure(text="Preț listă (€)")
            self._lbl_furnizor.grid(row=1, column=0, **pad_e)
            self.inputs["furnizor"].grid(row=1, column=1, **pad)
            self._lbl_categorie.grid(row=2, column=0, **pad_e)
            self.inputs["categorie"].grid(row=2, column=1, **pad)
            self._lbl_colectie.grid_remove()
            self.inputs["colectie"].grid_remove()
            self._lbl_model.grid_remove()
            self.inputs["model"].grid_remove()
            self._lbl_decor.grid_remove()
            self.inputs["decor"].grid_remove()
            self._lbl_finisaj.grid_remove()
            self.inputs["finisaj"].grid_remove()
            self._lbl_finisaj_usi.grid_remove()
            self._frame_finisaj_usi.grid_remove()
            self._lbl_tip_toc.grid(row=3, column=0, **pad_e)
            self.inputs["tip_toc"].grid(row=3, column=1, **pad)
            self._lbl_reglaj.grid(row=4, column=0, **pad_e)
            self.inputs["reglaj"].grid(row=4, column=1, **pad)
            self._lbl_pret.grid(row=5, column=0, **pad_e)
            self.inputs["pret"].grid(row=5, column=1, **pad_w)
            self._btn_add.grid(row=6, column=0, columnspan=2, padx=10, pady=(15, 8), sticky="we")
            self._btn_import.grid(row=7, column=0, columnspan=2, padx=10, pady=(5, 8), sticky="we")
            self._lbl_hint.grid(row=8, column=0, columnspan=4, padx=10, pady=(5, 10), sticky="w")
        else:
            # Alte categorii: Furnizor, Categorie, Colecție, Model; apoi fie Decor+Finisaj (Manere, Accesorii), fie multi-select Finisaj (Uși)
            self._lbl_colectie.configure(text="Colecție")
            self._lbl_model.configure(text="Model")
            self._lbl_reglaj.configure(text="Reglaj")
            self._lbl_pret.configure(text="Preț listă (€)")
            este_usi = self.cat_selectata in ("Usi Interior", "Usi intrare apartament")
            self._lbl_furnizor.grid(row=1, column=0, **pad_e)
            self.inputs["furnizor"].grid(row=1, column=1, **pad)
            self._lbl_categorie.grid(row=2, column=0, **pad_e)
            self.inputs["categorie"].grid(row=2, column=1, **pad)
            self._lbl_colectie.grid(row=3, column=0, **pad_e)
            self.inputs["colectie"].grid(row=3, column=1, **pad)
            self._lbl_model.grid(row=4, column=0, **pad_e)
            self.inputs["model"].grid(row=4, column=1, **pad)
            if este_usi:
                self._lbl_decor.grid_remove()
                self.inputs["decor"].grid_remove()
                self._lbl_finisaj.grid_remove()
                self.inputs["finisaj"].grid_remove()
                self._lbl_finisaj_usi.grid(row=5, column=0, padx=10, pady=5, sticky="ne")
                self._frame_finisaj_usi.grid(row=5, column=1, padx=10, pady=5, sticky="nwe")
                row_pret, row_btn, row_imp, row_hint = 6, 7, 8, 9
            else:
                self._lbl_finisaj_usi.grid_remove()
                self._frame_finisaj_usi.grid_remove()
                self._lbl_finisaj.grid(row=5, column=0, **pad_e)
                self.inputs["finisaj"].grid(row=5, column=1, **pad)
                self._lbl_decor.grid(row=6, column=0, **pad_e)
                self.inputs["decor"].grid(row=6, column=1, **pad)
                row_pret, row_btn, row_imp, row_hint = 7, 8, 9, 10
            self._lbl_tip_toc.grid_remove()
            self.inputs["tip_toc"].grid_remove()
            self._lbl_reglaj.grid_remove()
            self.inputs["reglaj"].grid_remove()
            self._lbl_pret.grid(row=row_pret, column=0, **pad_e)
            self.inputs["pret"].grid(row=row_pret, column=1, **pad_w)
            self._btn_add.grid(row=row_btn, column=0, columnspan=2, padx=10, pady=(15, 8), sticky="we")
            self._btn_import.grid(row=row_imp, column=0, columnspan=2, padx=10, pady=(5, 8), sticky="we")
            self._lbl_hint.grid(row=row_hint, column=0, columnspan=4, padx=10, pady=(5, 10), sticky="w")

    def _go_back(self):
        """Revenire la ecranul anterior; dacă stiva e goală, revine la meniul principal."""
        if not self._nav_stack:
            self._show_meniu(from_back=True)
            return
        prev = self._nav_stack.pop()
        show_methods = {
            "meniu": lambda: self._show_meniu(from_back=True),
            "catalog": lambda: self._show_catalog(from_back=True),
            "istoric": lambda: self._show_istoric(from_back=True),
            "privilegii": lambda: self._show_privilegii(from_back=True),
            "monitorizare": lambda: self._show_monitorizare(from_back=True),
            "statistica": lambda: self._show_statistica(from_back=True),
            "parametri": lambda: self._show_parametri_calcul(from_back=True),
            "update_software": lambda: self._show_update_software(from_back=True),
        }
        if prev in show_methods:
            show_methods[prev]()

    def _show_meniu(self, from_back=False):
        self._nav_stack = []
        self._current_screen = "meniu"
        self.frame_catalog.pack_forget()
        self.frame_istoric.pack_forget()
        self.frame_privilegii.pack_forget()
        self.frame_monitorizare.pack_forget()
        if hasattr(self, "frame_parametri"):
            self.frame_parametri.pack_forget()
        if hasattr(self, "frame_statistica"):
            self.frame_statistica.pack_forget()
        if hasattr(self, "frame_update_software"):
            self.frame_update_software.pack_forget()
        self.frame_meniu.pack(fill="both", expand=True)
        self.btn_meniu.pack_forget()
        self.btn_back.pack_forget()
        self.btns_cat_frame.pack_forget()
        self._apply_modern_dark_recursive(self.frame_meniu)

    def _set_update_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.entry_update_version.configure(state=state)
        self.entry_update_drive_link.configure(state=state)
        self.entry_update_sha256.configure(state=state)
        self.txt_update_notes.configure(state=state)
        self.chk_update_mandatory.configure(state=state)
        self.btn_publish_update.configure(state=state)

    def _launch_update_upload(self) -> None:
        if self._update_upload_in_progress:
            return
        version_name = (self.entry_update_version.get() or "").strip()
        drive_link = (self.entry_update_drive_link.get() or "").strip()
        sha256 = (self.entry_update_sha256.get() or "").strip().lower()
        notes = (self.txt_update_notes.get("1.0", "end") or "").strip()
        mandatory = bool(self.update_mandatory_var.get())
        version_pattern = r"^\d+\.\d+\.\d+$"
        if not version_name:
            self._afiseaza_mesaj("Validare", "Completează câmpul „Versiune” înainte de upload.")
            return
        if not re.fullmatch(version_pattern, version_name):
            self._afiseaza_mesaj("Validare", "Versiunea trebuie să aibă formatul x.x.x (ex: 1.2.3).")
            return
        if not drive_link:
            self._afiseaza_mesaj("Validare", "Completează link-ul de update.")
            return
        if not drive_link.startswith("https://"):
            self._afiseaza_mesaj("Validare", "Link-ul de update trebuie să înceapă cu https://.")
            return
        if sha256 and not re.fullmatch(r"[a-f0-9]{64}", sha256):
            self._afiseaza_mesaj("Validare", "SHA256 invalid. Folosește 64 caractere hex.")
            return

        self._update_upload_in_progress = True
        self._set_update_controls_enabled(False)
        self.lbl_update_status.configure(text="Publicare versiune în cloud...", text_color="#f0c75e")
        self.progress_update_upload.grid(row=7, column=0, columnspan=2, padx=18, pady=(4, 2), sticky="w")
        self.progress_update_upload.start()

        t = threading.Thread(
            target=self._upload_update_worker,
            args=(version_name, drive_link, sha256, mandatory, notes),
            daemon=True,
        )
        t.start()

    def _upload_update_worker(self, version_name: str, drive_link: str, sha256: str, mandatory: bool, notes: str) -> None:
        try:
            result = upload_new_version(
                version_name=version_name,
                download_url=drive_link,
                sha256=sha256,
                mandatory=mandatory,
                notes=notes,
                is_active=True,
            )
            self.after(0, lambda: self._on_upload_update_done(result, version_name))
        except Exception as exc:
            self.after(0, lambda: self._on_upload_update_done({"ok": False, "error": str(exc)}, version_name))

    def _on_upload_update_done(self, result: dict, version_name: str) -> None:
        self._update_upload_in_progress = False
        self._set_update_controls_enabled(True)
        if self.progress_update_upload.winfo_ismapped():
            self.progress_update_upload.stop()
            self.progress_update_upload.grid_remove()

        if result.get("ok"):
            self.lbl_update_status.configure(
                text="Update publicat cu succes în app_updates!",
                text_color="#4caf50",
            )
            self._afiseaza_mesaj(
                "Succes",
                "Update publicat cu succes în app_updates!",
            )
            self._refresh_update_list()
            return

        error_text = str(result.get("error") or "Eroare necunoscută la upload.")
        self.lbl_update_status.configure(
            text=f"Eroare upload: {error_text}",
            text_color="#ff5555",
        )
        self._afiseaza_mesaj("Eroare", f"Nu s-a putut publica versiunea: {error_text}")

    def _deschide_creare_user(self):
        win = ctk.CTkToplevel(self)
        win.title("Creare user nou")
        win.geometry("500x540")
        win.grab_set()
        win.transient(self)
        f = ctk.CTkFrame(win, fg_color="transparent")
        f.pack(expand=True, fill="both", padx=30, pady=25)
        ctk.CTkLabel(f, text="CREARE USER NOU", font=("Segoe UI", 18, "bold"), text_color="#2E7D32").pack(pady=(0, 20))
        ctk.CTkLabel(f, text="Nume Complet:", font=("Segoe UI", 12)).pack(anchor="w")
        entry_nume = ctk.CTkEntry(f, placeholder_text="ex: Razvan Teodorescu", width=400)
        entry_nume.pack(pady=(4, 12))
        lbl_username = ctk.CTkLabel(f, text="Nume utilizator: —", font=("Segoe UI", 11), text_color="#aaaaaa")
        lbl_username.pack(anchor="w", pady=(0, 16))

        def _actualizeaza_username(*args):
            u = username_din_nume_complet(entry_nume.get())
            lbl_username.configure(text=f"Nume utilizator: {u}" if u else "Nume utilizator: —")

        entry_nume.bind("<KeyRelease>", lambda e: _actualizeaza_username())

        ctk.CTkLabel(f, text="Parolă:", font=("Segoe UI", 12)).pack(anchor="w", pady=(8, 0))
        entry_parola = ctk.CTkEntry(f, show="*", width=400)
        entry_parola.pack(pady=(4, 8))
        ctk.CTkLabel(f, text="Confirmă parola:", font=("Segoe UI", 12)).pack(anchor="w", pady=(8, 0))
        entry_confirm = ctk.CTkEntry(f, show="*", width=400)
        entry_confirm.pack(pady=(4, 8))
        ctk.CTkLabel(f, text="Nr. telefon mobil (contact pe PDF):", font=("Segoe UI", 12)).pack(anchor="w", pady=(12, 0))
        entry_telefon = ctk.CTkEntry(f, placeholder_text="ex: 0775 154 770", width=400)
        entry_telefon.pack(pady=(4, 20))
        lbl_err = ctk.CTkLabel(f, text="", text_color="#ff5555", font=("Segoe UI", 11))
        lbl_err.pack(pady=(0, 12))

        def _creaza():
            nume = entry_nume.get().strip()
            parola = entry_parola.get()
            confirm = entry_confirm.get()
            if not nume:
                lbl_err.configure(text="Introdu numele complet.")
                return
            username = username_din_nume_complet(nume)
            if not username:
                lbl_err.configure(text="Nume invalid pentru generare username.")
                return
            if parola != confirm:
                lbl_err.configure(text="Parolele nu coincid.")
                return
            if len(parola) < 4:
                lbl_err.configure(text="Parola trebuie să aibă cel puțin 4 caractere.")
                return
            try:
                if user_exists_by_username(self.cursor, username):
                    lbl_err.configure(text="Acest nume de utilizator există deja.")
                    return
                telefon_contact = (entry_telefon.get() or "").strip()
                insert_user(self.conn, self.cursor, nume, username, hash_parola(parola), approved=1, telefon_contact=telefon_contact)
                lbl_err.configure(text="")
                self._afiseaza_mesaj("Succes", "User creat. Poate accesa aplicația Ofertare cu username-ul și parola setate.")
                win.destroy()
                self._refresh_privilegii()
            except Exception:
                logger.exception("Creare user eșuată")
                lbl_err.configure(text="Eroare la salvare. Încearcă din nou.")

        ctk.CTkButton(f, text="Confirmare", width=220, height=44, font=("Segoe UI", 14, "bold"), fg_color="#2E7D32", command=_creaza).pack(pady=16, padx=8)
        entry_confirm.bind("<Return>", lambda e: _creaza())

    def _show_privilegii(self, from_back=False):
        if not from_back:
            self._nav_stack.append(self._current_screen)
        self._current_screen = "privilegii"
        self.frame_meniu.pack_forget()
        self.frame_catalog.pack_forget()
        self.frame_istoric.pack_forget()
        self.frame_monitorizare.pack_forget()
        self.btns_cat_frame.pack_forget()
        if hasattr(self, "frame_statistica"):
            self.frame_statistica.pack_forget()
        if hasattr(self, "frame_parametri"):
            self.frame_parametri.pack_forget()
        if hasattr(self, "frame_update_software"):
            self.frame_update_software.pack_forget()
        self.frame_privilegii.pack(fill="both", expand=True)
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back.pack(side="left", padx=5, pady=4)
        self._refresh_privilegii()
        self._apply_modern_dark_recursive(self.frame_privilegii)

    def _toggle_block(self, user_id: int, blocked: int) -> None:
        try:
            set_user_blocked(self.conn, self.cursor, user_id, blocked)
            self._afiseaza_mesaj("Succes", "User blocat." if blocked else "User deblocat.")
            self._refresh_privilegii()
        except Exception:
            logger.exception("Blocare/deblocare user eșuată")
            self._afiseaza_mesaj("Eroare", "Nu s-a putut actualiza starea.")

    def _sterge_user_dialog(self, user_id: int, nume_complet: str, username: str) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Ștergere user – confirmare parolă")
        win.geometry("440x220")
        win.grab_set()
        win.transient(self)
        f = ctk.CTkFrame(win, fg_color="transparent")
        f.pack(expand=True, fill="both", padx=24, pady=20)
        ctk.CTkLabel(
            f, text=f"Ștergi definitiv userul: {nume_complet} ({username})?",
            font=("Segoe UI", 13, "bold"), wraplength=380,
        ).pack(pady=(0, 8))
        ctk.CTkLabel(f, text="Introdu parola ta de admin pentru a confirma:", font=("Segoe UI", 12)).pack(anchor="w", pady=(12, 4))
        entry_parola = ctk.CTkEntry(f, show="*", width=280)
        entry_parola.pack(pady=(0, 12))
        lbl_err = ctk.CTkLabel(f, text="", text_color="#ff5555", font=("Segoe UI", 11))
        lbl_err.pack(pady=(0, 8))

        def _confirma():
            parola = entry_parola.get()
            if AppConfig().admin_password != parola:
                lbl_err.configure(text="Parolă incorectă.")
                return
            try:
                delete_user(self.conn, self.cursor, user_id)
                self._afiseaza_mesaj("Succes", "User șters.")
                win.destroy()
                self._refresh_privilegii()
            except Exception:
                logger.exception("Ștergere user eșuată")
                lbl_err.configure(text="Eroare la ștergere.")

        ctk.CTkButton(f, text="Confirmă ștergerea", width=180, height=36, fg_color="#7a1a1a", command=_confirma).pack(pady=10, padx=4)
        entry_parola.bind("<Return>", lambda e: _confirma())

    def _refresh_privilegii(self):
        for w in self.scroll_privilegii.winfo_children():
            w.destroy()
        users = get_approved_users_with_privileges(self.cursor)
        if not users:
            ctk.CTkLabel(
                self.scroll_privilegii,
                text="Nu există useri. Adaugă un user nou cu butonul „Adaugă user nou”.",
                font=("Segoe UI", 12),
                text_color="#aaaaaa",
            ).pack(pady=20)
            return
        for r in users:
            uid, nume_complet, username, can_modify_curs, max_discount, can_delete_offers, can_delete_clients, can_dev_mode, blocked = (
                r[0], r[1], r[2], r[3], r[4], r[5], r[6], (r[7] if len(r) > 7 else 0), (r[8] if len(r) > 8 else 0)
            )
            f = ctk.CTkFrame(self.scroll_privilegii, fg_color="#2b2b2b")
            f.pack(fill="x", pady=6, padx=5)
            left = ctk.CTkFrame(f, fg_color="transparent")
            left.pack(side="left", padx=12, pady=10)
            lbl_nume = f"{nume_complet}  ({username})"
            if blocked:
                lbl_nume += "  — BLOCAT"
            ctk.CTkLabel(left, text=lbl_nume, font=("Segoe UI", 13, "bold"), anchor="w", text_color="#b55" if blocked else None).pack(anchor="w")
            opts = ctk.CTkFrame(f, fg_color="transparent")
            opts.pack(side="left", padx=15, pady=8)
            cb_curs = ctk.CTkCheckBox(opts, text="Modificare curs EUR", width=180, font=("Segoe UI", 11))
            cb_curs.select() if can_modify_curs else cb_curs.deselect()
            cb_curs.grid(row=0, column=0, padx=8, pady=4, sticky="w")
            ctk.CTkLabel(opts, text="Discount max (%):", font=("Segoe UI", 11)).grid(row=0, column=1, padx=(15, 4), pady=4, sticky="w")
            entry_disc = ctk.CTkEntry(opts, width=50, font=("Segoe UI", 11))
            entry_disc.insert(0, str(max_discount))
            entry_disc.grid(row=0, column=2, padx=4, pady=4, sticky="w")
            cb_offers = ctk.CTkCheckBox(opts, text="Ștergere oferte", width=160, font=("Segoe UI", 11))
            cb_offers.select() if can_delete_offers else cb_offers.deselect()
            cb_offers.grid(row=1, column=0, padx=8, pady=4, sticky="w")
            cb_clients = ctk.CTkCheckBox(opts, text="Ștergere clienți", width=160, font=("Segoe UI", 11))
            cb_clients.select() if can_delete_clients else cb_clients.deselect()
            cb_clients.grid(row=1, column=1, columnspan=2, padx=8, pady=4, sticky="w")
            cb_dev_mode = ctk.CTkCheckBox(opts, text="Mod Dev", width=120, font=("Segoe UI", 11))
            cb_dev_mode.select() if can_dev_mode else cb_dev_mode.deselect()
            cb_dev_mode.grid(row=2, column=0, padx=8, pady=4, sticky="w")
            def _save(uid_=uid):
                try:
                    md = int(entry_disc.get().strip() or "0")
                    md = max(0, min(50, md))
                except ValueError:
                    md = 15
                update_user_privileges(
                    self.conn, self.cursor, uid_,
                    1 if cb_curs.get() else 0, md,
                    1 if cb_offers.get() else 0, 1 if cb_clients.get() else 0,
                    1 if cb_dev_mode.get() else 0,
                )
                self._afiseaza_mesaj("Succes", "Privilegii salvate.")
            btns_right = ctk.CTkFrame(f, fg_color="transparent")
            btns_right.pack(side="right", padx=12, pady=10)
            ctk.CTkButton(btns_right, text="Salvează", width=100, height=34, fg_color="#2E7D32", command=_save).pack(side="left", padx=5, pady=4)
            if blocked:
                ctk.CTkButton(btns_right, text="Deblochează", width=100, height=34, fg_color="#2E7D32", command=lambda u=uid: self._toggle_block(u, 0)).pack(side="left", padx=5, pady=4)
            else:
                ctk.CTkButton(btns_right, text="Blochează", width=90, height=34, fg_color="#7a4a1a", command=lambda u=uid: self._toggle_block(u, 1)).pack(side="left", padx=5, pady=4)
            ctk.CTkButton(btns_right, text="Șterge user", width=100, height=34, fg_color="#7a1a1a", command=lambda u=uid, n=nume_complet, un=username: self._sterge_user_dialog(u, n, un)).pack(side="left", padx=5, pady=4)
        self._apply_modern_dark_recursive(self.scroll_privilegii)

    def _show_monitorizare(self, from_back=False):
        if not from_back:
            self._nav_stack.append(self._current_screen)
        self._current_screen = "monitorizare"
        self.frame_meniu.pack_forget()
        self.frame_catalog.pack_forget()
        self.frame_istoric.pack_forget()
        self.frame_privilegii.pack_forget()
        self.btns_cat_frame.pack_forget()
        if hasattr(self, "frame_statistica"):
            self.frame_statistica.pack_forget()
        if hasattr(self, "frame_parametri"):
            self.frame_parametri.pack_forget()
        if hasattr(self, "frame_update_software"):
            self.frame_update_software.pack_forget()
        self.frame_monitorizare.pack(fill="both", expand=True)
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back.pack(side="left", padx=5, pady=4)
        self._refresh_monitorizare()
        self._apply_modern_dark_recursive(self.frame_monitorizare)

    def _show_statistica(self, from_back=False):
        """Afișează tab-ul de statistică oferte."""
        if not from_back:
            self._nav_stack.append(self._current_screen)
        self._current_screen = "statistica"
        self.frame_meniu.pack_forget()
        self.frame_catalog.pack_forget()
        self.frame_istoric.pack_forget()
        self.frame_privilegii.pack_forget()
        self.frame_monitorizare.pack_forget()
        self.btns_cat_frame.pack_forget()
        if hasattr(self, "frame_parametri"):
            self.frame_parametri.pack_forget()
        if hasattr(self, "frame_update_software"):
            self.frame_update_software.pack_forget()
        self.frame_statistica.pack(fill="both", expand=True)
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back.pack(side="left", padx=5, pady=4)
        try:
            self._calculeaza_statistica_zi()
        except Exception:
            logger.exception("Eroare la calcularea statisticii inițiale")
        self._apply_modern_dark_recursive(self.frame_statistica)

    def _show_update_software(self, from_back=False):
        if not from_back:
            self._nav_stack.append(self._current_screen)
        self._current_screen = "update_software"
        self.frame_meniu.pack_forget()
        self.frame_catalog.pack_forget()
        self.frame_istoric.pack_forget()
        self.frame_privilegii.pack_forget()
        self.frame_monitorizare.pack_forget()
        self.btns_cat_frame.pack_forget()
        if hasattr(self, "frame_statistica"):
            self.frame_statistica.pack_forget()
        if hasattr(self, "frame_parametri"):
            self.frame_parametri.pack_forget()
        self.frame_update_software.pack(fill="both", expand=True)
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back.pack(side="left", padx=5, pady=4)
        self._refresh_update_list()
        self._apply_modern_dark_recursive(self.frame_update_software)

    def _refresh_update_list(self) -> None:
        if not hasattr(self, "scroll_update_rows"):
            return
        for w in self.scroll_update_rows.winfo_children():
            w.destroy()
        rows = list_updates_for_admin(limit=20)
        if not rows:
            ctk.CTkLabel(
                self.scroll_update_rows,
                text="Nu există update-uri sau nu există acces la tabela app_updates.",
                text_color="#aaaaaa",
            ).pack(anchor="w", padx=8, pady=8)
            return
        for row in rows:
            text = (
                f"{row.get('version') or '-'} | active={1 if row.get('is_active') else 0} | "
                f"mandatory={1 if row.get('mandatory') else 0} | sha256={'da' if row.get('sha256') else 'nu'}"
            )
            ctk.CTkLabel(self.scroll_update_rows, text=text, anchor="w", justify="left").pack(
                anchor="w", padx=8, pady=2
            )

    def _refresh_monitorizare(self):
        for w in self.scroll_monitorizare_useri.winfo_children():
            w.destroy()
        for w in self.scroll_monitorizare_oferte.winfo_children():
            w.destroy()
        users = get_activity_users_with_counts(self.cursor)
        if not users:
            if hasattr(self, "combo_monitorizare_user"):
                self.combo_monitorizare_user.configure(values=[])
            ctk.CTkLabel(
                self.scroll_monitorizare_useri,
                text="Nu există useri aprobați.",
                font=("Segoe UI", 12),
                text_color="#aaaaaa",
            ).pack(pady=20)
            ctk.CTkLabel(
                self.scroll_monitorizare_oferte,
                text="Selectează un user din listă.",
                font=("Segoe UI", 12),
                text_color="#aaaaaa",
            ).pack(pady=20)
            return
        # Populează meniul derulant cu toți userii (username)
        if hasattr(self, "combo_monitorizare_user") and self.combo_monitorizare_user.winfo_exists():
            valori = [u for (u, _n, _c) in users]
            self.combo_monitorizare_user.configure(values=valori)
            if valori:
                try:
                    self.combo_monitorizare_user.set(valori[0])
                except Exception:
                    pass
                # La încărcare, afișăm implicit ofertele primului user
                self._select_user_oferte(valori[0])
        for username, nume_complet, nr_oferte in users:
            nr_oferte = nr_oferte or 0
            f = ctk.CTkFrame(self.scroll_monitorizare_useri, fg_color="#2D2D2D", corner_radius=4)
            f.pack(fill="x", pady=4, padx=4)
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=8)
            ctk.CTkLabel(inner, text=f"{nume_complet}", font=("Segoe UI", 12), anchor="w").pack(anchor="w")
            ctk.CTkLabel(inner, text=f"{username}  —  {nr_oferte} oferte", font=("Segoe UI", 11), text_color="#aaaaaa", anchor="w").pack(anchor="w")
            ctk.CTkButton(
                inner, text="Vezi oferte", width=100, height=34, fg_color="#2E7D32",
                command=lambda u=username: self._select_user_oferte(u),
            ).pack(anchor="w", pady=(8, 4), padx=(0, 4))
        ctk.CTkLabel(
            self.scroll_monitorizare_oferte,
            text="Selectează un user și apasă „Vezi oferte” pentru detalii.",
            font=("Segoe UI", 12),
            text_color="#888888",
        ).pack(pady=20)
        self._apply_modern_dark_recursive(self.frame_monitorizare)
        self._apply_modern_dark_recursive(self.frame_monitorizare)

    def _select_user_oferte(self, username: str):
        for w in self.scroll_monitorizare_oferte.winfo_children():
            w.destroy()
        rows = get_istoric_oferte_by_user(self.cursor, username)
        if not rows:
            ctk.CTkLabel(
                self.scroll_monitorizare_oferte,
                text=f"Niciun user selectat sau userul nu are oferte.",
                font=("Segoe UI", 12),
                text_color="#aaaaaa",
            ).pack(pady=20)
            return
        for r in rows:
            (id_o, id_client, nume, data, total_lei, detalii, telefon, adresa, utilizator, discount_proc, curs_euro, avans_incasat, safe_mode_enabled) = r
            nr_inreg = str(id_o).zfill(5)
            telefon = telefon or ""
            adresa = adresa or ""
            utilizator = (utilizator or "").strip() or "—"
            discount_proc = discount_proc if discount_proc is not None else 0
            curs_euro = curs_euro if curs_euro is not None else 0
            avans_incasat = 1 if (avans_incasat if avans_incasat is not None else 0) else 0
            safe_mode_enabled = 1 if (safe_mode_enabled if safe_mode_enabled is not None else 1) else 0
            safe_mode_txt = "DA" if safe_mode_enabled else "NU"
            status = "Încasat parțial" if avans_incasat else "În așteptare"
            f = ctk.CTkFrame(self.scroll_monitorizare_oferte, fg_color="#2b2b2b")
            f.pack(fill="x", pady=4, padx=5)
            left = ctk.CTkFrame(f, fg_color="transparent")
            left.pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(
                left,
                text=f"Nr. {nr_inreg}  |  Client: {nume.upper() if nume else '—'}  |  Data: {data}  |  Total: {total_lei:.2f} LEI  |  Status: {status}",
                font=("Segoe UI", 12),
                anchor="w",
            ).pack(anchor="w")
            curs_txt = f"{curs_euro:.4f} LEI" if curs_euro else "—"
            ctk.CTkLabel(
                left,
                text=f"Discount: {discount_proc}%  |  Curs euro: {curs_txt}  |  Safe mode: {safe_mode_txt}",
                font=("Segoe UI", 11),
                text_color="#2E7D32",
                anchor="w",
            ).pack(anchor="w")
            btns = ctk.CTkFrame(f, fg_color="transparent")
            btns.pack(side="right", padx=10, pady=8)
            ctk.CTkButton(
                btns,
                text="Vezi oferta",
                width=100,
                height=34,
                fg_color="#2E7D32",
                command=lambda _n=nume or "", _d=data, _det=detalii, _t=total_lei, _disc=discount_proc, _curs=curs_euro, _st=status, _nr=nr_inreg: self._vezi_oferta(
                    _n, _d, _det, _t, _disc, _curs, _st, _nr
                ),
            ).pack(side="left", padx=5, pady=4)
            ctk.CTkButton(
                btns,
                text="Descarcă PDF",
                width=110,
                height=34,
                fg_color="#F57C00",
                command=lambda _n=nume or "", _d=data, _det=detalii, _t=total_lei, _tel=telefon, _adr=adresa, _disc=discount_proc, _curs=curs_euro, _u=utilizator, _nr=nr_inreg: self._descarca_pdf_oferta(
                    _n, _d, _det, _t, _tel, _adr, _disc, _curs, _u, _nr
                ),
            ).pack(side="left", padx=5, pady=4)
        self._apply_modern_dark_recursive(self.scroll_monitorizare_oferte)
        self._apply_modern_dark_recursive(self.scroll_monitorizare_oferte)

    def _on_select_monitorizare_user(self, username: str):
        """Callback pentru meniul derulant de useri din Monitorizare activitate."""
        username = (username or "").strip()
        if not username:
            return
        try:
            self._select_user_oferte(username)
        except Exception:
            logger.exception("Eroare la încărcarea ofertelor pentru userul selectat din combo Monitorizare")

    def _calculeaza_statistica_zi(self):
        """Calculează statistica ofertelor pentru data introdusă (YYYY-MM-DD)."""
        from datetime import datetime

        data_raw = (self.entry_data_stat.get() or "").strip()
        if not data_raw:
            self.lbl_rezumat_stat.configure(text="Introduceți o dată în format YYYY-MM-DD.")
            return
        try:
            # Validare minimă format (YYYY-MM-DD)
            data_parsata = datetime.strptime(data_raw, "%Y-%m-%d").date()
        except ValueError:
            self.lbl_rezumat_stat.configure(
                text="Format dată invalid. Folosiți formatul YYYY-MM-DD (ex: 2026-03-17)."
            )
            return

        # În baza de date data_oferta este salvată ca string de forma „YYYY-Luna HH:MM” (ex: 2026-Martie 11:32).
        # Construim prefixul „YYYY-Luna” și folosim LIKE 'YYYY-Luna%'.
        luni_ro = [
            "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
            "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
        ]
        luna_txt = luni_ro[data_parsata.month - 1]
        data_prefix = f"{data_parsata.year}-{luna_txt}"
        data_sel = data_parsata.isoformat()

        # Golește panourile
        for w in self.scroll_stat_oferte.winfo_children():
            w.destroy()
        for w in self.scroll_stat_produse.winfo_children():
            w.destroy()

        rows = get_oferte_by_date(self.cursor, data_prefix)
        if not rows:
            self.lbl_rezumat_stat.configure(
                text=f"Nu există oferte înregistrate la data {data_sel}."
            )
            return

        nr_oferte = len(rows)
        suma_totala_zi = 0.0

        # Agregare produse: cele mai ofertate uși, mânere, parchet
        # Cheile vor fi numele produsului; valorile: cantitatea totală
        top_usi: dict[str, float] = {}
        top_manere: dict[str, float] = {}
        top_parchet: dict[str, float] = {}

        for (id_o, nume_client, total_lei, detalii_raw) in rows:
            total_lei = float(total_lei or 0)
            suma_totala_zi += total_lei

            # Afișare ofertă în coloana din stânga
            f = ctk.CTkFrame(self.scroll_stat_oferte, fg_color="#2b2b2b")
            f.pack(fill="x", pady=3, padx=5)
            nr_inreg = str(id_o).zfill(5)
            ctk.CTkLabel(
                f,
                text=f"Nr. {nr_inreg}  |  Client: {nume_client or '—'}  |  Total: {total_lei:.2f} LEI",
                font=("Segoe UI", 11),
                anchor="w",
            ).pack(anchor="w", padx=10, pady=(4, 2))

            # Parsează produsele din ofertă pentru agregare
            try:
                raw = loads_offer_items(detalii_raw)
                produse = raw.get("items", raw) if isinstance(raw, dict) else raw
            except Exception:
                produse = []
            for item in produse or []:
                nume_prod = (item.get("nume") or "").strip()
                if not nume_prod:
                    continue
                qty = float(item.get("qty") or 1)
                tip = (item.get("tip") or "").strip().lower()
                # Uși – tip explicit "usi"
                if tip == "usi":
                    top_usi[nume_prod] = top_usi.get(nume_prod, 0.0) + qty
                # Mânere – fie tip specific, fie nume care conține „maner”
                if tip in ("maner", "accesorii") and "maner" in nume_prod.lower():
                    top_manere[nume_prod] = top_manere.get(nume_prod, 0.0) + qty
                # Parchet – tip "parchet" sau accesorii de parchet
                if tip in ("parchet", "parchet_accesoriu"):
                    top_parchet[nume_prod] = top_parchet.get(nume_prod, 0.0) + qty

        self.lbl_rezumat_stat.configure(
            text=f"Data {data_sel}: {nr_oferte} oferte, total valoare {suma_totala_zi:.2f} LEI."
        )

        def _afiseaza_top(dct: dict[str, float], titlu: str):
            ctk.CTkLabel(
                self.scroll_stat_produse,
                text=titlu,
                font=("Segoe UI", 12),
                text_color="#2E7D32",
            ).pack(anchor="w", padx=8, pady=(6, 2))
            if not dct:
                ctk.CTkLabel(
                    self.scroll_stat_produse,
                    text="Nu există produse pentru această categorie în ziua selectată.",
                    font=("Segoe UI", 10),
                    text_color="#aaaaaa",
                ).pack(anchor="w", padx=12, pady=(0, 4))
                return
            for nume_prod, cant in sorted(dct.items(), key=lambda kv: kv[1], reverse=True)[:10]:
                ctk.CTkLabel(
                    self.scroll_stat_produse,
                    text=f"• {nume_prod}  —  {cant:g} buc",
                    font=("Segoe UI", 10),
                    anchor="w",
                    justify="left",
                ).pack(anchor="w", padx=14, pady=1)

        _afiseaza_top(top_usi, "Uși cele mai ofertate")
        _afiseaza_top(top_manere, "Mânere cele mai ofertate")
        _afiseaza_top(top_parchet, "Parchet / accesorii parchet cele mai ofertate")
        self._apply_modern_dark_recursive(self.frame_statistica)
        self._apply_modern_dark_recursive(self.frame_statistica)

    def _show_catalog(self, from_back=False):
        if not from_back:
            self._nav_stack.append(self._current_screen)
        self._current_screen = "catalog"
        self.frame_meniu.pack_forget()
        self.frame_istoric.pack_forget()
        self.frame_privilegii.pack_forget()
        self.frame_monitorizare.pack_forget()
        if hasattr(self, "frame_update_software"):
            self.frame_update_software.pack_forget()
        if hasattr(self, "frame_statistica"):
            self.frame_statistica.pack_forget()
        if hasattr(self, "frame_parametri"):
            self.frame_parametri.pack_forget()
        self.frame_catalog.pack(fill="both", expand=True)
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back.pack(side="left", padx=5, pady=4)
        self._vizibilitate_form_categorie()
        self._refresh_list()
        self._apply_modern_dark_recursive(self.frame_catalog)

    def _show_istoric(self, from_back=False):
        if not from_back:
            self._nav_stack.append(self._current_screen)
        self._current_screen = "istoric"
        self.frame_meniu.pack_forget()
        self.frame_catalog.pack_forget()
        self.frame_privilegii.pack_forget()
        self.frame_monitorizare.pack_forget()
        if hasattr(self, "frame_update_software"):
            self.frame_update_software.pack_forget()
        self.btns_cat_frame.pack_forget()
        if hasattr(self, "frame_statistica"):
            self.frame_statistica.pack_forget()
        if hasattr(self, "frame_parametri"):
            self.frame_parametri.pack_forget()
        self.frame_istoric.pack(fill="both", expand=True)
        self.btn_meniu.pack(side="left", padx=5, pady=4)
        self.btn_back.pack(side="left", padx=5, pady=4)
        self._refresh_istoric()
        self._apply_modern_dark_recursive(self.frame_istoric)

    def _refresh_istoric(self):
        for w in self.scroll_oferte.winfo_children():
            w.destroy()
        termen_raw = self.ent_cauta_oferte.get().strip()
        termen_like = f"%{termen_raw}%"
        id_egal = int(termen_raw) if termen_raw.isdigit() else None
        rows = get_istoric_oferte_admin(self.cursor, termen_like, id_egal)
        if not rows:
            ctk.CTkLabel(
                self.scroll_oferte,
                text="Nu există oferte salvate.",
                font=("Segoe UI", 12),
                text_color="#aaaaaa",
            ).pack(pady=20)
            return
        for r in rows:
            (id_o, id_client, nume, data, total_lei, detalii, telefon, adresa, utilizator, discount_proc, curs_euro, avans_incasat, safe_mode_enabled) = r
            nr_inreg = str(id_o).zfill(5)
            telefon = telefon or ""
            adresa = adresa or ""
            utilizator = (utilizator or "").strip() or "—"
            discount_proc = discount_proc if discount_proc is not None else 0
            curs_euro = curs_euro if curs_euro is not None else 0
            avans_incasat = 1 if (avans_incasat if avans_incasat is not None else 0) else 0
            safe_mode_enabled = 1 if (safe_mode_enabled if safe_mode_enabled is not None else 1) else 0
            safe_mode_txt = "DA" if safe_mode_enabled else "NU"
            status = "Încasat parțial" if avans_incasat else "În așteptare"
            f = ctk.CTkFrame(self.scroll_oferte, fg_color="#2b2b2b")
            f.pack(fill="x", pady=4, padx=5)
            left = ctk.CTkFrame(f, fg_color="transparent")
            left.pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(
                left,
                text=f"Nr. înreg.: {nr_inreg}  |  Client: {nume.upper()}  |  Data: {data}  |  Total: {total_lei:.2f} LEI  |  Status: {status}",
                font=("Segoe UI", 12),
                anchor="w",
            ).pack(anchor="w")
            curs_txt = f"{curs_euro:.4f} LEI" if curs_euro else "—"
            ctk.CTkLabel(
                left,
                text=f"Ofertat de: {utilizator}  |  Safe mode: {safe_mode_txt}  |  Discount: {discount_proc}%  |  Curs euro la ofertare: {curs_txt}  |  Total LEI (la acest curs): {total_lei:.2f}",
                font=("Segoe UI", 11),
                text_color="#2E7D32",
                anchor="w",
            ).pack(anchor="w")
            btns = ctk.CTkFrame(f, fg_color="transparent")
            btns.pack(side="right", padx=10, pady=8)
            ctk.CTkButton(
                btns,
                text="Vezi oferta",
                width=100,
                height=34,
                fg_color="#2E7D32",
                command=lambda _n=nume, _d=data, _det=detalii, _t=total_lei, _disc=discount_proc, _curs=curs_euro, _st=status, _nr=nr_inreg: self._vezi_oferta(
                    _n, _d, _det, _t, _disc, _curs, _st, _nr
                ),
            ).pack(side="left", padx=5, pady=4)
            ctk.CTkButton(
                btns,
                text="Descarcă PDF",
                width=110,
                height=34,
                fg_color="#F57C00",
                command=lambda _n=nume, _d=data, _det=detalii, _t=total_lei, _tel=telefon, _adr=adresa, _disc=discount_proc, _curs=curs_euro, _u=utilizator, _nr=nr_inreg: self._descarca_pdf_oferta(
                    _n, _d, _det, _t, _tel, _adr, _disc, _curs, _u, _nr
                ),
            ).pack(side="left", padx=5, pady=4)
            ctk.CTkButton(
                btns,
                text="Șterge ofertă",
                width=110,
                height=34,
                fg_color="#7a1a1a",
                command=lambda _id=id_o, _nr=nr_inreg: self._sterge_oferta_dialog(_id, _nr),
            ).pack(side="left", padx=5, pady=4)
        self._apply_modern_dark_recursive(self.scroll_oferte)
        return

    def _sterge_oferta_dialog(self, offer_id: int, nr_inreg: str) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Confirmare ștergere ofertă")
        win.geometry("500x230")
        win.grab_set()
        win.transient(self)

        f = ctk.CTkFrame(win, fg_color="transparent")
        f.pack(expand=True, fill="both", padx=24, pady=20)

        ctk.CTkLabel(
            f,
            text=f"Vrei să ștergi oferta cu nr. {nr_inreg}?",
            font=("Segoe UI", 14, "bold"),
            wraplength=440,
        ).pack(pady=(0, 8))
        ctk.CTkLabel(
            f,
            text="Odată ștearsă, oferta nu va mai putea fi recuperată.",
            font=("Segoe UI", 12),
            text_color="#ff8a8a",
            wraplength=440,
        ).pack(pady=(0, 16))
        ctk.CTkLabel(
            f,
            text="Sigur vrei să continui?",
            font=("Segoe UI", 12),
        ).pack(pady=(0, 12))

        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.pack(pady=(4, 0))

        ctk.CTkButton(
            btns,
            text="Nu",
            width=120,
            height=36,
            fg_color="#444444",
            command=win.destroy,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btns,
            text="Da, șterge",
            width=120,
            height=36,
            fg_color="#7a1a1a",
            command=lambda: self._sterge_oferta(offer_id, win),
        ).pack(side="left", padx=6)

    def _sterge_oferta(self, offer_id: int, dialog: ctk.CTkToplevel | None = None) -> None:
        try:
            delete_offer(self.conn, self.cursor, offer_id)
            if dialog is not None and dialog.winfo_exists():
                dialog.destroy()
            self._refresh_istoric()
            self._afiseaza_mesaj("Succes", "Oferta a fost ștearsă definitiv.")
        except Exception as e:
            logger.exception("Ștergere ofertă eșuată")
            self._afiseaza_mesaj("Eroare", f"Eroare la ștergere ofertă: {e}")

    def _vezi_oferta(self, nume: str, data: str, detalii_raw: str, total_lei: float, discount_proc: int = 0, curs_euro: float = 0, status: str = "În așteptare", nr_inreg: str = ""):
        raw = loads_offer_items(detalii_raw)
        produse = raw.get("items", raw) if isinstance(raw, dict) else raw
        win = ctk.CTkToplevel(self)
        win.title(f"Ofertă Nr. {nr_inreg} – {nume}")
        win.geometry("620x520")
        win.grab_set()
        if nr_inreg:
            ctk.CTkLabel(win, text=f"Nr. înreg.: {nr_inreg}", font=("Segoe UI", 14, "bold"), text_color="#2E7D32").pack(pady=(15, 2))
        ctk.CTkLabel(win, text=f"Client: {nume.upper()}", font=("Segoe UI", 16, "bold")).pack(
            pady=(5, 5)
        )
        ctk.CTkLabel(win, text=f"Data: {data}  |  Status: {status}", font=("Segoe UI", 12)).pack(pady=(0, 5))
        ctk.CTkLabel(
            win,
            text=f"Curs euro la ofertare: {curs_euro:.4f} LEI  |  Total LEI (ajustat la acest curs): {total_lei:.2f}",
            font=("Segoe UI", 12),
            text_color="#2E7D32",
        ).pack(pady=(0, 5))
        ctk.CTkLabel(win, text=f"Discount aplicat: {discount_proc}%", font=("Segoe UI", 12)).pack(
            pady=(0, 15)
        )
        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        for item in produse:
            nume_prod = item.get("nume", "")
            qty = item.get("qty", 1)
            pret_eur = item.get("pret_eur", 0)
            ctk.CTkLabel(
                scroll,
                text=f"• {nume_prod}  x{qty}  ({pret_eur} €/buc)",
                font=("Segoe UI", 11),
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=2)
        ctk.CTkButton(win, text="Închide", width=120, height=36, command=win.destroy).pack(pady=16, padx=8)

    def _descarca_pdf_oferta(
        self,
        nume: str,
        data: str,
        detalii_raw: str,
        total_lei: float,
        telefon: str,
        adresa: str,
        discount_proc: int = 0,
        curs_euro: float = 0,
        utilizator: str = "",
        nr_inreg: str = "",
    ):
        raw = loads_offer_items(detalii_raw)
        produse = raw.get("items", raw) if isinstance(raw, dict) else raw
        masuratori_pdf = float(raw.get("masuratori_lei", 0) or 0) if isinstance(raw, dict) else 0.0
        transport_pdf = float(raw.get("transport_lei", 0) or 0) if isinstance(raw, dict) else 0.0
        conditii_pdf = bool(raw.get("conditii_pdf", False)) if isinstance(raw, dict) else False
        termen_livrare_zile = str(raw.get("termen_livrare_zile", "0") or "0") if isinstance(raw, dict) else "0"
        if not produse:
            self._afiseaza_mesaj("Eroare", "Oferta nu conține produse.")
            return
        cale_salvare = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=f"Oferta_{nume.replace(' ', '_')}.pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not cale_salvare:
            return
        curs_pdf = curs_euro if curs_euro else self.config_app.curs_euro_initial
        # Nume agent care a întocmit oferta – folosim numele complet, nu username-ul tehnic.
        nume_utilizator = None
        try:
            u = (utilizator or "").strip()
            if u:
                nume_utilizator = get_user_full_name(self.cursor, u)
        except Exception:
            nume_utilizator = None
        if not nume_utilizator:
            nume_utilizator = (utilizator or "").strip() or "–"
        nr_inreg_pdf = (nr_inreg or "").strip() or "—"
        contact_tel_pdf = get_user_contact_phone(self.cursor, (utilizator or "").strip()) if (utilizator or "").strip() else None
        if not contact_tel_pdf:
            contact_tel_pdf = PDF_CONTACT_TEL
        try:
            # Folosim același șablon de PDF ca aplicația principală (build_oferta_pret_pdf),
            # cu contact al userului care a făcut oferta (tel. mobil din profil) și nr. înregistrare.
            build_oferta_pret_pdf(
                cale_salvare=cale_salvare,
                nr_inreg=nr_inreg_pdf,
                nume_utilizator=nume_utilizator,
                contact_tel=contact_tel_pdf,
                contact_email=PDF_CONTACT_EMAIL,
                nume_client=nume,
                telefon=telefon,
                adresa=adresa,
                email="",
                cos_cumparaturi=produse,
                discount_proc=discount_proc,
                tva_procent=self.config_app.tva_procent,
                curs_euro=curs_pdf,
                total_lei_cu_discount=total_lei,
                mentiuni=(raw.get("mentiuni", "") or "") if isinstance(raw, dict) else "",
                masuratori_lei=masuratori_pdf,
                transport_lei=transport_pdf,
                conditii_pdf=conditii_pdf,
                termen_livrare_zile=termen_livrare_zile,
                data_comanda=data,
            )
            self._afiseaza_mesaj("Succes", "PDF generat cu succes.")
        except Exception:
            logger.exception("Generare PDF ofertă (admin) eșuată")
            self._afiseaza_mesaj("Eroare", "Nu s-a putut genera PDF-ul ofertei.")

    def _salveaza_produs_manual(self):
        try:
            d = {k: v.get() for k, v in self.inputs.items()}
            pret_str = (d.get("pret") or "").strip().replace(",", ".")
            if not pret_str:
                raise ValueError("Preț obligatoriu")
            pret = float(pret_str)
            if pret < 0:
                raise ValueError("Prețul trebuie să fie în euro (număr pozitiv).")
        except ValueError:
            self._afiseaza_mesaj("Eroare", "Preț invalid. Te rog introdu un număr (preț în euro).")
            return
        except Exception:
            logger.warning("Preț invalid la salvare produs", exc_info=True)
            self._afiseaza_mesaj("Eroare", "Preț invalid, te rog introdu un număr (€).")
            return

        cat = d.get("categorie") or self.cat_selectata
        furnizor = d.get("furnizor") or "Stoc"
        colectie = (d.get("colectie") or "").strip()
        decor = (d.get("decor") or "").strip()
        finisaj = (d.get("finisaj") or "").strip()
        model_raw = (d.get("model") or "").strip()
        modele = [m.strip() for m in model_raw.split(",") if m.strip()]
        if not modele:
            modele = [model_raw or colectie or "Standard"]

        tip_toc = ""
        dimensiune = ""
        finisaje_usi_selectate = []

        if cat == "Tocuri":
            tip_toc = (d.get("tip_toc") or "Fix").strip()
            reglaj = (d.get("reglaj") or "").strip()
            dimensiune = re.sub(r"[^0-9\-]", "", reglaj)
            if dimensiune and not dimensiune.endswith(" MM"):
                dimensiune = dimensiune + " MM"
            colectie = ""
            model_raw = "Toc"
            modele = ["Toc"]
            decor = ""
            finisaj = ""
        elif cat in self.CATEGORII_PARCHET:
            # Parchet: colectie=Colectia, model=Cod produs, dimensiune=MP/cut (ex: 1.8), pret=eur/mp
            reglaj = (d.get("reglaj") or "").strip().replace(",", ".")
            dimensiune = re.sub(r"[^0-9.\-]", "", reglaj) or "0"
            tip_toc = ""
            decor = ""
            finisaj = ""
            furnizor = "Stoc"
        elif cat in ("Usi Interior", "Usi intrare apartament"):
            finisaje_usi_selectate = [f for f, cb in self._check_finisaj_usi.items() if cb.get()]
            if not finisaje_usi_selectate:
                self._afiseaza_mesaj("Eroare", "Selectați cel puțin un finisaj / decor.")
                return
            decor = ""
            finisaj = ""

        try:
            if cat in ("Usi Interior", "Usi intrare apartament") and finisaje_usi_selectate:
                for model in modele:
                    for fin in finisaje_usi_selectate:
                        insert_produs(
                            self.conn, self.cursor,
                            cat, furnizor, colectie, model, "", fin, "", "", pret,
                        )
                self._refresh_list()
                self._afiseaza_mesaj("Succes", f"{len(finisaje_usi_selectate) * len(modele)} produs(e) adăugat(e) în catalog.")
            else:
                for model in modele:
                    insert_produs(
                        self.conn, self.cursor,
                        cat, furnizor, colectie, model, decor, finisaj, tip_toc, dimensiune, pret,
                    )
                self._refresh_list()
                self._afiseaza_mesaj("Succes", f"{len(modele)} produs(e) adăugat(e) în catalog.")
        except Exception as e:
            logger.exception("Salvare produs manual")
            self._afiseaza_mesaj("Eroare", f"Eroare la salvare: {e}")

    def _incarca_excel(self):
        cale_fisier = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if not cale_fisier:
            return
        try:
            xl = pd.ExcelFile(cale_fisier)
            sheet_use = xl.sheet_names[0]
            for sn in xl.sheet_names:
                t = str(sn).strip().lower().replace("\xa0", " ")
                for a, b in (("ă", "a"), ("â", "a"), ("î", "i"), ("ș", "s"), ("ț", "t"), ("ţ", "t")):
                    t = t.replace(a, b)
                t = " ".join(t.split())
                if t == "usi" or t.startswith("usi ") or "import usi" in t:
                    sheet_use = sn
                    break
            df = pd.read_excel(cale_fisier, sheet_name=sheet_use)
            # Normalizare: lowercase + strip; elimină newline/carriage return din header
            cols_map = {}
            for c in df.columns:
                key = str(c).replace("\r", "").replace("\n", " ").replace("\xa0", " ").strip().lower()
                key = " ".join(key.split())
                cols_map[key] = c
                key_alt = key.replace(" / ", "/").replace("  ", " ")
                if key_alt != key:
                    cols_map[key_alt] = c
                key_flat = key.replace("ă", "a").replace("â", "a").replace("î", "i").replace("ș", "s").replace("ț", "t")
                if key_flat != key:
                    cols_map[key_flat] = c

            def get_val(keys, row):
                for k in keys:
                    if k in cols_map:
                        v = row.get(cols_map[k])
                        if pd.isna(v):
                            return ""
                        s = str(v).strip()
                        if s.lower() == "nan":
                            return ""
                        return s
                return ""

            # Detectare fișier parchet: are Colectia, Cod produs, MP/CUT
            file_is_parchet = (
                ("colectia" in cols_map or "colectie" in cols_map)
                and ("cod produs" in cols_map or "model" in cols_map)
                and ("mp/cut" in cols_map or "mp cut" in cols_map)
            )

            count = 0
            last_import_furn: str | None = None
            last_import_cat: str | None = None
            for _, row in df.iterrows():
                if not any(
                    pd.notna(row.get(col)) and str(row.get(col)).strip() not in ("", "nan")
                    for col in df.columns
                ):
                    continue
                furn_val = get_val(["furnizor"], row) or "Stoc"
                cat_val = get_val(["categorie", "categorie produs", "spc/laminat"], row)
                if not cat_val and self.inputs.get("categorie"):
                    cat_val = self.inputs["categorie"].get()
                if not cat_val:
                    cat_val = self.cat_selectata

                # Pentru fișiere tip „template” (Stoc / Erkado),
                # când nu există coloană separată de furnizor:
                # - coloana „Categorie” conține doar Stoc sau Erkado (furnizorul)
                # - categoria reală din aplicație este „Usi Interior” sau „Tocuri”
                #   în funcție de categoria selectată în formular.
                if "furnizor" not in cols_map:
                    cat_norm = (cat_val or "").strip().lower()
                    if cat_norm in ("stoc", "erkado"):
                        furn_val = cat_val or furn_val
                        # Dacă în formular este selectat "Tocuri", păstrăm categoria Tocuri;
                        # altfel folosim "Usi Interior" (comportamentul existent pentru uși).
                        if self.cat_selectata == "Tocuri":
                            cat_val = "Tocuri"
                        else:
                            cat_val = "Usi Interior"
                # Dacă fișierul e parchet, forțăm categoria parchet (dropdown sau implicit)
                if file_is_parchet and cat_val not in self.CATEGORII_PARCHET:
                    cat_val = (self.inputs.get("categorie") and self.inputs["categorie"].get()) or self.cat_selectata
                    if cat_val not in self.CATEGORII_PARCHET:
                        cat_val = self.CATEGORII_PARCHET[0] if self.CATEGORII_PARCHET else "Parchet Laminat Stoc"
                col_val = get_val(["colectia", "colectie", "colecție"], row)
                mod_raw = get_val(["cod produs", "cod_prod", "cod produs ", "model"], row)
                # Pentru accesorii (ex: plinte), „Denumire” / „Culoare” pot ține loc de decor.
                dec_val = get_val(
                    ["decor", "décor (denumire)", "culoare", "denumire"],
                    row,
                )
                fin_val = get_val(["finisaj", "finisaje"], row)

                # Coloană generică de preț (fallback); pentru parchet se recalculează mai jos.
                pret_key = next(
                    (k for k in [
                        "pret lista eur fara tva/mp",
                        "pret lista eur fara tva",
                        "pret lista eur fara tva/buc",
                        "pret_eur_fara_tva",
                        "pret eur/mp",
                        "pret eur/buc",
                        "pret eur fara tva",
                        "pret lista",
                        "preț listă",
                        "pret listă",
                        "pret",
                        "preț",
                    ] if k in cols_map),
                    None,
                )
                if not pret_key:
                    # Orice antet cu „pret/preț” + „lista/listă” (ex: „Pret lista (EUR)”)
                    for k in cols_map:
                        kl = k.replace("ț", "t").replace("ș", "s")
                        if "pret" in kl and ("lista" in kl or "listă" in k):
                            pret_key = k
                            break
                if not pret_key:
                    # Fallback generic: orice coloană care conține „pret” și „eur”
                    for k in cols_map:
                        if "pret" in k and "eur" in k:
                            pret_key = k
                            break
                try:
                    pret_val = float(str(row[cols_map[pret_key]]).replace(",", ".").strip() or "0") if pret_key else 0.0
                except (ValueError, TypeError, KeyError):
                    pret_val = 0.0

                tip_toc_val = ""
                dimensiune_val = ""
                if cat_val == "Tocuri":
                    tip_toc_excel = get_val(["tip_toc", "tip toc", "tipul tocului", "tip"], row)
                    tip_raw = (tip_toc_excel or "").strip().lower()
                    # Acceptăm orice valoare care conține „reglabil” (ex: „Toc reglabil”, „Reglabil Drept”)
                    tip_toc_val = "Reglabil" if "reglabil" in tip_raw else "Fix"
                    reglaj_excel = get_val(["reglaj", "reglajul", "dimensiune"], row)
                    dimensiune_val = re.sub(r"[^0-9\-]", "", (reglaj_excel or ""))
                    if dimensiune_val and not dimensiune_val.endswith(" MM"):
                        dimensiune_val = dimensiune_val + " MM"
                    col_val = ""
                    mod_raw = "Toc"
                    modele = ["Toc"]
                    dec_val = ""
                    # Păstrăm finisajul din Excel (coloana Finisaj) pentru tocuri Erkado
                    fin_val = get_val(["finisaj", "finisaje"], row) or fin_val
                elif cat_val in self.CATEGORII_PARCHET:
                    col_val = get_val(["colectia", "colectie", "colecție"], row)
                    mod_raw = get_val(["cod produs", "model"], row)
                    # Doar coloane explicite MP/cut – NU „Dimensiune” (e măsura fizică 1200x191x7,5MM și dă numere greșite)
                    mp_cut_excel = get_val(["mp/cut", "mp cut", "mp / cut", "mp/cut (sq m)", "mp/cut"], row)
                    if not mp_cut_excel:
                        for k in cols_map:
                            if ("mp" in k and "cut" in k) and "dimensiune" not in k:
                                v = row.get(cols_map[k])
                                if not pd.isna(v) and str(v).strip():
                                    mp_cut_excel = str(v).strip()
                                    break
                    raw = (mp_cut_excel or "").replace(",", ".").strip()
                    dimensiune_val = re.sub(r"[^0-9.\-]", "", raw) or "0"
                    try:
                        mp_float = float(dimensiune_val)
                        if mp_float > 100:
                            dimensiune_val = "0"
                    except (ValueError, TypeError):
                        dimensiune_val = "0"
                    # Ambele formulări: "Pret lista eur fara TVA/mp" (Naturen STOC) și "Pret lista eur fara TVA" (Naturen_Kronotex_Falquon)
                    pret_key_parchet = next(
                        (k for k in [
                            "pret lista eur fara tva/mp", "pret lista eur fara tva",
                            "pret eur/mp", "pret eur fara tva", "pret", "preț", "price"
                        ] if k in cols_map),
                        None,
                    )
                    if not pret_key_parchet:
                        for k in cols_map:
                            if "pret" in k and "eur" in k and ("mp" in k or "m2" in k or "sqm" in k or "tva" in k):
                                pret_key_parchet = k
                                break
                    if pret_key_parchet:
                        try:
                            pret_val = float(str(row[cols_map[pret_key_parchet]]).replace(",", ".").strip() or "0")
                        except (ValueError, TypeError):
                            pret_val = 0.0
                    furn_val = "Stoc"
                    dec_val = ""
                    fin_val = ""
                    tip_toc_val = ""
                    # Sari rânduri parchet fără colectie sau cod produs
                    if not col_val and not mod_raw:
                        continue
                elif cat_val == "Accesorii":
                    # Pentru accesorii (plinte): denumire -> colectie, culoare rămâne în decor, dimensiune din coloană.
                    col_val = get_val(["denumire", "denumirea"], row) or col_val
                    dec_val = get_val(["culoare", "decor"], row) or dec_val
                    dim_raw = get_val(["dimensiune", "dimensiun"], row)
                    dimensiune_val = (dim_raw or "").strip()

                modele = [m.strip() for m in (mod_raw or "").split(",") if m.strip()]
                if not modele:
                    modele = [(col_val or "").strip() or "Standard"]
                dec_val = (dec_val or "").strip()
                fin_val = (fin_val or "").strip()

                # Fără colecție/model real și fără preț: cel mai adesea rând Excel gol / incomplet (evită „Standard” la 0 €)
                if cat_val not in self.CATEGORII_PARCHET and cat_val != "Tocuri":
                    if pret_val <= 0 and not str(mod_raw or "").strip() and not str(col_val or "").strip():
                        continue

                for m in modele:
                    m_ins = m
                    if cat_val in self.CATEGORII_PARCHET and m:
                        try:
                            m_ins = str(int(float(m.replace(",", "."))))
                        except (ValueError, TypeError):
                            m_ins = m
                    insert_produs(
                        self.conn, self.cursor,
                        cat_val, furn_val, col_val, m_ins, dec_val, fin_val, tip_toc_val, dimensiune_val, pret_val,
                    )
                    count += 1
                    last_import_furn = furn_val
                    last_import_cat = cat_val

            if count > 0 and last_import_furn and last_import_cat:
                self._sync_ui_furnizor_categorie(last_import_furn, last_import_cat)
            else:
                self._refresh_list()
            if count == 0:
                self._afiseaza_mesaj(
                    "Import Excel",
                    "Nu s-a importat niciun produs.\n\n"
                    "Verifică:\n"
                    "• Foaia corectă (se caută «Uși» sau prima foaie).\n"
                    "• Coloane: Categorie, Furnizor, Colectie, Model, Finisaj, Decor, Pret lista (preț > 0).",
                )
            else:
                self._afiseaza_mesaj(
                    "Succes",
                    f"Import finalizat: {count} produs(e) adăugat(e).\n"
                    f"Lista afișează acum Furnizor «{last_import_furn}», Categorie «{last_import_cat}».",
                )
        except Exception as e:
            logger.exception("Import Excel eșuat")
            self._afiseaza_mesaj("Eroare", f"Eroare la import Excel: {e}")

    def _catalog_row_text(self, r: tuple, c_val: str) -> str:
        furn, col, mod, dec = r[1], r[2], r[3], r[4]
        fin = (r[5] or "")
        tip_toc = (r[6] or "").strip()
        dimensiune = (r[7] or "").strip()
        pret = r[8]
        if c_val == "Tocuri":
            dim_afis = dimensiune if dimensiune.endswith(" MM") else (f"{dimensiune} MM" if dimensiune else "")
            text = f"Toc {tip_toc}"
            if dim_afis:
                text += f" Drept {dim_afis}"
            if fin:
                text += f" – {fin}"
            text += f" | {pret} €"
        elif c_val in self.CATEGORII_PARCHET:
            text = f"Colectia {col} | Cod produs {mod} | MP/cut {dimensiune or '—'} | {pret} €/mp"
        elif c_val == "Plinta parchet":
            den = (col or "").strip()
            cod = (mod or "").strip()
            culoare = (dec or "").strip()
            parts_nume: list[str] = []
            if den:
                parts_nume.append(den)
            if cod:
                parts_nume.append(cod)
            if culoare:
                parts_nume.append(culoare)
            eticheta = " ".join(parts_nume) if parts_nume else "—"
            text = f"{eticheta} | {pret} €"
        else:
            afis_fin = (fin or dec or "—").strip()
            text = f"{col} {mod} {afis_fin} | {pret} €"
        return text

    def _refresh_list(self):
        self._catalog_list_refresh_id += 1
        rid = self._catalog_list_refresh_id
        for w in self.list_frame.winfo_children():
            w.destroy()
        furnizor = self.inputs.get("furnizor")
        categorie = self.inputs.get("categorie")
        c_val = categorie.get() if categorie else self.cat_selectata
        f_val = "Stoc" if c_val in self.CATEGORII_PARCHET else (furnizor.get() if furnizor else self.furnizor_selectat)

        loading = ctk.CTkLabel(
            self.list_frame,
            text="Se încarcă produsele…",
            font=("Segoe UI", 12),
            text_color="#aaaaaa",
        )
        loading.pack(pady=24)
        try:
            self.update_idletasks()
        except Exception:
            pass

        def _fetch_and_start_build() -> None:
            if rid != self._catalog_list_refresh_id:
                return
            try:
                rows = get_produse_for_admin_list(self.cursor, f_val, c_val)
            except Exception as e:
                logger.exception("Încărcare listă catalog admin")
                if rid != self._catalog_list_refresh_id:
                    return
                try:
                    loading.destroy()
                except Exception:
                    pass
                ctk.CTkLabel(
                    self.list_frame,
                    text=f"Eroare la încărcare: {e}",
                    font=("Segoe UI", 12),
                    text_color="#ff5555",
                    wraplength=520,
                ).pack(pady=20)
                return
            if rid != self._catalog_list_refresh_id:
                return
            try:
                loading.destroy()
            except Exception:
                pass
            if not rows:
                ctk.CTkLabel(
                    self.list_frame,
                    text="Nu există produse în această categorie încă.",
                    font=("Segoe UI", 12),
                    text_color="#aaaaaa",
                ).pack(pady=20)
                return

            chunk_size = 45

            def _build_chunk(start: int) -> None:
                if rid != self._catalog_list_refresh_id:
                    return
                end = min(start + chunk_size, len(rows))
                for i in range(start, end):
                    r = rows[i]
                    fr = ctk.CTkFrame(self.list_frame)
                    fr.pack(fill="x", pady=2, padx=5)
                    text = self._catalog_row_text(r, c_val)
                    ctk.CTkLabel(fr, text=text, anchor="w", justify="left").pack(side="left", padx=10, pady=4)
                    ctk.CTkButton(
                        fr,
                        text="Șterge",
                        width=70,
                        height=32,
                        fg_color="#7a1a1a",
                        command=lambda idx=r[0]: self._sterge_produs(idx),
                    ).pack(side="right", padx=8, pady=4)
                if end < len(rows):
                    try:
                        self.list_frame.update_idletasks()
                    except Exception:
                        pass
                    self.after(1, lambda s=end: _build_chunk(s))

            _build_chunk(0)

        self.after(12, _fetch_and_start_build)

    def _sterge_produs(self, prod_id: int):
        try:
            delete_produs(self.conn, self.cursor, prod_id)
            self._refresh_list()
        except Exception as e:
            logger.exception("Ștergere produs eșuată")
            self._afiseaza_mesaj("Eroare", f"Eroare la ștergere: {e}")

    def _afiseaza_mesaj(self, titlu: str, mesaj: str):
        win = ctk.CTkToplevel(self)
        win.title(titlu)
        win.geometry("420x200")
        win.grab_set()
        ctk.CTkLabel(win, text=mesaj, wraplength=380, font=("Segoe UI", 13)).pack(expand=True, pady=25, padx=20)
        ctk.CTkButton(win, text="OK", width=100, height=36, fg_color="#2E7D32", command=win.destroy).pack(pady=16, padx=8)

