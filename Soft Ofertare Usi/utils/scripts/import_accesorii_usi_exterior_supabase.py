# -*- coding: utf-8 -*-
"""
Importă accesorii_usi_exterior_template.csv în Supabase, tabela `produse`,
categorie «Accesorii ușă exterior» (preț EUR listă fără TVA).

Coloane CSV: nume, decor, pret_eur_fara_tva

Rulare (din folderul «Soft Ofertare Usi»):
  py utils/scripts/import_accesorii_usi_exterior_supabase.py
  py utils/scripts/import_accesorii_usi_exterior_supabase.py --csv cale\\fisier.csv --dry-run

Necesită SUPABASE_SERVICE_ROLE_KEY sau fișier supabase_service_role.key (ca la celelalte importuri).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

_soft_root = Path(__file__).resolve().parents[2]
if str(_soft_root) not in sys.path:
    sys.path.insert(0, str(_soft_root))

from ofertare.db_cloud import (  # noqa: E402
    CATEGORIE_ACCESORII_USA_EXTERIOR,
    FURNIZOR_ACCESORII_USA_EXTERIOR,
    delete_accesorii_usa_exterior_catalog,
    insert_produs,
)


def _out(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def _parse_csv(path: Path) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            return rows
        lower = {str(h).strip().lower(): h for h in r.fieldnames}

        def col(*names: str) -> str | None:
            for n in names:
                k = lower.get(n.lower().strip())
                if k:
                    return k
            return None

        c_nume = col("nume", "denumire", "name")
        c_decor = col("decor", "finisaj")
        c_pret = col("pret_eur_fara_tva", "pret", "pret_eur")
        if not c_nume or not c_pret:
            raise ValueError("CSV trebuie să conțină coloanele «nume» și «pret_eur_fara_tva» (sau «pret»).")

        for line in r:
            nume = str(line.get(c_nume) or "").strip()
            if not nume:
                continue
            decor = str(line.get(c_decor) or "").strip() if c_decor else ""
            raw = str(line.get(c_pret) or "").strip().replace(",", ".")
            try:
                pret = float(raw)
            except ValueError:
                _out(f"Sarit (preț invalid): {nume!r} — {raw!r}")
                continue
            rows.append((nume, decor, pret))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Import accesorii ușă exterior în Supabase (produse).")
    ap.add_argument(
        "--csv",
        type=Path,
        default=_soft_root / "accesorii_usi_exterior_template.csv",
        help="Cale către CSV (implicit accesorii_usi_exterior_template.csv)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Nu scrie în baza de date.")
    ap.add_argument(
        "--no-replace",
        action="store_true",
        help="Nu șterge catalogul existent «Accesorii ușă exterior» înainte de insert.",
    )
    args = ap.parse_args()

    if not args.csv.is_file():
        _out(f"Fișier inexistent: {args.csv}")
        return 1

    try:
        payloads = _parse_csv(args.csv)
    except Exception as e:
        _out(f"Eroare citire CSV: {e}")
        return 1

    if not payloads:
        _out("Nu există rânduri valide.")
        return 1

    _out(f"Categorie: {CATEGORIE_ACCESORII_USA_EXTERIOR} | furnizor: {FURNIZOR_ACCESORII_USA_EXTERIOR}")
    _out(f"Rânduri: {len(payloads)}")

    if args.dry_run:
        for nume, decor, pret in payloads:
            _out(f"  {nume!r} | decor={decor!r} | {pret} EUR fără TVA")
        return 0

    if not args.no_replace:
        delete_accesorii_usa_exterior_catalog()
        _out("Șters catalogul vechi «Accesorii ușă exterior».")

    for nume, decor, pret in payloads:
        insert_produs(
            None,
            None,
            CATEGORIE_ACCESORII_USA_EXTERIOR,
            FURNIZOR_ACCESORII_USA_EXTERIOR,
            "",
            nume,
            decor,
            "",
            "",
            "",
            pret,
        )

    _out(f"Import finalizat: {len(payloads)} rânduri.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
