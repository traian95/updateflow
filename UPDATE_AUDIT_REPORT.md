# UPDATE AUDIT REPORT

## 1. OVERVIEW GENERAL

- **Tip aplicație:** aplicație de ofertare produse (uși, tocuri, mânere, parchet) + aplicație separată de administrare.
- **Entry point principal (user app):** `Soft Ofertare Usi/main.py`.
- **Entry point aplicație admin:** `Soft Ofertare Usi/admin_app.py`.
- **Tehnologie interfață:** Python + `customtkinter` (desktop GUI).
- **Tip aplicație:** desktop app (Windows), nu web app.
- **Pornire normală:**
  - în dezvoltare: `python main.py` și `python admin_app.py`;
  - în producție: executabile generate cu PyInstaller (`Naturen Flow ...exe`, `Naturen Admin ...exe`);
  - distribuție prin instalatoare Inno Setup (`setup_flow.iss`, `setup_admin.iss`, `setup_flow_update.iss`).

---

## 2. IDENTIFICAREA SISTEMULUI DE UPDATE EXISTENT

### Verdict rapid
- **Există mecanism de update?** **DA**, există mai multe componente de update, unele active, unele parțial/istoric.

### Fișiere implicate direct
- `Soft Ofertare Usi/main.py`
- `Soft Ofertare Usi/ofertare/ui.py`
- `Soft Ofertare Usi/ofertare/updater.py`
- `Soft Ofertare Usi/updater.py` (updater extern executat separat)
- `Soft Ofertare Usi/ofertare/admin_ui.py` (publicare update din admin)
- `Soft Ofertare Usi/build_update.py` (creează pachet ZIP de update)

### Funcții/module cheie
- În `main.py`:
  - `_latest_update_for_app()`
  - `_download_update_archive()`
  - `_launch_external_updater()`
  - `check_and_start_auto_update()`
- În `ofertare/ui.py`:
  - `check_app_version()`
  - `_check_app_version_worker()`
  - `_start_auto_update_install()`
  - `_auto_update_worker()`
- În `ofertare/updater.py`:
  - `check_for_updates()`
  - `install_zip_update()`
  - `upload_new_version()` (folosit de Admin)
- În `updater.py` (root):
  - `extract_update()`
  - `restart_application()`

### Flux actual de update (pas cu pas)
1. La pornire, aplicația verifică versiunea remote (din Supabase) față de versiunea locală.
2. Dacă există versiune mai nouă, ia URL de download.
3. Descarcă `update.zip` local.
4. Lansează proces extern `updater.py` cu argumente (`--zip-path`, `--target-dir`, `--restart-cmd`).
5. Updater-ul extern așteaptă puțin, extrage ZIP peste folderul aplicației (suprascriere), șterge ZIP, repornește aplicația.

### Cod incomplet / parțial / inconsistent
- Există **două căi de logică update**:
  - logică în `main.py` (auto-update la startup),
  - logică în `ofertare/ui.py` + `ofertare/updater.py` (verificare + auto-install din UI).
- Există și logică alternativă mai veche în `ofertare/updater.py` (`check_and_install_update()` cu `ofertare_new.exe` + batch swap), care pare **nefolosită în fluxul principal actual**.
- UI admin etichetează câmpul ca “Google Drive”, dar validarea cere URL `https://github.com/...` (inconsistență text vs implementare).

---

## 3. SURSA DE VERIFICARE UPDATE

- **Sursa principală activă:** **Supabase** (tabela `app_updates`, plus fallback pe tabele de setări).
- **GitHub:** folosit ca sursă de URL asset pentru download (link de release/asset), nu integrare API GitHub Releases.
- **Fișier local / API custom:** nu apare ca mecanism principal de update.

### URL / variabile relevante
- `SUPABASE_URL` și `SUPABASE_KEY` în `Soft Ofertare Usi/ofertare/db_cloud.py`.
- `.env` existent în `Soft Ofertare Usi/.env` cu aceleași variabile.
- Cheie service role în `Soft Ofertare Usi/ofertare/updater.py`:
  - `SUPABASE_ADMIN_URL`
  - `SUPABASE_ADMIN_SERVICE_ROLE_KEY`

### Tabele Supabase implicate
- `app_updates` (principal)
- fallback pentru citire versiune:
  - `app_config`
  - `settings`
  - `app_settings`
  - `metadata`

### Coloane observate pentru update
- În `app_updates`:
  - `version`
  - `download_url` sau `url_download`
  - `created_at`
  - opțional `app_name` sau `slug` (filtrare pe `naturen_flow`)
- În fallback settings:
  - `latest_version`
  - `download_url` / `update_url` / `installer_url`
  - eventual `updated_at` / `created_at`

### Chei hardcodate (securitate)
- Da, există chei hardcodate în:
  - `ofertare/db_cloud.py` (anon key + URL)
  - `ofertare/updater.py` (service role key + URL)
- Nu sunt redate aici valorile complete (sensibile).

---

## 4. VERSIONARE

- **Unde e stocată versiunea locală:**
  - `main.py`: `VERSION = "1.0.1"`
  - `ofertare/ui.py`: `self.APP_VERSION = "1.0.1"`
  - `ofertare/updater.py`: `VERSION_LOCALA = '0.0.1'` (pare depășită față de celelalte)
- **Format versiune:** semantic simplu `x.y.z` (ex: `1.0.1`).
- **Cum se citește versiunea locală:** constantă hardcoded în cod (nu din `version.json`).
- **Cum se compară:** funcții de normalizare/comparare:
  - `main.py`: `_normalize_version()` + `_is_remote_newer()`
  - `ofertare/updater.py`: `_is_remote_newer()` (cu `packaging.version` fallback)
- **Fișiere de tip `version.json`, `__version__`, constants dedicate:** nu apar în fluxul activ.

---

## 5. DESCĂRCARE UPDATE

- **Există funcție de download?** **DA**
- **Fișiere:**
  - `main.py` -> `_download_update_archive()`
  - `ofertare/updater.py` -> `_download_update_archive()` și `_download_new_exe()`
- **Librării folosite:** `requests` (stream download).
- **Loc salvare fișiere descărcate:**
  - în directorul aplicației (`app_dir/update.zip`)
  - variantă veche: `ofertare_new.exe`.
- **Progress bar / feedback UI:**
  - în user app nu există progress numeric al download-ului;
  - există mesaje UI și status simplu (success/error);
  - în Admin există progress bar pentru publicare metadata (nu pentru download client).
- **Tip fișier descărcat:**
  - flux actual: `.zip` (`update.zip`);
  - flux alternativ vechi: `.exe`.

---

## 6. INSTALARE UPDATE

- **Există updater separat?** **DA**
- **Fișier updater separat:** `Soft Ofertare Usi/updater.py`.
- **Cum e lansat:** prin `subprocess.Popen(...)` din `main.py` sau `ofertare/updater.py`.
- **Argumente primite:**
  - `--zip-path`
  - `--target-dir`
  - `--restart-cmd`
- **Cum se închide aplicația principală:**
  - `main.py` folosește `os._exit(0)` după lansarea updater-ului;
  - din UI, aplicația se închide după confirmare rezultat update.
- **Cum se suprascriu fișierele:**
  - updater-ul face `zipfile.extractall(target_dir)` (suprascriere directă).
- **Foldere afectate:**
  - directorul de instalare al aplicației (target dir complet).
- **Backup / rollback:** nu există logică explicită.
- **Ștergere versiune veche:** nu există cleanup explicit pe fișiere vechi; doar suprascriere + ștergere `update.zip`.

---

## 7. BUILD ȘI DISTRIBUȚIE

- **Build aplicație:**
  - script: `Soft Ofertare Usi/build_apps.bat`
  - tool: `PyInstaller` cu fișiere `.spec`.
- **Fișiere de build relevante:**
  - `Naturen Flow 1.0.0.spec`
  - `Naturen Admin 1.0.0.spec`
  - `Soft_Ofertare.spec` (variantă mai veche/alternativă)
  - `build_update.py` (creează arhivă update ZIP)
  - `prepare_release_1.0.0.bat`
  - `1.0.0/compile_installers.bat`
  - `1.0.0/setup_flow.iss`, `1.0.0/setup_admin.iss`, `1.0.0/setup_flow_update.iss`
- **Generare executabil:** PyInstaller pornește din `main.py` și `admin_app.py`.
- **Pachet update pentru release:** DA, `naturen_flow_update.zip` din `build_update.py`.
- **Integrare GitHub Releases:** nu există integrare automată (API/CLI); se lucrează cu URL introdus manual.

---

## 8. CONFIGURAȚII ȘI SECRETE

### Fișiere de configurare
- `Soft Ofertare Usi/.env`
- `Soft Ofertare Usi/ofertare/config.py`
- (în runtime) `app_settings.json` în folder aplicație (gestionat de `config.py`)

### Variabile relevante pentru update
- `SUPABASE_URL`
- `SUPABASE_KEY`
- chei admin/service role (hardcodate în `ofertare/updater.py`)

### Ce lipsește / ce poate bloca update-ul
- Dacă tabelele Supabase pentru update (`app_updates` etc.) nu există sau nu au coloanele așteptate, update-ul nu pornește.
- Scriptul de schemă `utils/root_archive/supabase_full_schema.sql` nu include tabelele de update observate în cod (pot lipsi în DB).

### Probleme de securitate evidente
- Chei Supabase hardcodate în codul sursă (inclusiv service role) -> risc major.
- URL-uri și identificatori sensibili în cod.
- Lipsă verificare integritate update (hash/signature) înainte de instalare.

---

## 9. APLICAȚIA DE ADMIN

- **Există cod pentru push/update management în admin?** **DA**
- **Fișiere:**
  - `ofertare/admin_ui.py`
  - `ofertare/updater.py` (`upload_new_version`)

### Ce poate face acum
- **Publicare versiune:** DA (`version` + `download_url` în Supabase).
- **Setare mandatory:** NU (nu există câmp/logică explicită).
- **Setare URL download:** DA.
- **Release notes:** NU (nu apare câmp sau salvare).
- **Activare/dezactivare update:** NU (nu există toggle clar).

### Cum comunică cu Supabase
- Admin-ul apelează `upload_new_version(...)` -> folosește client Supabase admin (`service_role`) și face insert în `app_updates`.
- Există cleanup automat pentru revizii vechi (`_cleanup_old_revisions`, keep latest 3).

---

## 10. STRUCTURA DE FIȘIERE RELEVANTĂ

- `Soft Ofertare Usi/main.py` - entrypoint principal + verificare update la startup.
- `Soft Ofertare Usi/ofertare/ui.py` - UI principal; verifică versiune și declanșează auto-update.
- `Soft Ofertare Usi/ofertare/updater.py` - logică principală de verificare/update + upload versiune din admin.
- `Soft Ofertare Usi/updater.py` - updater extern (aplică ZIP și restart).
- `Soft Ofertare Usi/ofertare/admin_ui.py` - ecran “Update Software” pentru publicare versiune.
- `Soft Ofertare Usi/ofertare/db_cloud.py` - config Supabase (URL/key), folosit indirect de update.
- `Soft Ofertare Usi/.env` - configurare variabile Supabase.
- `Soft Ofertare Usi/build_update.py` - creează arhiva `naturen_flow_update.zip`.
- `Soft Ofertare Usi/build_apps.bat` - build executabile cu PyInstaller.
- `Soft Ofertare Usi/prepare_release_1.0.0.bat` - pregătește bundle de release în folderul `1.0.0`.
- `Soft Ofertare Usi/1.0.0/setup_flow_update.iss` - installer update (Inno Setup).
- `Soft Ofertare Usi/1.0.0/compile_installers.bat` - compilare setup-uri Inno.
- `Soft Ofertare Usi/Naturen Flow 1.0.0.spec` - spec PyInstaller pentru user app.
- `Soft Ofertare Usi/Naturen Admin 1.0.0.spec` - spec PyInstaller pentru admin app.

---

## 11. PROBLEME ȘI RISCURI IDENTIFICATE

### Ce lipsește pentru update robust
- Lipsă semnătură/verificare hash la pachetul update.
- Lipsă rollback automat în caz de update corupt.
- Lipsă backup fișiere înainte de suprascriere.

### Fragilități / bug-uri probabile
- Versiuni locale declarate în mai multe locuri (`main.py`, `ui.py`, `ofertare/updater.py`) -> risc de nealiniere.
- Flux dublu de update (startup + UI) -> complexitate și comportament greu de prevăzut.
- `extractall` suprascrie direct fără validare structură arhivă.

### Permisiuni / instalare
- Instalatoarele cer admin (`PrivilegesRequired=admin`), iar update-ul poate eșua dacă aplicația rulează fără drepturile necesare în folder protejat.
- Dacă `updater.py` nu există în folderul țintă, update-ul eșuează imediat.

### Securitate
- Chei sensibile hardcodate în repo.
- Service role key în codul client (risc foarte mare).
- Fără verificare criptografică a update-ului.

### Logică update
- UI admin are text “Google Drive”, dar validarea impune GitHub URL (inconsistență UX).
- Script SQL de schemă disponibil nu include tabelele de update cerute de cod -> posibil medii nealiniate.

---

## 12. CE TREBUIE SĂ ÎMI TRIMITĂ CHATGPT

## REZUMAT PENTRU CHATGPT

- **Stack aplicație:** Python desktop (`customtkinter`), `requests`, `supabase-py`, build cu PyInstaller, instalare cu Inno Setup.
- **Fișiere-cheie update:** `main.py`, `ofertare/ui.py`, `ofertare/updater.py`, `updater.py`, `ofertare/admin_ui.py`, `build_update.py`.
- **Flux actual:** client verifică Supabase (`app_updates`) -> dacă versiunea remote e mai nouă descarcă `update.zip` -> pornește updater extern -> extrage peste aplicație -> restart.
- **Ce funcționează deja:** verificare versiune, download, lansare updater extern, restart, publicare versiune din Admin către Supabase.
- **Ce lipsește:** verificare integritate update, rollback/backup, unificare clară a unei singure căi de update, management avansat (mandatory/release notes/toggle).
- **Decizia principală necesară mai departe:** alegerea arhitecturii finale de update (single-flow), plus model de securizare (fără chei hardcodate și cu verificare semnătură/hash).

---

## 13. ANEXĂ TEHNICĂ

### Exemplu A - verificare update la startup (`main.py`)
```python
def check_and_start_auto_update() -> bool:
    if not SUPABASE_URL.strip() or not SUPABASE_KEY.strip():
        return False
    latest = _latest_update_for_app()
    if not latest:
        return False
    version_cloud = str(latest.get("version") or "").strip()
    download_url = str(latest.get("url_download") or latest.get("download_url") or "").strip()
    if not _is_remote_newer(VERSION, version_cloud):
        return False
    update_zip_path = _app_base_dir() / UPDATE_ARCHIVE_NAME
    _download_update_archive(download_url, update_zip_path)
    _launch_external_updater(update_zip_path, _app_base_dir())
    return True
```
Sursă: `Soft Ofertare Usi/main.py`

### Exemplu B - verificare în UI + auto-install (`ofertare/ui.py`)
```python
def _check_app_version_worker(self) -> None:
    result = check_for_updates(self.APP_VERSION)
    self.after(0, lambda: self._on_check_app_version_done(result))

def _auto_update_worker(self, download_url: str) -> None:
    result = install_zip_update(download_url)
    self.after(0, lambda: self._on_auto_update_done(result))
```
Sursă: `Soft Ofertare Usi/ofertare/ui.py`

### Exemplu C - instalare ZIP și lansare updater extern (`ofertare/updater.py`)
```python
def install_zip_update(download_url: str) -> dict[str, Any]:
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    zip_path = app_dir / "update.zip"
    _download_update_archive(download_url, zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"Arhiva update lipseste: {zip_path}")
    _launch_zip_updater(zip_path, app_dir)
    return {"ok": True, "zip_path": str(zip_path)}
```
Sursă: `Soft Ofertare Usi/ofertare/updater.py`

### Exemplu D - updater extern care aplică arhiva (`updater.py`)
```python
def main() -> None:
    args = parse_args()
    zip_path = Path(args.zip_path).resolve()
    target_dir = Path(args.target_dir).resolve()
    restart_cmd = [token for token in str(args.restart_cmd).split("|||") if token]
    time.sleep(3)
    extract_update(zip_path, target_dir)
    try:
        os.remove(zip_path)
    except Exception:
        pass
    restart_application(restart_cmd, target_dir)
```
Sursă: `Soft Ofertare Usi/updater.py`

### Exemplu E - publicare update din admin (`ofertare/updater.py`)
```python
def upload_new_version(version_name: str, github_download_url: str) -> dict[str, Any]:
    supabase = _get_supabase_admin_client()
    normalized_version = str(version_name or "").strip()
    direct_download_url = str(github_download_url or "").strip()
    base_payload = {"version": normalized_version, "created_at": datetime.now(timezone.utc).isoformat()}
    insert_payload = {**base_payload, "download_url": direct_download_url, "url_download": direct_download_url, "app_name": "naturen_flow"}
    inserted = supabase.table(TABLE_UPDATES).insert(insert_payload).execute().data or []
    _cleanup_old_revisions(supabase, keep_latest=3)
    return {"ok": True, "version": normalized_version, "download_url": direct_download_url, "row": inserted[:1]}
```
Sursă: `Soft Ofertare Usi/ofertare/updater.py`

---

## Secțiune suplimentară: TODO/FIXME / comentarii update

- Căutarea globală pentru `TODO` / `FIXME` nu a returnat rezultate.
- Există comentarii utile despre update în cod (de exemplu descrieri de fallback, compatibilitate Supabase, comportament updater), dar nu sunt marcate ca TODO/FIXME.

---

## Secțiune suplimentară: fișiere suspecte / abandonate / variante multiple

- `Soft Ofertare Usi/utils/root_archive/` conține multe fișiere de build/release istorice; par arhivă, nu flux activ.
- `Soft Ofertare Usi/Soft_Ofertare.spec` pare o variantă mai veche față de specs 1.0.0 curente.
- În `ofertare/updater.py` există logică alternativă pentru update pe `.exe` (`check_and_install_update`) care nu pare calea principală activă.
- Implementarea curentă activă pare combinația:
  - `main.py` + `ofertare/ui.py` pentru trigger update,
  - `ofertare/updater.py` pentru verificare/download,
  - `updater.py` pentru aplicare ZIP.

