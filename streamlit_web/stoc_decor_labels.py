"""Etichete combobox uși Stoc — copie din `ofertare.ui` fără dependențe Tk."""

from __future__ import annotations

import re

# Decoruri cu sufix LAMINAT (nu INOVA 3D) – afișare uși Stoc.
_DECOR_STOC_AFISARE_LAMINAT = frozenset({
    "SILVER OAK",
    "ATTIC WOOD",
    "STEJAR SESIL",
    "BERGAN",
})


def _finisaj_stoc_redundant_pentru_afisare(f: str) -> bool:
    s = (f or "").strip()
    if not s:
        return True
    return bool(re.match(r"^inova\s*,?\s*laminat\s*$", s, re.I))


def _linie_decor_usi_stoc_afisare(decor: str) -> str:
    s = (decor or "").strip()
    if not s:
        return "—"
    u = s.upper()
    if u.endswith(" LAMINAT") or u.endswith(" INOVA 3D") or u.endswith(" INOVA"):
        return u
    base = re.sub(r"\s+inova\s+laminat\s*$", "", s, flags=re.IGNORECASE).rstrip()
    if not base:
        return u
    key = re.sub(r"\s+", " ", base.upper())
    bu = base.upper()
    if key in _DECOR_STOC_AFISARE_LAMINAT:
        return f"{bu} LAMINAT"
    return f"{bu} INOVA 3D"


def values_dropdown_usi_stoc(pairs: list[tuple[str, str]]) -> list[str]:
    """Etichete combobox uși Stoc, aliniate pe index cu pairs (preț din perechea completă)."""
    if not pairs:
        return []
    mains = [_linie_decor_usi_stoc_afisare(d) for d, f in pairs]
    freq: dict[str, int] = {}
    for lm in mains:
        freq[lm] = freq.get(lm, 0) + 1
    out: list[str] = []
    nofin: dict[str, int] = {}
    for (d, f), lm in zip(pairs, mains):
        f = (f or "").strip()
        if freq.get(lm, 0) <= 1:
            out.append(lm)
            continue
        if f and not _finisaj_stoc_redundant_pentru_afisare(f):
            cand = f"{lm} / {f}"
            k = 0
            while cand in out:
                k += 1
                cand = f"{lm} / {f} ({k})"
            out.append(cand)
            continue
        nofin[lm] = nofin.get(lm, 0) + 1
        n = nofin[lm]
        out.append(lm if n == 1 else f"{lm} ({n})")
    return out
