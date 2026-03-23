# -*- coding: utf-8 -*-
"""Cale fixă pentru loguri NDJSON de debug (evită __file__ / PyInstaller)."""
from __future__ import annotations

import json
import os
import time

_LOG_PATH: str | None = None
_PRINTED_PATH = False


def get_agent_debug_log_path() -> str:
    global _LOG_PATH
    if _LOG_PATH:
        return _LOG_PATH
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    folder = os.path.join(base, "Soft Ofertare Usi")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = base
    _LOG_PATH = os.path.join(folder, "debug-88fd1f.log")
    return _LOG_PATH


def append_agent_debug_ndjson(
    *,
    session_id: str,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
) -> None:
    global _PRINTED_PATH
    path = get_agent_debug_log_path()
    payload = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        if not _PRINTED_PATH:
            _PRINTED_PATH = True
            print(f"[Agent debug] Log NDJSON: {path}")
    except Exception:
        pass
