# Instrucțiuni: instalare Soft Ofertare pe fiecare PC (comunicare prin Azure)

Ca **Ofertare** și **Admin** de pe PC-uri diferite să comunice prin baza de date Azure, pe **fiecare PC** unde instalezi softul trebuie făcute pașii de mai jos. Connection string-ul către Azure trebuie să fie **același** pe toate PC-urile.

---

## 1. Ce ai nevoie pe fiecare PC

- **Dacă rulezi din setup (.exe):** nu ai nevoie de Python. Ai nevoie doar de:
  - **ODBC Driver 18 for SQL Server** – instalat pe Windows ([descărcare Microsoft](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)).
  - **Variabila de mediu AZURE_SQL_CONN_STR** setată permanent (vezi pasul 3).
- **Dacă rulezi din sursă (Python):** Python, **pyodbc** (`pip install pyodbc`), același ODBC Driver 18 și AZURE_SQL_CONN_STR.

---

## 2. Instalare pyodbc

Într-un terminal (PowerShell sau CMD) pe acel PC:

```powershell
pip install pyodbc
```

(Sau, dacă folosești un mediu virtual: activezi env-ul apoi rulezi `pip install pyodbc`.)

---

## 3. Setare variabilă de mediu pentru Azure (obligatoriu pe fiecare PC)

Connection string-ul trebuie setat ca variabilă de mediu **înainte** de a porni Ofertare sau Admin.

### Variantă A: Doar pentru sesiunea curentă (PowerShell)

Deschizi PowerShell și rulezi (înlocuiești cu connection string-ul tău real):

```powershell
$env:AZURE_SQL_CONN_STR = "Driver={ODBC Driver 18 for SQL Server};Server=tcp:NUME_SERVER.database.windows.net,1433;Database=NUME_BAZA;Uid=USER;Pwd=PAROLA;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30"
```

Apoi din **același** PowerShell pornești aplicația. La fiecare nouă deschidere a PowerShell-ului trebuie să rulezi din nou comanda.

### Variantă B: Permanent pentru utilizatorul Windows (recomandat)

1. **Win + R** → scrii `sysdm.cpl` → Enter.
2. Tab **Avansat** → **Variabile de mediu**.
3. La **Variabile utilizator** (sau **Variabile de sistem** dacă vrei pentru toți userii) → **Nou**.
4. **Nume variabilă:** `AZURE_SQL_CONN_STR`
5. **Valoare:** connection string-ul complet (același pe toate PC-urile), de forma:
   ```
   Driver={ODBC Driver 18 for SQL Server};Server=tcp:naturen-flow-server.database.windows.net,1433;Database=NaturenFlowDB;Uid=...;Pwd=...;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30
   ```
6. OK → OK. **Repornește** aplicația (sau delogare/logare Windows) ca să vadă variabila.

**Important pentru instalarea din setup (.exe):** Aplicațiile instalate din NaturenFlow_Ofertare_Setup.exe / NaturenFlow_Admin_Setup.exe **nu** citesc variabila din PowerShell. Trebuie setată **permanent** la pasul 4 (Variabile utilizator sau de sistem). Altfel „Sincronizează cu Azure” va spune că AZURE_SQL_CONN_STR lipsește.

Connection string-ul îl iei din Azure Portal (baza de date → **Connection strings**), sau îl ai deja din prima configurare. **Același string** pe toate PC-urile.

---

## 4. (O singură dată) Inițializare schema în Azure

Schema tabelelor în Azure se creează **o singură dată** (de pe orice PC sau de pe un server).

- Setezi `AZURE_SQL_CONN_STR` (ca mai sus).
- Din rădăcina proiectului rulezi:

```powershell
cd "C:\calea\ta\Soft Ofertare Usi"
python scripts/init_azure_schema.py
```

Când vezi „Initializare schema Azure finalizata cu succes.” și lista de tabele, schema e în regulă. Nu mai e nevoie să rulezi scriptul pe fiecare PC.

---

## 5. Pornire aplicații pe fiecare PC

- **Ofertare:** `python run_ofertare.py` (sau exe-ul tău).
- **Admin:** `python admin_app.py` (sau exe-ul tău).

Asigură-te că **înainte** de a le porni ai setat `AZURE_SQL_CONN_STR` (pasul 3).

---

## 6. Cum se comunică datele (flux normal)

- **Pe PC-ul unde se fac ofertele (Ofertare):**  
  După ce creezi/actualizezi oferte, apeși butonul **„Sincronizează cu Azure”** din Ofertare. Se trimit ofertele (și clienții/users) în Azure.

- **Pe PC-ul unde folosești Admin:**  
  Apeși **„Sincronizează cu Azure”** din Admin. Se descarcă datele din Azure (inclusiv ofertele de pe celelalte PC-uri) și se actualizează și baza locală.

Fără apăsarea butonului de sync, datele **nu** se trimit/descarcă automat.

---

## 7. Verificare rapidă pe un PC nou

1. `AZURE_SQL_CONN_STR` setată (permanent sau în sesiunea curentă).
2. `pip install pyodbc` rulat.
3. Pornești Ofertare → te loghezi → apeși **„Sincronizează cu Azure”** → mesaj **„Sincronizare cu Azure reușită”**.
4. Pe alt PC (sau același): pornești Admin → **„Sincronizează cu Azure”** → ofertele apar în Admin.

Dacă primești „Azure indisponibil” sau erori la sync, verifici:
- variabila `AZURE_SQL_CONN_STR` (exact aceeași valoare ca pe PC-urile care funcționează),
- internetul și firewall-ul (port 1433 către `*.database.windows.net`),
- că baza Azure nu e în stare „pauzată” (în Portal: Resume dacă e cazul).

---

## Rezumat pe fiecare PC

| Pas | Ce faci |
|-----|--------|
| 1 | Instalezi Python + ODBC Driver 18 for SQL Server (dacă lipsește). |
| 2 | `pip install pyodbc` |
| 3 | Setezi `AZURE_SQL_CONN_STR` (același string pe toate PC-urile) – fie în sesiune, fie permanent. |
| 4 | (O dată în proiect) Rulezi `python scripts/init_azure_schema.py` când Azure e pornit. |
| 5 | Pornești Ofertare / Admin; pentru sync apeși butonul **„Sincronizează cu Azure”** când vrei să trimiți sau să primești date. |

Dacă toate PC-urile au acești pași făcuți și același `AZURE_SQL_CONN_STR`, totul poate comunica perfect prin Azure.
