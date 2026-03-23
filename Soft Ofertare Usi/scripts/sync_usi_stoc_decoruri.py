# -*- coding: utf-8 -*-
"""
Rescrie in Supabase produsele „Usi Interior” / „Stoc”: pentru fiecare pereche
(colectie, model) existenta, sterge randurile vechi si insereaza cele 13 decoruri
din catalog (9 x „… INOVA” + 4 x „… LAMINAT”).

Inainte de stergere se salveaza backup JSON langa acest script:
  _usi_stoc_sync_backup.json

Rulare normala (din folderul care contine pachetul ofertare):
  python scripts/sync_usi_stoc_decoruri.py

Daca nu mai exista uși Stoc in BD (ex. migrare esuata), poti insera doar din lista:
  python scripts/sync_usi_stoc_decoruri.py --from-json scripts/usi_stoc_groups.example.json

Format JSON (lista de obiecte):
  [{"colectie": "…", "model": "…", "pret": 199.0}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from supabase import create_client

from ofertare.db_cloud import TABLE_PRODUSE, _invalidate
from ofertare.updater import SUPABASE_ADMIN_URL, SUPABASE_ADMIN_SERVICE_ROLE_KEY

CATEGORIE = "Usi Interior"
FURNIZOR = "Stoc"

DECORURI_INOVA = [
    "STEJAR GOTIC",
    "CARPEN",
    "NUC",
    "ALB",
    "KASMIR",
    "STEJAR RIVIERA",
    "STEJAR PASTEL",
    "WENGE ALB",
    "HALIFAX",
]

DECORURI_LAMINAT = [
    "SILVER OAK",
    "ATTIC WOOD",
    "STEJAR SESIL",
    "BERGAN",
]

BATCH_INSERT = 200
BACKUP_NAME = "_usi_stoc_sync_backup.json"
SQLITE_IMPORT_BACKUP = "_usi_stoc_sqlite_import_backup.json"


def _find_sqlite_date_ofertare() -> str:
    """Aceeași rezolvare ca la utils/scripts/reimport_usi_sqlite_to_supabase."""
    explicit = (os.environ.get("SQLITE_PRODUSE_IMPORT_PATH") or "").strip()
    if explicit and os.path.isfile(explicit):
        return explicit
    here = _root
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
        "Nu gasesc date_ofertare.db. Seteaza SQLITE_PRODUSE_IMPORT_PATH sau copiaza fisierul langa proiect."
    )


def _split_modele_sqlite(model_raw: str) -> list[str]:
    s = (model_raw or "").strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(",") if p.strip()]
    return parts if parts else [s]


def _groups_from_sqlite_stoc(db_path: str) -> list[tuple[str, str, float]]:
    """Usi Interior + Stoc din SQLite; pret = max pe (colectie, model)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='produse'")
    if not cur.fetchone():
        conn.close()
        raise RuntimeError("Tabela produse lipseste din SQLite.")
    cur.execute(
        """
        SELECT colectie, model, pret FROM produse
        WHERE LOWER(TRIM(COALESCE(categorie, ''))) = 'usi interior'
          AND LOWER(TRIM(COALESCE(furnizor, ''))) = 'stoc'
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    preturi: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        col = str(r.get("colectie") or "").strip()
        mod_raw = str(r.get("model") or "").strip()
        try:
            pret = float(r.get("pret") or 0)
        except (TypeError, ValueError):
            pret = 0.0
        for mod in _split_modele_sqlite(mod_raw):
            if col and mod:
                preturi[(col, mod)].append(pret)
    out: list[tuple[str, str, float]] = []
    for (col, mod), plist in sorted(preturi.items(), key=lambda x: (x[0][0], x[0][1])):
        mx = max(plist) if plist else 0.0
        if mx <= 0:
            mx = 1.0
        out.append((col, mod, mx))
    return out


def _client():
    return create_client(SUPABASE_ADMIN_URL.strip(), SUPABASE_ADMIN_SERVICE_ROLE_KEY.strip())


def _max_produse_id(client) -> int:
    r = client.table(TABLE_PRODUSE).select("id").order("id", desc=True).limit(1).execute().data or []
    if not r:
        return 0
    try:
        return int(r[0].get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _fetch_all_produse(client) -> list[dict]:
    out: list[dict] = []
    page = 1000
    offset = 0
    while True:
        batch = (
            client.table(TABLE_PRODUSE)
            .select("*")
            .range(offset, offset + page - 1)
            .execute()
            .data
            or []
        )
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return out


def _build_rows_for_groups(groups: list[tuple[str, str, float]]) -> list[dict]:
    new_rows: list[dict] = []
    for col, mod, pret in groups:
        if pret <= 0:
            pret = 1.0
        for name in DECORURI_INOVA:
            new_rows.append(
                {
                    "categorie": CATEGORIE,
                    "furnizor": FURNIZOR,
                    "colectie": col,
                    "model": mod,
                    "decor": f"{name} INOVA",
                    "finisaj": "",
                    "tip_toc": "",
                    "dimensiune": "",
                    "pret": pret,
                    "este_izolatie": 0,
                }
            )
        for name in DECORURI_LAMINAT:
            new_rows.append(
                {
                    "categorie": CATEGORIE,
                    "furnizor": FURNIZOR,
                    "colectie": col,
                    "model": mod,
                    "decor": f"{name} LAMINAT",
                    "finisaj": "",
                    "tip_toc": "",
                    "dimensiune": "",
                    "pret": pret,
                    "este_izolatie": 0,
                }
            )
    return new_rows


def _insert_rows(client, new_rows: list[dict]) -> None:
    start_id = _max_produse_id(client) + 1
    for i, row in enumerate(new_rows):
        row["id"] = start_id + i
    for i in range(0, len(new_rows), BATCH_INSERT):
        client.table(TABLE_PRODUSE).insert(new_rows[i : i + BATCH_INSERT]).execute()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--from-json",
        metavar="FILE",
        help="Insereaza din lista colectie/model/pret.",
    )
    ap.add_argument(
        "--wipe-stoc",
        action="store_true",
        help="Cu --from-json: sterge inainte toate randurile Usi Interior / Stoc (evita duplicate).",
    )
    ap.add_argument(
        "--from-sqlite",
        nargs="?",
        const="__AUTO__",
        default=None,
        metavar="PATH",
        help="Importa toate modelele Usi Interior/Stoc din date_ofertare.db si rescrie in Supabase cu 13 decoruri. Cale optionala.",
    )
    args = ap.parse_args()

    client = _client()

    if args.from_sqlite:
        db_path = _find_sqlite_date_ofertare() if args.from_sqlite == "__AUTO__" else (args.from_sqlite or "").strip()
        if not db_path or not os.path.isfile(db_path):
            print("SQLite inexistent:", db_path)
            return 1
        print("SQLite:", db_path)
        groups_list = _groups_from_sqlite_stoc(db_path)
        if not groups_list:
            print("Nu exista randuri Usi Interior / Stoc in SQLite.")
            return 1
        snap_path = os.path.join(os.path.dirname(__file__), SQLITE_IMPORT_BACKUP)
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(
                [{"colectie": a, "model": b, "pret": c} for a, b, c in groups_list],
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"Backup modele: {snap_path} ({len(groups_list)} modele)")
        all_rows = _fetch_all_produse(client)
        usi_del = [
            r
            for r in all_rows
            if str(r.get("categorie") or "") == CATEGORIE and str(r.get("furnizor") or "") == FURNIZOR
        ]
        ids_del = [int(r["id"]) for r in usi_del if r.get("id") is not None]
        if ids_del:
            print(f"Sterg {len(ids_del)} rand(uri) Usi Interior / Stoc din Supabase...")
            for i in range(0, len(ids_del), 100):
                client.table(TABLE_PRODUSE).delete().in_("id", ids_del[i : i + 100]).execute()
        new_rows = _build_rows_for_groups(groups_list)
        print(f"Inserez {len(new_rows)} randuri ({len(groups_list)} modele x 13 decoruri INOVA/LAMINAT)...")
        _insert_rows(client, new_rows)
        _invalidate(TABLE_PRODUSE)
        print("Gata import SQLite -> Supabase.")
        return 0

    if args.from_json:
        path = args.from_json
        if not os.path.isfile(path):
            print("Fisier inexistent:", path)
            return 1
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        groups = []
        for o in raw:
            col = str(o.get("colectie") or "").strip()
            mod = str(o.get("model") or "").strip()
            try:
                pret = float(o.get("pret") or 0)
            except (TypeError, ValueError):
                pret = 0.0
            if not col or not mod:
                continue
            groups.append((col, mod, pret))
        if not groups:
            print("JSON fara perechi valide (colectie, model).")
            return 1
        if args.wipe_stoc:
            all_rows = _fetch_all_produse(client)
            usi_del = [
                r
                for r in all_rows
                if str(r.get("categorie") or "") == CATEGORIE and str(r.get("furnizor") or "") == FURNIZOR
            ]
            ids_del = [int(r["id"]) for r in usi_del if r.get("id") is not None]
            if ids_del:
                print(f"--wipe-stoc: sterg {len(ids_del)} rand(uri) Usi Interior / Stoc...")
                for i in range(0, len(ids_del), 100):
                    client.table(TABLE_PRODUSE).delete().in_("id", ids_del[i : i + 100]).execute()
        new_rows = _build_rows_for_groups(groups)
        print(f"Insert din JSON: {len(groups)} modele x 13 = {len(new_rows)} randuri...")
        _insert_rows(client, new_rows)
        _invalidate(TABLE_PRODUSE)
        print("Gata.")
        return 0

    all_rows = _fetch_all_produse(client)
    usi = [
        r
        for r in all_rows
        if str(r.get("categorie") or "") == CATEGORIE and str(r.get("furnizor") or "") == FURNIZOR
    ]
    if not usi:
        print(
            "Nu exista randuri Usi Interior / Stoc. "
            "Daca ai pierdut datele la o migrare esuata, restaureaza din backup Supabase "
            f"sau foloseste: python scripts/sync_usi_stoc_decoruri.py --from-json <lista.json>"
        )
        return 1

    from collections import defaultdict

    groups_map: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in usi:
        col = str(r.get("colectie") or "")
        mod = str(r.get("model") or "")
        groups_map[(col, mod)].append(r)

    backup_path = os.path.join(os.path.dirname(__file__), BACKUP_NAME)
    snap = []
    for (col, mod), rows in groups_map.items():
        prets = [float(r.get("pret") or 0) for r in rows]
        pret = max(prets) if prets else 0.0
        snap.append({"colectie": col, "model": mod, "pret": pret})
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    print(f"Backup salvat: {backup_path} ({len(snap)} modele)")

    ids_del = [int(r["id"]) for r in usi if r.get("id") is not None]
    print(f"Sterg {len(ids_del)} rand(uri) vechi Usi Interior / Stoc...")
    for i in range(0, len(ids_del), 100):
        chunk = ids_del[i : i + 100]
        client.table(TABLE_PRODUSE).delete().in_("id", chunk).execute()

    groups_list: list[tuple[str, str, float]] = []
    for (col, mod), rows in sorted(groups_map.items(), key=lambda x: (x[0][0], x[0][1])):
        prets = [float(r.get("pret") or 0) for r in rows]
        pret = max(prets) if prets else 0.0
        groups_list.append((col, mod, pret))

    new_rows = _build_rows_for_groups(groups_list)
    print(f"Inserez {len(new_rows)} rand(uri) noi ({len(groups_map)} modele x 13 decoruri)...")
    _insert_rows(client, new_rows)
    _invalidate(TABLE_PRODUSE)
    print("Gata. Reporneste aplicatia sau asteapta expirarea cache-ului (TTL).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
