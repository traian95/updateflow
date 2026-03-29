"""
Construiește arhiva ZIP pentru GitHub Releases (auto-update onedir).

Conținutul ZIP oglindește folderul de instalare: NaturenFlow.exe, _internal\\..., updater.exe, version.json.
Rulează după PyInstaller (ex. make_build.bat) sau folosește --rebuild pentru a reconstrui dist/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_APP = ROOT / "dist" / "NaturenFlow"
DEFAULT_OUT_DIR = ROOT / "release"


def _write_version_json(target_dir: Path, version: str) -> None:
    payload = {
        "version": version.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    # Lângă exe (după update) și în bundle (citire inițială)
    (target_dir / "version.json").write_text(text, encoding="utf-8")
    internal = target_dir / "_internal" / "version.json"
    if internal.parent.is_dir():
        internal.write_text(text, encoding="utf-8")


def _ensure_updater_exe(app_dir: Path) -> None:
    dst = app_dir / "updater.exe"
    if not dst.is_file():
        raise FileNotFoundError(
            f"Lipsește updater.exe în {app_dir}. Rulează make_build.bat sau: "
            f"py -3 -m PyInstaller --noconfirm NaturenFlow.spec"
        )


def _zip_ondir(app_dir: Path, out_zip: Path) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in app_dir.rglob("*"):
            if path.is_file():
                arc = path.relative_to(app_dir).as_posix()
                zf.write(path, arcname=arc)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rebuild_dist(version: str) -> None:
    """Scrie version.json în proiect, rulează PyInstaller (NaturenFlow.spec: app + updater în același onedir)."""
    proj_v = ROOT / "version.json"
    proj_v.write_text(
        json.dumps(
            {"version": version.strip(), "updated_at": datetime.now(timezone.utc).isoformat()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(ROOT / "NaturenFlow.spec")],
        cwd=str(ROOT),
        check=True,
    )
    _write_version_json(DIST_APP, version)


def main() -> int:
    p = argparse.ArgumentParser(description="ZIP onedir pentru GitHub Release / auto-update.")
    p.add_argument("--version", default="1.0.0", help="Versiune semantică (ex. 1.0.0)")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Folder pentru ZIP + checksum (implicit: release/)",
    )
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Rescrie version.json, rulează PyInstaller (app+updater), apoi creează ZIP",
    )
    args = p.parse_args()
    ver = str(args.version or "").strip()
    if not ver:
        print("Versiune goală.", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir).resolve()
    safe = ver.replace("/", "-")
    out_zip = out_dir / f"NaturenFlow_update_{safe}.zip"

    try:
        if args.rebuild:
            print("Rebuild dist (PyInstaller)...")
            _rebuild_dist(ver)
        else:
            if not DIST_APP.is_dir() or not (DIST_APP / "NaturenFlow.exe").is_file():
                print(f"Lipsește {DIST_APP} sau NaturenFlow.exe. Folosește --rebuild sau make_build.bat.", file=sys.stderr)
                return 1
            _write_version_json(DIST_APP, ver)
            _ensure_updater_exe(DIST_APP)

        _zip_ondir(DIST_APP, out_zip)
        digest = _sha256(out_zip)
        (out_dir / f"{out_zip.stem}.sha256").write_text(f"{digest}  {out_zip.name}\n", encoding="utf-8")

        print("Done.")
        print(f"  ZIP:     {out_zip}")
        print(f"  SHA256:  {digest}")
        print()
        print("GitHub Release:")
        print(f"  - Create tag v{ver} (must be newer than clients' local version).")
        print(f"  - Upload as first release asset: {out_zip.name} (app uses API's first asset).")
        return 0
    except Exception as exc:
        print(f"Eroare: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
