import os
import sqlite3
import sys
from typing import Any

from supabase import create_client
from ofertare.db_cloud import SUPABASE_KEY, SUPABASE_URL

# Ignoram "produse" (deja populat in cloud), migram doar aceste tabele:
TABLES_IN_ORDER = [
    "clienti",      # trebuie inainte de oferte (FK id_client)
    "users",
    "izolatiile",
    "oferte",
]


def fail(message: str, details: str | None = None) -> None:
    print(f"Eroare: {message}")
    if details:
        print(f"Detalii: {details}")
    sys.exit(1)


def get_supabase_client():
    url = SUPABASE_URL.strip()
    key = SUPABASE_KEY.strip()

    if not url or not key:
        fail("Lipsesc SUPABASE_URL/SUPABASE_KEY in configurarea aplicatiei.")
    return create_client(url, key)


def read_table_rows(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name}")
    return [dict(row) for row in cur.fetchall()]


def upload_rows(sb, table_name: str, rows: list[dict[str, Any]], batch_size: int = 500) -> None:
    if not rows:
        print(f"{table_name}: 0 randuri (nimic de migrat).")
        return

    total = len(rows)
    uploaded = 0
    for i in range(0, total, batch_size):
        chunk = rows[i : i + batch_size]
        # upsert pe id => sigur la rerulare (nu dubleaza PK)
        sb.table(table_name).upsert(chunk, on_conflict="id").execute()
        uploaded += len(chunk)
        print(f"{table_name}: {uploaded}/{total}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    db_path = "date_ofertare.db"
    if not os.path.exists(db_path):
        fail(f"Nu gasesc baza locala: {db_path}")

    sb = get_supabase_client()
    conn = sqlite3.connect(db_path)
    try:
        for table in TABLES_IN_ORDER:
            rows = read_table_rows(conn, table)
            upload_rows(sb, table, rows)
    finally:
        conn.close()

    print("Migrare finala completa! (clienti, users, izolatiile, oferte)")


if __name__ == "__main__":
    main()
