"""
Updater extern NaturenFlow (rădăcină proiect — intrare PyInstaller pentru updater.exe).

Mod ZIP: lansat din aplicație cu --zip-path / --target-dir / --restart-cmd.
Mod standalone: dublu-click fără --zip-path → citește version.json lângă exe, verifică GitHub.

Log: updater_debug.log în folderul de instalare (lângă NaturenFlow.exe / updater.exe); fallback
dacă scrierea eșuează: %ProgramFiles%\\NaturenFlow (când diferă de folderul exe).

Notă: logica UI/ZIP/taskkill nu trăiește în ofertare/updater.py — acolo e biblioteca aplicației
(Supabase, requests); folosind acel fișier ca Analysis entry, exe-ul ar include întreaga stivă.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

MAIN_APP_EXE = "NaturenFlow.exe"
PRESERVED_TOP_DIRS = {"data", "config"}
GITHUB_API_VERSION_HEADER = "2022-11-28"
USER_AGENT = "NaturenFlow-updater"


def _program_files_naturenflow() -> Path:
    base = (os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files").strip()
    return Path(base) / "NaturenFlow"


def _debug_log_paths() -> list[Path]:
    """Întâi folderul de instalare (lângă exe); apoi Program Files\\NaturenFlow dacă e alt path."""
    install_dir = _updater_exe_dir() / "updater_debug.log"
    pf = _program_files_naturenflow() / "updater_debug.log"
    out = [install_dir]
    try:
        if pf.resolve() != install_dir.resolve():
            out.append(pf)
    except OSError:
        out.append(pf)
    return out


def debug_log(message: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {message}\n"
    for path in _debug_log_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
            return
        except OSError:
            continue
        except Exception:
            continue


def _updater_exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _is_zip_update_argv() -> bool:
    return "--zip-path" in sys.argv


def _wants_cli_help() -> bool:
    return "-h" in sys.argv or "--help" in sys.argv


def parse_zip_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NaturenFlow updater (ZIP flow, launched from the app).")
    parser.add_argument(
        "install_root",
        nargs="?",
        default=None,
        help="Application directory (next to NaturenFlow.exe). Optional if --target-dir is set.",
    )
    parser.add_argument("--zip-path", required=True, help="Path to update.zip")
    parser.add_argument("--target-dir", required=True, help="Application directory to overwrite")
    parser.add_argument(
        "--restart-cmd",
        required=True,
        help="Restart command tokens separated by |||",
    )
    parser.add_argument("--new-version", required=False, default="", help="Version string for version.json")
    return parser.parse_args()


def _github_env_owner_repo() -> tuple[str, str]:
    owner = (os.environ.get("GITHUB_RELEASES_OWNER") or "traian95").strip()
    repo = (os.environ.get("GITHUB_RELEASES_REPO") or "updateflow").strip()
    return owner, repo


def _github_headers() -> dict[str, str]:
    h: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION_HEADER,
    }
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _fetch_github_latest_release() -> dict[str, Any] | None:
    owner, repo = _github_env_owner_repo()
    if not owner or not repo:
        return None
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    req = urllib.request.Request(url, headers=_github_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        debug_log(f"GitHub HTTPError {exc.code}: {exc.reason}")
        return None
    except Exception as exc:
        debug_log(f"GitHub request failed: {exc!r}")
        return None


def _strip_v_prefix(version: str) -> str:
    s = (version or "").strip()
    if len(s) >= 2 and s[0] in "vV" and (s[1].isdigit() or s[1] == "."):
        return s[1:].strip()
    return s


def _version_tuple(version: str) -> tuple[int, ...]:
    raw = _strip_v_prefix(version or "").lower().replace("-", ".")
    parts: list[int] = []
    for token in raw.split("."):
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return tuple(parts or [0])


def _remote_is_newer(local_version: str, remote_version: str) -> bool:
    rc = _strip_v_prefix(remote_version or "")
    lc = _strip_v_prefix(local_version or "")
    if not rc:
        return False
    if rc != lc:
        return _version_tuple(rc) > _version_tuple(lc)
    return False


def _read_local_version(app_dir: Path) -> str:
    vf = app_dir / "version.json"
    if not vf.is_file():
        debug_log(f"standalone: no version.json at {vf}")
        return "0.0.0"
    try:
        payload = json.loads(vf.read_text(encoding="utf-8"))
        v = str((payload or {}).get("version") or "").strip()
        return v or "0.0.0"
    except Exception as exc:
        debug_log(f"standalone: version.json read error: {exc}")
        return "0.0.0"


def _kill_main_app() -> None:
    if sys.platform != "win32":
        debug_log("taskkill: skipped (non-Windows)")
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = ["taskkill", "/F", "/IM", MAIN_APP_EXE, "/T"]
    debug_log(f"taskkill: running {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, creationflags=flags)
    debug_log(f"taskkill exit={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")


def _normalize_zip_name(name: str) -> str:
    return name.replace("\\", "/").strip("/")


def _single_top_level_prefix(namelist: list[str]) -> str | None:
    paths: list[str] = []
    for raw in namelist:
        n = _normalize_zip_name(raw)
        if not n:
            continue
        paths.append(n)
    if not paths:
        return None
    roots: set[str] = {p.split("/", 1)[0] for p in paths}
    if len(roots) != 1:
        return None
    root = next(iter(roots))
    prefix = root + "/"
    for p in paths:
        if p != root and not p.startswith(prefix):
            return None
    return prefix


def _is_preserved_relative(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    return bool(parts) and parts[0].lower() in PRESERVED_TOP_DIRS


def _safe_dest_path(target_dir: Path, relative_posix: str) -> Path | None:
    if not relative_posix or ".." in relative_posix.split("/"):
        return None
    out = (target_dir / relative_posix.replace("/", os.sep)).resolve()
    try:
        out.relative_to(target_dir.resolve())
    except ValueError:
        return None
    return out


def extract_archive_to_app_root(zip_path: Path, target_dir: Path) -> None:
    debug_log(f"UNZIP: opening {zip_path} -> {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        prefix = _single_top_level_prefix(names)
        debug_log(f"UNZIP: prefix strip = {prefix!r}" if prefix else "UNZIP: flat layout (no single root folder)")
        count = 0
        for info in zf.infolist():
            name = _normalize_zip_name(info.filename)
            if not name or name.endswith("/"):
                continue
            if prefix:
                if name == prefix.rstrip("/"):
                    continue
                if not name.startswith(prefix):
                    continue
                rel = name[len(prefix) :].lstrip("/")
            else:
                rel = name
            if not rel or _is_preserved_relative(rel):
                continue
            dest = _safe_dest_path(target_dir, rel)
            if dest is None:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    debug_log(f"UNZIP: wrote {count} files under {target_dir}")


def _write_version_file(target_dir: Path, new_version: str) -> None:
    if not str(new_version or "").strip():
        return
    payload = {
        "version": str(new_version).strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    vf = target_dir / "version.json"
    vf.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    debug_log(f"OVERWRITE: wrote version.json -> {vf}")


def _log_version_json_status(target_dir: Path) -> None:
    vf = target_dir / "version.json"
    if not vf.is_file():
        debug_log("POST: version.json missing after update")
        return
    try:
        text = vf.read_text(encoding="utf-8")
        debug_log(f"POST: version.json content: {text!r}")
    except Exception as exc:
        debug_log(f"POST: version.json read failed: {exc}")


def restart_application(restart_cmd: list[str], target_dir: Path) -> None:
    creation_flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creation_flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    debug_log(f"RESTART: cmd={restart_cmd!r} cwd={target_dir}")
    subprocess.Popen(
        restart_cmd,
        cwd=str(target_dir),
        close_fds=True,
        creationflags=creation_flags,
    )


def _make_status_window(title: str, initial_text: str) -> tuple[tk.Tk, ttk.Label]:
    root = tk.Tk()
    root.title(title)
    root.geometry("440x130")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.pack(fill=tk.BOTH, expand=True)
    lbl = ttk.Label(frm, text=initial_text, wraplength=400, justify=tk.CENTER)
    lbl.pack(expand=True)
    root.update_idletasks()
    return root, lbl


def _ui_set(root: tk.Tk, label: ttk.Label, text: str) -> None:
    label.config(text=text)
    root.update_idletasks()
    root.update()


def run_standalone() -> None:
    app_dir = _updater_exe_dir()
    debug_log("=== STANDALONE: start ===")
    debug_log(f"standalone: app_dir={app_dir} getcwd={os.getcwd()!r}")

    root, lbl = _make_status_window("NaturenFlow — actualizare", "Se verifică actualizările…")
    result_title = "NaturenFlow"
    result_body = ""

    try:
        _ui_set(root, lbl, "Se citește version.json…")
        local_v = _read_local_version(app_dir)
        debug_log(f"standalone: local version = {local_v!r}")

        _ui_set(root, lbl, "Conectare la GitHub…")
        data = _fetch_github_latest_release()
        if not data or not isinstance(data, dict):
            result_body = "Could not reach GitHub or parse the latest release.\nSee updater_debug.log for details."
        else:
            tag = str(data.get("tag_name") or "").strip()
            remote_v = _strip_v_prefix(tag) or tag
            html_url = str(data.get("html_url") or "").strip()
            debug_log(f"standalone: remote tag={tag!r} remote_v={remote_v!r}")

            if _remote_is_newer(local_v, remote_v):
                result_body = (
                    f"A new version may be available.\n\n"
                    f"Installed: {local_v}\n"
                    f"Latest (GitHub): {remote_v}\n\n"
                    f"Use Check for updates inside NaturenFlow to download and install.\n"
                    f"{html_url}"
                )
            else:
                result_body = f"You are up to date.\n\nInstalled: {local_v}\nLatest (GitHub): {remote_v or '—'}"

        _ui_set(root, lbl, "Gata.")
        root.update()
        messagebox.showinfo(result_title, result_body, parent=root)
    except Exception as exc:
        debug_log(f"standalone: exception:\n{traceback.format_exc()}")
        messagebox.showerror("NaturenFlow Updater", str(exc), parent=root)
    finally:
        debug_log("=== STANDALONE: end ===")
        root.destroy()


def run_zip_update(args: argparse.Namespace) -> None:
    zip_path = Path(args.zip_path).resolve()
    target_dir = _resolve_target_dir(args)
    new_version = str(args.new_version or "").strip()
    restart_cmd = [token for token in str(args.restart_cmd).split("|||") if token]

    debug_log("=== ZIP UPDATE: start ===")
    debug_log(f"BOOT: getcwd()={os.getcwd()!r}")
    debug_log(f"BOOT: zip_path={zip_path!r}")
    debug_log(f"BOOT: target_dir={target_dir!r}")
    debug_log(f"BOOT: updater_exe_dir={_updater_exe_dir()!r}")

    root, lbl = _make_status_window("NaturenFlow — actualizare", "Se verifică…")

    try:
        _ui_set(root, lbl, "Se închide NaturenFlow dacă rulează…")
        time.sleep(0.5)
        _kill_main_app()
        time.sleep(1.5)

        if not zip_path.is_file():
            raise FileNotFoundError(f"Update archive not found: {zip_path}")

        _ui_set(root, lbl, "Se extrag fișierele…")
        extract_archive_to_app_root(zip_path, target_dir)

        _ui_set(root, lbl, "Se actualizează versiunea…")
        _write_version_file(target_dir, new_version)
        _log_version_json_status(target_dir)
        debug_log(f"ZIP UPDATE: new_version arg={new_version or '-'}")

        try:
            os.remove(zip_path)
            debug_log(f"ZIP UPDATE: removed archive {zip_path}")
        except OSError as exc:
            debug_log(f"ZIP UPDATE: could not remove zip: {exc}")

        if not restart_cmd:
            raise RuntimeError("Missing --restart-cmd")

        _ui_set(root, lbl, "Se pornește NaturenFlow…")
        restart_application(restart_cmd, target_dir)
        debug_log("ZIP UPDATE: restart launched")
        _ui_set(root, lbl, "Gata.")
        time.sleep(0.8)
    except Exception:
        debug_log(f"ZIP UPDATE failed:\n{traceback.format_exc()}")
        messagebox.showerror("NaturenFlow Updater", "Update failed. See console and updater_debug.log.", parent=root)
        raise
    finally:
        root.destroy()


def _resolve_target_dir(args: argparse.Namespace) -> Path:
    if getattr(sys, "frozen", False):
        return _updater_exe_dir()
    raw = (args.install_root or args.target_dir or "").strip()
    return Path(raw).resolve()


def main() -> None:
    if _is_zip_update_argv():
        args = parse_zip_args()
        run_zip_update(args)
    elif _wants_cli_help():
        print(
            "NaturenFlow updater:\n"
            "  Double-click updater.exe — check GitHub for updates (no ZIP install).\n"
            "  From the app: updater.exe [app_dir] --zip-path … --target-dir … --restart-cmd …\n"
            "  Use: updater.exe --zip-path X --target-dir Y --restart-cmd Z --help  (full ZIP options)"
        )
    else:
        run_standalone()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)
