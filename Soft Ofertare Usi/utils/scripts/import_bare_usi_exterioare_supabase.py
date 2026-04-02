# -*- coding: utf-8 -*-
"""
Importă bare_preturi.csv în Supabase, tabel dedicat `bare_exterioare` (listă separată de uși).

Dacă tabelul `bare_exterioare` nu e încă în API (PGRST205), scriptul scrie automat barele
în `usi_exterioare` (model + pret_baza) — compatibil cu configuratorul.
Alternativă completă (CREATE TABLE + import): bare_exterioare_via_postgres.py + supabase_db.url.

Rulare (din folderul «Soft Ofertare Usi»):
  py utils/scripts/import_bare_usi_exterioare_supabase.py

CSV implicit: bare_preturi.csv în updateflow/ sau lângă aplicație.

Necesită SUPABASE_SERVICE_ROLE_KEY sau fișier supabase_service_role.key.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_soft_root = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = Path(__file__).resolve().parent
for _p in (_SCRIPTS, _soft_root):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from supabase import create_client

from bare_csv_payloads import MODEL_PREFIX, build_bar_payloads_from_csv, resolve_default_csv
from ofertare.db_cloud import SUPABASE_URL, TABLE_BARE_EXTERIOARE, TABLE_USI_EXTERIOARE, _invalidate
from ofertare.updater import SUPABASE_ADMIN_SERVICE_ROLE_KEY, SUPABASE_ADMIN_URL


def _out(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


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
        except Exception:
            pass
    return ""


def main() -> int:
    p = argparse.ArgumentParser(description="Import bare în Supabase (tabel bare_exterioare).")
    p.add_argument("--csv", type=Path, default=None, help="Cale bare_preturi.csv")
    p.add_argument("--dry-run", action="store_true", help="Doar afișează rândurile, fără Supabase.")
    args = p.parse_args()

    csv_path = args.csv if args.csv is not None else resolve_default_csv(_soft_root, _REPO_ROOT)
    if not csv_path.is_file():
        _out(f"Fisier inexistent: {csv_path}")
        return 1

    def on_skip(msg: str, row: dict) -> None:
        _out(f"Sarit ({msg}): {row}")

    payloads = build_bar_payloads_from_csv(csv_path, on_skip=on_skip)

    if not payloads:
        _out("Nu exista randuri valide de importat.")
        return 1

    if args.dry_run:
        for pl in payloads:
            _out(str(pl))
        _out(f"Dry-run: {len(payloads)} randuri.")
        return 0

    url = (SUPABASE_ADMIN_URL or SUPABASE_URL or "").strip()
    key = _service_role_key()
    if not url or not key:
        _out("Lipseste URL Supabase sau cheia service_role (env sau supabase_service_role.key).")
        return 1

    client = create_client(url, key)

    def _bare_table_missing_api(exc: BaseException) -> bool:
        s = str(exc).lower()
        return "bare_exterioare" in s and ("pgrst205" in s or "schema cache" in s)

    use_bare_table = True
    try:
        client.table(TABLE_BARE_EXTERIOARE).delete().neq("model", "").execute()
    except Exception as e:
        if _bare_table_missing_api(e):
            use_bare_table = False
            _out(
                f"`{TABLE_BARE_EXTERIOARE}` nu e vizibil in API — import in `{TABLE_USI_EXTERIOARE}` (bare)."
            )
        else:
            _out(f"Stergere veche din `{TABLE_BARE_EXTERIOARE}`: {e}")
            return 1

    batch = 100
    insert_table = TABLE_BARE_EXTERIOARE if use_bare_table else TABLE_USI_EXTERIOARE

    if not use_bare_table:
        try:
            client.table(TABLE_USI_EXTERIOARE).delete().like("model", f"{MODEL_PREFIX}%").execute()
        except Exception as e:
            _out(f"Stergere bare vechi din `{TABLE_USI_EXTERIOARE}`: {e}")
            return 1

    for i in range(0, len(payloads), batch):
        chunk = payloads[i : i + batch]
        try:
            client.table(insert_table).insert(chunk).execute()
        except Exception as e:
            _out(f"Eroare la insert in `{insert_table}`: {e}")
            return 1

    if use_bare_table:
        try:
            client.table(TABLE_USI_EXTERIOARE).delete().like("model", f"{MODEL_PREFIX}%").execute()
        except Exception as e:
            _out(f"Atentie: nu s-au putut sterge randuri vechi din `{TABLE_USI_EXTERIOARE}`: {e}")

    _invalidate(TABLE_BARE_EXTERIOARE, TABLE_USI_EXTERIOARE)
    _out(f"Import finalizat: {len(payloads)} randuri in `{insert_table}`.")
    if use_bare_table:
        _out(f"(Randuri «{MODEL_PREFIX}…» eliminate din `{TABLE_USI_EXTERIOARE}` daca existau.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
