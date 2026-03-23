import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

UPDATER_LOG_FILE = "update-updater.log"
PRESERVED_TOP_DIRS = {"data", "config"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Updater extern pentru Naturen Flow.")
    parser.add_argument("--zip-path", required=True, help="Calea catre update.zip")
    parser.add_argument("--target-dir", required=True, help="Directorul aplicatiei de suprascris")
    parser.add_argument(
        "--restart-cmd",
        required=True,
        help="Comanda de restart separata prin delimitatorul |||",
    )
    parser.add_argument(
        "--new-version",
        required=False,
        default="",
        help="Noua versiune care trebuie scrisa in version.json",
    )
    return parser.parse_args()


def _log_path(target_dir: Path) -> Path:
    return target_dir / UPDATER_LOG_FILE


def _log(target_dir: Path, message: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {message}"
    try:
        with _log_path(target_dir).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _extract_to_temp(zip_path: Path) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="naturen_update_"))
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(temp_root)
    return temp_root


def _is_preserved(path: Path, base_dir: Path) -> bool:
    rel = path.relative_to(base_dir)
    if not rel.parts:
        return False
    return rel.parts[0].lower() in PRESERVED_TOP_DIRS


def _copy_extracted_content(temp_dir: Path, target_dir: Path) -> None:
    backup_dir = target_dir / "_update_backup"
    for src in temp_dir.rglob("*"):
        if src.is_dir():
            continue
        if _is_preserved(src, temp_dir):
            continue
        rel = src.relative_to(temp_dir)
        dst = target_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            backup_target = backup_dir / rel
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(dst, backup_target)
            except Exception:
                pass
        shutil.copy2(src, dst)


def _write_version_file(target_dir: Path, new_version: str) -> None:
    if not str(new_version or "").strip():
        return
    payload = {
        "version": str(new_version).strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (target_dir / "version.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def restart_application(restart_cmd: list[str], target_dir: Path) -> None:
    creation_flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creation_flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        restart_cmd,
        cwd=str(target_dir),
        close_fds=True,
        creationflags=creation_flags,
    )


def main() -> None:
    args = parse_args()
    zip_path = Path(args.zip_path).resolve()
    target_dir = Path(args.target_dir).resolve()
    new_version = str(args.new_version or "").strip()
    restart_cmd = [token for token in str(args.restart_cmd).split("|||") if token]

    # Asteapta inchiderea aplicatiei curente.
    time.sleep(3)
    _log(target_dir, "Updater started.")

    if not zip_path.exists():
        raise FileNotFoundError(f"Nu exista arhiva de update: {zip_path}")

    temp_dir = _extract_to_temp(zip_path)
    _copy_extracted_content(temp_dir, target_dir)
    _write_version_file(target_dir, new_version)
    _log(target_dir, f"Update files copied. version={new_version or '-'}")

    try:
        os.remove(zip_path)
    except Exception:
        pass
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    if not restart_cmd:
        raise RuntimeError("Comanda de restart lipseste.")

    restart_application(restart_cmd, target_dir)
    _log(target_dir, "Application restart command launched.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Evitam crash popup-uri; updaterul ruleaza silent.
        sys.exit(1)
