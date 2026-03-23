# -*- coding: utf-8 -*-
"""
Drop-in replacements for customtkinter widgets using ttkbootstrap, for use with
``ofertare.ui`` when ``sys.modules['customtkinter']`` is pointed here.

Does not modify ui.py; keeps layout and method calls compatible.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from typing import Any, Callable, Optional

import ttkbootstrap as tb
from PIL import Image, ImageTk
from ttkbootstrap.scrolled import ScrolledFrame

# Re-export for ui.py
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar  # noqa: F401

filedialog = filedialog
messagebox = messagebox

_THEME_NAME = "darkly"


def set_theme_name(name: str) -> None:
    global _THEME_NAME
    _THEME_NAME = name or "darkly"


def get_theme_name() -> str:
    return _THEME_NAME


def set_appearance_mode(_mode: str) -> None:
    """No-op: theme is controlled by ttkbootstrap."""
    return


def set_default_color_theme(_theme: str) -> None:
    """No-op."""
    return


def _px_to_chars(w: int | None) -> int:
    if w is None:
        return 20
    return max(4, int(w) // 8)


def _windows_ui_font(master: Any) -> tuple[str, int]:
    """Prefer Segoe UI (Windows), else Roboto; size 10."""
    try:
        import tkinter.font as tkfont

        families = set(tkfont.families(master))
        if "Segoe UI" in families:
            return ("Segoe UI", 10)
        if "Roboto" in families:
            return ("Roboto", 10)
    except Exception:
        pass
    return ("TkDefaultFont", 10)


def _apply_global_theme(win: tb.Window) -> None:
    """Default font + entry/button internal padding (ttk style); runs once per root window."""
    try:
        st = win.style
        font = _windows_ui_font(win)
        for name in (
            "TLabel",
            "TButton",
            "TEntry",
            "TCheckbutton",
            "TRadiobutton",
            "TCombobox",
            "TNotebook.Tab",
            "Horizontal.TProgressbar",
            "Treeview",
        ):
            try:
                st.configure(name, font=font)
            except tk.TclError:
                pass
        try:
            st.configure("TButton", font=font, padding=(12, 7))
        except tk.TclError:
            pass
        try:
            st.configure("TEntry", font=font, padding=(12, 7))
        except tk.TclError:
            pass
    except Exception:
        pass


def _button_bootstyle(
    fg_color: str | None,
    border_width: int | None,
    hover_color: str | None = None,
) -> str:
    del hover_color  # theme handles hover
    if border_width and (not fg_color or str(fg_color).lower() in {"transparent", "none"}):
        return PRIMARY_OUTLINE
    if fg_color:
        s = str(fg_color).lower()
        if any(x in s for x in ("#2c6e49", "#2a5a29", "#1f7a43", "#1d4a1c", "#2d5a27", "#186235")):
            return SUCCESS
        if any(x in s for x in ("#6f1d1b", "#8b2522", "#b75e00", "#b07d00", "#926600")):
            return "warning"
    return PRIMARY  # electric blue primary actions → info


PRIMARY = "info"
SUCCESS = "success"
PRIMARY_OUTLINE = "info-outline"


def _ctk_frame_bg(master: Any, fg_color: Any) -> str:
    """Map CTk fg_color to tk.Frame bg; transparent → match parent (CustomTkinter-like)."""
    if fg_color is None:
        fg_color = "transparent"
    s = str(fg_color).lower()
    if s in ("transparent", "none"):
        try:
            return str(master.cget("bg"))
        except (tk.TclError, AttributeError):
            pass
        return "#1b1e23"
    if isinstance(fg_color, str) and fg_color.startswith("#"):
        return fg_color
    return "#1e1e1e"


class CTkImage:
    """Holds a PhotoImage for Tk labels (CTkImage-compatible)."""

    def __init__(
        self,
        light_image: Image.Image | None = None,
        dark_image: Image.Image | None = None,
        size: tuple[int, int] = (100, 100),
    ) -> None:
        src = dark_image or light_image
        if src is None:
            raise ValueError("CTkImage needs an image")
        self._pil = src.copy().convert("RGBA")
        self._size = size
        self._pil = self._pil.resize(size, Image.Resampling.LANCZOS)
        self._photo: ImageTk.PhotoImage | None = None

    def _ensure_photo(self) -> ImageTk.PhotoImage:
        if self._photo is None:
            self._photo = ImageTk.PhotoImage(self._pil)
        return self._photo

    def get_tk_photo(self) -> ImageTk.PhotoImage:
        return self._ensure_photo()


class CTk(tb.Window):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        kwargs.setdefault("themename", get_theme_name())
        super().__init__(*args, **kwargs)
        _apply_global_theme(self)

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        for k in ("fg_color", "corner_radius", "border_width", "border_color"):
            kwargs.pop(k, None)
        if cnf:
            return super().configure(cnf, **kwargs)
        return super().configure(**kwargs)


class CTkToplevel(tb.Toplevel):
    def __init__(self, master: Any = None, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        super().__init__(master, *args, **kwargs)

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        for k in ("fg_color", "corner_radius", "border_width", "border_color"):
            kwargs.pop(k, None)
        if cnf:
            return super().configure(cnf, **kwargs)
        return super().configure(**kwargs)


class CTkFrame(tk.Frame):
    """Pixel-sized frames like CustomTkinter (tk.Frame), not ttk.Frame."""

    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_width", None)
        kwargs.pop("border_color", None)
        fg = kwargs.pop("fg_color", None)
        w = kwargs.pop("width", None)
        h = kwargs.pop("height", None)
        bg = _ctk_frame_bg(master, fg)
        kwargs.setdefault("bg", bg)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, *args, **kwargs)
        if w is not None:
            try:
                self.configure(width=int(w))
            except (tk.TclError, ValueError, TypeError):
                pass
        if h is not None:
            try:
                self.configure(height=int(h))
            except (tk.TclError, ValueError, TypeError):
                pass

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if "fg_color" in kwargs:
            fg = kwargs.pop("fg_color")
            kwargs["bg"] = _ctk_frame_bg(self.master, fg)
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_width", None)
        kwargs.pop("border_color", None)
        if "width" in kwargs and kwargs["width"] is not None:
            try:
                kwargs["width"] = int(kwargs["width"])
            except (ValueError, TypeError):
                kwargs.pop("width", None)
        if "height" in kwargs and kwargs["height"] is not None:
            try:
                kwargs["height"] = int(kwargs["height"])
            except (ValueError, TypeError):
                kwargs.pop("height", None)
        if cnf:
            return tk.Frame.configure(self, cnf, **kwargs)
        return tk.Frame.configure(self, **kwargs)


class CTkLabel(tb.Label):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        self._image_ref: Any = None
        if "text_color" in kwargs:
            kwargs["foreground"] = kwargs.pop("text_color")
        kwargs.pop("fg_color", None)
        img = kwargs.pop("image", None)
        if isinstance(img, CTkImage):
            self._image_ref = img.get_tk_photo()
            kwargs["image"] = self._image_ref
        elif img is not None:
            kwargs["image"] = img
        super().__init__(master, *args, **kwargs)

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if "text_color" in kwargs:
            kwargs["foreground"] = kwargs.pop("text_color")
        kwargs.pop("fg_color", None)
        if "image" in kwargs and isinstance(kwargs["image"], CTkImage):
            self._image_ref = kwargs["image"].get_tk_photo()
            kwargs["image"] = self._image_ref
        if cnf:
            return super().configure(cnf, **kwargs)
        return super().configure(**kwargs)


class CTkButton(tb.Button):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        fg = kwargs.pop("fg_color", None)
        hv = kwargs.pop("hover_color", None)
        kwargs.pop("corner_radius", None)
        kwargs.pop("text_color", None)
        bd = kwargs.pop("border_width", None)
        kwargs.setdefault("bootstyle", _button_bootstyle(fg, bd, hv))
        kwargs.setdefault("padding", (12, 7))
        super().__init__(master, *args, **kwargs)

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if "fg_color" in kwargs or "hover_color" in kwargs or "border_width" in kwargs:
            fg = kwargs.pop("fg_color", None)
            hv = kwargs.pop("hover_color", None)
            bd = kwargs.pop("border_width", None)
            kwargs.setdefault("bootstyle", _button_bootstyle(fg, bd, hv))
        kwargs.setdefault("padding", (12, 7))
        kwargs.pop("corner_radius", None)
        kwargs.pop("text_color", None)
        if cnf:
            return super().configure(cnf, **kwargs)
        return super().configure(**kwargs)


class CTkEntry(tb.Entry):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_color", None)
        kwargs.pop("height", None)
        ph = kwargs.pop("placeholder_text", None)
        show_pw = kwargs.get("show") == "*"
        w = kwargs.pop("width", None)
        if w is not None:
            kwargs["width"] = _px_to_chars(int(w))
        kwargs.setdefault("bootstyle", "dark")
        super().__init__(master, *args, **kwargs)
        self._placeholder = ph if not show_pw else None
        if ph and not show_pw:
            self.insert(0, ph)
            self.bind("<FocusIn>", self._on_in, add="+")
            self.bind("<FocusOut>", self._on_out, add="+")
        self._ph_active = bool(ph and not show_pw)

    def _on_in(self, _e: Any = None) -> None:
        if self._placeholder and self._ph_active and self.get() == self._placeholder:
            self.delete(0, "end")
            self._ph_active = False

    def _on_out(self, _e: Any = None) -> None:
        if self._placeholder and not self.get().strip():
            self.delete(0, "end")
            self.insert(0, self._placeholder)
            self._ph_active = True

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        kwargs.pop("fg_color", None)
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_color", None)
        kwargs.pop("height", None)
        if "width" in kwargs and kwargs["width"] is not None:
            kwargs["width"] = _px_to_chars(int(kwargs["width"]))
        if cnf:
            return super().configure(cnf, **kwargs)
        return super().configure(**kwargs)


class CTkComboBox(tb.Combobox):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_color", None)
        kwargs.pop("button_color", None)
        kwargs.pop("button_hover_color", None)
        kwargs.pop("dropdown_font", None)
        kwargs.pop("height", None)
        var = kwargs.pop("variable", None)
        if var is not None:
            kwargs["textvariable"] = var
        vals = kwargs.pop("values", None)
        w = kwargs.pop("width", None)
        if w is not None:
            kwargs["width"] = _px_to_chars(int(w))
        kwargs.setdefault("bootstyle", "dark")
        super().__init__(master, *args, **kwargs)
        if vals is not None:
            super().configure(values=vals)
        self._entry = self

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if "variable" in kwargs:
            kwargs["textvariable"] = kwargs.pop("variable")
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_color", None)
        kwargs.pop("button_color", None)
        kwargs.pop("button_hover_color", None)
        kwargs.pop("dropdown_font", None)
        kwargs.pop("height", None)
        if "width" in kwargs and kwargs["width"] is not None:
            kwargs["width"] = _px_to_chars(int(kwargs["width"]))
        if cnf:
            return super().configure(cnf, **kwargs)
        return super().configure(**kwargs)


class CTkScrollableFrame(ScrolledFrame):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        kwargs.pop("corner_radius", None)
        kwargs.setdefault("autohide", True)
        super().__init__(master, *args, **kwargs)


class CTkTabview(tb.Frame):
    """Maps CTkTabview.add / .tab to a ttkbootstrap Notebook."""

    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        kwargs.pop("corner_radius", None)
        w = kwargs.pop("width", None)
        h = kwargs.pop("height", None)
        super().__init__(master, *args, **kwargs)
        self._nb = tb.Notebook(self, bootstyle="dark")
        self._nb.pack(fill="both", expand=True)
        if w:
            self.configure(width=w)
        if h:
            self.configure(height=h)
        self._tabs: dict[str, tb.Frame] = {}

    def add(self, name: str) -> None:
        f = tb.Frame(self._nb, padding=4)
        self._tabs[name] = f
        self._nb.add(f, text=name)

    def tab(self, name: str) -> tb.Frame:
        return self._tabs[name]


class CTkProgressBar(tb.Progressbar):
    """Maps CTk progress bar; ttk uses ``length`` (not pixel width/height like CTk)."""

    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("progress_color", None)
        kwargs.pop("height", None)  # ttk.Horizontal Progressbar has no height in px
        w = kwargs.pop("width", None)
        mode = kwargs.pop("mode", "determinate")
        kwargs["mode"] = mode
        kwargs.setdefault("bootstyle", "success-striped")
        if w is not None:
            kwargs.setdefault("length", max(80, int(w)))
        super().__init__(master, *args, **kwargs)
        self._mode = mode

    def start(self) -> None:
        try:
            super().start(10)
        except tk.TclError:
            pass

    def stop(self) -> None:
        try:
            super().stop()
        except tk.TclError:
            pass


class CTkTextbox(tb.Frame):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        kwargs.pop("border_color", None)
        kwargs.pop("border_width", None)
        kwargs.pop("text_color", None)
        h = int(kwargs.pop("height", 100) or 100)
        super().__init__(master, *args, **kwargs)
        lines = max(2, h // 16)
        self._txt = tk.Text(self, height=lines, wrap=tk.WORD, relief=tk.FLAT, padx=12, pady=7)
        self._txt.pack(fill="both", expand=True)

    def insert(self, *a: Any, **k: Any) -> Any:
        return self._txt.insert(*a, **k)

    def delete(self, *a: Any, **k: Any) -> Any:
        return self._txt.delete(*a, **k)

    def get(self, *a: Any, **k: Any) -> Any:
        return self._txt.get(*a, **k)

    def bind(self, *a: Any, **k: Any) -> Any:
        return self._txt.bind(*a, **k)

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if cnf:
            return self._txt.configure(cnf, **kwargs)
        return self._txt.configure(**kwargs)

    def focus_set(self) -> None:
        self._txt.focus_set()


class CTkCheckBox(tb.Checkbutton):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        kwargs.pop("hover_color", None)
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_width", None)
        kwargs.setdefault("bootstyle", "round-toggle")
        super().__init__(master, *args, **kwargs)


class CTkRadioButton(tb.Radiobutton):
    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        kwargs.pop("hover_color", None)
        kwargs.pop("corner_radius", None)
        kwargs.pop("border_width", None)
        kwargs.setdefault("bootstyle", "success-toolbutton")
        super().__init__(master, *args, **kwargs)


class CTkOptionMenu(CTkComboBox):
    """OptionMenu-like behavior via Combobox."""

    def __init__(self, master: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("state", "readonly")
        super().__init__(master, *args, **kwargs)


class CTkInputDialog:
    def __init__(self, text: str = "", title: str = "", **kwargs: Any) -> None:
        kwargs.pop("fg_color", None)
        self._text = text
        self._title = title
        self._show = kwargs.pop("show", None)

    def get_input(self) -> Optional[str]:
        mask = "*" if self._show == "*" else None
        return simpledialog.askstring(self._title, self._text, show=mask)


class CTkMessagebox:
    """Minimal replacement for CTkMessagebox with .get() returning button text."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        message: str = "",
        option_1: str = "OK",
        option_2: str | None = None,
        icon: str = "info",
        width: int = 400,
        height: int = 200,
        wraplength: int = 360,
        **kwargs: Any,
    ) -> None:
        del kwargs
        self._master = master
        self._title = title
        self._message = message
        self._option_1 = option_1
        self._option_2 = option_2
        self._icon = icon
        self._choice: str = option_1

        if master is not None:
            win = tb.Toplevel(master)
        else:
            win = tb.Window(themename=get_theme_name())
            _apply_global_theme(win)
        self._win = win
        win.title(title)
        if master is not None:
            win.transient(master)
        win.grab_set()
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        tb.Label(win, text=message, wraplength=wraplength, justify="center").pack(
            expand=True, fill="both", padx=12, pady=12
        )
        f = tb.Frame(win, padding=8)
        f.pack(fill="x")

        def _pick(s: str) -> None:
            self._choice = s
            win.destroy()

        tb.Button(
            f,
            text=option_1,
            bootstyle="info",
            padding=(12, 7),
            command=lambda: _pick(option_1),
        ).pack(side="left", padx=6, expand=True)
        if option_2:
            tb.Button(
                f,
                text=option_2,
                bootstyle="secondary",
                padding=(12, 7),
                command=lambda: _pick(option_2),
            ).pack(side="left", padx=6, expand=True)

        win.protocol("WM_DELETE_WINDOW", lambda: _pick(option_1))
        win.update_idletasks()
        w = max(320, width)
        h = max(160, height)
        win.geometry(f"{w}x{h}")

    def get(self) -> str:
        self._win.wait_window()
        return self._choice


# Export CTkMessagebox for module CTkMessagebox
__all__ = [
    "CTk",
    "CTkToplevel",
    "CTkFrame",
    "CTkLabel",
    "CTkButton",
    "CTkEntry",
    "CTkComboBox",
    "CTkScrollableFrame",
    "CTkTabview",
    "CTkProgressBar",
    "CTkTextbox",
    "CTkCheckBox",
    "CTkRadioButton",
    "CTkOptionMenu",
    "CTkInputDialog",
    "CTkImage",
    "CTkMessagebox",
    "StringVar",
    "BooleanVar",
    "IntVar",
    "DoubleVar",
    "set_appearance_mode",
    "set_default_color_theme",
    "set_theme_name",
    "get_theme_name",
    "filedialog",
    "messagebox",
]
