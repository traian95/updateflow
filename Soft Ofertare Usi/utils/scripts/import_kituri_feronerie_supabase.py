# -*- coding: utf-8 -*-
"""
Importă kituri_organizat.xlsx în Supabase (tabel `kituri_feronerie`).

Rulare (din «Soft Ofertare Usi»):
  py utils/scripts/import_kituri_feronerie_supabase.py
  py utils/scripts/import_kituri_feronerie_supabase.py --xlsx "cale\\kituri_organizat.xlsx" --dry-run

Necesită migrarea SQL aplicată și SUPABASE_SERVICE_ROLE_KEY sau supabase_service_role.key.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

_soft_root = Path(__file__).resolve().parents[2]
_SCRIPTS = Path(__file__).resolve().parent
for _p in (_SCRIPTS, _soft_root):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from supabase import create_client

from ofertare.db_cloud import SUPABASE_URL, TABLE_KITURI_FERONERIE, _invalidate
from ofertare.updater import SUPABASE_ADMIN_SERVICE_ROLE_KEY, SUPABASE_ADMIN_URL


def _service_role_key() -> str:
    env_key = (SUPABASE_ADMIN_SERVICE_ROLE_KEY or "").strip()
    if env_key:
        return env_key
    for c in (
        _soft_root / "supabase_service_role.key",
        Path(os.environ.get("APPDATA", "")) / "Soft Ofertare Usi" / "supabase_service_role.key",
    ):
        try:
            if c.is_file():
                val = c.read_text(encoding="utf-8").strip()
                if val:
                    return val
        except OSError:
            pass
    return ""


def _norm(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return str(s).strip()


def main() -> int:
    p = argparse.ArgumentParser(description="Import kituri feronerie în Supabase.")
    p.add_argument(
        "--xlsx",
        type=Path,
        default=_soft_root / "kituri_organizat.xlsx",
        help="Fișier kituri_organizat.xlsx (format organize_kituri.py)",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    path = args.xlsx
    if not path.is_file():
        print(f"Fisier inexistent: {path}")
        return 1

    df = pd.read_excel(path, sheet_name=0)
    col_map = {c.lower().strip(): c for c in df.columns}

    def col(*names: str) -> str | None:
        for n in names:
            if n in df.columns:
                return n
            ln = n.lower()
            for k, v in col_map.items():
                if k == ln:
                    return v
        return None

    c_kit = col("kit")
    c_toc = col("tip_toc", "tip toc")
    c_dec = col("decor")
    c_pret = col("pret_eur_fara_tva", "pret")
    c_desc = col("descriere_feronerie", "descriere")
    if not all([c_kit, c_toc, c_dec, c_pret]):
        print("Lipsesc coloane obligatorii (kit, tip_toc, decor, pret_eur_fara_tva).")
        print("Coloane gasite:", list(df.columns))
        return 1

    rows: list[dict] = []
    for _, r in df.iterrows():
        kit = _norm(r[c_kit])
        tip_toc = _norm(r[c_toc])
        decor = _norm(r[c_dec])
        desc = _norm(r[c_desc]) if c_desc else ""
        try:
            pret = float(str(r[c_pret]).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if not kit or not tip_toc or not decor:
            continue
        rows.append(
            {
                "kit": kit,
                "tip_toc": tip_toc,
                "decor": decor,
                "pret_eur_fara_tva": pret,
                "descriere_feronerie": desc,
            }
        )

    if not rows:
        print("Nu exista randuri valide.")
        return 1

    print(f"Pregatite {len(rows)} randuri pentru insert.")

    if args.dry_run:
        for x in rows[:5]:
            print(x)
        print("...")
        return 0

    url = (SUPABASE_ADMIN_URL or SUPABASE_URL or "").strip()
    key = _service_role_key()
    if not url or not key:
        print("Lipseste URL Supabase sau cheia service_role.")
        return 1

    client = create_client(url, key)
    try:
        client.table(TABLE_KITURI_FERONERIE).delete().neq("id", 0).execute()
    except Exception as e:
        s = str(e).lower()
        if "pgrst205" in s or "does not exist" in s:
            print(
                "Tabelul `kituri_feronerie` nu exista sau nu e in API. "
                "Ruleaza utils/scripts/supabase_migrare_kituri_feronerie.sql in SQL Editor."
            )
            return 1
        print(f"Stergere veche: {e}")
        return 1

    batch = 200
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        client.table(TABLE_KITURI_FERONERIE).insert(chunk).execute()

    _invalidate(TABLE_KITURI_FERONERIE)
    print(f"Import finalizat: {len(rows)} randuri in `{TABLE_KITURI_FERONERIE}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
