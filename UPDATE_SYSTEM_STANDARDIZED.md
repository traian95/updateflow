# UPDATE SYSTEM STANDARDIZED

## Flux final standardizat

1. Client app citește versiunea locală din `version.json`.
2. Client app citește update-ul activ doar din tabela Supabase `app_updates`.
3. Dacă `version` remote > local:
   - descarcă ZIP-ul din `download_url`;
   - verifică SHA256 (dacă `sha256` este prezent);
   - lansează updater-ul extern (`updater.py`);
   - închide aplicația principală.
4. Updater-ul extern:
   - așteaptă închiderea aplicației;
   - extrage update-ul într-un folder temporar;
   - copiază fișierele peste aplicație (fără `data/` și `config/`);
   - actualizează `version.json`;
   - curăță temporarele și repornește aplicația.

## Fișiere implicate

- `Soft Ofertare Usi/ofertare/updater.py`
  - sursa unică pentru:
    - `get_local_version()`
    - citire metadata update din `app_updates`
    - verificare versiune
    - download + SHA256
    - publicare update din admin
- `Soft Ofertare Usi/main.py`
  - trigger startup pentru fluxul de update unificat.
- `Soft Ofertare Usi/ofertare/ui.py`
  - folosește aceeași logică centrală (fără versiuni hardcodate).
- `Soft Ofertare Usi/updater.py`
  - updater extern unic activ.
- `Soft Ofertare Usi/version.json`
  - sursa unică a versiunii locale.

## Structura metadata în `app_updates`

Câmpurile standard consumate/publicate:

- `version` (string, ex. `1.0.2`)
- `download_url` (string URL direct la ZIP)
- `sha256` (string, 64 hex, opțional dar recomandat)
- `mandatory` (bool/int)
- `notes` (text release notes)
- `is_active` (bool/int)
- opțional pentru filtrare app: `app_name` / `slug` (`naturen_flow`)

## Publicare update din Admin

În Admin -> ecran `Update Software`:

- introduci `version`;
- introduci `download_url`;
- opțional `sha256`;
- opțional `notes`;
- bifezi `mandatory` dacă este cazul;
- publici update.

La publicare cu `is_active=1`, update-urile active anterioare sunt dezactivate automat.

## Ce face fiecare componentă

- **Admin app:** publică metadata update în Supabase și listează update-urile existente.
- **Client app:** verifică periodic/startup dacă există update activ mai nou și pornește instalarea.
- **Updater extern:** aplică efectiv pachetul ZIP și repornește aplicația.

## Build și release (standardizat)

- `build_update.py` include obligatoriu în arhiva de update:
  - `main.py`
  - `updater.py`
  - `requirements.txt`
  - `version.json`
  - folderul `ofertare`
  - folderul `assets`
- `prepare_release_1.0.0.bat` copiază și `updater.py`, `version.json` în bundle.
- `1.0.0/setup_flow.iss` și `1.0.0/setup_flow_update.iss` includ explicit `updater.py` + `version.json`.

## Date necesare în Supabase

Minim necesar pentru funcționare robustă:

- tabela `app_updates` cu câmpuri:
  - `id` (PK)
  - `version` text
  - `download_url` text
  - `sha256` text nullable
  - `mandatory` bool/int default false
  - `notes` text nullable
  - `is_active` bool/int default true
  - `app_name` text (sau `slug`)
  - `created_at` timestamp/text

## Securitate minimă aplicată

- cheia `service_role` nu mai este hardcodata în client;
- pentru operații admin se citește din `SUPABASE_SERVICE_ROLE_KEY` (env);
- clientul continuă pe cheia de citire (`SUPABASE_KEY`).

