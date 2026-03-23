from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)


def fetch_bnr_eur_rate(timeout_s: int = 5) -> float | None:
    try:
        resp = requests.get("https://www.bnr.ro/nbrfxrates.xml", timeout=timeout_s)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        namespace = {"bnr": "http://www.bnr.ro/xsd"}
        for rate in root.findall(".//bnr:Rate", namespace):
            if rate.get("currency") == "EUR":
                return float(rate.text)
    except Exception:
        logger.warning("BNR curs EUR indisponibil", exc_info=True)
        return None
    return None

