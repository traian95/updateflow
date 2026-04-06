# -*- coding: utf-8 -*-
"""
Creează tabelul `dimensiuni_tocuri` și încarcă «DIMENSIUNI TOCURI.csv» direct pe Postgres
(fără PostgREST). Necesită parola bazei din Supabase Dashboard → Database.

URI: Supabase Dashboard -> Project Settings -> Database -> Connection string -> URI
Fișier: Soft Ofertare Usi/supabase_db.url  (o linie)
Sau:     set SUPABASE_DB_URL=postgresql://...

Dependență:  pip install "psycopg[binary]" pandas

Rulare (din folderul Soft Ofertare Usi):
  py utils/scripts/dimensiuni_tocuri_via_postgres.py --schema-only
  py utils/scripts/dimensiuni_tocuri_via_postgres.py
  py utils/scripts/dimensiuni_tocuri_via_postgres.py --csv "DIMENSIUNI TOCURI.csv" --dry-run
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_SOFT_ROOT = _SCRIPTS.parents[1]
_MIGRATION_SQL = _SCRIPTS / "supabase_migrare_dimensiuni_tocuri.sql"
_DEFAULT_CSV = _SOFT_ROOT / "DIMENSIUNI TOCURI.csv"


def _out(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def _load_db_url() -> str:
    env = (os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if env:
        return env
    f = _SOFT_ROOT / "supabase_db.url"
    if f.is_file():
        return f.read_text(encoding="utf-8").strip()
    return ""


def _sql_executable_chunks(sql_text: str) -> list[str]:
    lines: list[str] = []
    for line in sql_text.splitlines():
        s = line.strip()
        if s.startswith("--"):
            continue
        lines.append(line)
    blob = "\n".join(lines)
    chunks: list[str] = []
    for part in blob.split(";"):
        p = part.strip()
        if p:
            chunks.append(p)
    return chunks


def _rows_from_csv(path: Path) -> list[tuple[str, str, str, str, str]]:
    import pandas as pd

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
    c_lat = col("latime_foaie_de_usa")
    c_ld = col("latime_deschidere")
    c_id = col("inaltime_deschidere")
    if not all([c_tip, c_mat, c_lat, c_ld, c_id]):
        raise ValueError("Coloane CSV incomplete.")

    def _norm(s) -> str:
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return ""
        return str(s).strip()

    out: list[tuple[str, str, str, str, str]] = []
    for _, r in df.iterrows():
        tip = _norm(r[c_tip])
        if not tip:
            continue
        out.append(
            (
                tip,
                _norm(r[c_mat]),
                _norm(r[c_lat]),
                _norm(r[c_ld]),
                _norm(r[c_id]),
            )
        )
    return out


def main() -> int:
    try:
        import argparse

        import psycopg
    except ImportError as e:
        if "psycopg" in str(e).lower():
            _out('Lipseste psycopg. Ruleaza: pip install "psycopg[binary]"')
        else:
            _out(str(e))
        return 1

    ap = argparse.ArgumentParser(description="Migrare + import dimensiuni_tocuri via Postgres.")
    ap.add_argument("--schema-only", action="store_true", help="Doar creeaza tabelul/index/RLS (fara CSV).")
    ap.add_argument("--csv", type=Path, default=_DEFAULT_CSV)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.schema_only:
        if not args.csv.is_file():
            _out(f"Fisier inexistent: {args.csv}")
            return 1

        try:
            rows = _rows_from_csv(args.csv)
        except Exception as e:
            _out(f"Eroare citire csv: {e}")
            return 1

        if not rows:
            _out("Nu exista randuri valide.")
            return 1

        _out(f"Pregatite {len(rows)} randuri.")
        if args.dry_run:
            for t in rows[:3]:
                _out(str(t))
            _out("...")
            return 0

    url = _load_db_url()
    if not url or not url.startswith("postgres"):
        _out(
            "Lipseste URI Postgres. Creeaza Soft Ofertare Usi/supabase_db.url (o linie) "
            "cu URI din Dashboard -> Database, sau seteaza SUPABASE_DB_URL."
        )
        return 1

    if not _MIGRATION_SQL.is_file():
        _out(f"Lipseste {_MIGRATION_SQL}")
        return 1

    mig = _MIGRATION_SQL.read_text(encoding="utf-8")
    stmts = _sql_executable_chunks(mig)

    try:
        with psycopg.connect(url, autocommit=True) as conn:
            with conn.cursor() as cur:
                for st in stmts:
                    cur.execute(st)
                if args.schema_only:
                    _out("Tabel dimensiuni_tocuri: migrare aplicata (schema-only).")
                    return 0
                cur.execute("delete from public.dimensiuni_tocuri")
                cur.executemany(
                    """
                    insert into public.dimensiuni_tocuri
                      (tip_toc, material_toc, latime_foaie_de_usa, latime_deschidere, inaltime_deschidere)
                    values (%s, %s, %s, %s, %s)
                    """,
                    rows,
                )
                cur.execute("notify pgrst, 'reload schema'")
    except Exception as e:
        _out(f"Eroare Postgres: {e}")
        return 1

    _out(f"Gata: {len(rows)} randuri in dimensiuni_tocuri.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
