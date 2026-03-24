# Inno installer runtime fix (Python DLL / full onedir copy)

## Exact cause

1. **PyInstaller was building one-file (`onefile`) bundles** — a single large `ofertare.exe` / `admin.exe` in `dist\` with the Python runtime embedded in the archive.

2. **Inno Setup scripts only installed a subset of files** — explicitly `ofertare.exe`, `updater.exe`, `updater.py`, `version.json`, and `assets\*`. For **onefile**, that is *usually* enough because `python312.dll` is **inside** the `.exe` archive, not as a separate file on disk.

3. **Observed failure after install:** `Failed to load Python DLL ... python312.dll` — this typically happens when:
   - The bootloader expects to load `python312.dll` from the **onedir** layout (`_internal\`), but only a **partial** install exists; or
   - The installed **onefile** executable is **truncated**, **blocked**, or **inconsistent**; or
   - Antivirus / compression edge cases affect the single large EXE.

4. **Root fix requested:** Treat the build like **onedir** — ship **`ofertare.exe` + `_internal\`** (full PyInstaller output) and install **recursively** so the installer is a **faithful copy** of `dist\ofertare\` and `dist\admin\`, matching how a working manual copy from `dist` behaves.

## What was missing in the old Inno `[Files]` (conceptually)

- The **`_internal\`** directory (contains `python312.dll`, dependent DLLs, extracted Python stdlib pieces, and bundled `assets` from PyInstaller).
- Any other files PyInstaller emits next to the main EXE in **onedir** mode.

The old `[Files]` list did **not** include `_internal\` because the build was **onefile** and there was no `_internal` folder to ship.

## What we changed (packaging only — no application logic)

### 1. PyInstaller specs → **onedir**

- **`ofertare.spec`**, **`admin.spec`**: switched to `EXE(..., exclude_binaries=True)` + **`COLLECT(..., name='ofertare'|'admin')`**.
- Output:
  - `dist\ofertare\ofertare.exe` + `dist\ofertare\_internal\...`
  - `dist\admin\admin.exe` + `dist\admin\_internal\...`
- **`updater.spec`**: remains **onefile** `dist\updater.exe` (small helper; copied next to the main app folder).

### 2. `scripts/build_release.bat`

- Stages **`dist\ofertare\*`** → `v1.0.0 stabila\ofertare_app\` (recursive).
- Stages **`dist\admin\*`** → `admin_app\` (recursive).
- Copies **`updater.py`**, **`version.json`**, **`updater.exe`** into **`dist\ofertare\`** before staging (so tests run from `dist\ofertare\` as one folder).
- Overlays project **`assets\`** onto `ofertare_app\assets` and `admin_app\assets` (icons / side-by-side paths).

### 3. Inno Setup `[Files]` — **full tree**

**Main app** (`setup_ofertare.iss`, `setup_ofertare_update.iss`):

```iss
Source: "..\ofertare_app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
```

**Admin** (`setup_admin.iss`):

```iss
Source: "..\admin_app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
```

This installs **everything** staged under `ofertare_app` / `admin_app`, including `_internal\`, `updater.exe`, `version.json`, `updater.py`, and `assets\`.

### 4. `compile_installers.bat`

- Fails fast if **`_internal`** is missing under `ofertare_app` or `admin_app` (wrong or incomplete build).

## How to verify

1. **Rebuild**

   ```bat
   cd /d "<project>\Soft Ofertare Usi\Soft Ofertare Usi"
   scripts\build_release.bat
   ```

2. **Manual test (no Inno)**  
   Run `dist\ofertare\ofertare.exe` — should start without the Python DLL error. Confirm `dist\ofertare\_internal\python312.dll` exists.

3. **Compile installers**

   ```bat
   cd /d "<workspace>\v1.0.0 stabila\installers"
   compile_installers.bat
   ```

4. **Install** the generated `Naturen_Flow_*_Setup.exe` on a clean VM or folder.

5. **After install**, check `{app}\_internal\python312.dll` exists next to `{app}\ofertare.exe`.

6. **Launch** from the Start Menu shortcut (WorkingDir `{app}`).

## Note on remote zip updates

If you publish **`update.zip`** from `build_update.py` or custom scripts, it must contain the **full onedir** layout (or at least all files that change), not only a single `ofertare.exe`, or updates may break. Adjust publishing separately if needed.
