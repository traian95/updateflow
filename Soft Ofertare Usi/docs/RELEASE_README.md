# Release v1.0.0 (stable) — Windows distribution

This folder contains staged binaries, installers, and scripts for the **Naturen Flow** offer application and the separate **Naturen Admin** application.

**Canonical sources:** Inno scripts and this file are copied from the project under `Soft Ofertare Usi\release\installers\` and `Soft Ofertare Usi\docs\` when you run `scripts\build_release.bat`. See `RELEASE_REBUILD_REPORT.md` in the project root for the latest full rebuild notes.

## Application entry points (source code)

| Role | Entry script | Packaged executable |
|------|----------------|---------------------|
| Main offer app | `Soft Ofertare Usi/main.py` | `ofertare.exe` |
| Admin app | `Soft Ofertare Usi/admin_app.py` | `admin.exe` |

**Decision:** The repository uses two top-level scripts on purpose. There is no single entry that switches between modes; admin is always launched via `admin_app.py` (or `admin.exe` after packaging). The main app performs automatic update checks via `ofertare/updater.py` before starting the UI.

## Folder layout

| Path | Contents |
|------|----------|
| `ofertare_app/` | **PyInstaller onedir:** `ofertare.exe`, `_internal\` (Python DLL + runtime), `updater.exe`, `updater.py`, `version.json`, `assets\` — full tree must be installed (see Inno recursive `[Files]`). |
| `admin_app/` | **Onedir:** `admin.exe`, `_internal\`, `assets\` — full tree required in the installer. |
| `installers/` | Inno Setup 6 scripts (`setup_ofertare.iss`, `setup_ofertare_update.iss`, `setup_admin.iss`) and `compile_installers.bat`. |
| `assets/` | Optional reference copy of `application_icon.ico` for documentation; primary assets live under each `*_app/` folder. |
| `scripts/` | Short notes for automation (`README_SCRIPTS.txt`). |

## Update system (do not remove)

The main app expects these files **next to `ofertare.exe`** after installation:

- **`updater.exe`** — standalone external updater (built with `updater.spec`); **preferred** when frozen (no Python required on the PC).
- **`updater.py`** — fallback if `updater.exe` is missing (frozen app uses `py -3` to run it).
- **`version.json`** — local version metadata read by `ofertare/updater.py` and updated after a successful zip update.

Downloads go to `%LOCALAPPDATA%\NaturenFlow\updates\` (not under the install folder). Inno scripts install `updater.exe`, `updater.py`, and `version.json`. For testing without Inno, run the main app from **`dist\ofertare\ofertare.exe`** (folder includes `_internal\`, `updater.exe`, etc.). `scripts\build_release.bat` stages that full folder into `ofertare_app\`.

**AppId note:** `setup_ofertare.iss` and `setup_ofertare_update.iss` share the same `AppId` so Windows treats them as the same product for upgrades.

**Default install path (main app):** `%LOCALAPPDATA%\NaturenFlow` (`{localappdata}\NaturenFlow` in Inno Setup) — user-writable, suitable for the zip-based updater.

**Admin installer** (`setup_admin.iss`): separate `AppId`; default is `%ProgramFiles%\NaturenAdmin` (`{autopf}\NaturenAdmin`) — machine-wide, separate from the main app (see header comments in `setup_admin.iss` and `INSTALL_PATH_CHANGE_REPORT.md`).

## Build steps (developer machine)

1. Open a terminal in `Soft Ofertare Usi\Soft Ofertare Usi\` (the Python project root).
2. Run:

   `scripts\build_release.bat`

   This will:

   - Sync assets (`sync_assets_for_build.py`).
   - Clean `build/` and `dist/`.
   - Run PyInstaller with `ofertare.spec` and `admin.spec`.
   - Copy outputs into `v1.0.0 stabila` (`ofertare_app/`, `admin_app/`, `assets/`, `installers/`, `docs/`).

3. Install **Inno Setup 6**, then run:

   `v1.0.0 stabila\installers\compile_installers.bat`

   Generated setup programs are written to `v1.0.0 stabila\installers\`.

## Requirements

- Python 3 with project dependencies installed (see `requirements.txt` in the project root).
- PyInstaller (`pip install pyinstaller`).
- Inno Setup 6 (`ISCC.exe` on PATH or default install path).

## Legacy build names

Older scripts may still reference `Naturen Flow 1.0.0.spec` / `Naturen Admin 1.0.0.spec` and produce differently named executables. The **stable release pipeline** described here uses `ofertare.spec` / `admin.spec` and the outputs `ofertare.exe` / `admin.exe` only.

**Historical folder:** An older staging layout may exist as `Soft Ofertare Usi\1.0.0\` (legacy). The **current** stable bundle is `v1.0.0 stabila\` at the workspace root.
