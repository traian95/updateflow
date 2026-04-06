"""
Normalizează tabelul «kituri» din Excel: un rând per combinație
(kit, tip toc, decor) cu preț individual.

Sursa tipică: «Soft Ofertare Usi/kituri.xlsx» — structură cu antet pe 2 rânduri,
coloane de preț per decor (ex. INOX / NEGRU), kit pe coloana A doar la unele rânduri.

Utilizare:
  python organize_kituri.py
  python organize_kituri.py --input "C:\\cale\\kituri.xlsx" --output kituri_organizat.xlsx
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd

# Rădăcina folderului «Soft Ofertare Usi»
DIR_SOFT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_INPUT = os.path.join(DIR_SOFT, "kituri.xlsx")


def _strip_cell(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def _is_kit_label(s: str) -> str | None:
    m = re.match(r"^KIT\s+([A-Z0-9]+)\s*$", s.strip().upper())
    if m:
        return f"KIT {m.group(1)}"
    return None


def _is_cilindru_preamble_row(descriere: str) -> bool:
    """Rândul «cilindru cu buton/cheie» + THERMO HOT 88 aparține kit-ului de pe rândul următor.
    Nu folosim `search`: texte lungi («sistem cheie… cilindru cu buton») nu trebuie să declanșeze lookahead."""
    d = (descriere or "").strip().lower()
    return bool(re.match(r"cilindru\s+cu\s+(buton|cheie)\b", d))


def _read_decor_headers(df_raw: pd.DataFrame) -> tuple[list[str], int]:
    """Găsește rândul cu numele decorurilor (coloane cu prețuri) și indexul primului rând de date."""
    decor_cols: list[str] = []
    data_start = 0
    for i in range(min(5, len(df_raw))):
        row = df_raw.iloc[i]
        texts = [_strip_cell(c) for c in row.tolist()]
        # Heuristic: rând cu «Pret» sau cu două+ celule non-goale după coloanele de text
        joined = " ".join(texts).lower()
        if "pret" in joined and ("eur" in joined or "tva" in joined):
            data_start = i + 1
            # coloanele de preț: de la primul index unde avem număr în rândurile următoare
            break
        # alternativ: primul rând unde ultimele coloane arată ca nume decor (nu «Unnamed»)
    if data_start == 0:
        # fără rând «Pret...»: folosim primul rând ca titluri decor dacă există text în ultimele coloane
        header_row = df_raw.iloc[0]
        for j in range(4, len(header_row)):
            t = _strip_cell(header_row.iloc[j])
            if t and not t.lower().startswith("unnamed"):
                decor_cols.append(t)
        data_start = 2 if len(df_raw) > 1 and "pret" in _strip_cell(df_raw.iloc[1, 0]).lower() else 1
    else:
        # nume decoruri din rândul de deasupra rândului «Pret...»
        title_row = df_raw.iloc[data_start - 2] if data_start >= 2 else df_raw.iloc[0]
        for j in range(4, len(df_raw.columns)):
            t = _strip_cell(title_row.iloc[j]) if j < len(title_row) else ""
            if not t or t.lower().startswith("unnamed"):
                # încearcă rândul imediat deasupra «Pret»
                t = _strip_cell(df_raw.iloc[data_start - 1, j]) if j < len(df_raw.columns) else ""
            if t and not re.match(r"^pret\b", t, re.I):
                decor_cols.append(t)
        if not decor_cols:
            for j in range(4, len(df_raw.columns)):
                decor_cols.append(f"decor_{j}")

    if len(decor_cols) < 2:
        # fallback: ultimele N coloane numerice din primele rânduri
        n_price = len(df_raw.columns) - 4
        decor_cols = [f"decor_{k}" for k in range(max(2, n_price))]

    return decor_cols, data_start


def organize_kituri_excel(path_xlsx: str) -> pd.DataFrame:
    df_raw = pd.read_excel(path_xlsx, sheet_name=0, header=None)
    if df_raw.shape[1] < 6:
        raise ValueError("Fișierul are prea puține coloane; așteptat format cu cel puțin 6 coloane.")

    decor_names, data_start = _read_decor_headers(df_raw)
    # Mapare index coloană -> nume decor (coloane 4, 5, ... pentru prețuri)
    price_col_indices = list(range(4, 4 + len(decor_names)))

    rows_out: list[dict] = []
    last_kit: str | None = None

    for i in range(data_start, len(df_raw)):
        r = df_raw.iloc[i]
        c0 = _strip_cell(r.iloc[0])
        c1 = _strip_cell(r.iloc[1])
        c3 = _strip_cell(r.iloc[3])

        kit_here = _is_kit_label(c0)
        if kit_here:
            last_kit = kit_here

        # kit pentru rândul curent: explicit sau lookahead sau last_kit
        kit_row = kit_here or last_kit
        if not kit_here and not c0 and _is_cilindru_preamble_row(c1):
            # Doar rândul-preambul «cilindru cu buton/cheie» ia kit-ul de pe rândul următor;
            # «sistem cheie unica» rămâne la last_kit (nu la kit-ul următor).
            if i + 1 < len(df_raw):
                next_kit = _is_kit_label(_strip_cell(df_raw.iloc[i + 1, 0]))
                if next_kit:
                    kit_row = next_kit

        if not kit_row:
            continue
        if not c3:
            continue

        prices = []
        for j in price_col_indices:
            if j >= len(r):
                prices.append(None)
                continue
            v = r.iloc[j]
            if pd.isna(v):
                prices.append(None)
            else:
                try:
                    prices.append(float(v))
                except (TypeError, ValueError):
                    prices.append(None)

        if all(p is None for p in prices):
            continue

        for decor_name, pret in zip(decor_names, prices):
            if pret is None:
                continue
            rows_out.append(
                {
                    "kit": kit_row,
                    "tip_toc": c3,
                    "decor": decor_name,
                    "pret_eur_fara_tva": pret,
                    "descriere_feronerie": c1 or None,
                }
            )

    result = pd.DataFrame(rows_out)
    if result.empty:
        return result
    # ordine lizibilă
    kit_order = sorted(result["kit"].unique(), key=lambda x: (re.sub(r"\D", "", x) or "0", x))
    toc_order = sorted(result["tip_toc"].unique())
    decor_order = list(dict.fromkeys(result["decor"].tolist()))
    cat_kit = pd.Categorical(result["kit"], categories=kit_order, ordered=True)
    cat_toc = pd.Categorical(result["tip_toc"], categories=toc_order, ordered=True)
    cat_dec = pd.Categorical(result["decor"], categories=decor_order, ordered=True)
    result = result.assign(_k=cat_kit, _t=cat_toc, _d=cat_dec).sort_values(["_k", "_t", "_d"]).drop(columns=["_k", "_t", "_d"])
    return result.reset_index(drop=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Organizează kituri.xlsx în format lung (kit × toc × decor).")
    p.add_argument("--input", "-i", default=DEFAULT_INPUT, help="Cale către kituri.xlsx")
    p.add_argument(
        "--output",
        "-o",
        default="",
        help="Fișier ieșire (.xlsx sau .csv). Implicit: kituri_organizat.xlsx lângă intrare.",
    )
    args = p.parse_args()
    path_in = os.path.abspath(args.input)
    if not os.path.isfile(path_in):
        print(f"Fișier inexistent: {path_in}", file=sys.stderr)
        return 1

    out = organize_kituri_excel(path_in)
    if args.output:
        path_out = os.path.abspath(args.output)
    else:
        base, _ = os.path.splitext(path_in)
        path_out = base + "_organizat.xlsx"

    if path_out.lower().endswith(".csv"):
        out.to_csv(path_out, index=False, encoding="utf-8-sig")
    else:
        out.to_excel(path_out, index=False, sheet_name="kituri")

    print(f"Scrie {len(out)} rânduri -> {path_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
