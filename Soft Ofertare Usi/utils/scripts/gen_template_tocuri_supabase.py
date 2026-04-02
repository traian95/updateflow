"""Generează template Excel pentru import tocuri (Supabase / tabela produse). Rulare din folderul «Soft Ofertare Usi»."""
from __future__ import annotations

import os
import sys

import pandas as pd

def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out_dir = os.path.join(root, "templates")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "import_tocuri_supabase.xlsx")

    exemplu = pd.DataFrame(
        [
            {
                "Categorie": "Tocuri",
                "Furnizor": "Erkado",
                "tip_toc": "Toc Reglabil Usi cu Falt",
                "reglaj": "100-120 MM",
                "Decor": "CPL ALB",
                "Finisaj": "CPL",
                "Pret lista (EUR)": 99.5,
            },
            {
                "Categorie": "Tocuri",
                "Furnizor": "Erkado",
                "tip_toc": "Toc Reglabil Usi Fara Falt",
                "reglaj": "90-100 MM",
                "Decor": "CPL STEJAR",
                "Finisaj": "CPL",
                "Pret lista (EUR)": 88.0,
            },
            {
                "Categorie": "Tocuri",
                "Furnizor": "Erkado",
                "tip_toc": "Fix 90 MM",
                "reglaj": "90 MM",
                "Decor": "",
                "Finisaj": "CPL",
                "Pret lista (EUR)": 72.0,
            },
            {
                "Categorie": "Tocuri",
                "Furnizor": "Stoc",
                "tip_toc": "Fix",
                "reglaj": "80 MM",
                "Decor": "",
                "Finisaj": "",
                "Pret lista (EUR)": 55.0,
            },
        ]
    )

    legenda = pd.DataFrame(
        {
            "Coloana_Supabase": [
                "categorie",
                "furnizor",
                "tip_toc",
                "dimensiune (din reglaj)",
                "decor",
                "finisaj",
                "colectie",
                "model",
                "pret",
            ],
            "Excel_admin_import": [
                "Categorie",
                "Furnizor",
                "tip_toc",
                "reglaj sau dimensiune",
                "Decor",
                "Finisaj",
                "(ignorat la Tocuri)",
                "Toc (implicit)",
                "Pret lista (EUR)",
            ],
            "Observatie": [
                "Tocuri",
                "Stoc sau Erkado",
                "Fix | Fix 90 MM | Reglabil / Toc Reglabil Usi cu Falt (→ DB: Reglabil) | Toc Reglabil Usi Fara Falt",
                "ex: 100-120 MM",
                "Obligatoriu pentru linii Erkado cu perechi decor/finisaj",
                "Finisaj (CPL, PREMIUM, …)",
                "La import Tocuri rămâne gol",
                "Rândurile Tocuri folosesc model «Toc»",
                "EUR listă fără TVA",
            ],
        }
    )

    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        exemplu.to_excel(xw, sheet_name="Exemplu_date", index=False)
        legenda.to_excel(xw, sheet_name="Mapare_Supabase", index=False)

    print("Scrie:", out_path)


if __name__ == "__main__":
    sys.exit(0 if main() is None else 0)
