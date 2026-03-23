import os
import shutil
import sys
from pathlib import Path


FILES_TO_DELETE = [
    "build/test/PKG-00.toc",
    "build/test/PYZ-00.toc",
    "build/test/Analysis-00.toc",
    "build/test/EXE-00.toc",
    "build/test/warn-test.txt",
    "build/test/xref-test.html",
    "test.py",
    "test.spec",
]

DIRS_TO_DELETE = [
    "build/test",
]


def delete_files(base_path: Path) -> None:
    for relative_path in FILES_TO_DELETE:
        file_path = base_path / relative_path
        if file_path.is_file():
            print(f"Șterg fișier: {file_path}")
            try:
                file_path.unlink()
            except Exception as exc:
                print(f"  Eroare la ștergerea fișierului: {exc}")
        else:
            print(f"Nu există fișierul (salt): {file_path}")


def delete_dirs(base_path: Path) -> None:
    for relative_path in DIRS_TO_DELETE:
        dir_path = base_path / relative_path
        if dir_path.is_dir():
            print(f"Șterg folder: {dir_path}")
            try:
                shutil.rmtree(dir_path)
            except Exception as exc:
                print(f"  Eroare la ștergerea folderului: {exc}")
        else:
            print(f"Nu există folderul (salt): {dir_path}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("Pornesc curățarea artefactelor de build/test (mod sigur).")
    base_path = Path(__file__).resolve().parent
    delete_files(base_path)
    delete_dirs(base_path)
    print("Curățare terminată.")


if __name__ == "__main__":
    main()

