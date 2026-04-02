# -*- coding: utf-8 -*-
"""
Creează tabelul `bare_exterioare`, încarcă CSV-ul și curăță barele vechi din `usi_exterioare`
— direct pe Postgres, fără PostgREST (rezolvă PGRST205 / „schema cache”).

Nu pot rula asta „din cloud” fără parola bazei tale. Pe PC-ul tău: pune URI-ul Postgres
într-un fișier ignorat de git sau în variabilă de mediu, apoi rulezi o singură comandă.

Unde găsești URI: Supabase Dashboard → Project Settings → Database → Connection string → URI
(ex: postgresql://postgres.[PROJECT]:PAROLA@aws-0-....pooler.supabase.com:6543/postgres
 sau host db.xxx.supabase.co port 5432).

Fișier (recomandat):  Soft Ofertare Usi/supabase_db.url  — o singură linie, URI complet.
Sau:  set SUPABASE_DB_URL=postgresql://...

Dependență:  pip install "psycopg[binary]"

Rulare (din folderul Soft Ofertare Usi):
  py utils/scripts/bare_exterioare_via_postgres.py
  py utils/scripts/bare_exterioare_via_postgres.py --csv C:\\cale\\bare_preturi.csv
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_SOFT_ROOT = _SCRIPTS.parents[1]
_REPO_ROOT = _SCRIPTS.parents[2]
_MIGRATION_SQL = _SCRIPTS / "supabase_migrare_bare_exterioare.sql"


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
    """Elimină comentarii -- și împarte la ';' (fișierul de migrare nu are ';' în string-uri)."""
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


def main() -> int:
    try:
        import psycopg
    except ImportError:
        _out('Lipseste psycopg. Ruleaza: pip install "psycopg[binary]"')
        return 1

    import argparse

    from bare_csv_payloads import MODEL_PREFIX, build_bar_payloads_from_csv, resolve_default_csv

    ap = argparse.ArgumentParser(description="Migrare + import bare_exterioare via Postgres.")
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    csv_path = args.csv if args.csv is not None else resolve_default_csv(_SOFT_ROOT, _REPO_ROOT)
    if not csv_path.is_file():
        _out(f"Fisier inexistent: {csv_path}")
        return 1

    def on_skip(msg: str, row: dict) -> None:
        _out(f"Sarit ({msg}): {row}")

    payloads = build_bar_payloads_from_csv(csv_path, on_skip=on_skip)
    if not payloads:
        _out("Nu exista randuri valide.")
        return 1

    if args.dry_run:
        _out(f"Dry-run: {len(payloads)} randuri.")
        return 0

    url = _load_db_url()
    if not url or not url.startswith("postgres"):
        _out(
            "Lipseste URI Postgres. Creeaza fisierul supabase_db.url (o linie) in folderul "
            "'Soft Ofertare Usi' cu URI din Dashboard → Database, sau seteaza SUPABASE_DB_URL."
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
                cur.execute("delete from public.bare_exterioare")
                cur.executemany(
                    "insert into public.bare_exterioare (model, pret_baza) values (%s, %s)",
                    [(p["model"], float(p["pret_baza"])) for p in payloads],
                )
                cur.execute(
                    "delete from public.usi_exterioare where model like %s",
                    (f"{MODEL_PREFIX}%",),
                )
                cur.execute("notify pgrst, 'reload schema'")
    except Exception as e:
        _out(f"Eroare Postgres: {e}")
        return 1

    _out(f"Gata: {len(payloads)} randuri in bare_exterioare; bare vechi eliminate din usi_exterioare.")
    _out("Reporneste aplicatia sau asteapta cateva secunde ca API-ul sa reincarce schema.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_SCRIPTS))
    raise SystemExit(main())
