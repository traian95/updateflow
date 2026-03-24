"""Logica pairing ușă–toc (Safe Mode) — extrasă din `ui.py`."""

from __future__ import annotations

from typing import Any

from .offer_math import get_furnizor_from_item, get_item_tip


def map_erkado_usa_finisaj_to_toc_finisaj(usa_finisaj: str) -> str | None:
    v = (usa_finisaj or "").strip().upper()
    if not v:
        return None
    if "GREKO" in v:
        return "GREKO"
    if "LACUIT" in v:
        return "LACUIT"
    if "PREMIUM" in v:
        return "CPL/ST PREMIUM"
    if "CPL" in v:
        return "CPL/ST PREMIUM"
    return None


def required_toc_decor_option(
    cos: list[dict[str, Any]],
    furnizor: str,
    decor_values: list[str],
    pairs: list[tuple[str, str]],
) -> str | None:
    """Valoarea din dropdown-ul de finisaj/decor pentru următorul toc Erkado (sau Stoc)."""
    usi_match = [i for i in cos if get_item_tip(i) == "usi" and get_furnizor_from_item(i) == furnizor]
    tocuri_match = [i for i in cos if get_item_tip(i) == "tocuri" and get_furnizor_from_item(i) == furnizor]
    idx_next = len(tocuri_match)
    if idx_next >= len(usi_match):
        return None

    usa_item = usi_match[idx_next]
    usa_decor = (usa_item.get("usa_decor") or "").strip()
    usa_finisaj = (usa_item.get("usa_finisaj") or "").strip()
    if not usa_decor:
        usa_decor = (usa_item.get("usa_decor_display") or "").strip()
    if not usa_finisaj:
        nume_usa = usa_item.get("nume") or ""
        if "(" in nume_usa and ")" in nume_usa:
            try:
                inner = nume_usa.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
                if " / " in inner:
                    parts = inner.split(" / ")
                    usa_decor = (parts[0] or "").strip()
                    usa_finisaj = (parts[1] or "").strip() if len(parts) > 1 else usa_finisaj
                else:
                    usa_decor = inner
            except Exception:
                pass
    toc_finisaj = usa_finisaj
    if furnizor == "Erkado":
        mapped = map_erkado_usa_finisaj_to_toc_finisaj(usa_finisaj)
        if mapped:
            toc_finisaj = mapped
    required_raw = (
        f"{usa_decor} / {toc_finisaj}" if (usa_decor and toc_finisaj) else (toc_finisaj or usa_decor or None)
    )
    required = required_raw
    values = list(decor_values or [])
    if not values or not pairs:
        return required_raw if required_raw in values else None

    norm = lambda s: str(s or "").strip().lower()
    target_dec = norm(usa_decor)
    target_fin = norm(toc_finisaj)
    best_idx = None
    for i, (d, f) in enumerate(pairs):
        if norm(d) == target_dec and norm(f) == target_fin:
            best_idx = i
            break
    if best_idx is None and target_fin:
        for i, (d, f) in enumerate(pairs):
            if norm(f) == target_fin:
                best_idx = i
                break
    if best_idx is None and target_dec:
        for i, (d, f) in enumerate(pairs):
            if norm(d) == target_dec:
                best_idx = i
                break
    if best_idx is not None and best_idx < len(values):
        return values[best_idx]
    if required_raw and required_raw in values:
        return required_raw
    return None
