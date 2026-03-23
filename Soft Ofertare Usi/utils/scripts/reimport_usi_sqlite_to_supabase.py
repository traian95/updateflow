"""
Reimportă din SQLite (date_ofertare.db) în Supabase rândurile echivalente celor șterse în masă:
- categorie Usi Interior sau Usi intrare apartament, sau
- furnizor Erkado (oricare categorie).

Folosește cheia service_role din ofertare.updater ca să treacă de RLS.
Nu trimite `id` (ID noi în Supabase). Coloane necunoscute în Postgres sunt ignorate.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from typing import Any

# Rulare: din folderul Soft Ofertare Usi (cel cu pachetul ofertare)
if __name__ == "__main__":
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _root not in sys.path:
        sys.path.insert(0, _root)

from supabase import create_client

from ofertare.db_cloud import SUPABASE_URL, TABLE_PRODUSE, _invalidate
from ofertare.updater import SUPABASE_ADMIN_SERVICE_ROLE_KEY

# Coloane acceptate de tabela public.produse (fără id)
SUPABASE_PRODUSE_COLS = frozenset(
    {
        "categorie",
        "furnizor",
        "colectie",
        "model",
        "decor",
        "tip_toc",
        "dimensiune",
        "pret",
        "finisaj",
        "este_izolatie",
    }
)


def _find_sqlite_path() -> str:
    explicit = (os.environ.get("SQLITE_PRODUSE_IMPORT_PATH") or "").strip()
    if explicit and os.path.isfile(explicit):
        return explicit
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(os.path.dirname(here), "date_ofertare.db"),
        os.path.join(here, "date_ofertare.db"),
    ]
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        candidates.append(os.path.join(appdata, "Soft Ofertare Usi", "date_ofertare.db"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(
        "Nu găsesc date_ofertare.db. Pune calea în SQLITE_PRODUSE_IMPORT_PATH sau copiază fișierul lângă proiect."
    )


def _row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    rid = row.get("id")
    if rid is not None:
        try:
            out["id"] = int(rid)
        except (TypeError, ValueError):
            pass
    for k, v in row.items():
        if k == "id":
            continue
        if k == "nume":
            continue
        if k not in SUPABASE_PRODUSE_COLS:
            continue
        if v is None:
            out[k] = None
        elif k == "pret":
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = 0.0
        elif k == "este_izolatie":
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                out[k] = 0
        else:
            out[k] = v
    return out


def main() -> int:
    url = (SUPABASE_URL or "").strip()
    key = (SUPABASE_ADMIN_SERVICE_ROLE_KEY or "").strip()
    if not url or not key:
        print("Lipsește SUPABASE_URL sau SUPABASE_ADMIN_SERVICE_ROLE_KEY (updater).")
        return 1

    db_path = _find_sqlite_path()
    print("SQLite:", db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='produse'")
    if not cur.fetchone():
        print("Nu există tabela produse în SQLite.")
        conn.close()
        return 1

    cur.execute(
        """
        SELECT * FROM produse
        WHERE categorie IN ('Usi Interior', 'Usi intrare apartament')
           OR LOWER(TRIM(COALESCE(furnizor, ''))) = 'erkado'
        """
    )
    raw_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not raw_rows:
        print("0 rows match filter (Usi Interior / intrare or Erkado).")
        return 0

    payloads = []
    for r in raw_rows:
        p = _row_to_payload(r)
        if not p.get("categorie") and not p.get("furnizor"):
            continue
        payloads.append(p)

    print(f"Rows to insert: {len(payloads)}")

    cli = create_client(url, key)
    batch = 80
    ok = 0
    for i in range(0, len(payloads), batch):
        chunk = payloads[i : i + batch]
        try:
            cli.table(TABLE_PRODUSE).insert(chunk).execute()
        except Exception as e:
            # Reîncearcă pe bucăți dacă un rând are coloană invalidă
            for one in chunk:
                try:
                    cli.table(TABLE_PRODUSE).insert(one).execute()
                    ok += 1
                except Exception as e2:
                    print("SKIP:", one.get("categorie"), one.get("furnizor"), one.get("colectie"), one.get("model"), e2)
            continue
        ok += len(chunk)
        print(f"  inserted {ok}/{len(payloads)}")

    _invalidate(TABLE_PRODUSE)
    print("Done. Successful inserts:", ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
