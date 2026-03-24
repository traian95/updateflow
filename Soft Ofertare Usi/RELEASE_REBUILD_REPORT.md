# Release rebuild report

**Last full rebuild:** 2026-03-24 (PyInstaller + staged `v1.0.0 stabila` + synced Inno scripts from `release\installers\`; old `Naturen_Flow_*` / `Naturen_Admin_*` Setup EXEs removed from `installers\` before sync — run `compile_installers.bat` locally to produce new installer EXEs).

## What was regenerated

| Artifact | Spec / source | Output |
|----------|-----------------|--------|
| Main offer app | `ofertare.spec` → `main.py` | `dist\ofertare.exe` |
| Admin app | `admin.spec` → `admin_app.py` | `dist\admin.exe` |

- **PyInstaller** `build/` and `dist/` were wiped before each build (see `scripts\build_release.bat`).
- **Staged bundles** under `v1.0.0 stabila\ofertare_app\` and `v1.0.0 stabila\admin_app\` were **fully replaced** with fresh copies (exe, assets, and for the main app: `updater.py`, `version.json` from project root).

## Code included in this build

- Latest `ofertare/updater.py` behavior: `update.zip` downloads to `%LOCALAPPDATA%\NaturenFlow\updates\` (not next to the exe).
- `version.json` and root `updater.py` staged next to `ofertare.exe` for the existing zip-update flow.

## Files replaced in the release folder

| Location | Contents |
|----------|----------|
| `v1.0.0 stabila\ofertare_app\` | `ofertare.exe`, `updater.py`, `version.json`, full `assets\` tree |
| `v1.0.0 stabila\admin_app\` | `admin.exe`, full `assets\` tree |
| `v1.0.0 stabila\assets\` | `application_icon.ico` (reference copy) |
| `v1.0.0 stabila\installers\` | Synced from project `release\installers\` (`*.iss`, `compile_installers.bat`); **previous** `Naturen_Flow_*_Setup.exe`, `Naturen_Flow_*_Update.exe`, `Naturen_Admin_*_Setup.exe` in that folder were **deleted** so old installers are not left as the “current” build (re-run compile to produce new Setup EXEs). |
| `v1.0.0 stabila\docs\` | `RELEASE_README.md` copied from project `docs\` |

## Inno Setup scripts (canonical copy in repo)

Edit these in the project; `build_release.bat` copies them into the release tree:

- `Soft Ofertare Usi\Soft Ofertare Usi\release\installers\setup_ofertare.iss` — main app; default install `{localappdata}\NaturenFlow`
- `Soft Ofertare Usi\Soft Ofertare Usi\release\installers\setup_ofertare_update.iss` — same AppId, full replacement
- `Soft Ofertare Usi\Soft Ofertare Usi\release\installers\setup_admin.iss` — admin; default `{autopf}\NaturenAdmin`
- `Soft Ofertare Usi\Soft Ofertare Usi\release\installers\compile_installers.bat` — runs ISCC on all three

Mirrored under: `v1.0.0 stabila\installers\`

## Where to find the final EXE files (staged)

| App | Path |
|-----|------|
| Main | `c:\Users\Selena\Desktop\Soft Ofertare Usi\v1.0.0 stabila\ofertare_app\ofertare.exe` |
| Admin | `c:\Users\Selena\Desktop\Soft Ofertare Usi\v1.0.0 stabila\admin_app\admin.exe` |

Also in the project after build: `Soft Ofertare Usi\Soft Ofertare Usi\dist\ofertare.exe` and `dist\admin.exe`.

## Where assets live

- Main: `v1.0.0 stabila\ofertare_app\assets\` (and bundled inside `ofertare.exe` via PyInstaller).
- Admin: `v1.0.0 stabila\admin_app\assets\`
- Reference icon: `v1.0.0 stabila\assets\application_icon.ico`

## What you run for a full rebuild

1. **Rebuild binaries + stage release (required):**

   ```bat
   cd /d "c:\Users\Selena\Desktop\Soft Ofertare Usi\Soft Ofertare Usi"
   scripts\build_release.bat
   ```

2. **Build Windows installers (.exe Setup) — requires Inno Setup 6:**

   ```bat
   cd /d "c:\Users\Selena\Desktop\Soft Ofertare Usi\v1.0.0 stabila\installers"
   compile_installers.bat
   ```

   Outputs appear in the **same** `installers` folder: `Naturen_Flow_1.0.0_Setup.exe`, `Naturen_Flow_1.0.0_Update.exe`, `Naturen_Admin_1.0.0_Setup.exe`.

3. **Optional:** open any `*.iss` in Inno Setup Compiler GUI and use **Build → Compile** (same result as `compile_installers.bat`).

## Legacy / historical

- **`Soft Ofertare Usi\1.0.0\`** (if present): older staging layout (`Naturen Flow 1.0.0.exe`, etc.). **Not** the current stable bundle. Use **`v1.0.0 stabila\`** only for distribution aligned with `ofertare.exe` / `admin.exe`.

After editing this report, run `scripts\build_release.bat` again to copy `RELEASE_REBUILD_REPORT.md` into `v1.0.0 stabila\docs\` (or copy the file manually).
