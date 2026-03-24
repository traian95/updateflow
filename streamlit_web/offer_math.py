"""Totaluri coș / discount — aceeași logică ca `AplicatieOfertare.refresh_cos` (fără UI)."""

from __future__ import annotations

from typing import Any

from ofertare.pdf_export import _is_item_fara_discount


def parse_discount_percent(raw: str | int | float | None) -> int:
    import re

    if raw is None:
        return 0
    s = str(raw).strip().replace("%", "").replace(",", ".")
    if not s:
        return 0
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return 0
    try:
        v = float(m.group(0))
    except ValueError:
        return 0
    return int(round(max(0.0, min(50.0, v))))


def compute_cart_totals(
    cos: list[dict[str, Any]],
    *,
    discount_proc: int,
    tva_procent: float,
    curs_euro: float,
) -> dict[str, float]:
    """Returnează totaluri pentru etichetele din dreapta (RON, TVA inclus) — mirror `refresh_cos`."""
    total_eur = 0.0
    total_eur_fara_discount = 0.0
    total_eur_cu_discount = 0.0
    sum_eng_baza = 0.0
    sum_eng_disc = 0.0
    disc = max(0, min(50, int(discount_proc)))
    tva = float(tva_procent)
    ce = float(curs_euro)

    for item in cos:
        val = float(item.get("pret_eur") or 0) * float(item.get("qty") or 1)
        total_eur += val
        item_fara_discount = _is_item_fara_discount(item) or bool(item.get("fara_discount"))
        if item_fara_discount:
            total_eur_fara_discount += val
        else:
            total_eur_cu_discount += val

        pret_eur = float(item.get("pret_eur") or 0)
        qty = int(item.get("qty") or 1)
        disc_linie = 0 if item_fara_discount else disc
        if item.get("tip") == "manere_engs":
            pl = float(item.get("pret_lei_cu_tva") or 0)
            pret_total_lei_cu_tva = pl * qty * (1 - disc_linie / 100)
            sum_eng_baza += pl * qty
            sum_eng_disc += pret_total_lei_cu_tva

    total_fara_disc_lei = round((total_eur * (1 + tva / 100)) * ce + sum_eng_baza, 2)
    lei_cu_disc = round(
        (total_eur_cu_discount * (1 - disc / 100) * (1 + tva / 100)) * ce + sum_eng_disc,
        2,
    )
    lei_fara_disc_servicii = round((total_eur_fara_discount * (1 + tva / 100)) * ce, 2)

    # Ca în desktop: măsurători/transport NU intră în totalul ofertei (apar separat în PDF).
    ultima_valoare_lei = round(lei_cu_disc + lei_fara_disc_servicii, 2)
    discount_ron = round(total_fara_disc_lei - ultima_valoare_lei, 2)
    avans_40 = round(ultima_valoare_lei * 0.40, 2)

    return {
        "total_fara_disc_lei": total_fara_disc_lei,
        "lei_cu_disc": lei_cu_disc,
        "lei_fara_disc_servicii": lei_fara_disc_servicii,
        "ultima_valoare_lei": ultima_valoare_lei,
        "discount_ron": discount_ron,
        "avans_40": avans_40,
    }


def get_item_tip(item: dict[str, Any]) -> str:
    if item.get("tip"):
        return str(item["tip"])
    nume = item.get("nume") or ""
    if "Toc " in nume or "Toc Drept" in nume:
        return "tocuri"
    if "(" in nume and ")" in nume and "Toc" not in nume:
        return "usi"
    return "accesorii"


def get_furnizor_from_item(item: dict[str, Any]) -> str:
    f = (item.get("furnizor") or "").strip()
    if f in ("Stoc", "Erkado"):
        return f
    nume = item.get("nume") or ""
    if nume.strip().startswith("["):
        end = nume.find("]")
        if end != -1:
            return nume[1:end].strip()
    return "Stoc"


def total_usi(cos: list[dict[str, Any]]) -> int:
    return sum(int(i.get("qty") or 1) for i in cos if get_item_tip(i) == "usi")


def total_tocuri(cos: list[dict[str, Any]]) -> int:
    return sum(int(i.get("qty") or 1) for i in cos if get_item_tip(i) == "tocuri")


def validate_offer_usi_toc(cos: list[dict[str, Any]], safe_mode: bool) -> tuple[bool, str]:
    """Port al `_validare_oferta_usi_tocuri` din ui.py (fără self)."""
    if not safe_mode:
        return (True, "")

    tu = total_usi(cos)
    tt = total_tocuri(cos)
    if (tu > 0 or tt > 0) and tu != tt:
        return (False, f"Numărul de uși trebuie să fie egal cu numărul de tocuri. Acum: {tu} uși, {tt} tocuri.")

    has_usi_stoc = any(get_furnizor_from_item(i) == "Stoc" and get_item_tip(i) == "usi" for i in cos)
    has_usi_erkado = any(get_furnizor_from_item(i) == "Erkado" and get_item_tip(i) == "usi" for i in cos)
    has_toc_stoc = any(get_furnizor_from_item(i) == "Stoc" and get_item_tip(i) == "tocuri" for i in cos)
    has_toc_erkado = any(get_furnizor_from_item(i) == "Erkado" and get_item_tip(i) == "tocuri" for i in cos)
    if (has_usi_stoc and has_toc_erkado) or (has_usi_erkado and has_toc_stoc):
        return (
            False,
            "Nu puteți închide/salva oferta: există uși de un furnizor (Stoc/Erkado) și tocuri de alt furnizor.",
        )

    def _map_erkado_usa_finisaj_to_toc_finisaj(usa_finisaj: str) -> str | None:
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

    def _get_toc_finisaj_from_item(item: dict) -> str | None:
        fin = item.get("toc_finisaj")
        if fin:
            return str(fin).strip()
        nume = item.get("nume") or ""
        if "(" in nume and ")" in nume:
            try:
                return nume.rsplit("(", 1)[1].rsplit(")", 1)[0].strip() or None
            except Exception:
                return None
        return None

    if has_usi_erkado and has_toc_erkado:
        usi_erkado = [i for i in cos if get_item_tip(i) == "usi" and get_furnizor_from_item(i) == "Erkado"]
        tocuri_erkado = [i for i in cos if get_item_tip(i) == "tocuri" and get_furnizor_from_item(i) == "Erkado"]
        limit = min(len(usi_erkado), len(tocuri_erkado))
        for idx in range(limit):
            usa_item = usi_erkado[idx]
            usa_finisaj = (usa_item.get("usa_finisaj") or "").strip()
            if not usa_finisaj:
                nume_usa = usa_item.get("nume") or ""
                if "(" in nume_usa and ")" in nume_usa:
                    try:
                        usa_finisaj = nume_usa.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
                    except Exception:
                        usa_finisaj = ""
            expected = _map_erkado_usa_finisaj_to_toc_finisaj(usa_finisaj)
            if not expected:
                continue
            toc_item = tocuri_erkado[idx]
            actual = _get_toc_finisaj_from_item(toc_item) or ""
            if not actual or actual != expected:
                return (
                    False,
                    f"Finisajul tocului Erkado nu se potrivește cu ușa corespunzătoare (pereche {idx + 1}).",
                )

    if tu > 0 and tt > 0:
        has_usa_dubla = any(get_item_tip(i) == "usi" and i.get("dubla") == "usa" for i in cos)
        has_usa_simpla = any(get_item_tip(i) == "usi" and not i.get("dubla") for i in cos)
        has_toc_dublu = any(get_item_tip(i) == "tocuri" and i.get("dubla") == "toc" for i in cos)
        has_toc_simplu = any(get_item_tip(i) == "tocuri" and not i.get("dubla") for i in cos)
        if (has_usa_dubla and has_toc_simplu) or (has_usa_simpla and has_toc_dublu):
            return (
                False,
                "Nu puteți închide oferta: există ușă dublă cu toc simplu sau invers.",
            )

    def _has_usa_cu_kit_glisare() -> bool:
        for i in cos:
            if get_item_tip(i) == "usi" and i.get("glisare_activ"):
                return True
            if (i.get("nume") or "").strip() == "Kit Glisare Simplu Peste Perete":
                return True
        return False

    if _has_usa_cu_kit_glisare():
        has_tunel = any(
            get_item_tip(i) == "tocuri" and get_furnizor_from_item(i) == "Stoc" and bool(i.get("toc_tunel"))
            for i in cos
        )
        if not has_tunel:
            return (
                False,
                "Există ușă cu kit de glisare activ, dar nu este selectat niciun toc tunel de Stoc.",
            )

    return (True, "")
