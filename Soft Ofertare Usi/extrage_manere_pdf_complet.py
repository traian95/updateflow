"""
Extrage mânere din PDF-uri scanate: OCR pe coloane + parsare blocuri cod:/AS…R 7S.
Îmbină cu manere_sortate_final.csv (prioritate) și adaugă modele găsite doar în OCR.

Ieșire:
  - manere_preturi_unitar.csv
  - manere_extrase_ocr_brut.csv (rezultat parsare brută, pentru control)
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance
import pytesseract

from ocr_env import configure_ocr

Image.MAX_IMAGE_PIXELS = 500_000_000

FINISH_7 = ["LC", "SC", "WH", "LG", "BK", "KG", "SNM"]
FINISH_4 = ["LC", "SC", "WH", "LG"]
FINISH_3 = ["LC", "KG", "LG"]


def _pregateste(img: Image.Image, max_w: int = 3200) -> Image.Image:
    g = img.convert("L")
    w, h = g.size
    if w > max_w:
        nh = int(h * (max_w / w))
        g = g.resize((max_w, nh), Image.Resampling.LANCZOS)
    return ImageEnhance.Contrast(g).enhance(1.38)


def ocr_image(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, lang="ron+eng", config="--oem 3 --psm 6")


def ocr_pdf_split_cols(pdf_path: Path, dpi: int = 300) -> str:
    tess, poppler = configure_ocr()
    if not tess:
        raise RuntimeError("Tesseract nu e disponibil.")
    kwargs: dict = {"dpi": dpi}
    if poppler:
        kwargs["poppler_path"] = poppler
    pages = convert_from_path(str(pdf_path), **kwargs)
    parts: list[str] = []
    for i, pagina in enumerate(pages):
        preg = _pregateste(pagina)
        w, h = preg.size
        mid = w // 2
        margin = int(w * 0.02)
        left = preg.crop((0, 0, max(mid - margin, 1), h))
        right = preg.crop((min(mid + margin, w - 1), 0, w, h))
        for label, crop in (("LEFT", left), ("RIGHT", right)):
            parts.append(f"\n=== {pdf_path.name} P{i + 1} {label} ===\n")
            parts.append(ocr_image(crop))
    return "".join(parts)


def parse_prices_line(s: str) -> list[float]:
    out: list[float] = []
    for m in re.finditer(r"\d{1,4}[.,]\d{2}", s):
        t = m.group(0).replace(",", ".")
        try:
            v = float(t)
        except ValueError:
            continue
        if 12.0 <= v <= 2800.0:
            out.append(v)
    # OCR fără separator: 7801, 12818 -> 78.01, 128.18
    for m in re.finditer(r"\b(\d{4,5})\b", s):
        raw = m.group(1)
        if len(raw) == 5:
            v = int(raw) / 100.0
        else:
            v = int(raw) / 100.0
        if 12.0 <= v <= 2800.0:
            out.append(round(v, 2))
    return out


def normalize_model_name(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw.strip()).upper()
    for pref in ("AT ", "AS "):
        if s.startswith(pref):
            s = s[len(pref) :].strip()
    s = re.sub(r"^M\s+", "", s)
    s = re.sub(r"^G\s+", "", s)
    return s.strip()


def detect_rozeta(window: str) -> str:
    u = window.upper()
    if re.search(r"RTH\s*SLIM|RT\s*SLIM", u):
        return "RTH SLIM"
    if re.search(r"SUPER\s*SLIM|SUM\s*5MM", u):
        return "R SUPER SLIM 5MM"
    if re.search(r"Q\s*SLIM|QSLIM", u):
        return "Q SLIM 7MM"
    if re.search(r"SLIM\s*7|SLIMTMM|SIMTMM", u):
        return "R SLIM 7MM"
    if re.search(r"LEATHER", u):
        return "LEATHER"
    return ""


def map_finishes(n: int) -> list[str]:
    if n == 7:
        return FINISH_7[:]
    if n == 4:
        return FINISH_4[:]
    if n == 3:
        return FINISH_3[:]
    if n == 2:
        return ["C1", "C2"]
    if n == 1:
        return ["UNIC"]
    return [f"C{i+1}" for i in range(n)]


def find_model_near(lines: list[str], start: int, back: int = 12, fwd: int = 14) -> str | None:
    for j in range(start, min(start + fwd, len(lines))):
        m = _extract_model_from_line(lines[j])
        if m:
            return m
    for j in range(max(0, start - back), start):
        m = _extract_model_from_line(lines[j])
        if m:
            return m
    return None


def _extract_model_from_line(line: str) -> str | None:
    """
    Variante tipărite în catalog: AS ALORA R 7S, AS LUPINA RTH 7S, AS YUKAQ7S, ST ARTA Q7S, AS IXIA QR 7S.
    """
    tests: list[tuple[str, str | None]] = [
        (r"(?:AS|AT)\s+([A-Z][A-Z0-9\s]{2,34}?)\s+R\s*TH\s*7\s*S", None),
        (r"(?:AS|AT)\s+([A-Z][A-Z0-9\s]{2,34}?)\s+RTH\s*7\s*S", None),
        (r"(?:AS|AT)\s+([A-Z][A-Z0-9\s]{2,34}?)\s+R\s*7\s*S", None),
        (r"(?:AS|AT)\s+([A-Z][A-Z0-9\s]{2,34}?)\s+R\s*5\s*S", None),
        (r"(?:AS|AT)\s+([A-Z][A-Z0-9\s]{2,40}?)\s*QR\s*7\s*S", None),
        (r"AS\s+([A-Z]+)\s*QR\s*7\s*S", None),
        (r"ST\s+([A-Z][A-Z0-9\s]{2,28}?)\s+Q\s*7\s*S", "ST "),
        (r"AS\s+([A-Z][A-Z0-9\s]{2,28}?)\s+Q\s*7\s*S", None),
        (r"AS\s*([A-Z]{3,22})Q7S", None),
    ]
    for pat, prefix in tests:
        m = re.search(pat, line, re.I)
        if m:
            name = normalize_model_name(m.group(1))
            if prefix:
                name = (prefix + name).strip()
            return name
    return None


def _first_acc_prices(sub: list[str], patterns: list[str]) -> list[float]:
    for s in sub:
        su = s.upper()
        if any(re.search(p, su) for p in patterns):
            p = parse_prices_line(s)
            if len(p) >= 1:
                return p
    return []


def parse_split_ocr_to_dataframe(ocr_text: str) -> pd.DataFrame:
    """
    Parsare euristică: pentru fiecare linie «cod:» cu prețuri, asociază model și
    linii accesorii OB/PZ/WC din același fragment de linii.
    """
    rows: list[dict] = []
    parts = re.split(r"\n===\s*[^=\n]+\s*===\s*\n", ocr_text)
    for part in parts:
        lines = [ln.strip() for ln in part.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        roz = detect_rozeta("\n".join(lines[:25]))

        i = 0
        while i < len(lines):
            ln = lines[i]
            if "cod:" not in ln.lower():
                i += 1
                continue
            handle = parse_prices_line(ln)
            if not handle and i > 0:
                handle = parse_prices_line(lines[i - 1])
            if not handle:
                i += 1
                continue
            model = find_model_near(lines, i)
            if not model:
                i += 1
                continue

            fins = map_finishes(len(handle))
            sub = lines[i + 1 : i + 36]

            ob_only = _first_acc_prices(
                sub,
                [r"SOB", r"7S\s*0B", r"ASR.*OB", r"ATR.*OB", r"AS\s*R\s*5S\s*OB"],
            )
            pz_only = _first_acc_prices(sub, [r"SPZ", r"7S\s*PZ", r"ASR.*PZ", r"ATR.*PZ"])
            wc_only = _first_acc_prices(sub, [r"SWC", r"7S\s*WC", r"ASR.*WC", r"ATR.*WC"])

            for idx, fin in enumerate(fins):
                pm = handle[idx] if idx < len(handle) else handle[-1]
                for tip, arr in (("OB", ob_only), ("PZ", pz_only), ("WC", wc_only)):
                    if not arr:
                        continue
                    pr = arr[idx] if idx < len(arr) else arr[-1]
                    rows.append(
                        {
                            "Model": model,
                            "Finisaj": fin,
                            "Tip_Rozeta": tip,
                            "Pret_Maner": round(pm, 2),
                            "Pret_Rozeta": round(pr, 2),
                            "Rozeta": roz,
                        }
                    )
            i += 1

    if not rows:
        return pd.DataFrame(columns=["Model", "Finisaj", "Tip_Rozeta", "Pret_Maner", "Pret_Rozeta", "Rozeta"])
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["Model", "Finisaj", "Tip_Rozeta"], keep="first")
    return df


def explode_unitar(df: pd.DataFrame, roze: dict[str, str]) -> pd.DataFrame:
    rows_out: list[dict] = []
    for _, r in df.iterrows():
        model = str(r["Model"]).strip()
        fin = str(r["Finisaj"]).strip()
        tip_acc = str(r["Tip_Rozeta"]).strip()
        pm = float(r["Pret_Maner"])
        pr = float(r["Pret_Rozeta"])
        roz = str(r.get("Rozeta", "") or "").strip() or roze.get(model, "")

        rows_out.append(
            {
                "Model": model,
                "Rozeta": roz,
                "Tip Element": "Măner",
                "Cod Produs": f"AS {model} R 7S",
                "Finisaj": fin,
                "Pret Net (Lei)": round(pm, 2),
                "_dedupe_key": f"{model}|{fin}|Măner",
            }
        )
        rows_out.append(
            {
                "Model": model,
                "Rozeta": roz,
                "Tip Element": tip_acc,
                "Cod Produs": f"AS {model} R 7S {tip_acc}",
                "Finisaj": fin,
                "Pret Net (Lei)": round(pr, 2),
                "_dedupe_key": f"{model}|{fin}|{tip_acc}|acc",
            }
        )

    out = pd.DataFrame(rows_out)
    manere = out[out["Tip Element"] == "Măner"].drop_duplicates(subset=["_dedupe_key"], keep="first")
    acc = out[out["Tip Element"] != "Măner"]
    out = pd.concat([manere, acc], ignore_index=True)
    out = out.drop(columns=["_dedupe_key"])
    smap = {"Măner": 0, "OB": 1, "PZ": 2, "WC": 3}
    out["_stip"] = out["Tip Element"].map(lambda x: smap.get(str(x), 9))
    out = out.sort_values(by=["Model", "Finisaj", "_stip"]).drop(columns=["_stip"])
    return out.reset_index(drop=True)


def build_roze_map(ocr_text: str, modele: list[str]) -> dict[str, str]:
    ocr = re.sub(r"\s+", " ", ocr_text)
    roze: dict[str, str] = {}
    U = ocr.upper()
    for m in modele:
        mu = m.upper().strip()
        idx = U.find(mu)
        if idx < 0:
            idx = U.find(mu.replace(" ", ""))
        if idx < 0:
            roze[m] = ""
            continue
        win = ocr[max(0, idx - 1400) : idx + 700]
        roze[m] = detect_rozeta(win) or ""
    return roze


def main() -> None:
    ap = argparse.ArgumentParser(description="Extrage modele din PDF (OCR) + CSV")
    ap.add_argument("--force-ocr", action="store_true")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--prefer-csv", type=Path, default=None)
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    cache = base / "_ocr_manere_split_cols.txt"
    prefer = args.prefer_csv or (base / "manere_sortate_final.csv")
    out_csv = base / "manere_preturi_unitar.csv"
    brut_csv = base / "manere_extrase_ocr_brut.csv"

    pdfs = sorted(
        base.glob("Scanned*.pdf"),
        key=lambda p: (0 if p.name.lower() == "scanned documents.pdf" else 1, p.name.lower()),
    )
    if not pdfs:
        raise FileNotFoundError("Lipsește Scanned*.pdf în folderul aplicației.")

    if args.force_ocr or not cache.is_file():
        buf: list[str] = []
        for pdf in pdfs:
            buf.append(ocr_pdf_split_cols(pdf, dpi=args.dpi))
        cache.write_text("\n".join(buf), encoding="utf-8")

    ocr_full = cache.read_text(encoding="utf-8")

    df_ocr = parse_split_ocr_to_dataframe(ocr_full)
    df_ocr.to_csv(brut_csv, index=False, encoding="utf-8-sig")

    df_csv = pd.read_csv(prefer, encoding="utf-8-sig")
    if "Rozeta" not in df_csv.columns:
        df_csv["Rozeta"] = ""

    csv_models = {str(x).strip() for x in df_csv["Model"].unique()}

    extra_parts: list[pd.DataFrame] = []
    if not df_ocr.empty:
        df_ocr2 = df_ocr.copy()
        # Doar modele care nu apar deloc în CSV (evită dubluri / mapări greșite de finisaje)
        mask = ~df_ocr2["Model"].map(lambda m: str(m).strip() in csv_models)
        extra_parts.append(df_ocr2.loc[mask])

    if extra_parts:
        df_extra = pd.concat(extra_parts, ignore_index=True)
        df_extra = df_extra.drop_duplicates(subset=["Model", "Finisaj", "Tip_Rozeta"], keep="first")
    else:
        df_extra = pd.DataFrame(columns=list(df_csv.columns))

    if not df_extra.empty:
        for c in df_csv.columns:
            if c not in df_extra.columns:
                df_extra[c] = pd.NA
        df_extra["Total"] = (
            df_extra["Pret_Maner"].astype(float) + df_extra["Pret_Rozeta"].astype(float)
        ).round(2)
        df_final = pd.concat([df_csv, df_extra[df_csv.columns]], ignore_index=True)
    else:
        df_final = df_csv.copy()

    modele = sorted(df_final["Model"].unique(), key=lambda x: str(x).upper())
    roze = build_roze_map(ocr_full, list(modele))
    for _, r in df_final.iterrows():
        m = str(r["Model"]).strip()
        if "Rozeta" in df_final.columns and pd.notna(r.get("Rozeta")) and str(r.get("Rozeta", "")).strip():
            roze[m] = str(r["Rozeta"]).strip()

    ex = df_final[["Model", "Finisaj", "Tip_Rozeta", "Pret_Maner", "Pret_Rozeta"]].copy()
    ex["Rozeta"] = df_final["Rozeta"].fillna("").astype(str)

    unitar = explode_unitar(ex, roze)
    unitar.loc[unitar["Rozeta"].astype(str).str.strip() == "", "Rozeta"] = "R SLIM 7MM"

    unitar.to_csv(out_csv, index=False, encoding="utf-8-sig")

    print("PDF-uri:", [p.name for p in pdfs])
    print("Cache OCR:", cache, "chars:", len(ocr_full))
    print("Randuri parsare bruta:", len(df_ocr))
    print("Randuri CSV sursa:", len(df_csv))
    print("Randuri adaugate din OCR:", len(df_extra))
    print("Total unitar:", len(unitar), "->", out_csv)


if __name__ == "__main__":
    main()
