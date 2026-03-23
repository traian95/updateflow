from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ARCHIVE_NAME = "naturen_flow_update.zip"
REQUIRED_FILES = ("main.py", "updater.py", "requirements.txt", "version.json")
RESOURCE_DIR_CANDIDATES = ("assets", "ofertare")
EXCLUDED_DIR_NAMES = {"__pycache__", ".git", ".venv", ".vscode"}
EXCLUDED_SUFFIXES = {".db", ".log"}


def read_version_from_file(version_file: Path) -> str:
    raw = json.loads(version_file.read_text(encoding="utf-8"))
    version = str((raw or {}).get("version") or "").strip()
    if not version:
        raise ValueError("Nu am gasit campul 'version' in version.json.")
    return version


def should_exclude(path: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    return path.suffix.lower() in EXCLUDED_SUFFIXES


def add_file_to_zip(zip_file: ZipFile, file_path: Path, project_root: Path) -> None:
    if should_exclude(file_path):
        return
    zip_file.write(file_path, arcname=str(file_path.relative_to(project_root)))


def add_directory_to_zip(zip_file: ZipFile, dir_path: Path, project_root: Path) -> None:
    for path in dir_path.rglob("*"):
        if path.is_dir():
            continue
        if should_exclude(path):
            continue
        add_file_to_zip(zip_file, path, project_root)


def build_archive(project_root: Path) -> tuple[Path, str]:
    archive_path = project_root / ARCHIVE_NAME
    version = read_version_from_file(project_root / "version.json")

    missing_files = [name for name in REQUIRED_FILES if not (project_root / name).is_file()]
    if missing_files:
        raise FileNotFoundError(f"Lipsesc fisiere obligatorii: {', '.join(missing_files)}")

    if archive_path.exists():
        archive_path.unlink()

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as zip_file:
        for file_name in REQUIRED_FILES:
            add_file_to_zip(zip_file, project_root / file_name, project_root)

        for folder_name in RESOURCE_DIR_CANDIDATES:
            folder = project_root / folder_name
            if folder.is_dir():
                add_directory_to_zip(zip_file, folder, project_root)

    return archive_path, version


def main() -> int:
    project_root = Path(__file__).resolve().parent
    try:
        archive_path, version = build_archive(project_root)
        print(f"Arhiva pentru versiunea [{version}] a fost creata cu succes!")
        print(f"Locatie arhiva: {archive_path}")
        return 0
    except Exception as exc:
        print(f"Eroare la creare arhiva update: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
