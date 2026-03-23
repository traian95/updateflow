import os
import sys
from urllib.parse import urlparse

import requests
from ofertare.db_cloud import SUPABASE_KEY, SUPABASE_URL
from supabase import create_client


def _fail(message: str, exc: Exception | None = None) -> None:
    print(f"Eroare: {message}")
    if exc is not None:
        print(f"Detalii tehnice: {type(exc).__name__}: {exc}")
    sys.exit(1)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    supabase_url = SUPABASE_URL.strip()
    key_name = "SUPABASE_KEY"
    supabase_key = SUPABASE_KEY.strip()

    if not supabase_url:
        _fail("Lipseste SUPABASE_URL in configurarea aplicatiei.")
    if not supabase_key:
        _fail("Lipseste cheia Supabase in configurarea aplicatiei.")

    parsed = urlparse(supabase_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        _fail("SUPABASE_URL nu este un URL valid (ex: https://xxxx.supabase.co).")

    try:
        # Initializare client Supabase (verifica formatul URL/key in SDK).
        create_client(supabase_url, supabase_key)

        # Health check simplu: apel la endpoint-ul REST de baza.
        response = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
            timeout=10,
        )
        response.raise_for_status()

        print(f"Testat cu cheia: {key_name}")
        print("Conexiune reușită!")
    except Exception as exc:
        _fail(f"Conectarea la Supabase a esuat (cheie folosita: {key_name}).", exc)


if __name__ == "__main__":
    main()
