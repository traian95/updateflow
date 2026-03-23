# -*- coding: utf-8 -*-
"""
Test: temă întunecată modernă cu ttkbootstrap (aspect apropiat de CustomTkinter).

- Folosește stratul ``ofertare.ttkbootstrap_ctk_compat`` (``import ttkbootstrap as tb`` în
  compat), ``themename='darkly'`` implicit.
- Nu modifică ``ofertare/ui.py``: același ``.grid()`` / ``.pack()`` / ``.place()`` și aceeași logică.
- Spațierea exterioară din codul tău (padx/pady la pack) rămâne neschimbată; stilurile globale
  (font Segoe UI 10, padding intern butoane/câmpuri) sunt în compat.

La baza ferestrei principale (după login): 3 butoane tip „link” pentru teme Cyborg, Darkly, Superhero.

Utilizare:
    python modern_test.py
"""
from __future__ import annotations

import logging
import os
import sys
import types

import tkinter as tk


def _install_ctk_shim() -> None:
    import ofertare.ttkbootstrap_ctk_compat as shim

    shim.set_theme_name("darkly")
    sys.modules["customtkinter"] = shim
    mb = types.ModuleType("CTkMessagebox")
    mb.CTkMessagebox = shim.CTkMessagebox
    sys.modules["CTkMessagebox"] = mb


def _patch_theme_switcher() -> None:
    from ofertare.ui import AplicatieOfertare
    import ttkbootstrap as tb

    from ofertare.ttkbootstrap_ctk_compat import set_theme_name

    _orig = AplicatieOfertare.show_ecran_start

    def _wrapped(self: AplicatieOfertare) -> None:
        _orig(self)
        _build_bottom_theme_links(self, tb, set_theme_name)

    AplicatieOfertare.show_ecran_start = _wrapped  # type: ignore[assignment]


def _build_bottom_theme_links(self: AplicatieOfertare, tb: object, set_theme_name) -> None:
    """Bară mică jos: butoane link pentru Cyborg / Darkly / Superhero."""
    try:
        old = getattr(self, "_ttb_theme_bar", None)
        if old is not None and old.winfo_exists():
            old.destroy()
    except Exception:
        pass

    outer = tb.Frame(self, padding=(10, 10))
    outer.pack(side="bottom", fill="x")
    self._ttb_theme_bar = outer

    row = tb.Frame(outer)
    row.pack(fill="x")

    def _use(name: str) -> None:
        set_theme_name(name)
        try:
            self.style.theme_use(name)  # type: ignore[attr-defined]
        except tk.TclError:
            logging.getLogger(__name__).warning("Tema nu e disponibilă: %s", name)

    specs = (
        ("Cyborg", "cyborg", "Deep Black"),
        ("Darkly", "darkly", "Standard Dark"),
        ("Superhero", "superhero", "Modern Blue/Grey"),
    )
    for label, theme_key, subtitle in specs:
        tb.Button(
            row,
            text=f"{label} ({subtitle})",
            bootstyle="link",
            command=lambda t=theme_key: _use(t),
        ).pack(side="left", padx=(0, 12))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _install_ctk_shim()
    _patch_theme_switcher()

    from ofertare.ui import run_app

    run_app()


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if __package__ is None or __package__ == "":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
