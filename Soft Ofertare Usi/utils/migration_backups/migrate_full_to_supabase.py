import os
import sqlite3
import sys
from typing import Any

from supabase import create_client
from ofertare.db_cloud import SUPABASE_KEY, SUPABASE_URL

TABLES_ORDER = [
    "schema_version",
    "sync_state",
    "clienti",
    "users",
    "produse",
    "izolatiile",
    "oferte",
]


def fail(message: str, details: str | None = None) -> None:
    print(f"Eroare: {message}")
    if details:
        print(f"Detalii: {details}")
    sys.exit(1)


def get_supabase():
    url = SUPABASE_URL.strip()
    key = SUPABASE_KEY.strip()
    if not url or not key:
        fail("Lipsesc SUPABASE_URL/SUPABASE_KEY in configurarea aplicatiei.")
    return create_client(url, key)


def sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def upload_table(sb, table: str, rows: list[dict[str, Any]], batch_size: int = 500) -> None:
    sb.table(table).delete().neq("id", -1).execute()
    if not rows:
        print(f"{table}: 0 randuri (gol).")
        return
    total = len(rows)
    uploaded = 0
    for i in range(0, total, batch_size):
        chunk = rows[i : i + batch_size]
        sb.table(table).insert(chunk).execute()
        uploaded += len(chunk)
        print(f"{table}: {uploaded}/{total}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    db_path = "date_ofertare.db"
    if not os.path.exists(db_path):
        fail(f"Nu gasesc baza locala: {db_path}")

    sb = get_supabase()
    conn = sqlite3.connect(db_path)
    try:
        for table in TABLES_ORDER:
            rows = sqlite_rows(conn, table)
            upload_table(sb, table, rows)
    finally:
        conn.close()

    print("Migrare completa finalizata cu succes!")


if __name__ == "__main__":
    main()
