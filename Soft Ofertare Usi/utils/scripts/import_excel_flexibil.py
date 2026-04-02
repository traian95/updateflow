"""
Import produse din Excel „haotic” în baza de date.

Suportă:
- Rând diferit pentru header (nu neapărat primul)
- Foaie anume (prima implicit)
- Mapare flexibilă: recunoaște multe variante de nume pentru coloane
- Ignoră rânduri goale, curăță spații

Utilizare:
  python import_excel_flexibil.py "C:\cale\la\fisier.xlsx"
  python import_excel_flexibil.py "fisier.xlsx" --header 2
  python import_excel_flexibil.py "fisier.xlsx" --sheet "Produse"
  python import_excel_flexibil.py "fisier.xlsx" --dry-run   (doar afișează ce s-ar importa, nu scrie în DB)
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd

# Rădăcina proiectului «Soft Ofertare Usi» (folderul care conține pachetul ofertare)
DIR_PROIECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, DIR_PROIECT)

from ofertare.config import get_database_path
from ofertare.db import init_schema, open_db
from ofertare.db_cloud import tip_toc_from_excel_cell

# Mapare: nume posibile în Excel (lowercase) -> câmp în baza de date
COLOANE_EXCEL_TO_DB = {
    "furnizor": "furnizor",
    "categorie": "categorie",
    "categorie produs": "categorie",
    "categoria": "categorie",
    "colectie": "colectie",
    "colecție": "colectie",
    "colectia": "colectie",
    "denumire": "denumire",
    "denumirea": "denumire",
    "model": "model",
    "modele": "model",
    "decor": "decor",
    "finisaj": "finisaj",
    "finisaje": "finisaj",
    # Preț – acceptăm mai multe denumiri uzuale din fișierele Naturen
    "pret": "pret",
    "preț": "pret",
    "preț (eur)": "pret",
    "pret eur": "pret",
    "price": "pret",
    "eur": "pret",
    "pret lista": "pret",
    "pret lista (eur)": "pret",
    "pret lista eur fara tva/mp": "pret",
    "pret lista eur fara tva": "pret",
    "pret eur/mp": "pret",
    "pret eur fara tva": "pret",
    "preț lista": "pret",
    "preț lista eur fără tva/mp": "pret",
    "preț lista eur fără tva": "pret",
    "tip_toc": "tip_toc",
    "tip toc": "tip_toc",
    "tipul tocului": "tip_toc",
    "reglaj": "reglaj",
    "reglajul": "reglaj",
    "dimensiune": "reglaj",  # la tocuri, dimensiune = reglaj
}


def _normalize_col(s: str) -> str:
    return (s or "").strip().lower()


def build_column_map(df: pd.DataFrame) -> dict[str, str]:
    """Construiește maparea coloana Excel (nume) -> câmp DB."""
    col_map = {}
    for col in df.columns:
        key = _normalize_col(str(col))
        if key in COLOANE_EXCEL_TO_DB:
            col_map[col] = COLOANE_EXCEL_TO_DB[key]
    return col_map


def get_val(row: pd.Series, col_map: dict, db_field: str) -> str:
    """Returnează valoarea din rând pentru câmpul DB (prin mapare)."""
    for excel_col, field in col_map.items():
        if field == db_field:
            v = row.get(excel_col)
            if pd.isna(v):
                return ""
            return str(v).strip()
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Import produse din Excel în baza de date")
    parser.add_argument("excel_path", nargs="?", help="Calea către fișierul Excel (.xlsx)")
    parser.add_argument("--header", type=int, default=0, help="Indexul rândului care conține header-ul (0 = primul)")
    parser.add_argument("--sheet", default=0, help="Index sau nume foii (0 = prima foaie)")
    parser.add_argument("--dry-run", action="store_true", help="Doar afișează datele, nu inserează în DB")
    args = parser.parse_args()

    excel_path = args.excel_path
    if not excel_path:
        print("Lipsă cale Excel. Exemplu: python import_excel_flexibil.py \"C:\\cale\\fisier.xlsx\"")
        print("Opțiuni: --header 2  --sheet \"Produse\"  --dry-run")
        return
    if not os.path.isfile(excel_path):
        print(f"Fișier negăsit: {excel_path}")
        return

    try:
        df = pd.read_excel(excel_path, header=args.header, sheet_name=args.sheet)
    except Exception as e:
        print(f"Eroare la citire Excel: {e}")
        return

    # Elimină rânduri complet goale
    df = df.dropna(how="all")
    if df.empty:
        print("Nu există date în foaie (după eliminarea rândurilor goale).")
        return

    col_map = build_column_map(df)
    # Mesajele de debug simple, fără diacritice (pentru console CP1252)
    print("Coloane gasite in Excel:", list(df.columns))
    print("Mapare la campuri DB:", col_map)

    if not col_map:
        print("Nicio coloana recunoscuta. Adauga in script sinonime in COLOANE_EXCEL_TO_DB sau redenumeste coloanele in Excel.")
        print("Campuri asteptate: furnizor, categorie, colectie, model, decor, finisaj, pret, tip_toc, reglaj")
        return

    # Vedem daca exista in mod explicit o coloana de furnizor in Excel
    has_furnizor_col = any(field == "furnizor" for field in col_map.values())

    # Pregătește inserarea
    db_path = get_database_path()
    if not args.dry_run:
        handles = open_db(db_path)
        init_schema(handles.cursor, handles.conn)

    count = 0
    for idx, row in df.iterrows():
        furn_val = get_val(row, col_map, "furnizor") or "Stoc"
        cat_val = get_val(row, col_map, "categorie")
        col_val = get_val(row, col_map, "colectie")
        mod_raw = get_val(row, col_map, "model")
        dec_val = get_val(row, col_map, "decor")
        fin_val = get_val(row, col_map, "finisaj")

        # Corectie pentru fisierele de tip „template_usi_interior”,
        # unde coloana „Categorie” contine doar Stoc/Erkado (furnizor),
+        # iar categoria reala este Usi Interior.
        if not has_furnizor_col:
            cat_norm = _normalize_col(cat_val)
            if cat_norm in ("stoc", "erkado"):
                furn_val = cat_val or furn_val
                cat_val = "Usi Interior"

        # Preț
        pret_raw = get_val(row, col_map, "pret")
        try:
            pret_val = float(str(pret_raw).replace(",", ".").strip() or "0")
        except ValueError:
            pret_val = 0.0

        tip_toc_val = ""
        dimensiune_val = ""
        if cat_val and _normalize_col(cat_val) == "tocuri":
            tip_toc_excel = get_val(row, col_map, "tip_toc")
            tip_toc_val = tip_toc_from_excel_cell(tip_toc_excel, furn_val)
            reglaj_excel = get_val(row, col_map, "reglaj")
            dimensiune_val = re.sub(r"[^0-9\-]", "", (reglaj_excel or ""))
            if dimensiune_val and not dimensiune_val.endswith(" MM"):
                dimensiune_val = dimensiune_val + " MM"
            col_val = ""
            mod_raw = "Toc"
            modele = ["Toc"]
            dec_val = ""
            if _normalize_col(furn_val) == "erkado":
                fin_val = get_val(row, col_map, "finisaj") or fin_val
            else:
                fin_val = ""

        modele = [m.strip() for m in (mod_raw or "").split(",") if m.strip()]
        if not modele:
            denumire_val = get_val(row, col_map, "denumire") or col_val
            modele = [denumire_val.strip() or "Standard"]
        dec_val = (dec_val or "").strip()
        fin_val = (fin_val or "").strip()

        # Sari rânduri complet goale (nici categorie, nici model, nici preț)
        if not cat_val and not mod_raw and pret_val == 0:
            continue

        for m in modele:
            if args.dry_run:
                print(f"  [dry-run] {cat_val} | {furn_val} | {col_val} | {m} | {dec_val} | {fin_val} | {tip_toc_val} | {dimensiune_val} | {pret_val}")
            else:
                handles.cursor.execute(
                    "INSERT INTO produse (categorie, furnizor, colectie, model, decor, finisaj, tip_toc, dimensiune, pret) VALUES (?,?,?,?,?,?,?,?,?)",
                    (cat_val, furn_val, col_val, m, dec_val, fin_val, tip_toc_val, dimensiune_val, pret_val),
                )
            count += 1

    if not args.dry_run and count > 0:
        handles.conn.commit()
        print(f"Import finalizat: {count} produse adaugate in {db_path}")
    elif args.dry_run:
        print(f"[dry-run] S-ar insera {count} produse. Ruleaza fara --dry-run pentru a scrie in DB.")
    else:
        print("Niciun rand valid de importat.")


if __name__ == "__main__":
    main()
