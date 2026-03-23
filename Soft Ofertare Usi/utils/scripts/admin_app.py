def _preload_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    import os
    import sys
    from pathlib import Path

    load_dotenv()
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(os.path.dirname(sys.executable)))
    roots.append(Path(__file__).resolve().parent.parent.parent)
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        roots.append(Path(appdata) / "Soft Ofertare Usi")
    seen = set()
    for r in roots:
        try:
            r = r.resolve()
        except Exception:
            continue
        if r in seen:
            continue
        seen.add(r)
        p = r / ".env"
        if p.is_file():
            load_dotenv(p, override=False)


_preload_env_files()

from ofertare.admin_ui import AdminApp, AdminLoginWindow


def resource_path(relative_path):
    import sys
    import os
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


if __name__ == "__main__":
    def on_login_ok():
        app = AdminApp()
        app.mainloop()

    login = AdminLoginWindow(on_success=on_login_ok)
    login.mainloop()

