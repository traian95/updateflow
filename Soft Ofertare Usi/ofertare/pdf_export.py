"""Export ofertă către PDF – folosit de aplicația principală și de admin."""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Optional

from fpdf import FPDF

from .config import AppConfig

_SERVICII_FARA_DISCOUNT = frozenset({
    "scurtare set usa +toc",
    "redimensionare k",
    "redimensionare sus-jos",
    "broasca wc",
    "broasca cilindru",
})


def discount_price_factor(discount_proc: int) -> float:
    """
    Factor aplicat pe prețul supus discountului.
    Regulă unică: împărțire la (1 + p/100) — ex. 10% → /1.10, 20% → /1.20.
    (Nu se folosește scăderea clasică 1 − p/100, care ar da alt rezultat.)
    """
    d = int(discount_proc) if discount_proc else 0
    if d <= 0:
        return 1.0
    return 1.0 / (1.0 + d / 100.0)


def _is_item_fara_discount(item: dict[str, Any]) -> bool:
    """Discountul NU se aplică doar serviciilor suplimentare fixe din listă."""
    nume_norm = (item.get("nume") or "").strip().casefold()
    return nume_norm in _SERVICII_FARA_DISCOUNT


def _item_majuscule_stoc_erkado_usi_toc(item: dict[str, Any]) -> bool:
    """Uși/tocuri Stoc sau Erkado: afișare cu majuscule în coș și PDF."""
    fu = (item.get("furnizor") or "").strip()
    if not fu:
        raw = (item.get("nume") or "").strip()
        if raw.startswith("[") and "]" in raw:
            fu = raw[1 : raw.index("]")].strip()
    tip = (item.get("tip") or "").strip()
    if not tip:
        raw = (item.get("nume") or "") or ""
        if "Toc " in raw or "Toc Drept" in raw:
            tip = "tocuri"
        elif "(" in raw and ")" in raw and "Toc" not in raw:
            tip = "usi"
    return fu in ("Stoc", "Erkado") and tip in ("usi", "tocuri")


def _item_afisare_majuscule_cos_pdf(item: dict[str, Any]) -> bool:
    """Stoc/Erkado sau linii ușă exterior (ușă+toc, bară, accesorii)."""
    if _item_majuscule_stoc_erkado_usi_toc(item):
        return True
    if str(item.get("furnizor") or "").strip() != "Exterior":
        return False
    if (
        item.get("usi_exterior_kit")
        or item.get("usi_exterior_bara_line")
        or item.get("usi_exterior_feronerie_line")
        or item.get("usi_exterior_accesoriu")
    ):
        return True
    return False


def apply_majuscule_line_stoc_erkado(item: dict[str, Any], line: str) -> str:
    """Aplică majuscule pe linia de produs dacă e ușă/toc Stoc sau Erkado."""
    if not line:
        return line
    if _item_afisare_majuscule_cos_pdf(item):
        return line.upper()
    return line


def format_nume_maner_afisare(item: dict[str, Any], nume: str) -> str:
    """Coș / PDF: «Maner (denumire)» — fără [Stoc]/[Erkado]; Enger din «MANER …»."""
    raw = (nume or "").strip()
    if not raw:
        return raw
    tip = (item.get("tip") or "").strip()
    if tip == "manere_engs" and raw.upper().startswith("MANER "):
        inner = raw[6:].strip()
        return f"Maner ({inner})" if inner else "Maner"
    return raw


def _pdf_safe_text(s) -> str:
    """Convertește textul la caractere latin-1 pentru FPDF (evită erori la salvare)."""
    if not s:
        return ""
    t = str(s)
    for a, b in [
        ("\u2014", "-"), ("\u2013", "-"), ("\u021b", "t"), ("\u021a", "T"),
        ("\u0219", "s"), ("\u0218", "S"), ("\u0103", "a"), ("\u0102", "A"),
        ("\u00e2", "a"), ("\u00c2", "A"), ("\u00ee", "i"), ("\u00ce", "I"),
        ("\u0163", "t"), ("\u0162", "T"), ("\u015f", "s"), ("\u015e", "S"),
    ]:
        t = t.replace(a, b)
    return t.encode("latin-1", "replace").decode("latin-1")


def _format_data_pdf(data_comanda: str) -> str:
    """Normalizează data în format zi/luna/an, indiferent de formatul intern."""
    raw = (data_comanda or "").strip()
    if not raw:
        return datetime.now().strftime("%d/%m/%Y")

    # Formate numerice uzuale
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass

    # Format intern posibil: YYYY-LunaRo HH:MM (ex: 2026-Martie 11:32)
    m = re.match(r"^\s*(\d{4})-([A-Za-zĂÂÎȘȚăâîșț]+)(?:\s+\d{1,2}:\d{2})?\s*$", raw)
    if m:
        year = int(m.group(1))
        luna_ro = m.group(2).strip().lower()
        luni = {
            "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4,
            "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
            "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
        }
        month = luni.get(luna_ro)
        if month:
            # Formatul intern nu include zi; folosim ziua curentă pentru afișarea cerută.
            return datetime.now().replace(year=year, month=month).strftime("%d/%m/%Y")

    # Fallback robust
    return datetime.now().strftime("%d/%m/%Y")


def build_oferta_pret_pdf(
    cale_salvare: str,
    nr_inreg: str,
    nume_utilizator: str,
    contact_tel: Optional[str],
    contact_email: Optional[str],
    nume_client: str,
    telefon: str,
    adresa: str,
    email: str,
    cos_cumparaturi: list[dict[str, Any]],
    discount_proc: int,
    tva_procent: float,
    curs_euro: float,
    total_lei_cu_discount: float,
    mentiuni: str = "",
    masuratori_lei: float = 0.0,
    transport_lei: float = 0.0,
    conditii_pdf: bool = False,
    termen_livrare_zile: str | int = 0,
    aplica_adaugiri_denumire: bool = True,
    data_comanda: str = "",
) -> None:
    """
    Generează PDF-ul ofertei în format „OFERTA DE PRET” (chenar, tabel, texte în română).
    Toate datele sunt primite ca parametri; același aspect ca în aplicația principală.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header central
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "OFERTA DE PRET", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    header_nr = _pdf_safe_text(f"Nr. înregistrare: {nr_inreg}")
    pdf.cell(0, 9, header_nr, ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    data_afisata = _format_data_pdf(data_comanda)
    pdf.cell(0, 7, _pdf_safe_text(f"Oferta întocmită de {nume_utilizator} la data de {data_afisata}"), ln=True, align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(
        0,
        5,
        _pdf_safe_text(
            "Showroom: Str. Valea Cascadelor nr. 23, București, sector 6\n"
            "Complex comercial ExpoConstruct, Stand V1 – V2"
        ),
        align="C",
    )
    if contact_tel or contact_email:
        parts = []
        if contact_tel:
            parts.append(f"Tel: {contact_tel}")
        if contact_email:
            parts.append(f"Email: {contact_email}")
        # Multi-cell + font puțin mai mic pentru a evita depășirea cadrului la contacte lungi.
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(0, 5, _pdf_safe_text("  |  ".join(parts)), align="C")
        pdf.set_font("Helvetica", "", 9)

    # Blocuri Furnizor/Beneficiar în poziția standard de sub header.
    x_stanga = 12
    x_dreapta = 118
    y_start = pdf.get_y() + 7

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(x_stanga, y_start)
    pdf.cell(84, 6, "Furnizor:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(x_stanga)
    pdf.multi_cell(84, 5, _pdf_safe_text("Naturen Concept S.R.L\nRO: 332221186\nJ 2014000877057\nCalea Borsului 53\nOradea, Judetul Bihor"))
    y_end_furnizor = pdf.get_y()

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(x_dreapta, y_start)
    pdf.cell(84, 6, "Beneficiar:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(x_dreapta)
    linii_client = [_pdf_safe_text(nume_client.strip())]
    if telefon:
        linii_client.append(_pdf_safe_text(f"Tel: {telefon}"))
    if email:
        linii_client.append(_pdf_safe_text(f"Email: {email}"))
    if adresa:
        linii_client.append(_pdf_safe_text(adresa))
    pdf.multi_cell(84, 5, "\n".join(linii_client))
    y_end_beneficiar = pdf.get_y()

    # Tabelul începe sub blocul cel mai înalt ca să evităm suprapunerea.
    y_tabel_start = max(y_end_furnizor, y_end_beneficiar) + 6
    if pdf.get_y() < y_tabel_start:
        pdf.set_y(y_tabel_start)

    are_parchet = any(i.get("tip") == "parchet" for i in cos_cumparaturi)
    header_pret = " PRET RON (cu TVA)" if are_parchet else " Pret unitar RON"
    # Lățimi ajustate astfel încât antetul "Total RON (cu TVA)" să încapă fără suprapuneri.
    w_prod, w_buc, w_unit, w_total = 95, 20, 35, 40
    line_h = 5

    def _draw_table_header() -> None:
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        # Font ușor mai mic pe antet pentru a preveni depășirea în celule înguste.
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(w_prod, 10, " Produs", 1, 0, "L", True)
        # Coloana afișează numărul de articole (bucăți), nu mp.
        pdf.cell(w_buc, 10, " Buc", 1, 0, "C", True)
        pdf.cell(w_unit, 10, header_pret, 1, 0, "C", True)
        pdf.cell(w_total, 10, " Total RON (cu TVA)", 1, 1, "C", True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)

    def _wrap_text_to_width(text: str, max_w: float) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        cur = words[0]
        for w in words[1:]:
            test = f"{cur} {w}"
            if pdf.get_string_width(test) <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    _draw_table_header()
    for item in cos_cumparaturi:
        if item.get("tip") == "manere_engs":
            pl = float(item.get("pret_lei_cu_tva") or 0)
            pret_unitar_ron_fara_discount = pl
            if _is_item_fara_discount(item):
                pret_unitar_ron_cu_discount = pl
            else:
                pret_unitar_ron_cu_discount = pl * discount_price_factor(discount_proc)
            pret_unitar_ron = pret_unitar_ron_fara_discount
            pret_eur = 0.0
            qty = item.get("qty") or 1
            pret_total_rand_ron = pret_unitar_ron * qty
        else:
            pret_eur = item.get("pret_eur") or 0
            pret_unitar_ron_fara_discount = (pret_eur * (1 + tva_procent / 100)) * curs_euro
            if _is_item_fara_discount(item):
                pret_unitar_ron_cu_discount = pret_unitar_ron_fara_discount
            else:
                pret_unitar_ron_cu_discount = (
                    pret_eur * discount_price_factor(discount_proc) * (1 + tva_procent / 100)
                ) * curs_euro
            # În tabel afișăm prețurile înainte de discount, ca să fie coerente cu
            # „Valoare totală (TVA inclus)” din secțiunea de totaluri.
            pret_unitar_ron = pret_unitar_ron_fara_discount
            qty = item.get("qty") or 1
            pret_total_rand_ron = pret_unitar_ron * qty
        # În coloana din mijloc afișăm numărul de articole (bucăți).
        buc_afis = str(qty)
        nume_afis = format_nume_maner_afisare(item, item.get("nume") or "")
        extra_nume = (item.get("nume_adaugire_pdf") or "").strip()
        if aplica_adaugiri_denumire and extra_nume:
            nume_afis = f"{nume_afis} {extra_nume}"
        if item.get("dubla") == "usa":
            nume_afis = nume_afis + " (Usa dubla)"
        elif item.get("dubla") == "toc":
            nume_afis = nume_afis + " (Toc dublu)"
        if item.get("debara"):
            nume_afis = nume_afis + " (DEBARA)"
        if item.get("debara_toc"):
            nume_afis = nume_afis + " (Toc DEBARA)"
        nume_afis = apply_majuscule_line_stoc_erkado(item, nume_afis)
        nume_safe = _pdf_safe_text(" " + nume_afis)
        wrapped = _wrap_text_to_width(nume_safe, w_prod - 4)
        row_h = max(8, line_h * len(wrapped))

        # Evităm rânduri rupte/intercalate: dacă nu încape rândul întreg, trecem pe pagina următoare și refacem antetul tabelului.
        if pdf.get_y() + row_h > 270:
            pdf.add_page()
            _draw_table_header()

        x = pdf.get_x()
        y = pdf.get_y()
        # Desenăm întâi conturul pe înălțimea finală a rândului, apoi textul;
        # evită rândurile "intercalate" când textul produsului are 1 linie.
        pdf.rect(x, y, w_prod, row_h)
        pdf.multi_cell(w_prod, line_h, "\n".join(wrapped), border=0, align="L")
        pdf.set_xy(x + w_prod, y)
        pdf.cell(w_buc, row_h, buc_afis, 1, 0, "C")
        pdf.cell(w_unit, row_h, f"{pret_unitar_ron:.2f}", 1, 0, "R")
        pdf.cell(w_total, row_h, f"{pret_total_rand_ron:.2f}", 1, 1, "R")
    distanta_minima_sectiuni = 10
    pdf.ln(distanta_minima_sectiuni)
    total_eur_pdf = sum((i.get("pret_eur") or 0) * (i.get("qty") or 1) for i in cos_cumparaturi)
    total_eur_discountabil = sum(
        (i.get("pret_eur") or 0) * (i.get("qty") or 1) for i in cos_cumparaturi if not _is_item_fara_discount(i)
    )
    total_eur_fara_discount = sum(
        (i.get("pret_eur") or 0) * (i.get("qty") or 1) for i in cos_cumparaturi if _is_item_fara_discount(i)
    )
    sum_eng_baza_pdf = sum(
        float(i.get("pret_lei_cu_tva") or 0) * (i.get("qty") or 1)
        for i in cos_cumparaturi
        if i.get("tip") == "manere_engs"
    )
    sum_eng_disc_pdf = sum(
        float(i.get("pret_lei_cu_tva") or 0)
        * (i.get("qty") or 1)
        * (1.0 if _is_item_fara_discount(i) else discount_price_factor(discount_proc))
        for i in cos_cumparaturi
        if i.get("tip") == "manere_engs"
    )
    total_fara_disc_lei = (total_eur_pdf * (1 + tva_procent / 100)) * curs_euro + sum_eng_baza_pdf
    total_cu_disc_calculat_lei = (
        (total_eur_discountabil * discount_price_factor(discount_proc) + total_eur_fara_discount)
        * (1 + tva_procent / 100)
        * curs_euro
        + sum_eng_disc_pdf
    )
    total_lei_final = total_lei_cu_discount if total_lei_cu_discount > 0 else total_cu_disc_calculat_lei
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, _pdf_safe_text(f"Valoare totala (TVA INCLUS): {total_fara_disc_lei:.2f} RON"), ln=True)

    if discount_proc:
        discount_ron = max(0.0, total_fara_disc_lei - total_lei_final)
        pdf.cell(0, 8, _pdf_safe_text(f"Discount Aplicat (valoare discountului in RON): {discount_ron:.2f} RON"), ln=True)
        avans_40 = total_lei_final * 0.40
        pdf.cell(0, 8, _pdf_safe_text(f"AVANS (40% din valoarea comenzii): {avans_40:.2f} RON"), ln=True)
    else:
        # Fără discount: nu afișăm linia de discount, doar avansul pe totalul fără discount.
        avans_40 = total_fara_disc_lei * 0.40
        pdf.cell(0, 8, _pdf_safe_text(f"AVANS (40% din valoarea comenzii): {avans_40:.2f} RON"), ln=True)

    pdf.ln(4)
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", "B", 13)
    if discount_proc:
        box_label = f"  Valoare totala cu discount aplicat (TVA INCLUS): {total_lei_final:.2f} RON"
    else:
        box_label = f"  Valoare totala (TVA INCLUS): {total_fara_disc_lei:.2f} RON"
    pdf.cell(0, 14, _pdf_safe_text(box_label), 1, 1, "L", True)
    pdf.set_fill_color(255, 255, 255)
    pdf.ln(10)

    # Costuri suplimentare (Măsurători / Transport) – afișate mereu, separat; NU sunt incluse în totalul cu TVA.
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _pdf_safe_text("Costuri Suplimentare (TVA INCLUS)"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0,
        5,
        _pdf_safe_text(f"- Măsurători: {masuratori_lei:.2f} RON"),
        ln=True,
    )
    pdf.cell(
        0,
        5,
        _pdf_safe_text(f"- Transport: {transport_lei:.2f} RON"),
        ln=True,
    )
    pdf.ln(2)
    y_final_costuri_suplimentare = pdf.get_y()

    # Mentiuni opționale
    if mentiuni:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, _pdf_safe_text("Mențiuni / condiții speciale:"), ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _pdf_safe_text(mentiuni))
        pdf.ln(4)

    # Bloc opțional "Conditii"; dacă nu încape pe pagină, îl mutăm pe pagina următoare.
    if conditii_pdf:
        # Garantăm că "Condiții" nu ajunge niciodată mai aproape de
        # "Costuri suplimentare" decât spațiul dintre caseta totalului și costuri.
        y_conditii_minim = y_final_costuri_suplimentare + distanta_minima_sectiuni
        if pdf.get_y() < y_conditii_minim:
            pdf.set_y(y_conditii_minim)
        termen_raw = str(termen_livrare_zile or "").strip()
        nums = re.findall(r"\d+", termen_raw)
        if not nums:
            termen_afisat = "0"
        elif len(nums) == 1:
            termen_afisat = str(max(0, min(200, int(nums[0]))))
        else:
            st = max(0, min(200, int(nums[0])))
            dr = max(0, min(200, int(nums[1])))
            if st > dr:
                st, dr = dr, st
            termen_afisat = f"{st}-{dr}"
        conditii_text = (
            f"TERMEN DE LIVRARE: maximum [{termen_afisat}] zile lucratoare, din momentul achitarii avansului si a lansarii comenzii ferme. "
            "Plata integrala a comenzii se face cu 1,2 zile inainte de livrare.\n"
            "In termen de 24 ore de la lansarea comenzii, Naturen isi rezerva dreptul de a anunta Clientul cu privire la orice modificare survenita in oferta sa, "
            "modificare ce poate duce la anularea comenzii acestuia, in intregime sau partial, situatie ce implica returnarea avansului aferent comenzii respective.\n"
            "Din momentul lansarii comenzii, clientul nu mai are dreptul sa refuze produsele comandate, cu exceptia situatiei prevazute mai sus. "
            "Pentru neplata sau plata cu intarziere a diferentei de pret din valoarea comenzii, Clientul va fi obligat la plata de penalitati de 0,2% pe zi de intarziere din valoarea sumei datorate.\n"
            "Transportul produselor se face pana la adresa indicata de Client, fara a include manipularea in incinta Clientului."
        )
        # Păstrăm spațiu rezervat pentru "EMITENT / CLIENT".
        # Estimare conservatoare, pentru a evita orice suprapunere.
        spatiu_necesar = 50
        if pdf.get_y() > (297 - 15 - spatiu_necesar):
            pdf.add_page()
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 7)
        pdf.multi_cell(0, 3.3, _pdf_safe_text(conditii_text))
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 8)
        # Apropie etichetele între ele, într-un bloc centrat.
        page_w = pdf.w - pdf.l_margin - pdf.r_margin
        block_w = 140
        col_w = 60
        gap_w = 20
        x_block = pdf.l_margin + (page_w - block_w) / 2
        pdf.set_x(x_block)
        pdf.cell(col_w, 5, _pdf_safe_text("EMITENT"), 0, 0, "L")
        pdf.cell(gap_w, 5, "", 0, 0, "C")
        pdf.cell(col_w, 5, _pdf_safe_text("CLIENT"), 0, 1, "R")
        pdf.ln(1)

    pdf.output(cale_salvare)


def genereaza_pdf_oferta(
    cale_logo: str,
    cale_salvare: str,
    nume_client: str,
    telefon: str,
    adresa: str,
    data_oferta_str: str,
    cos_cumparaturi: list[dict[str, Any]],
    total_lei: float,
    curs_euro: float | None = None,
    tva_procent: int | None = None,
    discount_proc: int = 0,
    aplica_adaugiri_denumire: bool = True,
) -> None:
    """Generează fișier PDF pentru o ofertă (din aplicație sau din istoric admin)."""
    config = AppConfig()
    if curs_euro is None:
        curs_euro = config.curs_euro_initial
    if tva_procent is None:
        tva_procent = config.tva_procent

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    if os.path.exists(cale_logo):
        pdf.image(cale_logo, 10, 8, 40)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "OFERTA COMERCIALA", ln=True, align="R")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 10, f"Data: {data_oferta_str}", ln=True, align="R")
    pdf.ln(10)
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, f" Beneficiar: {nume_client.upper()}", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f" Telefon: {telefon or '-'}", ln=True)
    pdf.cell(0, 7, f" Adresa: {adresa or '-'}", ln=True)
    pdf.ln(5)
    pdf.set_fill_color(0, 0, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 10, " Produs", 1, 0, "L", True)
    pdf.cell(20, 10, " Cant.", 1, 0, "C", True)
    pdf.cell(35, 10, " Pret Unit. LEI", 1, 0, "C", True)
    pdf.cell(35, 10, " Total LEI", 1, 1, "C", True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    for item in cos_cumparaturi:
        pret_eur = item.get("pret_eur", 0) or 0
        qty = item.get("qty", 1) or 1
        nume = format_nume_maner_afisare(item, item.get("nume", ""))
        extra_nume = (item.get("nume_adaugire_pdf") or "").strip()
        if aplica_adaugiri_denumire and extra_nume:
            nume = f"{nume} {extra_nume}"
        if item.get("dubla") == "usa":
            nume = nume + " (Usa dubla)"
        elif item.get("dubla") == "toc":
            nume = nume + " (Toc dublu)"
        if item.get("debara"):
            nume = nume + " (DEBARA)"
        if item.get("debara_toc"):
            nume = nume + " (Toc DEBARA)"
        if _item_afisare_majuscule_cos_pdf(item):
            nume = nume.upper()
        if item.get("tip") == "manere_engs":
            pl = float(item.get("pret_lei_cu_tva") or 0)
            if _is_item_fara_discount(item):
                pret_unitar_lei = pl
            else:
                pret_unitar_lei = pl * discount_price_factor(discount_proc)
        elif _is_item_fara_discount(item):
            pret_unitar_lei = pret_eur * (1 + tva_procent / 100) * curs_euro
        else:
            pret_unitar_lei = (
                pret_eur * discount_price_factor(discount_proc) * (1 + tva_procent / 100) * curs_euro
            )
        pret_total_rand_lei = pret_unitar_lei * qty
        pdf.cell(100, 8, f" {nume}", 1)
        pdf.cell(20, 8, str(qty), 1, 0, "C")
        pdf.cell(35, 8, f"{pret_unitar_lei:.2f}", 1, 0, "R")
        pdf.cell(35, 8, f"{pret_total_rand_lei:.2f}", 1, 1, "R")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(155, 10, "TOTAL DE PLATA (LEI cu TVA inclus):", 0, 0, "R")
    pdf.cell(35, 10, f"{total_lei:.2f} RON", 0, 1, "R")
    pdf.output(cale_salvare)
