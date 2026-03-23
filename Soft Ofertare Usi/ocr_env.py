"""
Configurare căi Tesseract și Poppler pentru OCR din PDF (pytesseract + pdf2image).
Importă la începutul scriptului:  import ocr_env  sau  from ocr_env import configure_ocr
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytesseract

# Opțional: setează în mediu sau în .env înainte de rulare
# setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
# setx POPPLER_PATH "C:\poppler\Library\bin"


def _resolve_tesseract_exe() -> str | None:
    env = os.environ.get("TESSERACT_CMD", "").strip()
    if env and os.path.isfile(env):
        return env
    w = shutil.which("tesseract")
    if w:
        return w
    for p in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.isfile(p):
            return p
    return None


def _resolve_poppler_bin_dir() -> str | None:
    env = os.environ.get("POPPLER_PATH", "").strip()
    if env and os.path.isdir(env) and (
        os.path.isfile(os.path.join(env, "pdftoppm.exe"))
        or os.path.isfile(os.path.join(env, "pdftoppm"))
    ):
        return env
    w = shutil.which("pdftoppm")
    if w:
        return os.path.dirname(w)
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        base = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if base.is_dir():
            for pdftoppm in sorted(base.glob("oschwartz10612.Poppler_*/**/Library/bin/pdftoppm.exe")):
                if pdftoppm.is_file():
                    return str(pdftoppm.parent)
    return None


def _apply_project_tessdata_prefix() -> None:
    """
    Dacă există tessdata/ lângă rădăcina proiectului (folderul exterior «Soft Ofertare Usi»),
    setează TESSDATA_PREFIX ca Tesseract să găsească limbi extra (ex. ron) fără scriere în Program Files.
    """
    app_dir = Path(__file__).resolve().parent
    project_root = app_dir.parent
    local_td = project_root / "tessdata"
    if local_td.is_dir() and any(local_td.glob("*.traineddata")):
        # Build-ul Windows (UB Mannheim) rezolvă datele ca PREFIX/ron.traineddata
        os.environ["TESSDATA_PREFIX"] = str(local_td)


def configure_ocr() -> tuple[str | None, str | None]:
    """
    Setează pytesseract.pytesseract.tesseract_cmd dacă găsește executabilul.
    Returnează (cale_tesseract, folder_poppler_bin) — folosește folderul Poppler la pdf2image:
        convert_from_path(pdf_path, poppler_path=poppler_bin)
    """
    _apply_project_tessdata_prefix()
    tess = _resolve_tesseract_exe()
    if tess:
        pytesseract.pytesseract.tesseract_cmd = tess
    poppler = _resolve_poppler_bin_dir()
    return tess, poppler
