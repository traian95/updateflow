"""Generează bytes PDF pentru `st.download_button` (fără dialog fișier local)."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from ofertare.pdf_export import build_oferta_pret_pdf


def build_offer_pdf_bytes(**kwargs: Any) -> bytes:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        build_oferta_pret_pdf(cale_salvare=path, **kwargs)
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
