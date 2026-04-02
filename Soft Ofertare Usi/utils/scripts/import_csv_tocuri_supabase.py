"""
Import CSV cu tocuri Erkado (Fara Falt) in baza Supabase — aceeasi mapare ca la import Excel din admin:
categorie, furnizor, model=Toc, decor gol, finisaj din coloana Finisaj, tip_toc din tip_toc_from_excel_cell,
dimensiune din reglaj (numere + MM), pret EUR.

Rulare (din folderul «Soft Ofertare Usi»):
  python utils/scripts/import_csv_tocuri_supabase.py importab.csv
  python utils/scripts/import_csv_tocuri_supabase.py importab.csv --replace   (sterge mai intai catalogul Fara Falt Erkado)
  python utils/scripts/import_csv_tocuri_supabase.py importab.csv --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd

DIR_PROIECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, DIR_PROIECT)

from ofertare.db_cloud import (  # noqa: E402
    delete_tocuri_erkado_fara_falt_catalog,
    insert_produs,
    tip_toc_from_excel_cell,
)


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _get(row: pd.Series, *names: str) -> str:
    lower = {str(k).strip().lower(): k for k in row.index}
    for n in names:
        k = lower.get(n.lower().strip())
        if k is not None:
            v = row[k]
            if pd.isna(v):
                return ""
            return str(v).strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Import CSV tocuri Erkado (Fara Falt) in Supabase")
    ap.add_argument(
        "csv",
        nargs="?",
        default="importab.csv",
        help="Cale catre CSV (implicit importab.csv in folderul curent)",
    )
    ap.add_argument(
        "--replace",
        action="store_true",
        help="Sterge inainte toate produsele Tocuri/Erkado cu tip Fara Falt",
    )
    ap.add_argument("--dry-run", action="store_true", help="Nu scrie in baza de date")
    args = ap.parse_args()

    path = os.path.abspath(args.csv)
    if not os.path.isfile(path):
        print(f"Fisier negasit: {path}", file=sys.stderr)
        return 1

    df = _norm_cols(pd.read_csv(path, encoding="utf-8-sig"))
    if df.empty:
        print("CSV gol.")
        return 1

    if args.replace and not args.dry_run:
        delete_tocuri_erkado_fara_falt_catalog()
        print("Sterse produsele vechi Tocuri / Erkado / Fara Falt.")

    n = 0
    for _, row in df.iterrows():
        cat = _get(row, "Categorie", "categorie")
        if not cat or cat.lower() != "tocuri":
            continue
        furn = _get(row, "Furnizor", "furnizor") or "Erkado"
        tip_excel = _get(row, "tip_toc", "Tip toc")
        reglaj = _get(row, "reglaj", "Reglaj")
        decor = _get(row, "Decor", "decor")
        fin = _get(row, "Finisaj", "finisaj", "FINISAJ")
        pret_raw = _get(row, "Pret lista (EUR)", "pret lista (eur)", "pret", "Pret")
        try:
            pret = float(str(pret_raw).replace(",", ".").strip() or "0")
        except ValueError:
            pret = 0.0
        tip_toc_val = tip_toc_from_excel_cell(tip_excel, furn)
        dimensiune_val = re.sub(r"[^0-9\-]", "", reglaj)
        if dimensiune_val and not dimensiune_val.endswith(" MM"):
            dimensiune_val = dimensiune_val + " MM"

        if args.dry_run:
            print(f"  {tip_toc_val} | {dimensiune_val} | {fin!r} | {pret} EUR")
            n += 1
            continue

        insert_produs(
            None,
            None,
            cat,
            furn,
            "",
            "Toc",
            decor,
            fin,
            tip_toc_val,
            dimensiune_val,
            pret,
        )
        n += 1

    if args.dry_run:
        print(f"[dry-run] {n} linii.")
    else:
        print(f"Import finalizat: {n} produse in Supabase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
