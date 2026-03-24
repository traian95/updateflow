# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from supabase import Client, create_client

from ofertare.agent_debug_log import append_agent_debug_ndjson
from ofertare.db_cloud import SUPABASE_KEY, SUPABASE_URL

try:
    from packaging.version import Version as _PkgVersion
except Exception:
    _PkgVersion = None

TABLE_UPDATES = "app_updates"
APP_SLUG = "naturen_flow"
UPDATE_ARCHIVE_NAME = "update.zip"
VERSION_FILE_NAME = "version.json"
UPDATE_LOG_FILE = "update-client.log"
# External helper next to ofertare.exe (never "update.py" — that name is wrong).
EXTERNAL_UPDATER_EXE_NAME = "updater.exe"
EXTERNAL_UPDATER_SCRIPT_NAME = "updater.py"

logger = logging.getLogger(__name__)


def _debug_update_check_ndjson(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
    run_id: str = "banner-check",
) -> None:
    # #region agent log
    append_agent_debug_ndjson(
        session_id="88fd1f",
        run_id=run_id,
        hypothesis_id=hypothesis_id,
        location=location,
        message=message,
        data=data,
    )
    # #endregion


def _log_console(message: str) -> None:
    """
    Safe console print for Windows terminals with non-UTF-8 encoding.
    """
    try:
        print(message)
    except UnicodeEncodeError:
        safe = str(message).encode("ascii", errors="replace").decode("ascii")
        print(safe)
    except Exception:
        pass


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _user_download_dir_for_updates() -> Path:
    """
    Writable directory for the update archive (not under Program Files).
    Prefer %LOCALAPPDATA%\\NaturenFlow\\updates\\; fallback %TEMP%\\NaturenFlow\\updates\\.
    """
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return (Path(local) / "NaturenFlow" / "updates").resolve()
    return (Path(tempfile.gettempdir()) / "NaturenFlow" / "updates").resolve()


def _update_log_path() -> Path:
    return _app_dir() / UPDATE_LOG_FILE


def _log_update(message: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {message}"
    _log_console(line)
    try:
        _update_log_path().parent.mkdir(parents=True, exist_ok=True)
        with _update_log_path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _version_file_path() -> Path:
    return _app_dir() / VERSION_FILE_NAME


def get_local_version(default: str = "0.0.0") -> str:
    path = _version_file_path()
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        version = str((payload or {}).get("version") or "").strip()
        return version or default
    except Exception:
        return default


def set_local_version(version: str) -> None:
    payload = {
        "version": str(version or "").strip() or "0.0.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _version_file_path()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


SUPABASE_ADMIN_URL = (os.environ.get("SUPABASE_ADMIN_URL") or SUPABASE_URL or "").strip()
SUPABASE_ADMIN_SERVICE_ROLE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()


def _get_supabase_client() -> Client:
    url = SUPABASE_URL.strip()
    key = SUPABASE_KEY.strip()
    if not url or not key:
        raise RuntimeError("Lipsesc SUPABASE_URL/SUPABASE_KEY in configurarea aplicatiei.")
    return create_client(url, key)


def _get_supabase_admin_client() -> Client:
    if not SUPABASE_ADMIN_URL or not SUPABASE_ADMIN_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Lipsesc SUPABASE_ADMIN_URL/SUPABASE_SERVICE_ROLE_KEY pentru operatiuni admin update."
        )
    return create_client(SUPABASE_ADMIN_URL, SUPABASE_ADMIN_SERVICE_ROLE_KEY)


def _normalize_version(version: str) -> tuple[int, ...]:
    raw = (version or "").strip().lower().replace("v", "")
    parts = []
    for token in raw.replace("-", ".").split("."):
        try:
            parts.append(int(token))
        except Exception:
            parts.append(0)
    return tuple(parts or [0])


def _is_remote_newer(local_version: str, remote_version: str) -> bool:
    local_clean = (local_version or "").strip()
    remote_clean = (remote_version or "").strip()
    if not remote_clean:
        return False
    if _PkgVersion is not None:
        try:
            return _PkgVersion(remote_clean) > _PkgVersion(local_clean or "0")
        except Exception:
            pass
    # Fallback simplu: daca versiunile difera, consideram remote mai nou.
    if remote_clean != local_clean:
        return _normalize_version(remote_clean) > _normalize_version(local_clean)
    return False


def _get_latest_active_update_row(supabase: Client) -> Optional[dict[str, Any]]:
    query = supabase.table(TABLE_UPDATES).select("*")
    try:
        query = query.eq("is_active", True)
    except Exception:
        pass
    for app_column in ("app_name", "slug"):
        try:
            rows = query.eq(app_column, APP_SLUG).order("created_at", desc=True).limit(1).execute().data or []
            if rows:
                return rows[0]
        except Exception:
            continue
    rows = query.order("created_at", desc=True).limit(1).execute().data or []
    return rows[0] if rows else None


def _normalize_update_row(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    return {
        "id": row.get("id"),
        "version": str(row.get("version") or "").strip(),
        "download_url": str(row.get("download_url") or row.get("url_download") or "").strip(),
        "sha256": str(row.get("sha256") or "").strip().lower(),
        "mandatory": bool(row.get("mandatory") or False),
        "notes": str(row.get("notes") or "").strip(),
        "is_active": bool(row.get("is_active") if row.get("is_active") is not None else True),
        "app_name": str(row.get("app_name") or row.get("slug") or "").strip(),
        "created_at": str(row.get("created_at") or "").strip(),
    }


def upload_new_version(
    version_name: str,
    download_url: str,
    sha256: str = "",
    mandatory: bool = False,
    notes: str = "",
    is_active: bool = True,
) -> dict[str, Any]:
    """
    Publica metadata complet standardizat in app_updates.
    Daca noul update este activ, dezactiveaza update-urile active precedente.
    """
    try:
        supabase = _get_supabase_admin_client()
        normalized_version = str(version_name or "").strip()
        if not normalized_version:
            raise ValueError("version_name nu poate fi gol.")
        if not re.fullmatch(r"\d+\.\d+\.\d+", normalized_version):
            raise ValueError("Versiunea trebuie sa aiba formatul x.x.x (ex: 1.2.3).")

        direct_download_url = str(download_url or "").strip()
        if not direct_download_url:
            raise ValueError("URL-ul de update nu poate fi gol.")
        if not direct_download_url.startswith("https://"):
            raise ValueError("URL-ul de update trebuie sa inceapa cu https://")

        sha256_clean = str(sha256 or "").strip().lower()
        if sha256_clean and not re.fullmatch(r"[a-f0-9]{64}", sha256_clean):
            raise ValueError("SHA256 trebuie sa fie hash hex valid cu 64 caractere.")

        try:
            resp = requests.get(direct_download_url, timeout=25, allow_redirects=True, stream=True)
            status = int(resp.status_code or 0)
            resp.close()
            if status != 200:
                raise ValueError(f"URL de update invalid/inaccesibil (HTTP {status}).")
        except Exception as exc_validate:
            raise ValueError(f"Validare URL update esuata: {exc_validate}")

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "version": normalized_version,
            "download_url": direct_download_url,
            "sha256": sha256_clean,
            "mandatory": 1 if mandatory else 0,
            "notes": str(notes or "").strip(),
            "is_active": 1 if is_active else 0,
            "app_name": APP_SLUG,
            "created_at": now_iso,
        }

        if is_active:
            try:
                supabase.table(TABLE_UPDATES).update({"is_active": 0}).eq("app_name", APP_SLUG).eq("is_active", 1).execute()
            except Exception:
                pass
            try:
                supabase.table(TABLE_UPDATES).update({"is_active": 0}).eq("slug", APP_SLUG).eq("is_active", 1).execute()
            except Exception:
                pass

        inserted = supabase.table(TABLE_UPDATES).insert(payload).execute().data or []
        return {
            "ok": True,
            "version": normalized_version,
            "download_url": direct_download_url,
            "sha256": sha256_clean,
            "mandatory": bool(mandatory),
            "notes": str(notes or "").strip(),
            "is_active": bool(is_active),
            "row": inserted[:1],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "version": version_name}


def _download_update_archive(download_url: str, target_path: Path) -> None:
    response = requests.get(download_url, timeout=120, stream=True)
    if response.status_code != 200:
        raise RuntimeError(f"Download update esuat. HTTP status: {response.status_code}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)


def _restart_command_for_current_runtime() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [sys.executable, str((Path(__file__).resolve().parent.parent / "main.py").resolve())]


def _python_command_for_updater_script() -> list[str]:
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    return ["py", "-3"]


def _launch_zip_updater(update_zip_path: Path, app_dir: Path, new_version: str) -> None:
    """
    Prefer packaged updater.exe (no Python on PATH). Fallback: updater.py + python/py -3.
    Both must live in app_dir (same folder as ofertare.exe).
    """
    exe_path = (app_dir / EXTERNAL_UPDATER_EXE_NAME).resolve()
    py_path = (app_dir / EXTERNAL_UPDATER_SCRIPT_NAME).resolve()
    common_suffix = [
        "--zip-path",
        str(update_zip_path),
        "--target-dir",
        str(app_dir),
        "--new-version",
        str(new_version or "").strip(),
        "--restart-cmd",
        "|||".join(_restart_command_for_current_runtime()),
    ]
    if exe_path.is_file():
        cmd = [str(exe_path)] + common_suffix
    elif py_path.is_file():
        cmd = _python_command_for_updater_script() + [str(py_path)] + common_suffix
    else:
        raise FileNotFoundError(
            f"External updater not found in {app_dir}: need {EXTERNAL_UPDATER_EXE_NAME} "
            f"or {EXTERNAL_UPDATER_SCRIPT_NAME} next to the application executable."
        )

    creation_flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creation_flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(cmd, close_fds=True, creationflags=creation_flags)


def install_zip_update(download_url: str, expected_sha256: str = "", new_version: str = "") -> dict[str, Any]:
    """
    Descarca update.zip, lanseaza updater.py extern si intoarce status.
    """
    try:
        app_dir = _app_dir()
        download_dir = _user_download_dir_for_updates()
        download_dir.mkdir(parents=True, exist_ok=True)
        zip_path = download_dir / UPDATE_ARCHIVE_NAME
        resolved_zip = zip_path.resolve()
        logger.info("Update download path (writable): %s", resolved_zip)
        _log_update(f"[download] writing update archive to: {resolved_zip}")
        _download_update_archive(download_url, zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(f"Arhiva update lipseste: {resolved_zip}")
        logger.info("Update archive saved: %s", resolved_zip)
        _log_update(f"[download] completed: {resolved_zip}")
        expected = str(expected_sha256 or "").strip().lower()
        if expected:
            got = _sha256_file(zip_path)
            if got != expected:
                raise RuntimeError("Verificarea SHA256 a esuat pentru update.zip.")
        version_to_write = str(new_version or "").strip() or get_local_version()
        _launch_zip_updater(zip_path, app_dir, version_to_write)
        return {"ok": True, "zip_path": str(resolved_zip), "new_version": version_to_write}
    except Exception as exc:
        _log_update(f"[ERROR] install_zip_update failed: {exc}")
        return {"ok": False, "error": str(exc)}

def check_for_updates(version_locala: str | None = None) -> dict[str, Any]:
    try:
        supabase = _get_supabase_client()
        local_clean = str(version_locala or get_local_version()).strip()
        _log_console(f"Versiunea locala este: {local_clean}")
        try:
            latest_updates_row = _get_latest_active_update_row(supabase)
        except Exception as exc_u:
            _debug_update_check_ndjson(
                "B1",
                "updater.py:check_for_updates",
                "app_updates_query_failed",
                {"error": str(exc_u)[:400]},
            )
            _log_console(f"[Updater] app_updates: {exc_u}")
        row = _normalize_update_row(latest_updates_row)
        version_cloud = row.get("version", "")
        download_url = row.get("download_url", "")
        if not version_cloud:
            _log_console("Cea mai noua versiune de pe Supabase este: - (fara candidati)")
            return {"update_available": False, "reason": "no_remote_version", "version_local": local_clean}
        if not _is_remote_newer(local_clean, version_cloud):
            return {
                "update_available": False,
                "reason": "already_latest",
                "version_local": local_clean,
                "version_cloud": version_cloud,
                "version_source": "app_updates",
            }

        return {
            "update_available": True,
            "version_local": local_clean,
            "version_cloud": version_cloud,
            "download_url": download_url,
            "sha256": row.get("sha256", ""),
            "mandatory": bool(row.get("mandatory", False)),
            "notes": row.get("notes", ""),
            "is_active": bool(row.get("is_active", True)),
            "version_source": "app_updates",
        }
    except Exception as exc:
        _log_console(f"[Updater] Eroare la verificarea update-ului: {exc}")
        _debug_update_check_ndjson(
            "B5",
            "updater.py:check_for_updates",
            "check_exception",
            {"exc_type": type(exc).__name__, "msg": str(exc)[:500]},
        )
        return {"update_available": False, "reason": "error", "error": str(exc)}


def list_updates_for_admin(limit: int = 30) -> list[dict[str, Any]]:
    try:
        supabase = _get_supabase_admin_client()
        rows = (
            supabase.table(TABLE_UPDATES)
            .select("*")
            .order("created_at", desc=True)
            .limit(max(1, int(limit)))
            .execute()
            .data
            or []
        )
        return [_normalize_update_row(r) for r in rows]
    except Exception:
        return []


# Legacy pathway intentionally preserved but disabled.
def check_and_install_update(*args, **kwargs) -> dict[str, Any]:
    return {
        "updated": False,
        "reason": "legacy_disabled",
        "error": "Legacy exe-swap flow is disabled. Use zip updater flow.",
    }
