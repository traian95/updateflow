# -*- coding: utf-8 -*-
"""
Creeaza tabelul `kituri_feronerie` si incarca `kituri_organizat.xlsx` direct pe Postgres
(fara PostgREST / service role REST).

URI: Supabase Dashboard -> Project Settings -> Database -> Connection string -> URI
Fisier: Soft Ofertare Usi/supabase_db.url  (o linie)
Sau:    set SUPABASE_DB_URL=postgresql://...

Rulare (din folderul Soft Ofertare Usi):
  py utils/scripts/kituri_feronerie_via_postgres.py
  py utils/scripts/kituri_feronerie_via_postgres.py --xlsx cale\\kituri_organizat.xlsx --dry-run
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_SOFT_ROOT = _SCRIPTS.parents[1]
_MIGRATION_SQL = _SCRIPTS / "supabase_migrare_kituri_feronerie.sql"


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


def _rows_from_xlsx(path: Path) -> list[tuple]:
    import pandas as pd

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

    def _norm(s) -> str:
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return ""
        return str(s).strip()

    c_kit = col("kit")
    c_toc = col("tip_toc", "tip toc")
    c_dec = col("decor")
    c_pret = col("pret_eur_fara_tva", "pret")
    c_desc = col("descriere_feronerie", "descriere")
    if not all([c_kit, c_toc, c_dec, c_pret]):
        raise ValueError("Lipsesc coloane: kit, tip_toc, decor, pret_eur_fara_tva")

    out: list[tuple] = []
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
        out.append((kit, tip_toc, decor, pret, desc))
    return out


def main() -> int:
    try:
        import psycopg
    except ImportError:
        _out('Lipseste psycopg. Ruleaza: pip install "psycopg[binary]"')
        return 1

    import argparse

    ap = argparse.ArgumentParser(description="Migrare + import kituri_feronerie via Postgres.")
    ap.add_argument("--xlsx", type=Path, default=_SOFT_ROOT / "kituri_organizat.xlsx")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.xlsx.is_file():
        _out(f"Fisier inexistent: {args.xlsx}")
        return 1

    try:
        rows = _rows_from_xlsx(args.xlsx)
    except Exception as e:
        _out(f"Eroare citire xlsx: {e}")
        return 1

    if not rows:
        _out("Nu exista randuri valide in xlsx.")
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
                cur.execute("delete from public.kituri_feronerie")
                cur.executemany(
                    """
                    insert into public.kituri_feronerie
                      (kit, tip_toc, decor, pret_eur_fara_tva, descriere_feronerie)
                    values (%s, %s, %s, %s, %s)
                    """,
                    rows,
                )
                cur.execute("notify pgrst, 'reload schema'")
    except Exception as e:
        _out(f"Eroare Postgres: {e}")
        return 1

    _out(f"Gata: {len(rows)} randuri in kituri_feronerie.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
