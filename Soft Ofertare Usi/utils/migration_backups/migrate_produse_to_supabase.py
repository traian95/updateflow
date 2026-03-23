import os
import sqlite3
import sys
from typing import Any

import requests
from ofertare.db_cloud import SUPABASE_KEY, SUPABASE_URL


def fail(message: str, details: str | None = None) -> None:
    print(f"Eroare: {message}")
    if details:
        print(f"Detalii: {details}")
    sys.exit(1)


def load_env() -> tuple[str, str]:
    supabase_url = SUPABASE_URL.strip()
    supabase_key = SUPABASE_KEY.strip()

    if not supabase_url:
        fail("Lipseste SUPABASE_URL in configurarea aplicatiei.")
    if not supabase_key:
        fail("Lipseste cheia Supabase in configurarea aplicatiei.")
    return supabase_url.rstrip("/"), supabase_key


def sqlite_type_to_pg(sqlite_type: str) -> str:
    t = (sqlite_type or "").upper()
    if "INT" in t:
        return "BIGINT"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "DOUBLE PRECISION"
    if "BLOB" in t:
        return "BYTEA"
    return "TEXT"


def build_create_table_sql(conn: sqlite3.Connection, table_name: str) -> tuple[str, list[str]]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = cur.fetchall()
    if not cols:
        fail(f"Tabelul '{table_name}' nu exista in baza SQLite.")

    col_defs: list[str] = []
    col_names: list[str] = []
    for _, name, col_type, notnull, default_value, pk in cols:
        col_names.append(name)
        pg_type = sqlite_type_to_pg(col_type)
        line = f'"{name}" {pg_type}'
        if notnull:
            line += " NOT NULL"
        if default_value is not None:
            line += f" DEFAULT {default_value}"
        if pk:
            line += " PRIMARY KEY"
        col_defs.append(line)

    sql = (
        f'CREATE TABLE IF NOT EXISTS public."{table_name}" (\n  '
        + ",\n  ".join(col_defs)
        + "\n);"
    )
    return sql, col_names


def postgrest_request(
    method: str,
    url: str,
    key: str,
    endpoint: str,
    *,
    json_data: Any = None,
    extra_headers: dict[str, str] | None = None,
) -> requests.Response:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return requests.request(
        method,
        f"{url}/rest/v1/{endpoint.lstrip('/')}",
        headers=headers,
        json=json_data,
        timeout=30,
    )


def table_exists_in_supabase(url: str, key: str, table_name: str) -> bool:
    res = postgrest_request("GET", url, key, f'{table_name}?select=id&limit=1')
    if res.status_code == 404:
        return False
    if res.status_code >= 400:
        fail("Nu pot verifica existenta tabelului in Supabase.", res.text)
    return True


def try_create_table_via_rpc(url: str, key: str, create_sql: str) -> bool:
    # Unele proiecte au un RPC custom (ex: exec_sql/run_sql/execute_sql).
    for rpc_name in ("exec_sql", "run_sql", "execute_sql"):
        res = postgrest_request("POST", url, key, f"rpc/{rpc_name}", json_data={"sql": create_sql})
        if res.status_code < 300:
            print(f"Tabel creat prin RPC: {rpc_name}")
            return True
        if res.status_code in (404, 400):
            continue
        fail(f"RPC {rpc_name} a esuat la creare tabel.", res.text)
    return False


def fetch_sqlite_rows(conn: sqlite3.Connection, table_name: str, col_names: list[str]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name}")
    rows = cur.fetchall()
    return [{col: row[col] for col in col_names} for row in rows]


def bulk_upload(url: str, key: str, table_name: str, rows: list[dict[str, Any]], batch_size: int = 500) -> int:
    inserted = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        res = postgrest_request(
            "POST",
            url,
            key,
            table_name,
            json_data=chunk,
            extra_headers={"Prefer": "return=minimal"},
        )
        if res.status_code >= 300:
            fail("Bulk upload esuat.", res.text)
        inserted += len(chunk)
        print(f"Upload: {inserted}/{len(rows)}")
    return inserted


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    supabase_url, supabase_key = load_env()
    db_path = "date_ofertare.db"
    table_name = "produse"

    if not os.path.exists(db_path):
        fail(f"Nu gasesc baza locala: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        create_sql, col_names = build_create_table_sql(conn, table_name)
        print("Schema SQLite detectata pentru tabelul produse.")

        exists = table_exists_in_supabase(supabase_url, supabase_key, table_name)
        if not exists:
            created = try_create_table_via_rpc(supabase_url, supabase_key, create_sql)
            if not created:
                fail(
                    "Nu pot crea tabelul in Supabase prin API-ul disponibil.",
                    "Ruleaza manual SQL-ul de mai jos in Supabase SQL Editor:\n\n" + create_sql,
                )
            exists = table_exists_in_supabase(supabase_url, supabase_key, table_name)
            if not exists:
                fail("Tabelul produse inca nu apare in cache-ul PostgREST dupa creare.")

        rows = fetch_sqlite_rows(conn, table_name, col_names)
        if not rows:
            print("Nu exista randuri in SQLite. Migrarea este gata (0 randuri).")
            return

        inserted = bulk_upload(supabase_url, supabase_key, table_name, rows, batch_size=500)
        print(f"Migrare gata! Au fost incarcate {inserted} randuri in Supabase.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
