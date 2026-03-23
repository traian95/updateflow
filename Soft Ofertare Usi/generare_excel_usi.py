"""
Generează un fișier Excel pentru importul ușilor în catalog (Admin → Importă produse din Excel).

Antetele sunt aliniate cu `admin_ui._incarca_excel`: Categorie, Furnizor, Colectie, Model,
Finisaj, Decor, Pret lista (coloana de preț trebuie să se normalizeze la „pret lista” în import).

Utilizare:
  python generare_excel_usi.py
  python generare_excel_usi.py -o C:\\temp\\usi.xlsx
  python generare_excel_usi.py --fara-exemplu
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# Ordinea coloanelor = ordinea cerută pentru uși; „Pret lista” e recunoscut de import (cheie „pret lista”).
COLS = ["Categorie", "Furnizor", "Colectie", "Model", "Finisaj", "Decor", "Pret lista"]

EXEMPLU_RANDURI = [
    {
        "Categorie": "Usi Interior",
        "Furnizor": "Erkado",
        "Colectie": "Full",
        "Model": "V09",
        "Finisaj": "INOVA",
        "Decor": "Stejar Riviera",
        "Pret lista": 249.99,
    },
    {
        "Categorie": "Usi Interior",
        "Furnizor": "Stoc",
        "Colectie": "Standard",
        "Model": "U1, U2",
        "Finisaj": "Alb",
        "Decor": "Mat",
        "Pret lista": 180,
    },
]

INSTRUCTIUNI = """IMPORT UȘI ÎN BAZĂ (via aplicația Admin)

1. Completați foaia „Uși”; păstrați rândul 1 cu antetele neschimbate. Puteți muta alte foi, dar foaia de date trebuie să se numească „Uși” (sau rămâne prima foaie).

2. Coloane:
   • Categorie — „Usi Interior” sau „Usi intrare apartament”
   • Furnizor — „Erkado” sau „Stoc”
   • Colectie — numele colecției
   • Model — cod/model; puteți pune mai multe modele despărțite prin virgulă (se creează câte un produs per model)
   • Finisaj — înainte de Decor (ca în catalog)
   • Decor — text liber
   • Pret lista — preț în EURO (număr, ex: 199 sau 199,50)

3. În Admin: Introducere produse → „Importă produse din Excel” → alegeți fișierul. După import, lista se aliniază automat la furnizorul/categoria din fișier.

4. Dacă lipsește coloana Furnizor dar în Categorie scrieți doar „Stoc” sau „Erkado”, importul tratează valoarea ca furnizor și folosește „Usi Interior” (dacă nu sunteți pe Tocuri în formular).

5. Dacă apare eroare la salvare: inserarea în baza cloud necesită cheie Supabase service role (variabilă de mediu sau configurare updater). Fără ea, importul poate fi respins de server.
"""


def _default_output() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        return desktop / "template_import_usi.xlsx"
    return Path.cwd() / "template_import_usi.xlsx"


def _latime_coloane(path: Path) -> None:
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path)
        ws = wb["Uși"]
        widths = {"A": 18, "B": 12, "C": 22, "D": 18, "E": 18, "F": 22, "G": 14}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        ws = wb["Instrucțiuni"]
        ws.column_dimensions["A"].width = 100
        wb.save(path)
    except Exception:
        pass


def main() -> None:
    p = argparse.ArgumentParser(description="Generează Excel pentru import uși (Admin).")
    p.add_argument("-o", "--output", type=Path, default=None, help="Cale fișier .xlsx de scris")
    p.add_argument(
        "--fara-exemplu",
        action="store_true",
        help="Doar antete, fără rânduri exemplu",
    )
    args = p.parse_args()
    out = args.output or _default_output()
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = [] if args.fara_exemplu else EXEMPLU_RANDURI
    df = pd.DataFrame(rows, columns=COLS)

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Uși", index=False)
        pd.DataFrame({"Instrucțiuni": [INSTRUCTIUNI]}).to_excel(
            writer, sheet_name="Instrucțiuni", index=False
        )

    _latime_coloane(out)
    print(f"Excel generat: {out}")


if __name__ == "__main__":
    main()
