# -*- coding: utf-8 -*-
"""Extrage din bare_preturi.csv lista {model, pret_baza} pentru import (fără dependență Supabase)."""
from __future__ import annotations

import csv
from pathlib import Path

MODEL_PREFIX = "Bara tragatoare | "


def resolve_default_csv(soft_root: Path, repo_root: Path) -> Path:
    for p in (repo_root / "bare_preturi.csv", soft_root / "bare_preturi.csv"):
        if p.is_file():
            return p
    return repo_root / "bare_preturi.csv"


def _norm_header(name: str) -> str:
    return str(name or "").replace("\r", "").replace("\n", " ").strip().lower()


def _row_by_norm(row: dict[str, str]) -> dict[str, str]:
    return {_norm_header(k): (v or "").strip() for k, v in row.items()}


def _row_model_label(n: dict[str, str]) -> str:
    cod = n.get("cod_model") or n.get("model") or ""
    lung_txt = n.get("lungime") or n.get("lungime_text") or ""
    lcm = n.get("lungime_cm") or ""
    decor = n.get("decor") or ""
    if not cod:
        raise ValueError("lipsește cod_model")
    if not decor:
        raise ValueError("lipsește decor")
    lung_disp = lung_txt if lung_txt else (f"{lcm} cm" if lcm else "")
    if not lung_disp:
        raise ValueError("lipsește lungime / lungime_cm")
    return f"{MODEL_PREFIX}{cod} | {lung_disp} | {decor}"


def _parse_pret(n: dict[str, str]) -> float:
    for key in ("pret_eur", "pret", "pret lista", "pret listă", "preț"):
        raw = n.get(_norm_header(key))
        if not raw:
            continue
        try:
            v = float(str(raw).replace(",", ".").strip())
            if v > 0:
                return v
        except ValueError:
            continue
    raise ValueError("lipsește pret_eur valid")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return [dict(row) for row in r]


def build_bar_payloads_from_csv(csv_path: Path, *, on_skip=None) -> list[dict]:
    """Returnează [{'model': str, 'pret_baza': float}, ...] deduplicat (ultimul câștigă)."""

    def _skip(msg: str, row: dict) -> None:
        if on_skip is not None:
            on_skip(msg, row)

    payloads: list[dict] = []
    for row in read_csv_rows(csv_path):
        n = _row_by_norm(row)
        if not any(n.values()):
            continue
        try:
            label = _row_model_label(n)
            pret = _parse_pret(n)
        except ValueError as e:
            _skip(str(e), row)
            continue
        payloads.append({"model": label, "pret_baza": pret})

    seen: set[str] = set()
    deduped: list[dict] = []
    for pl in payloads:
        m = pl["model"]
        if m in seen:
            deduped = [x for x in deduped if x["model"] != m]
        seen.add(m)
        deduped.append(pl)
    return deduped
