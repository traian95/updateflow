"""
Punct de intrare NaturenFlow. Resurse: `ofertare.paths.get_resource_path` (onedir: dirname(sys.executable)).

După logging, procesul își setează `os.chdir(get_app_dir())` astfel încât `os.getcwd()` să fie
rădăcina aplicației. Lansarea `updater.exe` cu UAC: `ofertare.elevation.launch_updater_elevated`.
"""
import logging
import os

from ofertare.elevation import launch_updater_elevated
from ofertare.paths import get_app_dir, get_resource_path
from ofertare.ui import run_app

__all__ = ["main", "get_app_dir", "get_resource_path", "launch_updater_elevated"]


def _setup_logging() -> None:
    """Configurează logging global: scrie în ofertare.log (lângă exe sau în AppData dacă nu e scriibil)."""
    try:
        log_dir = os.path.join(get_app_dir(), "utils", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "ofertare.log")
        if not os.access(log_dir, os.W_OK):
            appdata = os.environ.get("APPDATA", "").strip()
            log_dir = os.path.join(appdata, "Soft Ofertare Usi") if appdata else os.path.expanduser("~")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "ofertare.log")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)
    except Exception:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def main() -> None:
    _setup_logging()
    try:
        os.chdir(get_app_dir())
    except OSError:
        pass
    # Verificarea și instalarea update (GitHub Releases) se fac din UI, după confirmare CTkMessagebox.
    run_app()


if __name__ == "__main__":
    main()

