import logging
import os

from ofertare.ui import run_app
from ofertare.updater import check_for_updates, get_local_version, install_zip_update


def _setup_logging() -> None:
    """Configurează logging global: scrie în ofertare.log (lângă exe sau în AppData dacă nu e scriibil)."""
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils", "logs")
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


def check_and_start_auto_update() -> bool:
    """
    Returneaza True daca a pornit updater-ul extern si aplicatia trebuie inchisa imediat.
    """
    logger = logging.getLogger(__name__)

    try:
        info = check_for_updates(get_local_version())
        if not info.get("update_available"):
            return False
        download_url = str(info.get("download_url") or "").strip()
        version_cloud = str(info.get("version_cloud") or "").strip()
        if not download_url or not version_cloud:
            return False
        logger.info("Update gasit (%s -> %s).", get_local_version(), version_cloud)
        result = install_zip_update(
            download_url=download_url,
            expected_sha256=str(info.get("sha256") or ""),
            new_version=version_cloud,
        )
        return bool(result.get("ok"))
    except Exception as exc:
        logger.exception("Auto-update esuat: %s", exc)
        return False


def main() -> None:
    _setup_logging()
    if check_and_start_auto_update():
        os._exit(0)
    run_app()


if __name__ == "__main__":
    main()

