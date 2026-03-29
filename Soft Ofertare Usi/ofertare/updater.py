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
from typing import Any

import requests
from supabase import Client, create_client

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
# GitHub Releases — sursa de verificare pentru client (override prin variabile de mediu).
GITHUB_RELEASES_OWNER = (os.environ.get("GITHUB_RELEASES_OWNER") or "traian95").strip()
GITHUB_RELEASES_REPO = (os.environ.get("GITHUB_RELEASES_REPO") or "updateflow").strip()
GITHUB_API_VERSION_HEADER = "2022-11-28"
# External helper next to ofertare.exe (never "update.py" — that name is wrong).
EXTERNAL_UPDATER_EXE_NAME = "updater.exe"
EXTERNAL_UPDATER_SCRIPT_NAME = "updater.py"

logger = logging.getLogger(__name__)


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


def _strip_release_version_prefix(version: str) -> str:
    """Elimină prefixul 'v' din tag-uri GitHub (ex. v1.2.3 -> 1.2.3)."""
    s = (version or "").strip()
    if len(s) >= 2 and s[0] in "vV" and (s[1].isdigit() or s[1] == "."):
        return s[1:].strip()
    return s


def _normalize_semver_for_compare(version: str) -> str:
    return _strip_release_version_prefix(version)


def _is_remote_newer(local_version: str, remote_version: str) -> bool:
    local_clean = _normalize_semver_for_compare(local_version or "")
    remote_clean = _normalize_semver_for_compare(remote_version or "")
    if not remote_clean:
        return False
    if _PkgVersion is not None:
        try:
            return _PkgVersion(remote_clean) > _PkgVersion(local_clean or "0")
        except Exception:
            pass
    if remote_clean != local_clean:
        return _normalize_version(remote_clean) > _normalize_version(local_clean)
    return False


def _github_releases_request_headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "NaturenFlow-App",
        "X-GitHub-Api-Version": GITHUB_API_VERSION_HEADER,
    }
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _first_github_release_asset_url(payload: dict[str, Any]) -> tuple[str, str]:
    """
    GitHub API: primul element din assets — (browser_download_url, nume).
    """
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        return "", ""
    first = assets[0]
    if not isinstance(first, dict):
        return "", ""
    url = str(first.get("browser_download_url") or "").strip()
    name = str(first.get("name") or "").strip()
    return url, name


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
    """Ultimul release GitHub vs. version.json; fără Supabase. Aliasuri: update_found/version și update_available/version_cloud."""
    local_clean = str(version_locala or get_local_version()).strip()
    _log_console(f"Versiunea locala este: {local_clean}")

    def _base_false(**extra: Any) -> dict[str, Any]:
        out: dict[str, Any] = {
            "update_found": False,
            "update_available": False,
            "version": "",
            "version_cloud": "",
            "download_url": "",
            "notes": "",
            "version_local": local_clean,
            "version_source": "github_releases",
        }
        out.update(extra)
        return out

    owner = GITHUB_RELEASES_OWNER
    repo = GITHUB_RELEASES_REPO
    if not owner or not repo:
        _log_console("[Updater] GitHub releases: owner/repo neconfigurat (GITHUB_RELEASES_OWNER / GITHUB_RELEASES_REPO).")
        return _base_false(reason="github_not_configured")

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = _github_releases_request_headers()

    try:
        response = requests.get(api_url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        _log_console(f"[Updater] Eroare rețea GitHub: {exc}")
        return _base_false(reason="error", error=str(exc))

    if response.status_code == 404:
        return _base_false(reason="no_github_release")
    if response.status_code == 403:
        _log_console("[Updater] GitHub API 403 (rate limit sau acces refuzat).")
        return _base_false(reason="github_forbidden")

    if response.status_code != 200:
        return _base_false(reason="error", error=f"github_api_http_{response.status_code}")

    try:
        release = response.json()
    except Exception as exc:
        return _base_false(reason="error", error=str(exc))

    if not isinstance(release, dict):
        return _base_false(reason="error", error="github_api_invalid_json")

    tag_raw = str(release.get("tag_name") or "").strip()
    version_cloud = _normalize_semver_for_compare(tag_raw) or tag_raw
    notes = str(release.get("body") or "").strip()
    release_html = str(release.get("html_url") or "").strip()

    if not version_cloud:
        return _base_false(reason="no_remote_version", notes=notes)

    download_url, asset_name = _first_github_release_asset_url(release)

    if not download_url:
        _log_console("[Updater] Release GitHub fără assets sau fără URL la primul asset.")
        return _base_false(
            reason="no_release_asset",
            version=version_cloud,
            version_cloud=version_cloud,
            notes=notes,
        )

    if not _is_remote_newer(local_clean, version_cloud):
        return _base_false(
            reason="already_latest",
            version=version_cloud,
            version_cloud=version_cloud,
            notes=notes,
        )

    return {
        "update_found": True,
        "update_available": True,
        "version": version_cloud,
        "version_cloud": version_cloud,
        "version_local": local_clean,
        "download_url": download_url,
        "sha256": "",
        "mandatory": False,
        "notes": notes,
        "is_active": True,
        "version_source": "github_releases",
        "release_html_url": release_html,
        "zip_asset_name": asset_name,
    }


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
