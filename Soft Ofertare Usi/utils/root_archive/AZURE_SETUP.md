## Configurare Azure SQL pentru „Soft Ofertare Uși”

### 1. Connection string Azure SQL

- Creează o bază de date Azure SQL (ideal, tier Serverless cu auto-pause activat).
- Configurează pe fiecare stație o variabilă de mediu:

```text
AZURE_SQL_CONN_STR=Driver={ODBC Driver 18 for SQL Server};Server=tcp:<server>.database.windows.net,1433;Database=<nume_baza>;Uid=<user>;Pwd=<parola>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;
```

- Nu salva user / parolă în cod sau în repo – doar în mediul de execuție.

### 2. Modul de lucru cu datele (local vs Azure + cache)

- Implicit aplicația rulează doar pe SQLite local.
- Pentru a activa modul „Azure + cache local”, setează pe stație:

```text
SOFT_OFERTARE_MODE=azure_sync
```

- În acest mod:
  - la pornire, `AplicatieOfertare` deschide baza locală SQLite și apelează
    `check_for_remote_updates_and_refresh_cache`, care:
    - se conectează la Azure SQL;
    - verifică `app_versions.data_version`;
    - dacă există o versiune mai nouă decât ce e salvat local în `sync_state`,
      face un sync complet Azure → SQLite pentru tabelele:
      `produse`, `clienti`, `oferte` (ultimii ~3 ani), `users`;
    - actualizează `sync_state.data_version` în SQLite.
  - periodic (la câteva minute) se reface această verificare, tolerând erorile de rețea.

### 3. UPDATE toate stațiile (din Admin)

- În `AdminApp` există butonul `UPDATE date stații`.
- La apăsare:
  1. `sync_changes_local_to_azure` publică în Azure ultimele date critice
     (clienți + oferte) din baza locală, folosind o strategie „last write wins
     la nivel de înregistrare”:
     - dacă o înregistrare cu același `id` există deja în Azure este suprascrisă,
       iar un eveniment este înregistrat în tabelul `activity_log`.
  2. `bump_remote_data_version` inserează o nouă intrare în `app_versions`
     cu `data_version` incrementat.
- Toate stațiile care rulează cu `SOFT_OFERTARE_MODE=azure_sync` vor detecta
  noua versiune la următoarea verificare și își vor resincorniza cache-ul local.

### 4. Baza locală SQLite ca „cache”

- Fişierul local rămâne `date_ofertare.db` (vezi `get_database_path`).
- Tabelul `sync_state` din SQLite păstrează:
  - `data_version` – ultima versiune de date sincronizată din Azure;
  - `last_sync_at` – momentul ultimei sincronizări complete.
- Dacă Azure SQL nu este disponibil:
  - aplicația pornește normal și folosește datele locale existente;
  - orice eroare la conectare / timeout este logată, dar nu blochează UI-ul.

### 5. Comportament cu Azure SQL „în repaus” (Serverless auto-pause)

- În `open_azure_db` există retry-uri explicite pentru scenariul în care baza
  serverless este „adormită”:
  - se încearcă de mai multe ori conectarea, cu pauze progresive între încercări;
  - dacă după toate încercările nu se poate stabili conexiunea, aplicația
    continuă să funcționeze doar pe cache local.
- Recomandare de configurare în Azure:
  - setează opțiunea „auto-pause delay” la 15 minute pentru baza de tip Serverless;
  - aplicația este tolerantă la prima conexiune mai lentă după pauză (sync-ul
    poate dura mai mult, dar UI-ul continuă să funcționeze cu date locale).

