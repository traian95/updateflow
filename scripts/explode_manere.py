"""
Explodează date tabulare mânere: Model × Finisaj × Tip accesoriu (OB/PZ/WC).
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import pandas as pd


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cmap = {_norm_name(c): c for c in df.columns}
    for cand in candidates:
        n = _norm_name(cand)
        if n in cmap:
            return cmap[n]
    for c in df.columns:
        cn = _norm_name(c)
        for cand in candidates:
            if cn == _norm_name(cand):
                return c
    return None


def parse_eu_price(raw) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "-", "—", "n/a"):
        return None
    s = s.replace("*", "").replace("\u00a0", " ")
    if "/" in s:
        s = s.split("/")[0].strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s or s == "-":
        return None
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(".") == 1 and s.count(",") == 0:
        pass
    elif s.count(",") >= 1 and s.count(".") >= 1:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _sort_key_columns(series: pd.Series) -> pd.Series:
    """Sortare: Model și Finisaj alfabetic (fără diferență de majuscule), apoi OB → PZ → WC."""
    name = series.name
    if name in ("Nume_Model", "Finisaj"):
        return series.astype(str).str.strip().str.lower()
    if name == "Tip_Accesoriu":
        return series.map({"OB": 0, "PZ": 1, "WC": 2}).fillna(99)
    return series


def sort_manere_result(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values(
        by=["Nume_Model", "Finisaj", "Tip_Accesoriu"],
        key=_sort_key_columns,
    ).reset_index(drop=True)


def find_modele_preturi_manere_file(search_roots: list[Path]) -> Path | None:
    """Caută «modele si preturi manere» (.csv / .xlsx) în folderele aplicației."""
    exact_names = (
        "modele si preturi manere.csv",
        "modele si preturi manere.xlsx",
    )
    for root in search_roots:
        if not root.is_dir():
            continue
        for n in exact_names:
            p = root / n
            if p.is_file():
                return p
        try:
            for p in root.iterdir():
                if not p.is_file():
                    continue
                low = p.name.lower()
                if (
                    "modele" in low
                    and "pret" in low
                    and "manere" in low
                    and low.endswith((".csv", ".xlsx", ".xls"))
                ):
                    return p
        except OSError:
            continue
    return None


def read_csv_flexible(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        first = text.splitlines()[0] if text else ""
        n_comma, n_semi = first.count(","), first.count(";")
        sep = ";" if n_semi > n_comma else ","
        try:
            return pd.read_csv(path, sep=sep, encoding=enc, dtype=str)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Nu pot citi CSV: {path} ({last_err})")


def read_table(path: Path) -> pd.DataFrame:
    suf = path.suffix.lower()
    if suf in (".xlsx", ".xls"):
        try:
            return pd.read_excel(path, dtype=str, engine="openpyxl")
        except ImportError as e:
            raise RuntimeError(
                "Pentru fișiere .xlsx instalează: pip install openpyxl"
            ) from e
    return read_csv_flexible(path)


def explode_manere(
    df: pd.DataFrame,
    col_model: str,
    col_finisaje: str,
    col_baza: str,
    col_ob: str,
    col_pz: str,
    col_wc: str,
) -> pd.DataFrame:
    df = df.copy()
    df[col_model] = (
        df[col_model]
        .replace("", pd.NA)
        .replace(r"^\s*$", pd.NA, regex=True)
        .ffill()
    )

    rows: list[dict] = []
    acc_cols = [("OB", col_ob), ("PZ", col_pz), ("WC", col_wc)]

    for _, r in df.iterrows():
        model = r[col_model]
        if pd.isna(model) or str(model).strip() == "":
            continue

        fin_raw = r.get(col_finisaje, "")
        if pd.isna(fin_raw):
            fin_raw = ""
        fin_list = [f.strip() for f in str(fin_raw).split(",") if f.strip()]

        if not fin_list:
            fin_list = [""]

        pret_baza = parse_eu_price(r.get(col_baza))

        for fin in fin_list:
            for tip, ccol in acc_cols:
                p_acc = parse_eu_price(r.get(ccol))
                if p_acc is None:
                    continue
                pb_num = pret_baza if pret_baza is not None else 0.0
                total = pb_num + p_acc
                rows.append(
                    {
                        "Nume_Model": str(model).strip(),
                        "Finisaj": fin,
                        "Tip_Accesoriu": tip,
                        "Pret_Baza_Maner": pret_baza if pret_baza is not None else pd.NA,
                        "Pret_Accesoriu": p_acc,
                        "Pret_Total_Calculat": round(total, 2),
                    }
                )

    out = pd.DataFrame(rows)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Explodează CSV mânere în variații Model×Finisaj×Tip.")
    ap.add_argument(
        "input",
        nargs="?",
        default=None,
        type=Path,
        help="Fișier CSV sursă (implicit: manere_sursa.csv lângă script sau cwd)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="CSV ieșire (implicit: manere_final.csv în același folder cu intrarea)",
    )
    ap.add_argument("--model", help="Nume coloană explicit pentru model")
    ap.add_argument("--finisaje", help="Nume coloană explicit pentru Finisaje")
    ap.add_argument("--pret-baza", help="Nume coloană pentru preț mâner / bază")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent.parent
    app_dir = base / "Soft Ofertare Usi"
    inp = args.input
    if inp is None:
        inp = find_modele_preturi_manere_file([app_dir, base])
        if inp is None:
            for cand in (base / "manere_sursa.csv", Path.cwd() / "manere_sursa.csv"):
                if cand.is_file():
                    inp = cand
                    break
        if inp is None:
            print(
                "Nu s-a găsit «modele si preturi manere.csv» (sau .xlsx) în folderul programului "
                f"({app_dir}), nici manere_sursa.csv. Specifică calea: python explode_manere.py <fisier.csv>",
                file=sys.stderr,
            )
            return 1

    inp = inp.resolve()
    out = args.output
    if out is None:
        out = inp.parent / "manere_final.csv"

    df = read_table(inp)

    col_model = args.model or find_column(
        df,
        [
            "Nume_Model",
            "Nume model",
            "Model",
            "Nume Maner",
            "Nume_Maner",
            "Nume mâner",
        ],
    )
    col_finisaje = args.finisaje or find_column(df, ["Finisaje", "Finisaj"])
    col_ob = find_column(df, ["Preț OB", "Pret OB", "Pret_OB", "PrețOB"])
    col_pz = find_column(df, ["Preț PZ", "Pret PZ", "Pret_PZ", "PrețPZ"])
    col_wc = find_column(df, ["Preț WC", "Pret WC", "Pret_WC", "PrețWC"])
    col_baza = args.pret_baza or find_column(
        df,
        [
            "Preț Mâner",
            "Pret Maner",
            "Pret_Mâner",
            "Preț mâner",
            "Pret baza",
            "Preț bază",
            "Pret_Baza_Maner",
            "Preț de bază",
            "Pret de baza",
        ],
    )

    missing = []
    if not col_model:
        missing.append("model (Nume_Model / Model / …)")
    if not col_finisaje:
        missing.append("Finisaje")
    if not col_ob:
        missing.append("Preț OB")
    if not col_pz:
        missing.append("Preț PZ")
    if not col_wc:
        missing.append("Preț WC")
    if not col_baza:
        missing.append("preț bază mâner (Preț Mâner / …) — folosește --pret-baza")
    if missing:
        print("Coloane lipsă sau nerecunoscute:", ", ".join(missing), file=sys.stderr)
        print("Coloane găsite:", list(df.columns), file=sys.stderr)
        return 1

    result = explode_manere(df, col_model, col_finisaje, col_baza, col_ob, col_pz, col_wc)
    result = sort_manere_result(result)

    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(
        out,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )
    print(f"Scrie {out} ({len(result)} rânduri).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
