# Update permission fix report

## What changed

- **File:** `ofertare/updater.py`
- **New helper:** `_user_download_dir_for_updates()` — returns a user-writable directory using `pathlib.Path` and `os.environ`:
  - **Primary:** `%LOCALAPPDATA%\NaturenFlow\updates\` (resolved with `.resolve()`).
  - **Fallback** (if `LOCALAPPDATA` is missing): `%TEMP%\NaturenFlow\updates\`.
- **`install_zip_update()`** — no longer writes `update.zip` under `_app_dir()` (install folder, e.g. `Program Files\NaturenFlow`). It now:
  1. Creates the download directory with `mkdir(parents=True, exist_ok=True)`.
  2. Downloads to `download_dir / update.zip` (same archive name as before).
  3. Logs the final path via `logger.info` and `_log_update` (`[download] writing…` / `[download] completed…`).
  4. Keeps the same SHA256 check on the downloaded file and the same `_launch_zip_updater(zip_path, app_dir, …)` call so the external `updater.py` receives the **new absolute path** to the zip via `--zip-path`.

No other product logic was changed.

## New download location

| Item | Path |
|------|------|
| Directory | `%LOCALAPPDATA%\NaturenFlow\updates\` (or `%TEMP%\NaturenFlow\updates\` if `LOCALAPPDATA` is unset) |
| File | `update.zip` (name unchanged) |

Example (typical Windows user):

`C:\Users\<User>\AppData\Local\NaturenFlow\updates\update.zip`

## Remaining risk: writing under Program Files

Downloading to a writable folder fixes **`[Errno 13] Permission denied`** when **creating/writing** `update.zip` in the install directory.

The **external** updater (`updater.py` in the project root, launched after the main app exits) still applies the zip by copying files into `--target-dir`, which is the application directory (`_app_dir()`).

**Default installs (current Inno scripts):** `setup_ofertare.iss` / `setup_ofertare_update.iss` use **`{localappdata}\NaturenFlow`**, so `_app_dir()` is usually under **`%LOCALAPPDATA%\NaturenFlow`** and updates can replace files without admin. **Older installs** under `%ProgramFiles%\NaturenFlow` can still hit permission errors until reinstalled or moved.

### Will the updater have problems?

**Yes, it can** — mainly when the install directory is not user-writable (e.g. legacy `Program Files` installs). Standard users do not have permission to create/overwrite files under `Program Files`. The failure would typically occur in:

- **File:** `updater.py` (project root, not `ofertare/updater.py`)
- **Function:** `_copy_extracted_content()` (calls `shutil.copy2` / `mkdir` under `target_dir`), invoked from **`main()`** after `time.sleep(3)`.

If copy fails, the process exits with code `1` (errors are swallowed at the bottom of `main`); the app may not update until the user runs with sufficient rights or the installer uses another strategy.

### Where to address elevation / permissions (if needed later)

- **Same file:** `updater.py`
- **Relevant areas:** `main()` orchestration; `_copy_extracted_content()` (actual writes to `target_dir`); optionally `restart_application()` if the restarted app must run elevated (usually not desired).

Typical mitigations (out of scope for this fix):

- Ship a small elevated helper or manifest so only the updater elevates.
- Install the app to a user-writable location (e.g. under `%LOCALAPPDATA%`) so updates do not require admin.
- Use an MSI/EXE patcher that runs elevated via UAC prompt.

This report documents behavior only; no elevation logic was added here.
