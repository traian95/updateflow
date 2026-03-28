from __future__ import annotations

import ast
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def dumps_offer_items(
    items: Any,
    mentiuni: str | None = None,
    afiseaza_mentiuni_pdf: bool | None = None,
    masuratori_lei: float | None = None,
    transport_lei: float | None = None,
    conditii_pdf: bool | None = None,
    termen_livrare_zile: str | int | None = None,
    modificat_de: str | None = None,
    modificat_la: str | None = None,
) -> str:
    """
    Serializează conținutul coșului + metadate (mentiuni, flag PDF, costuri suplimentare) într-un string.

    - Nou format (preferat): dict cu chei 'items', 'mentiuni', 'afiseaza_mentiuni_pdf',
      opțional 'masuratori_lei', 'transport_lei', 'conditii_pdf', 'termen_livrare_zile'.
    - Backwards compatible: dacă nu primim mentiuni, păstrăm structura veche (listă simplă).
    """
    if (
        mentiuni is None
        and afiseaza_mentiuni_pdf is None
        and masuratori_lei is None
        and transport_lei is None
        and conditii_pdf is None
        and termen_livrare_zile is None
        and modificat_de is None
        and modificat_la is None
    ):
        # Comportament vechi: doar lista de produse.
        return json.dumps(items, ensure_ascii=False)

    payload: dict[str, Any] = {
        "items": items,
        "mentiuni": mentiuni or "",
        "afiseaza_mentiuni_pdf": bool(afiseaza_mentiuni_pdf),
    }
    if masuratori_lei is not None:
        payload["masuratori_lei"] = float(masuratori_lei)
    if transport_lei is not None:
        payload["transport_lei"] = float(transport_lei)
    if conditii_pdf is not None:
        payload["conditii_pdf"] = bool(conditii_pdf)
    if termen_livrare_zile is not None:
        payload["termen_livrare_zile"] = str(termen_livrare_zile).strip()
    if modificat_de:
        payload["modificat_de"] = str(modificat_de).strip()
    if modificat_la:
        payload["modificat_la"] = str(modificat_la).strip()
    return json.dumps(payload, ensure_ascii=False)


def _normalize_item(element: Any) -> dict[str, Any]:
    """Asigură că un element din lista de ofertă este întotdeauna un dict cu chei nume, qty, pret_eur."""
    if isinstance(element, dict):
        return element
    # Format vechi: elemente string sau alte tipuri → convertim la dict minimal
    return {
        "nume": str(element) if element not in (None, "") else "—",
        "qty": 1,
        "pret_eur": 0,
    }


def _normalize_items_list(lst: Any) -> list[dict[str, Any]]:
    """Normalizează o listă de elemente (dict sau string) la listă de dict-uri."""
    if not lst:
        return []
    if not isinstance(lst, list):
        return [_normalize_item(lst)]
    return [_normalize_item(x) for x in lst]


def loads_offer_items(raw: str):
    """
    Deserializează conținutul ofertei (detalii) din string.
    - Returnează fie un dict cu chei 'items', 'mentiuni', 'afiseaza_mentiuni_pdf' (format nou),
      fie o listă de produse (format vechi). Lista „items” este întotdeauna normalizată:
      fiecare element este un dict cu chei nume, qty, pret_eur (elemente string/vechi sunt convertite).
    """
    raw = (raw or "").strip()
    if not raw:
        return []

    data: Any = None

    if raw[:1] in ("[", "{", '"'):
        try:
            data = json.loads(raw)
        except Exception:
            logger.debug("loads_offer_items: JSON parse failed, trying ast", exc_info=True)

    if data is None:
        try:
            data = ast.literal_eval(raw)
        except Exception:
            logger.warning("loads_offer_items: ast.literal_eval failed", exc_info=True)
            return []

    if isinstance(data, dict):
        data["items"] = _normalize_items_list(data.get("items", []))
        return data
    return _normalize_items_list(data)


def get_offer_modificare_meta(raw: str) -> tuple[str, str] | None:
    """Din `detalii_oferta`: utilizator și moment ultimă modificare (nu afectează PDF)."""
    s = (raw or "").strip()
    if not s:
        return None
    data = loads_offer_items(s)
    if not isinstance(data, dict):
        return None
    u = (data.get("modificat_de") or "").strip()
    if not u:
        return None
    la = (data.get("modificat_la") or "").strip()
    return (u, la)

