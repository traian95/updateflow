# -*- coding: utf-8 -*-
"""
Încarcă «DIMENSIUNI TOCURI.csv» în Supabase (tabel `dimensiuni_tocuri`).

Rulare (din folderul «Soft Ofertare Usi»):
  py utils/scripts/import_dimensiuni_tocuri_supabase.py
  py utils/scripts/import_dimensiuni_tocuri_supabase.py --csv "DIMENSIUNI TOCURI.csv" --dry-run

Necesită migrarea SQL aplicată (utils/scripts/supabase_migrare_dimensiuni_tocuri.sql)
și SUPABASE_SERVICE_ROLE_KEY sau fișier supabase_service_role.key.
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

from ofertare.db_cloud import SUPABASE_URL, TABLE_DIMENSIUNI_TOCURI, _invalidate
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
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Import dimensiuni tocuri (CSV) in Supabase.")
    p.add_argument(
        "--csv",
        type=Path,
        default=_soft_root / "DIMENSIUNI TOCURI.csv",
        help="Fișier CSV (implicit DIMENSIUNI TOCURI.csv în rădăcina proiectului)",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    path = args.csv
    if not path.is_file():
        print(f"Fișier inexistent: {path}")
        return 1

    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
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

    c_tip = col("tip_toc")
    c_mat = col("material_toc")
    c_lat = col("latime_foaie_de_usa", "latime foaie")
    c_ld = col("latime_deschidere")
    c_id = col("inaltime_deschidere", "înălțime_deschidere")
    if not all([c_tip, c_mat, c_lat, c_ld, c_id]):
        print("Lipsesc coloane obligatorii (tip_toc, material_toc, latime_foaie_de_usa, latime_deschidere, inaltime_deschidere).")
        print("Coloane găsite:", list(df.columns))
        return 1

    rows: list[dict] = []
    for _, r in df.iterrows():
        tip_toc = _norm(r[c_tip])
        material_toc = _norm(r[c_mat])
        latime_foaie = _norm(r[c_lat])
        latime_d = _norm(r[c_ld])
        inaltime_d = _norm(r[c_id])
        if not tip_toc:
            continue
        rows.append(
            {
                "tip_toc": tip_toc,
                "material_toc": material_toc,
                "latime_foaie_de_usa": latime_foaie,
                "latime_deschidere": latime_d,
                "inaltime_deschidere": inaltime_d,
            }
        )

    if not rows:
        print("Nu există rânduri valide.")
        return 1

    print(f"Pregătite {len(rows)} rânduri pentru înlocuire integrală în `{TABLE_DIMENSIUNI_TOCURI}`.")

    if args.dry_run:
        for x in rows[:8]:
            print(x)
        if len(rows) > 8:
            print("...")
        return 0

    url = (SUPABASE_ADMIN_URL or SUPABASE_URL or "").strip()
    key = _service_role_key()
    if not url or not key:
        print("Lipsește URL Supabase sau cheia service_role (env SUPABASE_SERVICE_ROLE_KEY sau supabase_service_role.key).")
        return 1

    client = create_client(url, key)
    try:
        client.table(TABLE_DIMENSIUNI_TOCURI).delete().neq("id", 0).execute()
    except Exception as e:
        s = str(e).lower()
        if "pgrst205" in s or "does not exist" in s or "schema cache" in s:
            print(
                "Tabelul `dimensiuni_tocuri` nu există sau nu e expus în API.\n"
                "Rulează în Supabase → SQL Editor conținutul din:\n"
                f"  {_SCRIPTS / 'supabase_migrare_dimensiuni_tocuri.sql'}"
            )
            return 1
        print(f"Ștergere veche: {e}")
        return 1

    batch = 200
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        client.table(TABLE_DIMENSIUNI_TOCURI).insert(chunk).execute()

    _invalidate(TABLE_DIMENSIUNI_TOCURI)
    print(f"Import finalizat: {len(rows)} rânduri în `{TABLE_DIMENSIUNI_TOCURI}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
