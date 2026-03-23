# Import date din Excel în baza de date

## 1. Din aplicația Admin (Excel ordonat)

- Deschide **Soft Admin** → **Introducere produse** → **Importă produse din Excel**.
- Fișierul Excel trebuie să aibă **prima foaie** cu un rând de header și coloane recunoscute.

Coloane recunoscute (sau variante): `furnizor`, `categorie`, `colectie`/`colecție`, `model`, `decor`, `finisaj`/`finisaje`, `pret`/`preț`, `tip_toc`/`tip toc`, `reglaj`/`dimensiune`.

Pentru **Parchet** (categorii: Parchet Laminat Stoc, Parchet Laminat Comanda, Parchet Spc Stoc, Parchet Spc Floorify, Parchet Triplu Stratificat) coloanele din PDF/Excel sunt: **Colectia**, **Cod produs**, **MP/Cut**, **Pret lista eur fara TVA/mp**. Acestea apar în soft exact cu etichetele: Colectia, Cod Produs, MP/cut.

Poți genera un template: rulează `python genereaza_template_import.py` și completezi fișierul generat.

---

## 2. Excel „haotic” – script flexibil

Dacă Excel-ul are header pe alt rând, altă foaie sau coloane cu nume diferite, folosește:

```batch
cd "c:\Users\elena\Documents\Soft Ofertare Usi"

REM Previzualizare (nu scrie în DB):
python import_excel_flexibil.py "C:\cale\la\fisierul_tau.xlsx" --dry-run

REM Header pe rândul 3 (0 = primul, 1 = al doilea, etc.):
python import_excel_flexibil.py "fisierul_tau.xlsx" --header 2

REM Foaie anume (nume sau index):
python import_excel_flexibil.py "fisierul_tau.xlsx" --sheet "Produse"
python import_excel_flexibil.py "fisierul_tau.xlsx" --sheet 1

REM Import efectiv:
python import_excel_flexibil.py "fisierul_tau.xlsx"
```

Scriptul recunoaște multe variante de nume pentru coloane (ex.: categorie, categorie produs, pret, preț, price, tip toc, reglaj, dimensiune etc.). Dacă ai coloane cu alt nume, poți:

- **Varianta 1:** Redenumești în Excel prima linie să fie unul dintre: `furnizor`, `categorie`, `colectie`, `model`, `decor`, `finisaj`, `pret`, `tip_toc`, `reglaj`.
- **Varianta 2:** În fișierul `import_excel_flexibil.py`, în dicționarul `COLOANE_EXCEL_TO_DB`, adaugi o linie de forma `"numele din excel": "pret"` (sau alt câmp: categorie, model, etc.).

Baza de date folosită este aceeași ca la aplicație: `date_ofertare.db` din folderul proiectului.

---

## 3. Izolații parchet (categoria „Izolatii parchet”, Stoc)

Izolațiile parchet sunt stocate în categoria **Izolatii parchet**, furnizor **Stoc**. Ele apar în tab-ul **PARCHET** (popup Adaugă parchet) în dropdown-ul de izolații.

- Generează template: `python genereaza_template_izolatiile.py` → se creează `template_izolatiile_parchet.xlsx`.
- Completează foaia **Izolatiile** (Denumire, culoare, grosime, dimensiune, Cantitatea, Pret lista).
- Import: `python import_izolatiile_from_excel.py "template_izolatiile_parchet.xlsx"`.

Poți adăuga și din **Admin** → Furnizor Stoc → Categorie **Izolatii parchet** (introducere manuală sau import Excel cu coloana categorie = Izolatii parchet).

---

## 4. Plinte parchet (categoria „Plinta parchet”, Stoc)

Plintele parchet sunt stocate în categoria **Plinta parchet**, furnizor **Stoc**. Ele apar în tab-ul **PARCHET** (popup Adaugă parchet) în dropdown-ul de plinte.

- Generează template: `python genereaza_template_plinte_parchet.py` → se creează `template_plinte_parchet.xlsx`.
- Completează foaia **Plinte** (Denumire, culoare, model, dimensiune, Pret lista).
- Import: `python import_plinte_from_excel.py "template_plinte_parchet.xlsx"`.

Poți adăuga și din **Admin** → Furnizor Stoc → Categorie **Plinta parchet**.
