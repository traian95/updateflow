# Note implementare Azure SQL – Ofertare & Admin

## Arhitectură

- **Aplicația de ofertare (showroom)**  
  - La prima pornire descarcă baza relevantă din Azure SQL în `date_ofertare.db` (cache local).  
  - Apoi lucrează **doar** pe SQLite local.  
  - Periodic (și la repornire) verifică dacă există o versiune mai nouă în Azure și, dacă da, face refresh complet din Azure în cache.  
  - Dacă Azure SQL este în pauză (Serverless auto-pause), aplicația continuă din cache fără erori fatale.

- **Aplicația de admin**  
  - Se conectează la aceeași bază Azure SQL (prin același connection string).  
  - Lucrează pe baza locală `date_ofertare.db`; la „UPDATE date stații” urcă modificările în Azure și incrementează `data_version`, astfel că toate stațiile de showroom se actualizează la următoarea verificare.

- **Baza Azure SQL**  
  - Azure SQL Database, tip **Serverless**, cu **auto-pause delay = 15 minute**.  
  - Schema este creată/actualizată din cod (`init_schema_azure`: schema_version, produse, clienti, oferte, users, app_versions, activity_log).

---

## 1. Configurare stație showroom (nouă)

1. **Driver ODBC**  
   - Instalează **ODBC Driver 18 for SQL Server** (64-bit):  
     - [Descărcare Microsoft](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)  
     - Sau: `winget install Microsoft.SqlServer.ODBC.18`

2. **Python**  
   - Asigură-te că ai `pyodbc`:  
     `pip install pyodbc`

3. **Variabile de mediu** (nu le salva în cod sau fișiere versionate):  
   - `AZURE_SQL_CONN_STR` – connection string complet, de forma:  
     `Driver={ODBC Driver 18 for SQL Server};Server=tcp:<server>.database.windows.net,1433;Database=<nume_baza>;Uid=<user>;Pwd=<parola>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;`  
   - Opțional pentru mod sync: `SOFT_OFERTARE_MODE=azure_sync`  
     sau în `app_settings.json` adaugă: `"data_mode": "azure_sync"`

4. **Prima pornire**  
   - Pornește aplicația de ofertare. În modul `azure_sync` se face automat descărcarea completă din Azure în `date_ofertare.db`.  
   - Dacă Azure este indisponibil (ex. în repaus), aplicația pornește doar cu cache-ul existent (sau gol) și nu dă erori critice.

---

## 2. Configurare stație Admin

1. Același **ODBC Driver 18** și **pyodbc** ca la showroom.  
2. Același **AZURE_SQL_CONN_STR** (baza centrală Azure).  
3. Opțional: `SOFT_OFERTARE_MODE=azure_sync` dacă vrei ca și Admin să verifice versiunea la pornire (în practică Admin folosește baza locală și doar la „UPDATE date stații” scrie în Azure).  
4. Baza locală folosită este tot `date_ofertare.db` (vezi `get_database_path()` în `ofertare/config.py`).  
   Stația Admin este de obicei cea „master”: are catalogul și ofertele; la „UPDATE date stații” le urcă în Azure.

---

## 3. Ce face butonul „UPDATE date stații” (Admin)

1. **sync_changes_local_to_azure**  
   - Urcă în Azure modificările din baza locală pentru: **produse**, **clienti**, **oferte**, **users**.  
   - Strategie: „last write wins” la nivel de rând (dacă un id există deja în Azure, este suprascris cu valorile locale).

2. **bump_remote_data_version**  
   - Inserează o nouă linie în `app_versions` cu `data_version` incrementat.  
   - Toate stațiile showroom cu `azure_sync` vor vedea la următoarea verificare (periodică sau la repornire) că versiunea din Azure e mai mare și vor face un sync complet Azure → local.

---

## 4. Modul azure_sync (cache local + sync periodic)

- **La pornire** aplicația de ofertare:  
  - Deschide SQLite local (`date_ofertare.db`).  
  - Apelează `check_for_remote_updates_and_refresh_cache`: se conectează la Azure, compară `app_versions.data_version` cu `sync_state.data_version` din SQLite; dacă versiunea din Azure e mai mare, rulează `sync_from_azure_to_local` (refresh complet pentru produse, clienti, oferte, users) și actualizează `sync_state`.  
  - Programează verificări periodice cu `schedule_periodic_remote_update_check` (implicit la câteva minute).

- **În timpul rulării** toate citirile/scrierile sunt făcute **doar** pe SQLite; Azure este folosit doar pentru sync (verificare versiune + descărcare la nevoie).

- **Azure în repaus (Serverless auto-pause)**  
  - La verificarea periodică, dacă Azure nu răspunde, eroarea este prinsă și logată; aplicația continuă să funcționeze pe cache-ul local.

---

## 5. Infrastructură Azure (recomandări)

- **Tip**: Azure SQL Database, tier **Serverless**.  
- **Auto-pause delay**: 15 minute (serverul intră în stand-by după 15 minute fără activitate).  
- **Firewall**: adaugă reguli pentru IP-urile stațiilor de showroom și pentru stația Admin (Azure Portal → SQL server → Networking / Firewall).

Crearea bazei și a serverului se poate face din Azure Portal sau cu Azure CLI; nu stocăm niciodată parola în cod sau în fișiere din repo.

### Comenzi Azure CLI (exemplu)

Înlocuiește `<subscription-id>`, `<resource-group>`, `<server-name>`, `<database-name>`, `<admin-login>`, `<admin-password>` cu valorile tale.

```bash
# Login
az login

# Creare resurse (dacă nu există)
az sql server create --resource-group <resource-group> --name <server-name> --location westeurope --admin-user <admin-login> --admin-password <admin-password>

# Creare bază Serverless, auto-pause 15 minute
az sql db create --resource-group <resource-group> --server <server-name> --name <database-name> \
  --edition GeneralPurpose --compute-model Serverless --min-capacity 0.5 --max-capacity 4 \
  --auto-pause-delay 15

# Firewall: adaugă IP-ul curent (pentru test)
az sql server firewall-rule create --resource-group <resource-group> --server <server-name> --name AllowCurrent --start-ip-address <IP> --end-ip-address <IP>
```

Connection string (template):  
`Driver={ODBC Driver 18 for SQL Server};Server=tcp:<server-name>.database.windows.net,1433;Database=<database-name>;Uid=<admin-login>;Pwd=<admin-password>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;`

---

## 6. Inițializare schemă în Azure (o singură dată)

După ce ai creat baza și ai setat `AZURE_SQL_CONN_STR`:

```powershell
cd "c:\Users\elena\Videos\Soft Ofertare Usi"
# Setează mai întâi AZURE_SQL_CONN_STR (vezi mai sus)
python scripts/init_azure_schema.py
```

Scriptul apelează `open_azure_db` și `init_schema_azure` și afișează tabelele existente și versiunea din `app_versions`.

---

## 7. Verificări practice (2–3 pași)

1. **Showroom – prima pornire**  
   - Șterge sau redenumește `date_ofertare.db` (sau folosește un PC „curat”).  
   - Setează `SOFT_OFERTARE_MODE=azure_sync` și `AZURE_SQL_CONN_STR`.  
   - Pornește aplicația de ofertare; confirmă că se face sync complet Azure → local (prima descărcare).  

2. **Admin – UPDATE date stații**  
   - În Admin, modifică ceva (ex. un preț la un produs sau un client).  
   - Apasă „UPDATE date stații”.  
   - Verifică că nu apare eroare și că în Azure `app_versions.data_version` s-a incrementat (ex. prin `scripts/init_azure_schema.py` sau un SELECT în Azure).  

3. **Showroom – după update**  
   - Pe o stație showroom cu `azure_sync`, așteaptă următoarea verificare periodică sau repornește aplicația.  
   - Confirmă că modificarea făcută din Admin apare în aplicația de ofertare (cache-ul s-a actualizat din Azure).

---

## 8. Rezumat scurt

| Element | Detaliu |
|--------|--------|
| **Azure** | Azure SQL Database Serverless, auto-pause 15 min; firewall pentru IP-uri showroom + admin. |
| **Variabile** | `AZURE_SQL_CONN_STR` (obligatoriu pentru sync/init). `SOFT_OFERTARE_MODE=azure_sync` sau `app_settings.json` → `"data_mode": "azure_sync"`. |
| **Primul sync** | La prima pornire în `azure_sync`, aplicația descarcă întreaga bază relevantă din Azure în `date_ofertare.db`. |
| **Update toate stațiile** | Admin: modificări locale → „UPDATE date stații” → sync local→Azure + bump `data_version`; showroom-urile se actualizează la următoarea verificare. |
| **Verificare** | (1) Showroom curat + pornire → sync complet; (2) Admin „UPDATE date stații” → fără eroare; (3) Showroom după interval/repornire → date actualizate. |
