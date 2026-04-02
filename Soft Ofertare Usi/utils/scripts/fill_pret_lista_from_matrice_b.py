"""
Suprascrie in A coloanele «reglaj» si «Pret lista (EUR)» cu valorile din matricea B
(text reglaj din B + pret). Optional: --update-a rescrie A.xlsx.
Compararea dimensiunii: toate spatiile eliminate (ex. «180 -200» si «180 - 200» -> «180-200»).

Rulare (din folderul «Soft Ofertare Usi»):
  python utils/scripts/fill_pret_lista_from_matrice_b.py --a <tocuri.xlsx> --b B.xlsx --out A_Import_Supabase.csv
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

B_COL_GREKO = "GREKO"
B_COL_CPL_ST_PREMIUM = "CPL ST /PREMIUM"
B_COL_CPL_02 = "CPL 0.2"
B_COL_LACUIT = "LACUIT"


def _parse_interval_mm(s: str) -> tuple[float, float] | None:
    """Parseaza dupa normalizare: «80-100» -> (80, 100)."""
    s = str(s).strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$", s)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def resolve_reglaj_key(a_norm: str, lookup: dict[str, dict[str, float]]) -> str | None:
    """
    Daca nu exista exact a_norm in B, foloseste intervalul din B care contine mijlocul lui A,
    sau intervalul din B cel mai apropiat (liste de reglaj diferite intre A si B).
    """
    if a_norm in lookup:
        return a_norm
    pa = _parse_interval_mm(a_norm)
    if not pa:
        return None
    mid = (pa[0] + pa[1]) / 2.0
    inside: list[tuple[str, float]] = []
    for bk in lookup:
        pb = _parse_interval_mm(bk)
        if not pb:
            continue
        if pb[0] <= mid <= pb[1]:
            inside.append((bk, pb[1] - pb[0]))
    if inside:
        inside.sort(key=lambda x: x[1])
        return inside[0][0]
    best_k: str | None = None
    best_d: float | None = None
    for bk in lookup:
        pb = _parse_interval_mm(bk)
        if not pb:
            continue
        if mid < pb[0]:
            d = pb[0] - mid
        elif mid > pb[1]:
            d = mid - pb[1]
        else:
            d = 0.0
        if best_d is None or d < best_d:
            best_d = d
            best_k = bk
    return best_k


def normalize_reglaj(val: object) -> str:
    """
    Pentru potrivire cu prima coloana din B: elimina sufix MM, apoi TOATE spatiile
    (inclusiv «180 -200» / «180 - 200» -> «180-200»).
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    s = re.sub(r"\s*MM\s*$", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"\s+", "", s)
    return s


def normalize_finisaj_for_match(val: object) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def finisaj_to_b_column(finisaj: str) -> str | None:
    f = normalize_finisaj_for_match(finisaj)
    if not f:
        return None
    u = f.upper()
    if u == "GREKO":
        return B_COL_GREKO
    if u in ("CPL ST /PREMIUM", "CPL ST / PREMIUM"):
        return B_COL_CPL_ST_PREMIUM
    if u in ("CPL", "CPL 2.0"):
        return B_COL_CPL_02
    if u == "LACUIT":
        return B_COL_LACUIT
    return None


def _find_col(df: pd.DataFrame, names: list[str]) -> str | None:
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        key = n.strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None


def _toc_variant_key(text: object) -> str:
    """
    Identifica varianta de toc din text (tip_toc sau eticheta din B).
    «Fara Falt» vs «Cu Falt» au liste de pret diferite.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return "unknown"
    t = str(text).lower().replace("ă", "a").replace("â", "a").replace("î", "i")
    t = re.sub(r"\s+", " ", t).strip()
    if "fara" in t and "falt" in t:
        return "fara_falt"
    if "falt" in t:
        return "cu_falt"
    return "unknown"


def _is_toc_title_column(df: pd.DataFrame, col: object) -> bool:
    """Prima coloana poate fi titlul «TOC REGLABIL...» cu valori NaN pe randuri."""
    name = str(col).strip().upper()
    if "TOC" in name and "REGLAJ" in name and len(name) > 25:
        return True
    s = df[col]
    return bool(s.isna().all())


def _find_reglaj_column(df: pd.DataFrame) -> object | None:
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in ("reglaj", "reglajul", "reglaj "):
            return c
    for c in df.columns:
        if str(c).strip().upper() == "REGLAJ":
            return c
    for c in df.columns:
        if _is_toc_title_column(df, c):
            continue
        sample = df[c].dropna()
        if sample.empty:
            continue
        v = str(sample.iloc[0])
        if re.search(r"\d", v) and ("-" in v or "–" in v):
            return c
    return None


def _map_b_price_header_to_logical(header: object) -> str | None:
    """
    Antete posibile in B: GREKO, «CPL ST /PREMIUM», «CPL/PREMIUM», «CPL 0.2», LACUIT.
    Returneaza cheia logica (aceeasi ca finisaj_to_b_column).
    """
    h = str(header).strip().upper().replace(" ", "")
    h = h.replace("Ţ", "T").replace("Ț", "T")
    if h == "GREKO":
        return B_COL_GREKO
    if "CPL" in h and "0.2" in h:
        return B_COL_CPL_02
    if h == "LACUIT":
        return B_COL_LACUIT
    if "CPL" in h and "PREMIUM" in h:
        return B_COL_CPL_ST_PREMIUM
    if "CPL" in h and "ST" in h:
        return B_COL_CPL_ST_PREMIUM
    return None


def _find_price_col(df: pd.DataFrame) -> str | None:
    c = _find_col(
        df,
        [
            "pret lista (eur)",
            "pret lista (eur )",
            "pret lista",
            "pret 2025 eur fara tva",
            "preț listă (eur)",
        ],
    )
    if c is not None:
        return c
    for col in df.columns:
        lc = str(col).lower().replace("ț", "t").replace("ă", "a")
        if "pret" in lc and ("eur" in lc or "lista" in lc or "tva" in lc):
            return col
    return None


def load_matrix_b(path: Path, sheet_name: str | int = 0) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """
    Matrice B: rand 2 Excel = antete (poate include coloana titlu TOC + REGLAJ + preturi).
    Reglaj: coloana «REGLAJ» / «reglaj» sau prima coloana cu intervale numerice.
    Preturi: GREKO, CPL ST /PREMIUM sau CPL/PREMIUM, CPL 0.2, LACUIT — mapate la chei canonice.
    Returneaza si reglaj_display: cheie normalizata -> text exact din B (pentru coloana reglaj in A).
    """
    df = pd.read_excel(path, header=1, sheet_name=sheet_name)
    if df.empty or len(df.columns) < 2:
        return {}, {}

    reglaj_col = _find_reglaj_column(df)
    if reglaj_col is None:
        return {}, {}

    price_cols: list[object] = []
    for pc in df.columns:
        if pc == reglaj_col:
            continue
        if _is_toc_title_column(df, pc):
            continue
        logical = _map_b_price_header_to_logical(pc)
        if logical:
            price_cols.append((pc, logical))

    lookup: dict[str, dict[str, float]] = {}
    reglaj_display: dict[str, str] = {}
    for _, row in df.iterrows():
        raw_cell = row[reglaj_col]
        if pd.isna(raw_cell):
            continue
        raw_s = str(raw_cell).strip()
        r = normalize_reglaj(raw_cell)
        if not r:
            continue
        if r not in reglaj_display:
            reglaj_display[r] = raw_s
        if r not in lookup:
            lookup[r] = {}
        for pc, logical in price_cols:
            val = row[pc]
            if pd.isna(val):
                continue
            try:
                lookup[r][logical] = round(float(val), 4)
            except (TypeError, ValueError):
                continue
    return lookup, reglaj_display


def _matrix_label_row(path: Path, sheet_name: str | int) -> str:
    """Text din celula A2 (rand 1, col 0) in B — descrie tipul de toc pentru matrice."""
    raw = pd.read_excel(path, header=None, sheet_name=sheet_name)
    if raw.shape[0] < 2:
        return ""
    return str(raw.iloc[1, 0]).strip()


def build_b_lookups(
    path: Path,
) -> tuple[dict[str, dict[str, dict[str, float]]], dict[str, dict[str, str]], list[str]]:
    """
    Citeste toate foile din B; fiecare foaie = o matrice de pret.
    Cheie: varianta toc (fara_falt / cu_falt) din eticheta randului 2 col A sau din numele foii.
    """
    warnings: list[str] = []
    xl = pd.ExcelFile(path)
    out: dict[str, dict[str, dict[str, float]]] = {}
    out_labels: dict[str, dict[str, str]] = {}
    for sn in xl.sheet_names:
        label = _matrix_label_row(path, sn)
        key = _toc_variant_key(label)
        if key == "unknown":
            key = _toc_variant_key(sn)
        if key == "unknown":
            key = f"_sheet_{sn}"
        lu, lbl = load_matrix_b(path, sheet_name=sn)
        if not lu:
            warnings.append(f"Foaia B «{sn}» nu contine date de matrice valide.")
            continue
        if key in out:
            warnings.append(
                f"Mai multe foi B mapate la «{key}»; se foloseste ultima: «{sn}»."
            )
        out[key] = lu
        out_labels[key] = lbl
    return out, out_labels, warnings


def pick_lookup_for_tip(
    lookups_by_variant: dict[str, dict[str, dict[str, float]]],
    tip_toc_val: object,
) -> tuple[dict[str, dict[str, float]], str, str | None]:
    """
    Alege matricea B potrivita pentru tip_toc. Returneaza (lookup, cheie_folosita, avertisment).
    """
    want = _toc_variant_key(tip_toc_val)
    if want in lookups_by_variant and lookups_by_variant[want]:
        return lookups_by_variant[want], want, None
    non_empty = [(k, v) for k, v in lookups_by_variant.items() if v and not str(k).startswith("_sheet_")]
    if len(non_empty) == 1:
        k0, v0 = non_empty[0]
        if want != "unknown" and want != k0:
            return (
                v0,
                k0,
                f"ATENTIE: tip_toc din A ({tip_toc_val!r}) sugereaza «{want}», "
                f"dar in B exista o singura matrice («{k0}»). Verifica ca B.xlsx fie pentru acelasi tip de toc.",
            )
        return v0, k0, None
    if non_empty:
        k0, v0 = non_empty[0]
        return v0, k0, f"Lipsa matrice B pentru «{want}»; folosita «{k0}»."
    all_keys = [k for k, v in lookups_by_variant.items() if v]
    if not all_keys:
        return {}, want, "Nu exista matrice B valida."
    k0 = all_keys[0]
    return lookups_by_variant[k0], k0, None


def fill_prices(
    df_a: pd.DataFrame,
    lookups_by_variant: dict[str, dict[str, dict[str, float]]],
    reglaj_labels_by_variant: dict[str, dict[str, str]],
    *,
    no_match_zero: bool,
) -> tuple[pd.DataFrame, int, int, list[str]]:
    """
    Suprascrie pretul si (cand exista) textul reglaj cu valorile din B.
    Matricea B se alege dupa coloana tip_toc (Fara Falt / Cu Falt) cand exista mai multe foi.
    Fara potrivire: pastreaza vechiul pret (sau 0 cu --no-match-zero).
    """
    warnings: list[str] = []
    col_reglaj = _find_col(df_a, ["reglaj", "reglajul", "dimensiune"])
    col_finisaj = _find_col(df_a, ["finisaj", "FINISAJ"])
    col_tip = _find_col(df_a, ["tip_toc", "tip toc"])
    col_pret = _find_price_col(df_a)

    if not col_reglaj:
        warnings.append("Nu s-a gasit coloana «reglaj» (sau dimensiune); nu se modifica preturi.")
    if not col_finisaj:
        warnings.append("Nu s-a gasit coloana «Finisaj»; nu se modifica preturi.")
    if not col_pret:
        warnings.append("Nu s-a gasit coloana de pret; nu se modifica preturi.")

    out = df_a.copy()
    if not col_reglaj or not col_finisaj or not col_pret:
        return out, 0, len(out.index), warnings

    if not lookups_by_variant or not any(lookups_by_variant.values()):
        warnings.append("Nu exista matrice B incarcata.")
        return out, 0, len(out.index), warnings

    seen_tip_warn: set[str] = set()
    updated = 0
    unresolved = 0
    sentinela = 0.0 if no_match_zero else None

    for i in out.index:
        tip_v = out.at[i, col_tip] if col_tip else ""
        lookup, variant_key, tip_warn = pick_lookup_for_tip(lookups_by_variant, tip_v)
        if tip_warn and tip_warn not in seen_tip_warn:
            warnings.append(tip_warn)
            seen_tip_warn.add(tip_warn)

        labels_map = reglaj_labels_by_variant.get(variant_key, {})

        r = normalize_reglaj(out.at[i, col_reglaj])
        bcol = finisaj_to_b_column(str(out.at[i, col_finisaj]))
        if not r or not bcol:
            unresolved += 1
            if sentinela is not None:
                out.at[i, col_pret] = sentinela
            continue
        row_b = None
        rk_used: str | None = None
        if lookup:
            row_b = lookup.get(r)
            rk_used = r
            if row_b is None:
                rk = resolve_reglaj_key(r, lookup)
                if rk:
                    row_b = lookup.get(rk)
                    rk_used = rk
        if not row_b:
            unresolved += 1
            if sentinela is not None:
                out.at[i, col_pret] = sentinela
            continue
        price = row_b.get(bcol)
        if price is None:
            unresolved += 1
            if sentinela is not None:
                out.at[i, col_pret] = sentinela
            continue
        out.at[i, col_pret] = price
        if rk_used and rk_used in labels_map:
            out.at[i, col_reglaj] = labels_map[rk_used]
        updated += 1

    return out, updated, unresolved, warnings


def _resolve_sheet_name(path: Path, sheet_arg: str | int) -> str:
    xl = pd.ExcelFile(path)
    if isinstance(sheet_arg, int):
        return xl.sheet_names[sheet_arg]
    s = str(sheet_arg)
    if s.isdigit():
        return xl.sheet_names[int(s)]
    return s


def _resolve_default_a() -> Path:
    """Prima potrivire: tocuri dedicat, apoi template import, apoi A.xlsx."""
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    candidates = [
        root / "tocuri.xlsx",
        root / "tocuri_import.xlsx",
        root / "A.xlsx",
        root / "templates" / "import_tocuri_supabase.xlsx",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return root / "A.xlsx"


def main() -> int:
    ap = argparse.ArgumentParser(description="Suprascrie preturile din A cu matricea B.")
    ap.add_argument(
        "--a",
        type=Path,
        default=None,
        help="Fisier A (tocuri / baza de date). Implicit: A.xlsx sau templates/import_tocuri_supabase.xlsx daca exista.",
    )
    ap.add_argument("--b", type=Path, default=Path("B.xlsx"), help="Matrice preturi B.xlsx")
    ap.add_argument("--out", type=Path, default=Path("A_Import_Supabase.csv"), help="CSV iesire")
    ap.add_argument("--sheet-a", default=0, help="Sheet din A (index sau nume)")
    ap.add_argument(
        "--no-match-zero",
        action="store_true",
        help="La lipsa potrivire reglaj/finisaj, pune 0 in loc de gol",
    )
    ap.add_argument(
        "--update-a",
        action="store_true",
        help="Rescrie fisierul A.xlsx cu reglaj + pret actualizate (acelasi --a).",
    )
    args = ap.parse_args()

    path_a = (args.a.resolve() if args.a else _resolve_default_a().resolve())
    path_b = (Path.cwd() / args.b).resolve() if not args.b.is_absolute() else args.b.resolve()

    if not path_a.is_file():
        print(f"Avertisment: nu exista {path_a} — foloseste --a <cale_tocuri.xlsx>", file=sys.stderr)
        return 1
    if not path_b.is_file():
        print(f"Avertisment: nu exista {path_b}", file=sys.stderr)
        return 1

    try:
        sheet_a: str | int = args.sheet_a
        if isinstance(args.sheet_a, str) and args.sheet_a.isdigit():
            sheet_a = int(args.sheet_a)
        df_a = pd.read_excel(path_a, sheet_name=sheet_a)
    except Exception as e:
        print(f"Eroare citire A: {e}", file=sys.stderr)
        return 1

    lookups, reglaj_labels, b_sheet_warnings = build_b_lookups(path_b)
    for w in b_sheet_warnings:
        print(w, file=sys.stderr)
    if not any(bool(v) for v in lookups.values()):
        print("Avertisment: B nu a putut fi citit ca matrice (gol sau format neasteptat).", file=sys.stderr)

    out_df, updated, unresolved, warnings = fill_prices(
        df_a,
        lookups,
        reglaj_labels,
        no_match_zero=args.no_match_zero,
    )
    for w in warnings:
        print(w, file=sys.stderr)

    out_path = args.out if args.out.is_absolute() else (Path.cwd() / args.out)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"Scrie: {out_path}")
    print(f"Randuri cu pret + reglaj din B: {updated}, nerezolvate (fara potrivire): {unresolved}")

    if args.update_a:
        try:
            sn = _resolve_sheet_name(path_a, sheet_a)
            all_sheets = pd.read_excel(path_a, sheet_name=None)
            all_sheets[sn] = out_df
            with pd.ExcelWriter(path_a, engine="openpyxl") as writer:
                for name, d in all_sheets.items():
                    d.to_excel(writer, sheet_name=name, index=False)
            print(f"Actualizat A.xlsx: {path_a} (foaie «{sn}»)")
        except Exception as e:
            print(f"Eroare scriere A.xlsx: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
