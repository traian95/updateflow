import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

import requests
from supabase import Client, create_client

TABLE_PRODUSE = "produse"
TABLE_CLIENTI = "clienti"
TABLE_OFERTE = "oferte"
TABLE_SCHEMA_VERSION = "schema_version"
TABLE_USERS = "users"
TABLE_SYNC_STATE = "sync_state"
SCHEMA_VERSION_CURRENT = 9

# Tocuri „Fix 90 MM” — prețuri EUR listă (fără TVA); conversia globală în LEI + TVA rămâne în ofertare.
TOCURI_FIX90_TIP = "Fix 90 MM"
TOCURI_FIX90_DIM = "90 MM"


def _norm_toc_dimensiune(d: str) -> str:
    return str(d or "").replace(" ", "").strip().lower()


def _is_tocuri_fix90_mm(categorie: str, furnizor: str, tip_toc: str, dimensiune: str) -> bool:
    if str(categorie or "") != "Tocuri" or str(furnizor or "") not in ("Stoc", "Erkado"):
        return False
    if str(tip_toc or "").strip() != TOCURI_FIX90_TIP:
        return False
    return _norm_toc_dimensiune(dimensiune) == _norm_toc_dimensiune(TOCURI_FIX90_DIM)


def _tocuri_fix90_erkado_rows() -> list[tuple[str, str, float]]:
    """(decor, finisaj, pret_eur) — finisaje aliniate cu maparea Erkado (CPL/ST PREMIUM, CPL 0.2, …)."""
    return [
        ("", "GREKO", 78.0),
        ("", "CPL/ST PREMIUM", 86.0),
        ("", "CPL 0.2", 100.0),
        ("", "LACUIT", 173.0),
    ]


def _coerce_detalii_str(value: Any) -> str:
    """`detalii_oferta` trebuie să fie text; dacă primește dict/listă, o serializăm (evită chei extra la nivel de rând)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _build_oferte_insert_row(
    id_client: int,
    detalii_oferta: Any,
    total_lei: float,
    data_oferta: str,
    nume_client_temp: str,
    utilizator_creat: str,
    discount_proc: int,
    curs_euro: float,
    safe_mode_enabled: int,
) -> dict[str, Any]:
    """Exact coloanele din `public.oferte` — fără chei suplimentare (PGRST204)."""
    return {
        "id_client": int(id_client),
        "detalii_oferta": _coerce_detalii_str(detalii_oferta),
        "total_lei": float(total_lei),
        "data_oferta": str(data_oferta or ""),
        "nume_client_temp": str(nume_client_temp or ""),
        "utilizator_creat": str(utilizator_creat or ""),
        "discount_proc": int(discount_proc),
        "curs_euro": float(curs_euro),
        "safe_mode_enabled": 1 if safe_mode_enabled else 0,
    }


def _build_oferte_update_full_row(
    id_client: int,
    detalii_oferta: Any,
    total_lei: float,
    data_oferta: str,
    nume_client_temp: str,
    discount_proc: int,
    curs_euro: float,
    safe_mode_enabled: int,
) -> dict[str, Any]:
    return {
        "id_client": int(id_client),
        "detalii_oferta": _coerce_detalii_str(detalii_oferta),
        "total_lei": float(total_lei),
        "data_oferta": str(data_oferta or ""),
        "nume_client_temp": str(nume_client_temp or ""),
        "discount_proc": int(discount_proc),
        "curs_euro": float(curs_euro),
        "safe_mode_enabled": 1 if safe_mode_enabled else 0,
    }
SUPABASE_URL = "https://ingtefnrfjjribocqtgy.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImluZ3RlZm5yZmpqcmlib2NxdGd5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQwMjYyMjIsImV4cCI6MjA4OTYwMjIyMn0.mNinufQ1lIu02SXENo4LR1bvx3iRo5PuiwifwRDvEpQ"

_LOCK = threading.RLock()
_SUPA: Optional[Client] = None
_CACHE: dict[str, list[dict[str, Any]]] = {}
_CACHE_TS: dict[str, datetime] = {}
_CACHE_TTL_S = 20
# PostgREST limitează implicit răspunsul la max. 1000 rânduri; paginăm ca să nu lipsească produse.
_ROWS_PAGE_SIZE = 1000
VERBOSE_SYNC_LOG = True


def _verbose_log(message: str, payload: Any = None) -> None:
    if not VERBOSE_SYNC_LOG:
        return
    try:
        if payload is None:
            print(f"[SYNC] {message}")
        else:
            print(f"[SYNC] {message}: {payload}")
    except Exception:
        pass


def _get_supabase_client() -> Client:
    global _SUPA
    with _LOCK:
        if _SUPA is not None:
            return _SUPA
        url = SUPABASE_URL.strip()
        key = SUPABASE_KEY.strip()
        if not url or not key:
            raise RuntimeError("Lipsesc SUPABASE_URL/SUPABASE_KEY in configurarea aplicatiei.")
        _SUPA = create_client(url, key)
        return _SUPA


def _rows(table: str, force: bool = False) -> list[dict[str, Any]]:
    now = datetime.now()
    if not force and table in _CACHE and table in _CACHE_TS and (now - _CACHE_TS[table]).total_seconds() < _CACHE_TTL_S:
        return _CACHE[table]
    client = _get_supabase_client()
    data: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = (
            client.table(table)
            .select("*")
            .range(offset, offset + _ROWS_PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        data.extend(batch)
        if len(batch) < _ROWS_PAGE_SIZE:
            break
        offset += _ROWS_PAGE_SIZE
    _CACHE[table] = data
    _CACHE_TS[table] = now
    return data


def _invalidate(*tables: str) -> None:
    for t in tables:
        _CACHE.pop(t, None)
        _CACHE_TS.pop(t, None)


def _supabase_rest_v1_root() -> str:
    return f"{SUPABASE_URL.strip().rstrip('/')}/rest/v1"


def _postgrest_headers(*, return_representation: bool = True) -> dict[str, str]:
    k = SUPABASE_KEY.strip()
    h: dict[str, str] = {
        "apikey": k,
        "Authorization": f"Bearer {k}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if return_representation:
        h["Prefer"] = "return=representation"
    return h


def _postgrest_headers_minimal() -> dict[str, str]:
    k = SUPABASE_KEY.strip()
    return {
        "apikey": k,
        "Authorization": f"Bearer {k}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Prefer": "return=minimal",
    }


def _parse_new_row_id_from_postgrest_headers(resp: requests.Response) -> Optional[int]:
    loc = resp.headers.get("Content-Location") or resp.headers.get("Location") or ""
    m = re.search(r"id=eq\.(\d+)", loc)
    if m:
        return int(m.group(1))
    return None


def _postgrest_insert_oferte_row(payload: dict[str, Any]) -> dict[str, Any]:
    """POST direct la PostgREST; `select=id` + fallback `return=minimal` (evită PGRST204 pe cache cu coloane fantomă la RETURN)."""
    url = f"{_supabase_rest_v1_root()}/{TABLE_OFERTE}"
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    _verbose_log("INSERT oferte RAW JSON prefix", body[:500])

    r = requests.post(
        url,
        params={"select": "id"},
        headers=_postgrest_headers(return_representation=True),
        data=body.encode("utf-8"),
        timeout=90,
    )
    if r.status_code < 400:
        if (r.text or "").strip():
            try:
                data = r.json()
                if isinstance(data, list) and data:
                    return dict(data[0])
            except Exception:
                pass
        rid = _parse_new_row_id_from_postgrest_headers(r)
        if rid is not None:
            return {"id": rid}
        return {}

    err_first = (r.text or "").strip()
    _verbose_log("INSERT oferte select=id failed, retry minimal", {"status": r.status_code, "body": err_first[:400]})

    r2 = requests.post(
        url,
        headers=_postgrest_headers_minimal(),
        data=body.encode("utf-8"),
        timeout=90,
    )
    if r2.status_code >= 400:
        raise RuntimeError(err_first or (r2.text or "").strip() or f"HTTP {r2.status_code}")
    rid = _parse_new_row_id_from_postgrest_headers(r2)
    if rid is None:
        raise RuntimeError(
            "INSERT oferte: nu s-a putut determina id-ul noului rând. "
            f"Prima încercare: {err_first[:500]}"
        )
    return {"id": rid}


def _postgrest_patch_oferte_row(offer_id: int, payload: dict[str, Any]) -> None:
    url = f"{_supabase_rest_v1_root()}/{TABLE_OFERTE}"
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    _verbose_log("PATCH oferte RAW JSON prefix", body[:500])
    params = {"id": f"eq.{int(offer_id)}", "select": "id"}
    r = requests.patch(
        url,
        headers=_postgrest_headers(return_representation=True),
        params=params,
        data=body.encode("utf-8"),
        timeout=90,
    )
    if r.status_code >= 400:
        err_first = (r.text or "").strip()
        _verbose_log("PATCH oferte select=id failed, retry minimal", {"status": r.status_code, "body": err_first[:400]})
        r2 = requests.patch(
            url,
            headers=_postgrest_headers_minimal(),
            params={"id": f"eq.{int(offer_id)}"},
            data=body.encode("utf-8"),
            timeout=90,
        )
        if r2.status_code >= 400:
            raise RuntimeError(err_first or (r2.text or "").strip() or f"HTTP {r2.status_code}")


class CloudCursor:
    def __init__(self) -> None:
        self._rows: list[tuple] = []

    def execute(self, query: str, params: Iterable[Any] = ()) -> None:
        q = " ".join((query or "").split()).lower()
        p = list(params or [])
        if "from oferte" in q and "where nume_client_temp = ?" in q and "data_oferta = ?" in q:
            nume, data = str(p[0]), str(p[1])
            user = str(p[2]) if len(p) > 2 else None
            rows = [r for r in _rows(TABLE_OFERTE) if str(r.get("nume_client_temp") or "") == nume and str(r.get("data_oferta") or "") == data]
            if user is not None:
                rows = [r for r in rows if str(r.get("utilizator_creat") or "") == user]
            rows.sort(key=lambda r: int(r.get("id") or 0), reverse=True)
            self._rows = [(rows[0].get("id"),)] if rows else []
            return
        if "select id, data_oferta from oferte" in q and "where nume_client_temp = ?" in q:
            nume = str(p[0])
            rows = [r for r in _rows(TABLE_OFERTE) if str(r.get("nume_client_temp") or "") == nume]
            rows.sort(key=lambda r: int(r.get("id") or 0), reverse=True)
            self._rows = [(r.get("id"), r.get("data_oferta")) for r in rows[:3]]
            return
        self._rows = []

    def fetchone(self) -> Optional[tuple]:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


@dataclass
class DbHandles:
    conn: Any
    cursor: CloudCursor


def open_db(db_path: str) -> DbHandles:
    return DbHandles(conn=_get_supabase_client(), cursor=CloudCursor())


def _alter_safe(cursor: Any, conn: Any, sql: str) -> None:
    return


def init_schema(cursor: Any, conn: Any) -> None:
    return


def execute(cursor: CloudCursor, query: str, params: Iterable[Any] = ()) -> None:
    cursor.execute(query, params)


def fetchone(cursor: CloudCursor) -> Optional[tuple]:
    return cursor.fetchone()


def fetchall(cursor: CloudCursor) -> list[tuple]:
    return cursor.fetchall()


def _like(value: str, pattern: str) -> bool:
    return pattern.replace("%", "").lower() in (value or "").lower()


def _parse_offer_date(value: str):
    s = str(value or "").strip()
    if not s:
        return None
    token = s.split(" ", 1)[0]
    months_ro = {
        "ianuarie": 1,
        "februarie": 2,
        "martie": 3,
        "aprilie": 4,
        "mai": 5,
        "iunie": 6,
        "iulie": 7,
        "august": 8,
        "septembrie": 9,
        "octombrie": 10,
        "noiembrie": 11,
        "decembrie": 12,
    }
    if "-" in token:
        parts = token.split("-")
        if len(parts) == 2:
            try:
                y = int(parts[0])
                m = months_ro.get(parts[1].strip().lower())
                if m:
                    return datetime(y, m, 1).date()
            except Exception:
                pass
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            pass
    return None


def get_client_by_id(cursor, client_id: int):
    for r in _rows(TABLE_CLIENTI):
        if int(r.get("id") or 0) == int(client_id):
            return (r.get("nume"), r.get("telefon"), r.get("adresa"), r.get("email") or "")
    return None


def get_client_by_name(cursor, nume: str):
    for r in _rows(TABLE_CLIENTI):
        if str(r.get("nume") or "") == nume:
            return (r.get("nume"), r.get("telefon"), r.get("adresa"), r.get("email") or "")
    return None


def get_client_id_by_name(cursor, nume: str):
    for r in _rows(TABLE_CLIENTI):
        if str(r.get("nume") or "") == nume:
            return int(r.get("id") or 0)
    return None


def get_all_clienti_telefon(cursor):
    return [(r.get("nume"), r.get("telefon")) for r in _rows(TABLE_CLIENTI) if str(r.get("telefon") or "").strip()]


def get_clienti_with_oferte_count(cursor, nume_like: str, data_min: Optional[str] = None, utilizator_creat: Optional[str] = None):
    oferte = _rows(TABLE_OFERTE)
    offer_counts: dict[int, int] = {}
    for o in oferte:
        if utilizator_creat and str(o.get("utilizator_creat") or "") != utilizator_creat:
            continue
        cid = int(o.get("id_client") or 0)
        offer_counts[cid] = offer_counts.get(cid, 0) + 1
    out = []
    for c in _rows(TABLE_CLIENTI):
        if not _like(str(c.get("nume") or ""), nume_like):
            continue
        if data_min and str(c.get("data_creare") or "") < data_min:
            continue
        cid = int(c.get("id") or 0)
        cnt = offer_counts.get(cid, 0)
        out.append((c.get("id"), c.get("nume"), c.get("adresa"), c.get("telefon"), cnt))
    out.sort(key=lambda x: int(x[0] or 0), reverse=True)
    return out


def insert_client(conn, cursor, nume: str, telefon: str, adresa: str, email: str, data_creare: str) -> int:
    payload = {"nume": nume, "telefon": telefon, "adresa": adresa, "email": email, "data_creare": data_creare}
    _verbose_log("INSERT clienti payload", payload)
    started = time.perf_counter()
    res = _get_supabase_client().table(TABLE_CLIENTI).insert(payload).execute()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _verbose_log("INSERT clienti response", {"elapsed_ms": elapsed_ms, "data": res.data, "count": res.count})
    _invalidate(TABLE_CLIENTI)
    return int((res.data or [{}])[0].get("id") or 0)


def get_offers_by_client(cursor, client_id: int, utilizator_creat: Optional[str] = None):
    rows = [o for o in _rows(TABLE_OFERTE) if int(o.get("id_client") or 0) == int(client_id)]
    if utilizator_creat:
        rows = [o for o in rows if str(o.get("utilizator_creat") or "") == utilizator_creat]
    rows.sort(key=lambda r: int(r.get("id") or 0), reverse=True)
    return [(r.get("id"), r.get("data_oferta"), r.get("total_lei"), r.get("detalii_oferta"), r.get("avans_incasat")) for r in rows]


def get_offer_by_id(cursor, offer_id: int):
    for r in _rows(TABLE_OFERTE):
        if int(r.get("id") or 0) == int(offer_id):
            return (r.get("avans_incasat"),)
    return None


def get_istoric_oferte(
    cursor,
    nume_like: str,
    id_egal: Optional[int] = None,
    utilizator_creat: Optional[str] = None,
    utilizator_filter: Optional[str] = None,
    data_start: Optional[str] = None,
    data_end: Optional[str] = None,
):
    d_start = _parse_offer_date(data_start) if data_start else None
    d_end = _parse_offer_date(data_end) if data_end else None
    user_filter_norm = str(utilizator_filter or "").strip().lower()
    out = []
    for r in _rows(TABLE_OFERTE):
        ok = _like(str(r.get("nume_client_temp") or ""), nume_like) or (id_egal is not None and int(r.get("id") or 0) == int(id_egal))
        if not ok:
            continue
        user_created = str(r.get("utilizator_creat") or "").strip()
        if utilizator_creat and user_created.lower() != str(utilizator_creat).strip().lower():
            continue
        if user_filter_norm and user_created.lower() != user_filter_norm:
            continue
        if d_start or d_end:
            offer_date = _parse_offer_date(r.get("data_oferta"))
            if offer_date is None:
                continue
            if d_start and offer_date < d_start:
                continue
            if d_end and offer_date > d_end:
                continue
        out.append(
            (
                r.get("id"),
                r.get("nume_client_temp"),
                r.get("total_lei"),
                r.get("data_oferta"),
                r.get("detalii_oferta"),
                r.get("avans_incasat"),
                r.get("utilizator_creat"),
            )
        )
    out.sort(key=lambda x: int(x[0] or 0), reverse=True)
    return out


def insert_offer(conn, cursor, id_client: int, detalii_oferta: str, total_lei: float, data_oferta: str, nume_client_temp: str, utilizator_creat: str, discount_proc: int, curs_euro: float, safe_mode_enabled: int = 1) -> int:
    payload = _build_oferte_insert_row(
        id_client,
        detalii_oferta,
        total_lei,
        data_oferta,
        nume_client_temp,
        utilizator_creat,
        discount_proc,
        curs_euro,
        safe_mode_enabled,
    )
    _verbose_log("INSERT oferte payload keys", list(payload.keys()))
    _verbose_log("INSERT oferte payload", payload)
    started = time.perf_counter()
    row = _postgrest_insert_oferte_row(payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _verbose_log("INSERT oferte response", {"elapsed_ms": elapsed_ms, "data": row})
    _invalidate(TABLE_OFERTE)
    return int(row.get("id") or 0)


def update_avans(conn, cursor, offer_id: int, value: int) -> None:
    _get_supabase_client().table(TABLE_OFERTE).update({"avans_incasat": value}).eq("id", offer_id).execute()
    _invalidate(TABLE_OFERTE)


def update_offer_detalii(conn, cursor, offer_id: int, detalii_oferta: str) -> None:
    payload = {"detalii_oferta": _coerce_detalii_str(detalii_oferta)}
    _verbose_log("UPDATE oferte payload", {"id": offer_id, **payload})
    started = time.perf_counter()
    res = _get_supabase_client().table(TABLE_OFERTE).update(payload).eq("id", offer_id).execute()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _verbose_log("UPDATE oferte response", {"elapsed_ms": elapsed_ms, "data": res.data, "count": res.count})
    _invalidate(TABLE_OFERTE)


def _fetch_offer_row_by_id(offer_id: int) -> Optional[dict[str, Any]]:
    """O singură ofertă direct din PostgREST (fără cache listă completă)."""
    try:
        res = (
            _get_supabase_client()
            .table(TABLE_OFERTE)
            .select("*")
            .eq("id", int(offer_id))
            .limit(1)
            .execute()
        )
        row = (res.data or [None])[0]
        return dict(row) if row else None
    except Exception:
        return None


def get_offer_snapshot(cursor, offer_id: int, force_refresh: bool = False) -> Optional[dict[str, Any]]:
    if force_refresh:
        live = _fetch_offer_row_by_id(offer_id)
        if live is not None:
            return live
    for r in _rows(TABLE_OFERTE):
        if int(r.get("id") or 0) == int(offer_id):
            return dict(r)
    return None


def _detalii_text_matches(stored: str, expected: str) -> bool:
    if (stored or "").strip() == (expected or "").strip():
        return True
    try:
        return json.loads(stored or "null") == json.loads(expected or "null")
    except (json.JSONDecodeError, TypeError, ValueError):
        return False


def _offer_row_matches_full_update(
    row: dict[str, Any],
    *,
    detalii_oferta: str,
    total_lei: float,
    data_oferta: str,
    nume_client_temp: str,
    id_client: int,
    discount_proc: int,
    curs_euro: float,
    safe_mode_enabled: int,
) -> bool:
    if int(row.get("id_client") or 0) != int(id_client):
        return False
    if str(row.get("data_oferta") or "").strip() != str(data_oferta or "").strip():
        return False
    if str(row.get("nume_client_temp") or "").strip() != str(nume_client_temp or "").strip():
        return False
    if int(row.get("discount_proc") or 0) != int(discount_proc):
        return False
    try:
        if abs(float(row.get("total_lei") or 0) - float(total_lei)) > 0.05:
            return False
    except (TypeError, ValueError):
        return False
    try:
        if abs(float(row.get("curs_euro") or 0) - float(curs_euro)) > 0.001:
            return False
    except (TypeError, ValueError):
        return False
    if int(row.get("safe_mode_enabled") or 0) != (1 if safe_mode_enabled else 0):
        return False
    return _detalii_text_matches(str(row.get("detalii_oferta") or ""), detalii_oferta)


def update_offer_full(
    conn,
    cursor,
    offer_id: int,
    id_client: int,
    detalii_oferta: str,
    total_lei: float,
    data_oferta: str,
    nume_client_temp: str,
    discount_proc: int,
    curs_euro: float,
    safe_mode_enabled: int = 1,
) -> None:
    """Actualizează oferta existentă fără duplicat; `utilizator_creat` rămâne neschimbat."""
    detalii_norm = _coerce_detalii_str(detalii_oferta)
    payload = _build_oferte_update_full_row(
        id_client,
        detalii_norm,
        total_lei,
        data_oferta,
        nume_client_temp,
        discount_proc,
        curs_euro,
        safe_mode_enabled,
    )
    oid = int(offer_id)
    _verbose_log("UPDATE oferte (full) payload", {"id": oid, **payload})
    started = time.perf_counter()
    _postgrest_patch_oferte_row(oid, payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _verbose_log("UPDATE oferte (full) done", {"elapsed_ms": elapsed_ms})
    _invalidate(TABLE_OFERTE)

    verified = False
    for attempt in range(6):
        if attempt:
            time.sleep(0.08 * attempt)
        verify = _fetch_offer_row_by_id(oid)
        if verify and _offer_row_matches_full_update(
            verify,
            detalii_oferta=detalii_norm,
            total_lei=total_lei,
            data_oferta=data_oferta,
            nume_client_temp=nume_client_temp,
            id_client=id_client,
            discount_proc=discount_proc,
            curs_euro=curs_euro,
            safe_mode_enabled=safe_mode_enabled,
        ):
            verified = True
            break
    if not verified:
        raise RuntimeError(
            "UPDATE oferte: modificarea nu s-a regăsit în baza de date după salvare. "
            "Cauze frecvente: politici RLS în Supabase care blochează UPDATE sau SELECT pe «oferte», "
            "sau ID ofertă inexistent. Verifică în dashboard Supabase → Authentication → Policies."
        )


def delete_offer(conn, cursor, offer_id: int) -> None:
    _get_supabase_client().table(TABLE_OFERTE).delete().eq("id", offer_id).execute()
    _invalidate(TABLE_OFERTE)


def get_user_for_login(cursor, username: str):
    u = username.strip().lower()
    # Login-ul trebuie sa fie live: fortam citirea directa din Supabase la fiecare incercare.
    for r in _rows(TABLE_USERS, force=True):
        if str(r.get("username") or "").strip().lower() == u:
            return (r.get("password_hash"), r.get("approved"), r.get("username"), r.get("blocked", 0))
    return None


def user_exists_by_username(cursor, username: str) -> bool:
    u = username.strip().lower()
    return any(str(r.get("username") or "").strip().lower() == u for r in _rows(TABLE_USERS))


def insert_user(conn, cursor, nume_complet: str, username: str, password_hash: str, approved: int = 0, telefon_contact: str = "") -> int:
    res = _get_supabase_client().table(TABLE_USERS).insert({"nume_complet": nume_complet.strip(), "username": username.strip(), "password_hash": password_hash, "approved": approved, "created_at": datetime.now().isoformat(), "telefon_contact": (telefon_contact or "").strip()}).execute()
    _invalidate(TABLE_USERS)
    return int((res.data or [{}])[0].get("id") or 0)


def get_pending_users(cursor):
    rows = [r for r in _rows(TABLE_USERS) if int(r.get("approved") or 0) == 0]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return [(r.get("id"), r.get("nume_complet"), r.get("username"), r.get("created_at")) for r in rows]


def set_user_approved(conn, cursor, user_id: int, approved: int = 1) -> None:
    _get_supabase_client().table(TABLE_USERS).update({"approved": approved}).eq("id", user_id).execute()
    _invalidate(TABLE_USERS)


def set_user_blocked(conn, cursor, user_id: int, blocked: int = 1) -> None:
    _get_supabase_client().table(TABLE_USERS).update({"blocked": blocked}).eq("id", user_id).execute()
    _invalidate(TABLE_USERS)


def delete_user(conn, cursor, user_id: int) -> None:
    _get_supabase_client().table(TABLE_USERS).delete().eq("id", user_id).execute()
    _invalidate(TABLE_USERS)


def get_user_privileges(cursor, username: str):
    u = username.strip().lower()
    for r in _rows(TABLE_USERS):
        if str(r.get("username") or "").strip().lower() == u:
            return (int(r.get("can_modify_curs", 1) or 1), int(r.get("max_discount", 15) or 15), int(r.get("can_delete_offers", 1) or 1), int(r.get("can_delete_clients", 0) or 0), int(r.get("can_dev_mode", 0) or 0))
    return None


def get_user_can_see_all(cursor, username: str) -> int:
    u = username.strip().lower()
    for r in _rows(TABLE_USERS):
        if str(r.get("username") or "").strip().lower() == u:
            return 1 if int(r.get("can_see_all", 0) or 0) else 0
    return 0


def get_user_full_name(cursor, username: str):
    u = username.strip().lower()
    for r in _rows(TABLE_USERS):
        if str(r.get("username") or "").strip().lower() == u:
            v = str(r.get("nume_complet") or "").strip()
            return v or None
    return None


def get_user_contact_phone(cursor, username: str):
    u = username.strip().lower()
    for r in _rows(TABLE_USERS):
        if str(r.get("username") or "").strip().lower() == u:
            v = str(r.get("telefon_contact") or "").strip()
            return v or None
    return None


def get_approved_users_with_privileges(cursor):
    rows = [r for r in _rows(TABLE_USERS) if int(r.get("approved") or 0) == 1]
    rows.sort(key=lambda r: str(r.get("username") or ""))
    return [(r.get("id"), r.get("nume_complet"), r.get("username"), int(r.get("can_modify_curs", 1) or 1), int(r.get("max_discount", 15) or 15), int(r.get("can_delete_offers", 1) or 1), int(r.get("can_delete_clients", 0) or 0), int(r.get("can_dev_mode", 0) or 0), int(r.get("blocked", 0) or 0)) for r in rows]


def update_user_privileges(conn, cursor, user_id: int, can_modify_curs: int, max_discount: int, can_delete_offers: int, can_delete_clients: int, can_dev_mode: int = 0) -> None:
    _get_supabase_client().table(TABLE_USERS).update({"can_modify_curs": can_modify_curs, "max_discount": max(0, min(50, max_discount)), "can_delete_offers": can_delete_offers, "can_delete_clients": can_delete_clients, "can_dev_mode": 1 if can_dev_mode else 0}).eq("id", user_id).execute()
    _invalidate(TABLE_USERS)


def _produse():
    return _rows(TABLE_PRODUSE)


def get_categorii_distinct(cursor):
    return sorted({str(r.get("categorie") or "").strip() for r in _produse() if str(r.get("categorie") or "").strip() and str(r.get("categorie") or "").lower() != "nan"})


def search_produse(cursor, termen: str, limit: int = 80):
    rows = _produse()
    if termen and termen.strip():
        query = termen.strip().lower()
        tokens = [t for t in query.split() if t]
        search_cols = ("categorie", "furnizor", "colectie", "model", "decor", "finisaj", "tip_toc", "dimensiune")

        matched = []
        for r in rows:
            col_vals = {k: str(r.get(k) or "").strip().lower() for k in search_cols}
            # AND între cuvinte, OR între coloane.
            if not all(any(tok in col_vals[k] for k in search_cols) for tok in tokens):
                continue

            model = col_vals.get("model", "")
            colectie = col_vals.get("colectie", "")

            exact_model = int(model == query) if query else 0
            exact_colectie = int(colectie == query) if query else 0
            exact_model_token = int(any(tok == model for tok in tokens))
            exact_colectie_token = int(any(tok == colectie for tok in tokens))
            starts_model = int(any(model.startswith(tok) for tok in tokens if tok))
            starts_colectie = int(any(colectie.startswith(tok) for tok in tokens if tok))

            matched.append(
                (
                    exact_model,
                    exact_colectie,
                    exact_model_token,
                    exact_colectie_token,
                    starts_model,
                    starts_colectie,
                    r,
                )
            )

        # Prioritizare: potriviri exacte în model/colectie primele, apoi prefixe, apoi ordine alfa.
        matched.sort(
            key=lambda x: (
                -x[0], -x[1], -x[2], -x[3], -x[4], -x[5],
                str(x[6].get("categorie") or ""),
                str(x[6].get("colectie") or ""),
                str(x[6].get("model") or ""),
            )
        )
        rows = [x[6] for x in matched]
    else:
        rows = []
    rows = rows[:limit]
    # Ordine afișare: Categorie, Furnizor, Colectie, Model, Finisaj, Decor, apoi tip_toc, dimensiune, preț
    return [
        (
            r.get("categorie"),
            r.get("furnizor"),
            r.get("colectie"),
            r.get("model"),
            r.get("finisaj") or "",
            r.get("decor"),
            r.get("tip_toc") or "",
            r.get("dimensiune") or "",
            r.get("pret"),
        )
        for r in rows
    ]


def get_colectii_produse(cursor, categorie: str, furnizor: str, use_tip_toc: bool = False):
    rows = [r for r in _produse() if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == furnizor]
    k = "tip_toc" if use_tip_toc else "colectie"
    out = [x for x in sorted({str(r.get(k) or "") for r in rows}) if x]
    if categorie == "Tocuri" and use_tip_toc and furnizor in ("Stoc", "Erkado") and TOCURI_FIX90_TIP not in out:
        out = sorted(set(out) | {TOCURI_FIX90_TIP})
    return out


def get_modele_produse(cursor, categorie: str, furnizor: str, colectie_or_tip_toc: str, use_tip_toc: bool = False):
    rows = [r for r in _produse() if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == furnizor]
    if use_tip_toc:
        base = [x for x in sorted({str(r.get("dimensiune") or "") for r in rows if str(r.get("tip_toc") or "") == colectie_or_tip_toc}) if x]
        if (
            categorie == "Tocuri"
            and furnizor in ("Stoc", "Erkado")
            and str(colectie_or_tip_toc or "").strip() == TOCURI_FIX90_TIP
        ):
            if TOCURI_FIX90_DIM not in base:
                base = sorted(set(base) | {TOCURI_FIX90_DIM})
        return base
    return [x for x in sorted({str(r.get("model") or "") for r in rows if str(r.get("colectie") or "") == colectie_or_tip_toc})]


def get_finisaje_produse(cursor, categorie: str, furnizor: str, colectie: str):
    rows = [
        r for r in _produse()
        if str(r.get("categorie") or "") == categorie
        and str(r.get("furnizor") or "") == furnizor
        and str(r.get("colectie") or "") == colectie
    ]
    return [x for x in sorted({str(r.get("finisaj") or "").strip() for r in rows if str(r.get("finisaj") or "").strip()})]


def get_modele_produse_by_finisaj(cursor, categorie: str, furnizor: str, colectie: str, finisaj: str):
    rows = [
        r for r in _produse()
        if str(r.get("categorie") or "") == categorie
        and str(r.get("furnizor") or "") == furnizor
        and str(r.get("colectie") or "") == colectie
        and str(r.get("finisaj") or "").strip().lower() == str(finisaj or "").strip().lower()
    ]
    return [x for x in sorted({str(r.get("model") or "").strip() for r in rows if str(r.get("model") or "").strip()})]


def get_pret_model_finisaj(cursor, categorie: str, furnizor: str, colectie: str, model: str, finisaj: str):
    for r in _produse():
        if (
            str(r.get("categorie") or "") == categorie
            and str(r.get("furnizor") or "") == furnizor
            and str(r.get("colectie") or "") == colectie
            and str(r.get("model") or "").strip() == str(model or "").strip()
            and str(r.get("finisaj") or "").strip().lower() == str(finisaj or "").strip().lower()
        ):
            return (r.get("pret"),)
    return None


def get_pret_tocuri(cursor, categorie: str, furnizor: str, tip_toc: str, dimensiune: str):
    for r in _produse():
        if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == furnizor and str(r.get("tip_toc") or "") == tip_toc and str(r.get("dimensiune") or "") == (dimensiune or ""):
            return (r.get("pret"),)
    if _is_tocuri_fix90_mm(categorie, furnizor, tip_toc, dimensiune) and str(furnizor or "") == "Stoc":
        return (68.0,)
    return None


def get_decor_finisaj_pairs_tocuri(cursor, categorie: str, furnizor: str, tip_toc: str, dimensiune: str):
    vals = {(str(r.get("decor") or "").strip(), str(r.get("finisaj") or "").strip()) for r in _produse() if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == furnizor and str(r.get("tip_toc") or "") == tip_toc and str(r.get("dimensiune") or "").replace(" ", "") == str(dimensiune or "").replace(" ", "")}
    if (
        categorie == "Tocuri"
        and str(furnizor or "") == "Erkado"
        and str(tip_toc or "").strip() == TOCURI_FIX90_TIP
        and _norm_toc_dimensiune(dimensiune) == _norm_toc_dimensiune(TOCURI_FIX90_DIM)
    ):
        for d, f, _p in _tocuri_fix90_erkado_rows():
            if d or f:
                vals.add((d, f))
    return sorted([x for x in vals if x[0] or x[1]])


def get_finisaje_tocuri(cursor, categorie: str, furnizor: str, tip_toc: str, dimensiune: str):
    return [f for _, f in get_decor_finisaj_pairs_tocuri(cursor, categorie, furnizor, tip_toc, dimensiune) if f]


def get_pret_tocuri_finisaj(cursor, categorie: str, furnizor: str, tip_toc: str, dimensiune: str, finisaj: str):
    for r in _produse():
        if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == furnizor and str(r.get("tip_toc") or "") == tip_toc and str(r.get("dimensiune") or "").replace(" ", "") == str(dimensiune or "").replace(" ", "") and str(r.get("finisaj") or "").strip().lower() == str(finisaj or "").strip().lower():
            return (r.get("pret"),)
    if _is_tocuri_fix90_mm(categorie, furnizor, tip_toc, dimensiune) and str(furnizor or "") == "Erkado":
        fl = str(finisaj or "").strip().lower()
        for _d, f, p in _tocuri_fix90_erkado_rows():
            if str(f or "").strip().lower() == fl:
                return (p,)
    return None


def get_pret_tocuri_decor_finisaj(cursor, categorie: str, furnizor: str, tip_toc: str, dimensiune: str, decor: str, finisaj: str):
    for r in _produse():
        if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == furnizor and str(r.get("tip_toc") or "") == tip_toc and str(r.get("dimensiune") or "").replace(" ", "") == str(dimensiune or "").replace(" ", "") and str(r.get("finisaj") or "").strip().lower() == str(finisaj or "").strip().lower() and str(r.get("decor") or "").strip().lower() == str(decor or "").strip().lower():
            return (r.get("pret"),)
    if _is_tocuri_fix90_mm(categorie, furnizor, tip_toc, dimensiune) and str(furnizor or "") == "Erkado":
        dl = str(decor or "").strip().lower()
        fl = str(finisaj or "").strip().lower()
        for d, f, p in _tocuri_fix90_erkado_rows():
            if str(f or "").strip().lower() != fl:
                continue
            if str(d or "").strip().lower() == dl or not (d or "").strip():
                return (p,)
    return get_pret_tocuri_finisaj(cursor, categorie, furnizor, tip_toc, dimensiune, finisaj)


def get_decor_finisaj_pairs(cursor, categorie: str, colectie: str, model: str, furnizor: str):
    """Perechi (decor, finisaj) pentru același produs. Acceptă și rânduri cu doar decor sau doar finisaj (ex. mânere)."""
    out, seen = [], set()
    for r in _produse():
        if str(r.get("categorie") or "") != categorie or str(r.get("colectie") or "") != colectie or str(r.get("model") or "") != model or str(r.get("furnizor") or "") != furnizor:
            continue
        d, f = str(r.get("decor") or "").strip(), str(r.get("finisaj") or "").strip()
        opts = [(x.strip(), f) for x in d.split(",")] if "," in d else [(d, f)]
        for x in opts:
            if (not x[0] and not x[1]) or x in seen:
                continue
            seen.add(x)
            out.append(x)
    return out


def get_pret_decor_finisaj(cursor, categorie: str, colectie: str, model: str, furnizor: str, decor: str, finisaj: str):
    for r in _produse():
        if str(r.get("categorie") or "") == categorie and str(r.get("colectie") or "") == colectie and str(r.get("model") or "") == model and str(r.get("furnizor") or "") == furnizor and str(r.get("decor") or "") == decor and str(r.get("finisaj") or "") == finisaj:
            return (r.get("pret"),)
    if categorie == "Usi Interior" and furnizor in ("Stoc", "Erkado"):
        for r in _produse():
            if str(r.get("categorie") or "") == categorie and str(r.get("colectie") or "") == colectie and str(r.get("model") or "") == model and str(r.get("furnizor") or "") == furnizor:
                return (r.get("pret"),)
    return None


def get_parchet_dimensiune_pret(cursor, categorie: str, furnizor: str, colectie: str, model: str, model_alt: Optional[str] = None):
    for m in [model, model_alt]:
        if m is None:
            continue
        for r in _produse():
            if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == furnizor and str(r.get("colectie") or "") == colectie and str(r.get("model") or "") == m:
                return (str(r.get("dimensiune") or "0"), r.get("pret"))
    return None


def get_colectii_parchet(cursor, categorie: str):
    return [x for x in sorted({str(r.get("colectie") or "") for r in _produse() if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == "Stoc"}) if x]


def get_modele_parchet(cursor, categorie: str, colectie: str):
    return [x for x in sorted({str(r.get("model") or "") for r in _produse() if str(r.get("categorie") or "") == categorie and str(r.get("furnizor") or "") == "Stoc" and str(r.get("colectie") or "") == colectie})]


def get_parchet_dimensiune_pret_by_cat_col_mod(cursor, categorie: str, colectie: str, model: str, model_int: Optional[str] = None, model_float: Optional[str] = None):
    res = get_parchet_dimensiune_pret(cursor, categorie, "Stoc", colectie, model, model_int)
    if not res and model_float is not None:
        res = get_parchet_dimensiune_pret(cursor, categorie, "Stoc", colectie, model, model_float)
    return res


def get_plinte_for_calcul(cursor):
    rows = [r for r in _produse() if str(r.get("categorie") or "") == "Plinta parchet" and str(r.get("furnizor") or "") == "Stoc"]
    rows.sort(key=lambda r: (str(r.get("colectie") or ""), str(r.get("decor") or ""), str(r.get("model") or "")))
    return [(r.get("colectie") or "", r.get("decor") or "", r.get("model") or "", r.get("dimensiune") or "", r.get("pret")) for r in rows]


def get_izolatiile_for_calcul(cursor):
    rows = [r for r in _produse() if str(r.get("categorie") or "") == "Izolatii parchet" and str(r.get("furnizor") or "") == "Stoc"]
    rows.sort(key=lambda r: (str(r.get("colectie") or ""), str(r.get("model") or ""), str(r.get("decor") or "")))
    return [(r.get("colectie") or "", r.get("decor") or "", r.get("model") or "", r.get("dimensiune") or "", r.get("pret"), (str(r.get("finisaj") or "").strip() or "mp")) for r in rows]


def _manere_engs_rows() -> list[dict[str, Any]]:
    return [
        r
        for r in _produse()
        if str(r.get("categorie") or "") == "Manere" and str(r.get("furnizor") or "") == "Enger"
    ]


def get_manere_engs_modele(cursor) -> list[str]:
    """Listează modelele (coloana «colectie») pentru mânere Enger."""
    rows = _manere_engs_rows()
    return sorted({str(r.get("colectie") or "").strip() for r in rows if str(r.get("colectie") or "").strip()})


def get_manere_engs_finisaje(cursor, model: str) -> list[str]:
    """Finisaje / coduri culoare pentru un model Enger."""
    m = (model or "").strip()
    rows = [r for r in _manere_engs_rows() if str(r.get("colectie") or "").strip() == m]
    return sorted({str(r.get("finisaj") or "").strip() for r in rows if str(r.get("finisaj") or "").strip()})


def get_manere_engs_pret_lei(cursor, colectie: str, finisaj: str, decor: str) -> float | None:
    """
    Preț în LEI cu TVA inclus (din catalog importat), pentru o linie produs.
    decor: «Măner», «OB», «PZ», «WC» (ca în CSV).
    """
    c, f, d = (colectie or "").strip(), (finisaj or "").strip(), (decor or "").strip()
    for r in _manere_engs_rows():
        if str(r.get("colectie") or "").strip() != c:
            continue
        if str(r.get("finisaj") or "").strip() != f:
            continue
        if str(r.get("decor") or "").strip() != d:
            continue
        try:
            return float(r.get("pret") or 0)
        except (TypeError, ValueError):
            return 0.0
    return None


def get_produse_for_admin_list(cursor, furnizor: str, categorie: str):
    """Doar rândurile pentru furnizor+categorie (query filtrat în cloud), nu întreg tabelul produse."""
    client = _get_supabase_client()
    f = (furnizor or "").strip()
    c = (categorie or "").strip()
    data: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = (
            client.table(TABLE_PRODUSE)
            .select("*")
            .eq("furnizor", f)
            .eq("categorie", c)
            .order("id", desc=True)
            .range(offset, offset + _ROWS_PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        data.extend(batch)
        if len(batch) < _ROWS_PAGE_SIZE:
            break
        offset += _ROWS_PAGE_SIZE
    return [
        (
            r.get("id"),
            r.get("furnizor"),
            r.get("colectie"),
            r.get("model"),
            r.get("decor"),
            r.get("finisaj"),
            r.get("tip_toc") or "",
            r.get("dimensiune") or "",
            r.get("pret"),
        )
        for r in data
    ]


def insert_produs(conn, cursor, categorie: str, furnizor: str, colectie: str, model: str, decor: str, finisaj: str, tip_toc: str, dimensiune: str, pret: float):
    _get_supabase_client().table(TABLE_PRODUSE).insert(
        {
            "categorie": categorie,
            "furnizor": furnizor,
            "colectie": colectie,
            "model": model,
            "decor": decor,
            "finisaj": finisaj,
            "tip_toc": tip_toc,
            "dimensiune": dimensiune,
            "pret": pret,
        }
    ).execute()
    _invalidate(TABLE_PRODUSE)


def delete_produs(conn, cursor, prod_id: int):
    _get_supabase_client().table(TABLE_PRODUSE).delete().eq("id", prod_id).execute()
    _invalidate(TABLE_PRODUSE)


def insert_izolatie(conn, cursor, denumire: str, culoare: str, grosime: str, dimensiune: str, cantitate_metoda: str, pret: float):
    insert_produs(conn, cursor, "Izolatii parchet", "Stoc", denumire, grosime, culoare, (cantitate_metoda or "").strip() or "mp", "", dimensiune, pret)


def insert_plinta_parchet(conn, cursor, denumire: str, culoare: str, model: str, dimensiune: str, pret: float):
    insert_produs(conn, cursor, "Plinta parchet", "Stoc", denumire, model or "", culoare, "", "", dimensiune or "", pret)


def get_istoric_oferte_admin(cursor, nume_like: str, id_egal: Optional[int] = None):
    clienti = {int(c.get("id") or 0): c for c in _rows(TABLE_CLIENTI)}
    out = []
    for o in _rows(TABLE_OFERTE):
        ok = _like(str(o.get("nume_client_temp") or ""), nume_like) or (id_egal is not None and int(o.get("id") or 0) == int(id_egal))
        if not ok:
            continue
        c = clienti.get(int(o.get("id_client") or 0), {})
        out.append((o.get("id"), o.get("id_client"), o.get("nume_client_temp"), o.get("data_oferta"), o.get("total_lei"), o.get("detalii_oferta"), c.get("telefon"), c.get("adresa"), o.get("utilizator_creat"), o.get("discount_proc"), o.get("curs_euro"), o.get("avans_incasat"), o.get("safe_mode_enabled", 1)))
    out.sort(key=lambda x: int(x[0] or 0), reverse=True)
    return out


def get_activity_users_with_counts(cursor):
    users = [u for u in _rows(TABLE_USERS) if int(u.get("approved") or 0) == 1]
    offers = _rows(TABLE_OFERTE)
    out = []
    for u in users:
        name = str(u.get("username") or "").strip().lower()
        out.append((u.get("username"), u.get("nume_complet"), sum(1 for o in offers if str(o.get("utilizator_creat") or "").strip().lower() == name)))
    out.sort(key=lambda x: str(x[0] or ""))
    return out


def get_istoric_oferte_by_user(cursor, username: str):
    u = username.strip().lower()
    clienti = {int(c.get("id") or 0): c for c in _rows(TABLE_CLIENTI)}
    rows = [o for o in _rows(TABLE_OFERTE) if str(o.get("utilizator_creat") or "").strip().lower() == u]
    rows.sort(key=lambda r: int(r.get("id") or 0), reverse=True)
    return [(o.get("id"), o.get("id_client"), o.get("nume_client_temp"), o.get("data_oferta"), o.get("total_lei"), o.get("detalii_oferta"), clienti.get(int(o.get("id_client") or 0), {}).get("telefon"), clienti.get(int(o.get("id_client") or 0), {}).get("adresa"), o.get("utilizator_creat"), o.get("discount_proc"), o.get("curs_euro"), o.get("avans_incasat"), o.get("safe_mode_enabled", 1)) for o in rows]


def get_oferte_by_date(cursor, data_prefix: str):
    rows = [o for o in _rows(TABLE_OFERTE) if str(o.get("data_oferta") or "").startswith(data_prefix)]
    rows.sort(key=lambda r: int(r.get("id") or 0))
    return [(o.get("id"), o.get("nume_client_temp") or "", o.get("total_lei") or 0, o.get("detalii_oferta") or "") for o in rows]


# —— Uși exterior (prețuri în Supabase) ——
TABLE_USI_EXTERIOARE = "usi_exterioare"
TABLE_BARE_EXTERIOARE = "bare_exterioare"


def get_usi_exterioare_rows(*, force: bool = False) -> list[dict[str, Any]]:
    """Rânduri din `usi_exterioare` (model, prețuri și dimensiuni pentru configurator)."""
    return _rows(TABLE_USI_EXTERIOARE, force=force)


def get_usi_exterior_configurator_rows(*, force: bool = False) -> list[dict[str, Any]]:
    """Uși din `usi_exterioare` + bare din `bare_exterioare` (listă separată în Supabase)."""
    doors = _rows(TABLE_USI_EXTERIOARE, force=force)
    try:
        bars = _rows(TABLE_BARE_EXTERIOARE, force=force)
    except Exception:
        bars = []
    return doors + bars
