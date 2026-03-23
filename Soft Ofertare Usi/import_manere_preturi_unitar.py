# -*- coding: utf-8 -*-
"""
Importă manere_preturi_unitar.csv în Supabase, tabela «produse»,
pentru categoria «Manere» și furnizorul «Enger».

Mapare coloane CSV → DB (compatibil cu UI: Colecție → Model → Decor/Finisaj):
  - categorie  = Manere
  - furnizor   = Enger
  - colectie   = Model          (ex: ALORA)
  - model      = Cod Produs     (ex: AS ALORA R 7S OB)
  - decor      = Tip Element    (ex: Măner, OB, PZ, WC)
  - finisaj    = Finisaj        (ex: LC, BK)
  - pret       = LEI cu TVA inclus (numeric, ca în CSV — fără conversie la EUR)

Preț: CSV-ul «Pret Net (Lei)» este stocat direct în «pret» (LEI cu TVA inclus).
Oferta pentru mânere Enger nu mai aplică TVA sau curs la aceste valori.

Rulare (din folderul «Soft Ofertare Usi» care conține pachetul ofertare):
  python import_manere_preturi_unitar.py
  python import_manere_preturi_unitar.py --dry-run
  python import_manere_preturi_unitar.py --replace-enger   # șterge mai întâi toate rândurile Manere+Enger

Necesită cheie service_role (din ofertare.updater) pentru insert/ștergere peste RLS.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Rulare ca script: adaugă rădăcina proiectului pe path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from supabase import create_client

from ofertare.db_cloud import TABLE_PRODUSE, _invalidate
from ofertare.updater import SUPABASE_ADMIN_SERVICE_ROLE_KEY, SUPABASE_ADMIN_URL

COLS = (
    "categorie",
    "furnizor",
    "colectie",
    "model",
    "decor",
    "finisaj",
    "pret",
    "tip_toc",
    "dimensiune",
    "este_izolatie",
)


def _rows_to_payloads(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, r in df.iterrows():
        pret_lei = round(float(r["Pret Net (Lei)"]), 2)
        rows.append(
            {
                "categorie": "Manere",
                "furnizor": "Enger",
                "colectie": str(r["Model"]).strip(),
                "model": str(r["Cod Produs"]).strip(),
                "decor": str(r["Tip Element"]).strip(),
                "finisaj": str(r["Finisaj"]).strip(),
                "pret": pret_lei,
                "tip_toc": "",
                "dimensiune": "",
                "este_izolatie": 0,
            }
        )
    return rows


def _fetch_max_produse_id(client) -> int:
    """ID-ul maxim din «produse» (Supabase poate necesita id explicit la insert)."""
    r = client.table(TABLE_PRODUSE).select("id").order("id", desc=True).limit(1).execute()
    data = r.data or []
    if not data:
        return 0
    try:
        return int(data[0]["id"])
    except (TypeError, ValueError, KeyError):
        return 0


def _delete_enger_manere(client) -> int:
    """Șterge toate rândurile Manere + Enger (în batch-uri)."""
    deleted = 0
    while True:
        sel = (
            client.table(TABLE_PRODUSE)
            .select("id")
            .eq("categorie", "Manere")
            .eq("furnizor", "Enger")
            .limit(500)
            .execute()
        )
        ids = [r["id"] for r in (sel.data or []) if r.get("id") is not None]
        if not ids:
            break
        client.table(TABLE_PRODUSE).delete().in_("id", ids).execute()
        deleted += len(ids)
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser(description="Import manere_preturi_unitar.csv → Supabase (Manere / Enger)")
    ap.add_argument(
        "--csv",
        type=Path,
        default=_ROOT / "manere_preturi_unitar.csv",
        help="Cale către CSV (implicit: manere_preturi_unitar.csv lângă script)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Doar afișează primele rânduri, fără scriere în DB")
    ap.add_argument(
        "--replace-enger",
        action="store_true",
        help="Înainte de import: șterge toate produsele existente Manere + Enger",
    )
    ap.add_argument("--batch", type=int, default=300, help="Mărime lot insert")
    args = ap.parse_args()

    key = (SUPABASE_ADMIN_SERVICE_ROLE_KEY or "").strip()
    url = (SUPABASE_ADMIN_URL or "").strip()
    if not key or not url:
        print("Lipseste SUPABASE_ADMIN_* in ofertare/updater.py.")
        return 1

    if not args.csv.is_file():
        print("Nu gasesc fisierul:", args.csv)
        return 1

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    need = {"Model", "Cod Produs", "Tip Element", "Finisaj", "Pret Net (Lei)"}
    missing = need - set(df.columns)
    if missing:
        print("Coloane lipsa in CSV:", missing)
        return 1

    payloads = _rows_to_payloads(df)
    print("Randuri CSV:", len(df), "-> payload-uri:", len(payloads))
    print("Pret: LEI cu TVA inclus (fara conversie EUR)")

    if args.dry_run:
        for p in payloads[:5]:
            print("EXEMPLU:", json.dumps(p, ensure_ascii=True))
        return 0

    client = create_client(url, key)

    if args.replace_enger:
        n = _delete_enger_manere(client)
        print("Sters randuri Manere+Enger existente:", n)
        _invalidate(TABLE_PRODUSE)

    next_id = _fetch_max_produse_id(client) + 1
    for j, p in enumerate(payloads):
        p["id"] = next_id + j

    batch = max(50, min(args.batch, 500))
    inserted = 0
    for i in range(0, len(payloads), batch):
        chunk = payloads[i : i + batch]
        client.table(TABLE_PRODUSE).insert(chunk).execute()
        inserted += len(chunk)
        print("Inserat:", inserted, "/", len(payloads))

    _invalidate(TABLE_PRODUSE)
    print("Gata. Total inserat:", inserted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
