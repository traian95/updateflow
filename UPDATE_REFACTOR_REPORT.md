# UPDATE REFACTOR REPORT

## Ce am schimbat

Am unificat sistemul de update într-un flux principal unic, conservativ:

- sursa de update cloud: doar `app_updates`;
- sursa locală de versiune: doar `version.json`;
- flux aplicare update: ZIP + SHA256 + updater extern;
- logică veche de tip exe-swap păstrată doar ca legacy dezactivat.

## Fișiere modificate

- `Soft Ofertare Usi/ofertare/updater.py`
  - eliminat fallback-ul de versiune din `app_config/settings/app_settings/metadata`;
  - adăugat `get_local_version()` și `set_local_version()` pe `version.json`;
  - adăugat normalizare metadata update:
    - `version`, `download_url`, `sha256`, `mandatory`, `notes`, `is_active`;
  - adăugat verificare SHA256 înainte de instalare;
  - `upload_new_version(...)` extins pentru toate câmpurile standard;
  - dezactivare automată update-uri active anterioare la publish nou;
  - adăugat `list_updates_for_admin(...)`;
  - marcat/dezactivat fluxul legacy `check_and_install_update`.

- `Soft Ofertare Usi/main.py`
  - eliminată logica paralelă proprie de update;
  - folosește fluxul unificat din `ofertare/updater.py`.

- `Soft Ofertare Usi/ofertare/ui.py`
  - eliminată versiunea hardcodata;
  - folosește `get_local_version()` și transmite `sha256`/`version_cloud` la instalare.

- `Soft Ofertare Usi/updater.py`
  - updater extern extins:
    - extragere în temp;
    - copiere peste aplicație cu excludere `data/`, `config/`;
    - backup minimal fișiere suprascrise în `_update_backup`;
    - update `version.json`;
    - log updater (`update-updater.log`);
    - cleanup temporare.

- `Soft Ofertare Usi/ofertare/admin_ui.py`
  - publicare update extinsă cu:
    - `sha256`, `mandatory`, `notes`, `is_active`;
  - listă simplă update-uri existente + stare active/mandatory/sha.

- `Soft Ofertare Usi/build_update.py`
  - versiunea release citită din `version.json` (nu din hardcode în `main.py`);
  - include obligatoriu `version.json` în arhiva update.

- `Soft Ofertare Usi/prepare_release_1.0.0.bat`
  - copiază explicit `updater.py` și `version.json` în bundle.

- `Soft Ofertare Usi/1.0.0/setup_flow.iss`
- `Soft Ofertare Usi/1.0.0/setup_flow_update.iss`
  - includ explicit `updater.py` + `version.json` la instalare/update.

- adăugat `Soft Ofertare Usi/version.json`.

## Logică veche dezactivată / marcată legacy

- fluxul alternativ de update bazat pe `ofertare_new.exe` / batch swap nu mai este activ.
- fallback-ul pentru versiune remote din tabele de settings nu mai este folosit în update.

## Presupuneri făcute

- `app_updates` este tabela canonicală de update.
- schema DB suportă sau va suporta câmpurile:
  - `version`, `download_url`, `sha256`, `mandatory`, `notes`, `is_active`.
- `version.json` trebuie livrat în toate build-urile client.

## Ce trebuie configurat manual de către tine

1. Setează variabilele admin în mediu (sau `.env` încărcat de admin):
   - `SUPABASE_ADMIN_URL` (opțional dacă e același ca `SUPABASE_URL`)
   - `SUPABASE_SERVICE_ROLE_KEY` (obligatoriu pentru publish update în admin)
2. Verifică schema `app_updates` în Supabase să includă câmpurile standard.
3. Când publici un update, furnizează de preferat `sha256` (64 hex) pentru verificare integritate.
4. Rulează fluxul de build/release standardizat:
   - `build_apps.bat`
   - `prepare_release_1.0.0.bat`
   - `1.0.0\compile_installers.bat`

## Observații de compatibilitate

- Modificările sunt conservative și păstrează comportamentul principal (auto-update) dar elimină dublurile de arhitectură.
- Nu am făcut ștergeri de fișiere istorice; doar am consolidat fluxul activ și am documentat clar standardul nou.

