# Install path change report

## Scripts modified

| File | Purpose |
|------|---------|
| `v1.0.0 stabila/installers/setup_ofertare.iss` | Main Naturen Flow installer |
| `v1.0.0 stabila/installers/setup_ofertare_update.iss` | In-place update installer (same `AppId` as above) |

No application code was changed.

## Previous default location

- **Inno constant:** `{autopf}\NaturenFlow`
- **Typical resolved path:** `%ProgramFiles%\NaturenFlow` (e.g. `C:\Program Files\NaturenFlow`)

## New default location

- **Inno constant:** `{localappdata}\NaturenFlow`
- **Typical resolved path:** `%LOCALAPPDATA%\NaturenFlow` (e.g. `C:\Users\<User>\AppData\Local\NaturenFlow`)

## Why this helps auto-update

1. **Install folder matches user rights:** The running app’s `_app_dir()` is the directory containing `ofertare.exe`. If that directory is under `Program Files`, replacing files during an update usually requires administrator rights. Installing under the current user’s **Local App Data** keeps the application directory writable by that user.

2. **Aligns with update download path:** The client already downloads `update.zip` under `%LOCALAPPDATA%\NaturenFlow\updates\`. Keeping the installed app under `%LOCALAPPDATA%\NaturenFlow` keeps all per-user install and update data under one logical tree.

3. **External updater (`updater.py`):** It still copies extracted files into `--target-dir` (the install directory). With the new default path, those copy operations are far less likely to fail with permission errors than when the target was `Program Files`.

## Shortcuts and other installer settings

- **Unchanged:** `[Icons]` (Start Menu + optional desktop), `[Files]`, `[Run]`, `PrivilegesRequired`, `AppId`, and `OutputBaseFilename` values were not modified for this task—only `DefaultDirName` on the two main-app scripts listed above.

## Admin installer (`setup_admin.iss`)

- **Not changed.** It still defaults to `{autopf}\NaturenAdmin`.
- **Do you need the same change?** Only if you want the admin tool installed per-user without touching `Program Files`. The admin app does not use the main app’s zip auto-update pipeline; changing its default path is optional and independent. Apply the same pattern only if you want consistency: `DefaultDirName={localappdata}\NaturenAdmin` (and review `PrivilegesRequired` if you later switch to a per-user-only install).
