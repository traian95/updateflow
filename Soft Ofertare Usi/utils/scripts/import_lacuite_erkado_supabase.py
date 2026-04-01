from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from supabase import create_client

if __name__ == "__main__":
    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from ofertare.db_cloud import TABLE_PRODUSE, SUPABASE_URL, _invalidate
from ofertare.updater import SUPABASE_ADMIN_SERVICE_ROLE_KEY, SUPABASE_ADMIN_URL


def _norm_header(name: Any) -> str:
    s = str(name or "").replace("\r", "").replace("\n", " ").replace("\xa0", " ").strip().lower()
    repl = {"ă": "a", "â": "a", "î": "i", "ș": "s", "ş": "s", "ț": "t", "ţ": "t"}
    for a, b in repl.items():
        s = s.replace(a, b)
    return " ".join(s.split())


def _norm_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _service_role_key() -> str:
    env_key = (SUPABASE_ADMIN_SERVICE_ROLE_KEY or "").strip()
    if env_key:
        return env_key
    candidates = [
        _root / "supabase_service_role.key",
        Path(os.environ.get("APPDATA", "")) / "Soft Ofertare Usi" / "supabase_service_role.key",
    ]
    for c in candidates:
        try:
            if c.is_file():
                val = c.read_text(encoding="utf-8").strip()
                if val:
                    return val
        except Exception:
            pass
    return ""


def _pick_first(row: pd.Series, cols_map: dict[str, str], keys: list[str]) -> str:
    for k in keys:
        col = cols_map.get(k)
        if not col:
            continue
        v = row.get(col)
        if pd.isna(v):
            continue
        s = str(v).strip()
        if s and s.lower() != "nan":
            return s
    return ""


def _parse_price(row: pd.Series, cols_map: dict[str, str]) -> float:
    candidates = [
        "pret lista (€)",
        "pret lista (eur)",
        "pret lista eur",
        "pret lista",
        "pret",
        "pret listă (€)",
        "pret listă",
        "preț listă",
        "preț",
    ]
    for k in candidates:
        col = cols_map.get(_norm_header(k))
        if not col:
            continue
        v = row.get(col)
        if pd.isna(v):
            continue
        try:
            return float(str(v).replace(",", ".").strip() or "0")
        except (TypeError, ValueError):
            continue
    return 0.0


def main() -> int:
    csv_path = _root / "template_import_usi_erkado_supabase.csv"
    xlsx_path = _root / "template_import_usi_erkado_supabase.xlsx"
    source_path = csv_path if csv_path.is_file() else xlsx_path
    if not source_path.is_file():
        print(f"Fisier inexistent: {csv_path} sau {xlsx_path}")
        return 1

    url = (SUPABASE_ADMIN_URL or SUPABASE_URL or "").strip()
    key = _service_role_key()
    if not url or not key:
        print("Lipseste SUPABASE_ADMIN_URL/SUPABASE_SERVICE_ROLE_KEY (sau supabase_service_role.key).")
        return 1

    if source_path.suffix.lower() == ".csv":
        df = pd.read_csv(source_path)
    else:
        df = pd.read_excel(source_path)
    cols_map: dict[str, str] = {_norm_header(c): c for c in df.columns}

    payload_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for _, row in df.iterrows():
        if not any(pd.notna(row.get(c)) and str(row.get(c)).strip() not in ("", "nan") for c in df.columns):
            continue
        categorie = _pick_first(row, cols_map, ["categorie"]) or "Usi Interior"
        furnizor = _pick_first(row, cols_map, ["furnizor"]) or "Erkado"
        colectie = _pick_first(row, cols_map, ["colectie", "colectia", "colecție"])
        model = _pick_first(row, cols_map, ["cod produs", "cod_prod", "model"])
        pret = _parse_price(row, cols_map)

        # Cerință: categoria LACUITE -> finisaj forțat LACUIT.
        finisaj = "LACUIT"
        decor = ""

        if not colectie or not model:
            continue
        if pret <= 0:
            continue

        key_tuple = (_norm_key(categorie), _norm_key(furnizor), _norm_key(colectie), _norm_key(model), _norm_key(finisaj))
        payload_by_key[key_tuple] = {
            "categorie": categorie.strip(),
            "furnizor": furnizor.strip(),
            "colectie": colectie.strip(),
            "model": model.strip(),
            "finisaj": finisaj,
            "decor": decor,
            "tip_toc": "",
            "dimensiune": "",
            "pret": float(pret),
            "este_izolatie": 0,
        }

    if not payload_by_key:
        print("Nu exista randuri valide pentru import.")
        return 0

    client = create_client(url, key)

    existing_rows: list[dict[str, Any]] = []
    offset = 0
    page = 1000
    while True:
        batch = (
            client.table(TABLE_PRODUSE)
            .select("id,categorie,furnizor,colectie,model,finisaj,decor,pret")
            .eq("furnizor", "Erkado")
            .eq("categorie", "Usi Interior")
            .range(offset, offset + page - 1)
            .execute()
            .data
            or []
        )
        existing_rows.extend(batch)
        if len(batch) < page:
            break
        offset += page

    existing_by_key: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for r in existing_rows:
        k = (
            _norm_key(r.get("categorie")),
            _norm_key(r.get("furnizor")),
            _norm_key(r.get("colectie")),
            _norm_key(r.get("model")),
            _norm_key(r.get("finisaj")),
        )
        existing_by_key.setdefault(k, []).append(r)
    max_id = 0
    try:
        top = client.table(TABLE_PRODUSE).select("id").order("id", desc=True).limit(1).execute().data or []
        if top:
            max_id = int(top[0].get("id") or 0)
    except Exception:
        pass

    inserted = 0
    updated = 0
    for k, payload in payload_by_key.items():
        matches = existing_by_key.get(k, [])
        if matches:
            for r in matches:
                rid = r.get("id")
                if rid is None:
                    continue
                client.table(TABLE_PRODUSE).update({"pret": payload["pret"], "decor": ""}).eq("id", rid).execute()
                updated += 1
        else:
            max_id += 1
            ins = dict(payload)
            ins["id"] = max_id
            client.table(TABLE_PRODUSE).insert(ins).execute()
            inserted += 1

    _invalidate(TABLE_PRODUSE)
    print(f"Import LACUITE finalizat. Inserate: {inserted} | Actualizate: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

