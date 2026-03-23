"""Pregătește folderul assets/ înainte de PyInstaller: copiază PNG-urile din rădăcina proiectului, imagini/user.png, despre.gif."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


def main() -> int:
    ASSETS.mkdir(exist_ok=True)

    for name in ("customer.png", "istoric.png", "logout.png"):
        src = ROOT / name
        dst = ASSETS / name
        if src.is_file():
            shutil.copy2(src, dst)

    imagini = ASSETS / "imagini"
    imagini.mkdir(parents=True, exist_ok=True)
    user_dst = imagini / "user.png"
    for candidate in (ASSETS / "009.png", ASSETS / "error.png"):
        if candidate.is_file():
            shutil.copy2(candidate, user_dst)
            break
    else:
        print("sync_assets: lipsește 009.png sau error.png pentru imagini/user.png", file=sys.stderr)
        return 1

    gif = ASSETS / "despre.gif"
    if not gif.is_file():
        try:
            from PIL import Image
        except ImportError:
            print("sync_assets: Pillow lipsește; nu pot genera despre.gif", file=sys.stderr)
            return 1
        logo = ASSETS / "Naturen2.png"
        if not logo.is_file():
            print("sync_assets: lipsește Naturen2.png pentru despre.gif", file=sys.stderr)
            return 1
        im = Image.open(logo).convert("RGB")
        w, h = im.size
        max_w = 520
        if w > max_w:
            ratio = max_w / w
            im = im.resize((max_w, int(h * ratio)), Image.Resampling.LANCZOS)
        im.save(gif, format="GIF")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
