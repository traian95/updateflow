"""
Extrage rânduri tip mânere din PDF scanat (OCR) → CSV compatibil cu manere_sortate_from_inline.
Necesită: Tesseract (limba română), Poppler, pip: pytesseract pdf2image pandas pillow.
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance

from ocr_env import configure_ocr

# PDF-uri scanate mari la 300 DPI depășesc limita PIL implicită
Image.MAX_IMAGE_PIXELS = 500_000_000


def curata_pret(valoare) -> float:
    """Elimină stelutele, spațiile și alege prima variantă în caz de '/'."""
    if not valoare:
        return 0.0
    curat = str(valoare).split("/")[0].replace("*", "").strip()
    curat = curat.replace(",", ".")
    try:
        return float(re.sub(r"[^\d.]", "", curat))
    except (ValueError, TypeError):
        return 0.0


def _pare_pret_token(tok: str) -> bool:
    t = tok.replace("*", "").strip()
    return bool(re.search(r"\d+[.,]\d", t))


def _pregateste_pagina_pentru_ocr(img: Image.Image, max_latime: int = 3600) -> Image.Image:
    """Tonuri de gri, contrast, redimensionare ușoară — ajută OCR pe scanări mari."""
    g = img.convert("L")
    w, h = g.size
    if w > max_latime:
        nh = int(h * (max_latime / w))
        g = g.resize((max_latime, nh), Image.Resampling.LANCZOS)
    return ImageEnhance.Contrast(g).enhance(1.38)


def _looks_like_model_token(t: str) -> bool:
    """Cod produs / nume model: MAJUSCULE, litere+cifre (ex. ATR7SPZ, ARABIS, ASQ5)."""
    t = t.rstrip(".,;:|")
    if len(t) < 2:
        return False
    if len(t) >= 3 and t.isupper():
        return bool(re.match(r"^[A-Z0-9\.\-]+$", t))
    if len(t) >= 4 and re.match(r"^[A-Z]{2,}\d", t):
        return True
    return bool(re.match(r"^[A-Z]{2,}[0-9]+[A-Z0-9]*$", t))


def _preturi_coerente(preturi: list[float]) -> bool:
    """Respinge rânduri unde OCR a repetat prețul mânerului în coloanele de accesorii."""
    if len(preturi) != 4:
        return False
    a, b, c, d = preturi
    if abs(a - b) < 0.01 and abs(a - c) < 0.01 and abs(a - d) < 0.01:
        return False
    # preț mâner = OB = PZ — aproape mereu eroare de citire
    if abs(a - b) < 0.01 and abs(a - c) < 0.01:
        return False
    # prima coloană duplicată ca OB (scan tabel strâmb)
    if abs(a - b) < 0.01:
        return False
    return True


def _extrage_ultimele_4_preturi(linie: str) -> tuple[str, list[float]] | None:
    """Returnează (partea din stânga, [pret_maner, ob, pz, wc]) sau None."""
    parti = linie.split()
    if len(parti) < 4:
        return None
    preturi: list[float] = []
    idx_pret: list[int] = []
    for i in range(len(parti) - 1, -1, -1):
        if not _pare_pret_token(parti[i]):
            continue
        v = curata_pret(parti[i])
        if v <= 0:
            continue
        preturi.append(v)
        idx_pret.append(i)
        if len(preturi) == 4:
            break
    if len(preturi) < 4:
        return None
    preturi.reverse()
    idx_pret.reverse()
    lead = " ".join(parti[: idx_pret[0]]).strip()
    if not lead:
        return None
    return lead, preturi


def _parse_lead(lead: str, model_curent: str | None) -> tuple[str, str]:
    """
    Din textul dinaintea prețurilor: model (MAJUSCULE) + finisaj.
    Linii fără model nou folosesc model_curent.
    """
    lead = lead.strip().strip(",").strip()
    if not lead:
        return model_curent or "", ""

    tokens = lead.split()
    if not tokens:
        return model_curent or "", ""

    t0 = tokens[0].rstrip(".,;:|")
    # Model: token tip cod / nume sau două tokenuri tip "ARABIS R"
    if _looks_like_model_token(t0):
        model = t0
        rest_start = 1
        if (
            len(tokens) > 1
            and tokens[1].isupper()
            and len(tokens[1]) <= 3
            and not _pare_pret_token(tokens[1])
        ):
            model = f"{t0} {tokens[1]}"
            rest_start = 2
        finisaj = " ".join(tokens[rest_start:]).strip()
        return model, finisaj

    if model_curent:
        return model_curent, lead

    return "", lead


def curata_text_finisaj(s: str) -> str:
    """Elimină artefacte OCR comune din coloana Finisaje."""
    s = str(s).strip().strip('"').strip("'")
    s = re.sub(r"^\s*[\|¦]+\s*", "", s)
    s = re.sub(r"^\s*cod:\s*", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def curata_text_model(s: str) -> str:
    s = str(s).strip().rstrip(".,")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def incarca_modele_referinta(cale: Path) -> list[str]:
    """Coloana «Model» din manere_sortate_final.csv sau primul CSV cu coloană Model."""
    df = pd.read_csv(cale, encoding="utf-8-sig")
    col = None
    for c in df.columns:
        if str(c).strip().lower() in ("model", "nume_model", "nume model"):
            col = c
            break
    if col is None:
        col = df.columns[0]
    return sorted({str(x).strip() for x in df[col].dropna() if str(x).strip()})


def aliniaza_modele_la_referinta(nume_ocr: str, referinte: list[str], prag: float = 0.68) -> str:
    """Înlocuiește cu numele din referință dacă similaritatea e suficientă."""
    if not nume_ocr or not referinte:
        return curata_text_model(nume_ocr)
    n = curata_text_model(nume_ocr)
    best: tuple[str, float] = ("", 0.0)
    for r in referinte:
        ratio = difflib.SequenceMatcher(None, n.upper(), r.upper()).ratio()
        if ratio > best[1]:
            best = (r, ratio)
    if best[1] >= prag:
        return best[0]
    return n


def dedupe_randuri_ocr(df: pd.DataFrame) -> pd.DataFrame:
    """Elimină duplicate identice (același model, finisaj, 4 prețuri)."""
    if df.empty:
        return df
    cols = ["Nume Mâner", "Finisaje", "Preț Mâner", "Preț OB", "Preț PZ", "Preț WC"]
    return df.drop_duplicates(subset=cols, keep="first").reset_index(drop=True)


def finalizeaza_ocr_dataframe(
    df: pd.DataFrame,
    referinta_models: Path | None,
    prag_referinta: float,
) -> pd.DataFrame:
    df = df.copy()
    df["Nume Mâner"] = df["Nume Mâner"].map(curata_text_model)
    df["Finisaje"] = df["Finisaje"].map(curata_text_finisaj)
    df = dedupe_randuri_ocr(df)
    if referinta_models and referinta_models.is_file():
        ref = incarca_modele_referinta(referinta_models)
        df["Nume Mâner"] = df["Nume Mâner"].map(lambda x: aliniaza_modele_la_referinta(x, ref, prag_referinta))
    if df.empty:
        return df
    return df.sort_values(
        by=["Nume Mâner", "Finisaje"],
        key=lambda s: s.astype(str).str.lower(),
    ).reset_index(drop=True)


def extrage_din_pdf(
    cale_pdf: str | Path,
    dpi: int = 300,
    lang: str = "ron+eng",
    tesseract_config: str = "--oem 3 --psm 6",
) -> pd.DataFrame:
    tess, poppler = configure_ocr()
    if not tess:
        raise RuntimeError(
            "Tesseract nu a fost găsit. Setează TESSERACT_CMD sau instalează Tesseract."
        )

    kwargs: dict = {"dpi": dpi}
    if poppler:
        kwargs["poppler_path"] = poppler

    pagini = convert_from_path(str(cale_pdf), **kwargs)

    randuri: list[dict] = []
    model_curent: str | None = None

    for pagina in pagini:
        preg = _pregateste_pagina_pentru_ocr(pagina)
        text = pytesseract.image_to_string(
            preg,
            lang=lang,
            config=tesseract_config,
        )
        for linie in text.split("\n"):
            linie = linie.strip()
            if not linie or len(linie) < 8:
                continue
            if re.match(r"^(pret|preț|finisaj|nume|mâner|maner)\b", linie, re.I):
                continue

            out = _extrage_ultimele_4_preturi(linie)
            if not out:
                continue
            lead, preturi = out
            if not _preturi_coerente(preturi):
                continue
            model, finisaj = _parse_lead(lead, model_curent)
            if model:
                model_curent = model
            if not model_curent:
                continue

            randuri.append(
                {
                    "Nume Mâner": model_curent,
                    "Finisaje": finisaj,
                    "Preț Mâner": preturi[0],
                    "Preț OB": preturi[1],
                    "Preț PZ": preturi[2],
                    "Preț WC": preturi[3],
                }
            )

    return pd.DataFrame(randuri)


def _cale_explode_manere() -> Path:
    """scripts/explode_manere.py relativ la rădăcina proiectului (folderul «Soft Ofertare Usi» exterior)."""
    return Path(__file__).resolve().parent.parent / "scripts" / "explode_manere.py"


def explode_manere_final(ocr_csv: Path, final_csv: Path) -> None:
    """Apelează scripts/explode_manere.py → manere_final.csv sortat."""
    script = _cale_explode_manere()
    if not script.is_file():
        raise FileNotFoundError(f"Lipsește {script}")
    subprocess.check_call(
        [sys.executable, str(script), str(ocr_csv), "-o", str(final_csv)],
    )


def main() -> None:
    p = argparse.ArgumentParser(description="OCR PDF mânere → CSV (+ opțional manere_final)")
    p.add_argument(
        "pdf",
        type=Path,
        nargs="+",
        help="Unul sau mai multe PDF-uri scanate",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="CSV OCR combinat (implicit: manere_ocr_combined.csv dacă sunt 2+ fișiere, altfel <pdf>.ocr.csv)",
    )
    p.add_argument(
        "--manere-final",
        type=Path,
        default=None,
        help="Ieșire explode (implicit: manere_final.csv în folderul programului)",
    )
    p.add_argument(
        "--skip-explode",
        action="store_true",
        help="Nu genera manere_final.csv (doar CSV-ul intermediar OCR)",
    )
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument(
        "--lang",
        default="ron+eng",
        help="Limbi Tesseract (implicit: ron+eng)",
    )
    p.add_argument(
        "--tesseract-config",
        default="--oem 3 --psm 6",
        help="Argumente extra pentru Tesseract (implicit: --oem 3 --psm 6)",
    )
    p.add_argument(
        "--reference-models",
        type=Path,
        default=None,
        help="CSV referință (ex. manere_sortate_final.csv) pentru alinierea numelor de model",
    )
    p.add_argument(
        "--reference-min-ratio",
        type=float,
        default=0.68,
        help="Prag similaritate (0–1) pentru potrivirea la referință (implicit: 0.68)",
    )
    args = p.parse_args()

    pdfs = [Path(x).resolve() for x in args.pdf]
    for pdf in pdfs:
        if not pdf.is_file():
            raise FileNotFoundError(f"Nu există fișierul: {pdf}")

    ref_path = args.reference_models

    frames: list[pd.DataFrame] = []
    for pdf in pdfs:
        frames.append(
            extrage_din_pdf(
                pdf,
                dpi=args.dpi,
                lang=args.lang,
                tesseract_config=args.tesseract_config,
            )
        )
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    program_dir = Path(__file__).resolve().parent
    df = finalizeaza_ocr_dataframe(
        df,
        referinta_models=ref_path,
        prag_referinta=args.reference_min_ratio,
    )
    if args.output is not None:
        out = args.output
    elif len(pdfs) > 1:
        out = program_dir / "manere_ocr_combined.csv"
    else:
        out = pdfs[0].with_suffix(".ocr.csv")

    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Scrie {len(df)} rânduri OCR în {out}", flush=True)

    if args.skip_explode:
        return

    final_out = args.manere_final or (program_dir / "manere_final.csv")
    final_out = final_out.resolve()
    explode_manere_final(out, final_out)
    print(f"manere_final (sortat): {final_out}", flush=True)


if __name__ == "__main__":
    main()
