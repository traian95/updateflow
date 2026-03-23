"""
Procesare inline a tabelului mânere → manere_sortate_final.csv
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

csv_data = """Nume Mâner,Finisaje,Preț Mâner,Preț OB,Preț PZ,Preț WC
ALORA,"LC, SC, BK","269,54","65,85","65,85","113,13"
,"WH, LG, KG","323,43","79,03","79,03","129,59"
,SNM,"300,25","72,44","72,44","124,46"
,GYM,"300,25","79,03","79,03","129,59"
AMBROSIA,BK,"348,56","65,85","65,85","113,13"
,"LG, KG","418,28","79,03","79,03","129,59"
ARABIS R,"CP, MSC, BLACK","178,23","65,01","65,01","111,70"
,"WHITE, GOLD PVD","196,05","71,51","71,51","122,85"
,GOLD SATIN,"213,88","78,01","78,01","128,44"
,"MSN, MSB, BR","187,15","65,01","65,01","111,70"
ARIA,"LC, SC, BK","344,11","77,50","77,50","118,84"
,"LG, KG, PN PVD","412,94","93,00","93,00","136,11"
ARNICA R,"CP, MSC, BLACK","178,23","65,01","65,01","111,70"
,GOLD PVD,"196,05","71,51","71,51","122,85"
,GOLD SATIN,"213,88","78,01","78,01","128,44"
,"MSN, MSB","187,15","65,01","65,01","111,70"
ASTERIA,"LC, BK","356,39","77,50","77,50","118,84"
,LG,"427,66","93,00","93,00","136,11"
AZALIA,"LC, SC, BK","260,90","65,85","65,85","113,13"
,"WH, LG, KG, PN PVD","313,10","79,03","79,03","129,59"
,SNM,"290,65","72,44","72,44","124,46"
,GYM,"290,65","79,03","79,03","129,59"
BELLISA,"FB, GYM","821,35","79,03","79,03","129,59"
,SIL,"862,43","86,93","86,93","142,54"
CAMELIA,LG,"389,69","79,03","79,03","129,59"
,GYM,"361,75","79,03","79,03","129,59"
CYNIA,"CP, MSC, BLACK","231,15","65,01","65,01","111,70"
,GOLD PVD,"254,26","71,51","71,51","122,85"
DALIA,"LC, SC, BK","275,39","65,85","65,85","113,13"
,"LG, KG, PN PVD","330,46","79,03","79,03","129,59"
DEGLASIA,LG,"326,39","79,03","79,03","129,59"
,GYM,"303,00","79,03","79,03","129,59"
DETAZIA,BK/BLACK LEATHER,"531,00","65,85","65,85","121,13"
EGERIA,"BK, LC / BLACK LEATHER","557,55","65,85","65,85","113,13"
,"LG, KG / BROWN LEATHER","669,05","79,03","79,03","129,59"
EUPHORBIA,"KG, GYM","392,09","79,03","79,03","129,59"
,SNM,"363,99","72,44","72,44","124,46"
FRAGOLA,"CP, MSC, BLACK","178,23","65,01","65,01","111,70"
,GOLD PVD,"196,05","71,51","71,51","122,85"
,GOLD SATIN,"213,88","78,01","78,01","128,44"
,"MSN, MSB","187,15","65,01","65,01","111,70"
FUNKIA R,"CP, MSC, BLACK","226,59","65,01","65,01","111,70"
,GOLD PVD,"249,24","71,51","71,51","122,85"
GARDENIA,LC,"359,43","77,50","77,50","118,84"
,"LG, KG","431,30","93,00","93,00","136,11"
GERBERA,"LG PVD, KG","334,23","79,03","79,03","129,59"
HIACYNTA,"LC, SC, BK","344,33","77,50","77,50","118,84"
,"LG, KG, PN PVD","413,19","93,00","93,00","136,11"
INULA,"CP, MSC, BLACK","221,88","65,01","65,01","111,70"
,GOLD PVD,"244,06","71,51","71,51","122,85"
IRGA,"CP, MSC, BLACK","178,23","65,01","65,01","111,70"
,"WHITE, GOLD PVD","196,05","71,51","71,51","122,85"
,GOLD SATIN,"213,88","78,01","78,01","128,44"
KALMIA,"CP, MSC, BLACK","198,56","65,01","65,01","111,70"
,"WHITE, GOLD PVD","218,44","71,51","71,51","122,85"
,GOLD SATIN,"238,29","78,01","78,01","128,44"
,"MSN, MSB, BR","208,49","65,01","65,01","111,70"
KERRIA,BK,"771,96","65,85","65,85","113,13"
,"KG, GYM, FB","926,34 / 859,96","79,03","79,03","129,59"
LAVANDA,"KG, GYM","380,51","79,03","79,03","129,59"
,SNM,"353,10","72,44","72,44","124,46"
LIRA,"LC, SC, BK","343,93","77,50","77,50","118,84"
,"LG, KG, PN PVD","412,70","93,00","93,00","136,11"
LOBELIA,LC,"375,59","77,50","77,50","118,84"
,"LG, KG","450,71","93,00","93,00","136,11"
LORENZA,LG,"348,06","79,03","79,03","129,59"
,GYM,"316,41","79,03","79,03","129,59"
LUNA,"CP, MSC, BLACK","212,29","65,01","65,01","111,70"
,GOLD PVD,"233,50","71,51","71,51","122,85"
MARIGOLD,"LC, BK","382,10","65,85","65,85","113,13"
,"WH, LG, KG, PN PVD","458,54","79,03","79,03","129,59"
,FB,"829,78","79,03","79,03","129,59"
MOLINIA,"CP, BLACK","329,95","65,01","65,01","111,70"
,"GOLD PVD, GOLD SATIN","381,03","71,51","71,51","122,85"
,"MSN, MSB, BR","346,44","65,01","65,01","111,70"
NERINA,LC,"278,51","65,85","65,85","113,13"
,LG PVD,"334,23","79,03","79,03","129,59"
NINFEA R,"LC, SC","269,43","65,85","65,85","113,13"
OLEANDRO,"CP, MSC, BLACK","178,23","65,01","65,01","111,70"
,GOLD PVD,"196,05","71,51","71,51","122,85"
,GOLD SATIN,"213,88","78,01","78,01","128,44"
,"MSN, MSB","187,15","65,01","65,01","111,70"
ORCHIDE,"LC, SC, BK","327,36","65,85","65,85","113,13"
,"LG, KG","392,84","79,03","79,03","129,59"
PAPAVERA,"KG, GYM","389,65","79,03","79,03","129,59"
,SNM,"361,73","72,44","72,44","124,46"
PEONIA,"LC, SC, BK","327,91","65,85","66,85","113,13"
PETUNIA,LC,"481,73","77,50","77,50","118,84"
,"LG, KG","578,08","93,00","93,00","136,11" """


def clean_price(val) -> float:
    """Prima valoare la «/», fără *, format european → float."""
    if pd.isna(val) or val == "":
        return 0.0
    s = str(val).replace("*", "").replace("\u00a0", " ").strip()
    if "/" in s:
        s = s.split("/")[0].strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s or s == "-":
        return 0.0
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
        return 0.0


def process_data() -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_data))
    df["Nume Mâner"] = df["Nume Mâner"].ffill()

    final_rows = []
    for _, row in df.iterrows():
        fin_raw = row["Finisaje"]
        if pd.isna(fin_raw):
            finisaje = [""]
        else:
            finisaje = [f.strip() for f in str(fin_raw).split(",") if f.strip()]

        if not finisaje:
            finisaje = [""]

        p_maner = clean_price(row["Preț Mâner"])
        optiuni = {
            "OB": clean_price(row["Preț OB"]),
            "PZ": clean_price(row["Preț PZ"]),
            "WC": clean_price(row["Preț WC"]),
        }

        for f in finisaje:
            for tip, p_rozeta in optiuni.items():
                final_rows.append(
                    {
                        "Model": row["Nume Mâner"],
                        "Finisaj": f,
                        "Tip_Rozeta": tip,
                        "Pret_Maner": p_maner,
                        "Pret_Rozeta": p_rozeta,
                        "Total": round(p_maner + p_rozeta, 2),
                    }
                )

    result_df = pd.DataFrame(final_rows)

    def _key(s: pd.Series) -> pd.Series:
        if s.name in ("Model", "Finisaj"):
            return s.astype(str).str.strip().str.lower()
        if s.name == "Tip_Rozeta":
            return s.map({"OB": 0, "PZ": 1, "WC": 2}).fillna(99)
        return s

    result_df = result_df.sort_values(
        by=["Model", "Finisaj", "Tip_Rozeta"],
        key=_key,
    ).reset_index(drop=True)
    return result_df


def main() -> None:
    out = process_data()
    dest = Path(__file__).resolve().parent.parent / "Soft Ofertare Usi" / "manere_sortate_final.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"Scrie {dest} ({len(out)} rânduri).")
    print(out.head(15).to_string())


if __name__ == "__main__":
    main()
