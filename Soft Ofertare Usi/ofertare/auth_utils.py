"""Funcții partajate pentru autentificare și useri (hash parolă, generare username)."""
from __future__ import annotations

import hashlib
import re


def hash_parola(parola: str) -> str:
    """Hash parolă (același secret folosit la login și la creare user)."""
    return hashlib.sha256(("ofertare_salt_" + (parola or "")).encode()).hexdigest()


def username_din_nume_complet(nume_complet: str) -> str:
    """Generează username: Prenume + initiala numelui de familie (ex: Razvan Teodorescu -> Razvant)."""
    s = (nume_complet or "").strip()
    parts = re.sub(r"\s+", " ", s).split()
    if not parts:
        return ""
    prenume = parts[0]
    if len(parts) == 1:
        return prenume
    initiala = (parts[-1][:1] or "").lower()
    return prenume + initiala
