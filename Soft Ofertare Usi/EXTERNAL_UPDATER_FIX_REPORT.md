# External updater integration fix

## Diagnosis

1. **What name does the app look for?**  
   The code in `ofertare/updater.py` always referenced **`updater.py`** next to `ofertare.exe` (never `update.py`). A message mentioning `update.py` was likely a typo or misread path; the canonical script name is **`updater.py`**.

2. **Root cause of failure from `dist\`:**  
   PyInstaller only places **`ofertare.exe`** (and `admin.exe`) in `dist\`. It does **not** copy **`updater.py`**, **`version.json`**, or an **`updater`** helper next to the exe. The frozen app resolves the install directory to `dirname(ofertare.exe)`, so the external updater files were **missing** when testing only from `dist\`.

3. **Correct project file for the external updater process:**  
   **`updater.py`** at the repository root (same folder as `main.py`). It is **not** `ofertare/updater.py` (that module handles Supabase checks and launching the external helper).

## Standard naming (single convention)

| Role | File |
|------|------|
| External process (zip apply + restart) | Root **`updater.py`** → built to **`updater.exe`** |
| In-app update logic (download, SHA256, launch helper) | **`ofertare/updater.py`** (Python package) |

There is **no** supported name `update.py`.

## Fix applied

1. **`ofertare/updater.py`** (`_launch_zip_updater`):
   - Prefer **`updater.exe`** next to `ofertare.exe` if present (no Python install required).
   - Else use **`updater.py`** with `py -3` / current interpreter (development or fallback).
   - Clear error if neither file exists.

2. **`updater.spec`** (new): PyInstaller one-file build producing **`dist\updater.exe`** from root **`updater.py`**.

3. **`scripts/build_release.bat`**:
   - Runs `pyinstaller updater.spec` after `ofertare` and `admin`.
   - Copies **`updater.py`** and **`version.json`** into **`dist\`** so testing from `dist\` matches installed layout.
   - Stages **`updater.exe`**, **`updater.py`**, and **`version.json`** into **`v1.0.0 stabila\ofertare_app\`**.

4. **Inno Setup** (`setup_ofertare.iss`, `setup_ofertare_update.iss`): Added **`Source: ..\ofertare_app\updater.exe`** alongside existing `updater.py` and `version.json`.

5. **`compile_installers.bat`**: Fails early if **`updater.exe`** is missing from `ofertare_app`.

## Where files end up

| Location | Contents |
|----------|----------|
| `dist\` (after `build_release.bat`) | `ofertare.exe`, `admin.exe`, `updater.exe`, `updater.py`, `version.json` |
| `v1.0.0 stabila\ofertare_app\` | Same set (staged for installers / manual copy) |
| Installed app directory | Same files after running the Inno-built setup |

## Decision: `updater.exe` vs `updater.py` only

- **Primary for frozen installs:** **`updater.exe`** — robust when Python is not on `PATH`.
- **Fallback:** **`updater.py`** — kept for compatibility and dev; still shipped next to the main exe.

## Files modified

- `ofertare/updater.py` — launch logic (`_launch_zip_updater`).
- `updater.spec` — new.
- `scripts/build_release.bat` — build `updater.exe`, copy runtime files to `dist`, stage `updater.exe`.
- `release/installers/setup_ofertare.iss`, `setup_ofertare_update.iss` — include `updater.exe`.
- `v1.0.0 stabila/installers/…` — same Inno changes (mirrored).
- `release/installers/compile_installers.bat`, `v1.0.0 stabila/installers/compile_installers.bat` — check for `updater.exe`.
- `docs/RELEASE_README.md` — documentation.

## Rebuild command

```bat
cd /d "<project>\Soft Ofertare Usi\Soft Ofertare Usi"
scripts\build_release.bat
```

Then test auto-update from **`dist\`** with `ofertare.exe`, `updater.exe`, `updater.py`, and `version.json` all present in that folder.
