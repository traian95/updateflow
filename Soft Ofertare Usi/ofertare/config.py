from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Any, Dict

# Nume fișier DB folosit în get_database_path (doar pentru logică, nu pentru UI).
DB_FILENAME = "date_ofertare.db"

# Fișier JSON opțional cu setări modificabile din Admin (parametri calcul etc.).
SETTINGS_FILENAME = "app_settings.json"

DATA_MODE_ENV = "SOFT_OFERTARE_MODE"
DATA_MODE_LOCAL = "local"
DATA_MODE_AZURE_SYNC = "azure_sync"

# Timeout (secunde) pentru request BNR (folosit în services).
BNR_TIMEOUT_S = 5

# Contact afișat în PDF-ul ofertei (template „OFERTA DE PRET”) – folosit de aplicația de ofertare și de admin.
PDF_CONTACT_TEL = "0775 154 770"
PDF_CONTACT_EMAIL = "magazin.bucuresti@naturen.ro"


def _get_user_db_dir() -> str:
    """
    Director sigur pentru fișierul SQLite, cu drepturi de scriere pentru utilizatorul curent.
    Ordine: SOFT_OFERTARE_DB_DIR (env) -> %APPDATA%\\Soft Ofertare Usi -> ~\\Soft Ofertare Usi.
    """
    env_dir = os.environ.get("SOFT_OFERTARE_DB_DIR", "").strip()
    if env_dir:
        return env_dir
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return os.path.join(appdata, "Soft Ofertare Usi")
    return os.path.join(os.path.expanduser("~"), "Soft Ofertare Usi")


def get_database_path() -> str:
    """
    Calea bazei de date locale.
    1) DATABASE_PATH (env) → folosită exact.
    2) În modul azure_sync: se folosește întotdeauna directorul partajat
       (APPDATA/Soft Ofertare Usi) ca să folosească aceeași bază atât Ofertare cât și Admin.
    3) Altfel: locația legacy lângă exe dacă există și e scriibilă; altfel director sigur.
    """
    from .paths import resolve_asset_path

    explicit = os.environ.get("DATABASE_PATH", "").strip()
    if explicit:
        return explicit

    logger = logging.getLogger(__name__)
    legacy_path = resolve_asset_path(DB_FILENAME)

    def _is_writable(path: str) -> bool:
        if os.path.exists(path):
            return os.access(path, os.W_OK)
        return os.access(os.path.dirname(path) or ".", os.W_OK)

    # În modul azure_sync, Ofertare și Admin trebuie să folosească aceeași bază de date.
    # Forțăm calea partajată (APPDATA) ca să apară ofertele și userii în ambele aplicații.
    if get_data_mode() == DATA_MODE_AZURE_SYNC:
        user_dir = _get_user_db_dir()
        try:
            os.makedirs(user_dir, exist_ok=True)
        except Exception:
            logger.exception("Nu s-a putut crea directorul pentru baza de date: %s", user_dir)
            return legacy_path
        shared_path = os.path.join(user_dir, DB_FILENAME)
        # Migrare o singură dată: dacă există DB lângă exe dar nu în APPDATA, copiem acolo.
        if not os.path.exists(shared_path) and os.path.exists(legacy_path):
            try:
                shutil.copy2(legacy_path, shared_path)
                logger.info(
                    "Mod azure_sync: baza de date a fost copiată în locația partajată: %s",
                    shared_path,
                )
            except Exception:
                logger.exception("Copiere bază în locația partajată eșuată; se folosește %s", shared_path)
        return shared_path

    if os.path.exists(legacy_path) and _is_writable(legacy_path):
        return legacy_path

    user_dir = _get_user_db_dir()
    try:
        os.makedirs(user_dir, exist_ok=True)
    except Exception:
        logger.exception("Nu s-a putut crea directorul pentru baza de date: %s", user_dir)
        return legacy_path

    new_path = os.path.join(user_dir, DB_FILENAME)
    if os.path.exists(new_path):
        return new_path

    if os.path.exists(legacy_path) and not _is_writable(legacy_path):
        try:
            shutil.copy2(legacy_path, new_path)
            logger.warning(
                "Baza de date din %s era doar în citire. Copiată în: %s",
                legacy_path,
                new_path,
            )
            return new_path
        except Exception:
            logger.exception(
                "Nu s-a putut copia baza legacy în %s. Se folosește o bază nouă.", new_path
            )

    return new_path


def get_data_mode() -> str:
    """
    Mod de lucru cu datele:
      - "local" (default): doar SQLite local.
      - "azure_sync": SQLite local ca cache + Azure SQL ca sursă centrală,
        cu mecanism de sync la pornire și periodic.

    Se controlează prin variabila de mediu SOFT_OFERTARE_MODE sau prin câmpul
    `data_mode` din app_settings.json (AppConfig).
    """
    mode_env = os.environ.get(DATA_MODE_ENV, "").strip().lower()
    if mode_env:
        return mode_env
    try:
        cfg = AppConfig()
        if getattr(cfg, "data_mode", "").strip():
            return (cfg.data_mode or "").strip().lower()
    except Exception:
        pass
    return DATA_MODE_LOCAL


def get_settings_path() -> str:
    """Calea fișierului JSON cu setări de configurare modificabile din Admin (locație scriibilă)."""
    from .paths import get_app_dir

    return os.path.join(get_app_dir(), SETTINGS_FILENAME)


def _env_or_fallback(key: str, fallback: str) -> str:
    return os.environ.get(key, "").strip() or fallback


class AppConfig:
    # Keep defaults identical to existing app behavior.
    title: str = "Sistem Gestiune Pro v12.0"
    geometry: str = "1400x900"

    parola_admin: str = "admin123"
    curs_bnr_fallback: float = 5.00
    curs_markup_percent: float = 1.01
    curs_euro_initial: float = 5.15
    tva_procent: int = 21

    # Login aplicație principală: din env (LOGIN_USER, LOGIN_PASSWORD) sau fallback doar pentru development.
    login_user: str = _env_or_fallback("LOGIN_USER", "traianc")
    login_password: str = _env_or_fallback("LOGIN_PASSWORD", "admin123")

    # Login admin: din env (ADMIN_USER, ADMIN_PASSWORD) sau fallback pentru development.
    admin_user: str = _env_or_fallback("ADMIN_USER", "admin123")
    admin_password: str = _env_or_fallback("ADMIN_PASSWORD", "admin123")

    # Mod de lucru cu datele (vezi get_data_mode).
    # Poate fi suprascris și din app_settings.json prin cheia "data_mode".
    data_mode: str = DATA_MODE_LOCAL

    # Parametri calcul uși duble / tocuri / glisare (editabili din Admin).
    usa_dubla_factor_stoc: float = 2.35
    usa_dubla_factor_erkado: float = 2.0
    usa_dubla_plus_erkado: float = 37.0
    toc_dublu_factor_stoc: float = 2.0
    toc_dublu_factor_erkado: float = 1.30
    glisare_plus_stoc: float = 26.0
    glisare_plus_cu_inchidere: float = 47.0

    # Debară – doar uși/tocuri Stoc (factor ușă = același cu ușa dublă Stoc: usa_dubla_factor_stoc).
    debara_toc_reglabil_factor_stoc: float = 1.5
    debara_toc_fix_factor_stoc: float = 2.0

    def __init__(self) -> None:
        """Încarcă eventuale suprascrieri din fișierul JSON de setări."""
        settings_path = get_settings_path()
        data: Dict[str, Any] = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    data = raw
            except Exception:
                # Dacă fișierul este corupt, îl ignorăm și mergem pe valori default.
                data = {}
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

        # Dacă nu există în fișier, se folosește fallback-ul din env pentru data_mode.
        if not getattr(self, "data_mode", "").strip():
            self.data_mode = get_data_mode()


