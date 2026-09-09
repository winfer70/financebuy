"""cik_ticker_map.py — CIK -> ticker resolution via SEC's free company_tickers.json.

Form 4's ownership XML embeds issuerTradingSymbol directly, so it never
needed this. Form 144's XML only carries the issuer's CIK — SEC doesn't
require the filer to state the ticker — so a separate lookup is needed to
turn a 144 notice into something joinable against the rest of the schema
(which is ticker-keyed everywhere: InsiderFiling, PortfolioPosition, etc).

company_tickers.json is a small (~1MB), free, unauthenticated static file
SEC republishes regularly. Cached in-process with a TTL; refreshed lazily
on the next lookup after it expires, not on a timer.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import requests

_URL = "https://www.sec.gov/files/company_tickers.json"
_CACHE_TTL_SECONDS = 24 * 60 * 60
_FETCH_TIMEOUT = 15

_cache: dict[int, str] = {}
_cache_loaded_at: float = 0.0


def _fetch_map() -> dict[int, str]:
    ua = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not ua:
        return {}
    resp = requests.get(_URL, headers={"User-Agent": ua}, timeout=_FETCH_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    out: dict[int, str] = {}
    for row in data.values():
        cik = row.get("cik_str")
        ticker = row.get("ticker")
        if cik is not None and ticker:
            out[int(cik)] = str(ticker).upper()
    return out


def resolve_ticker(cik: str) -> Optional[str]:
    """Best-effort CIK -> ticker. None if unresolvable (private issuer,
    stale cache miss, or SEC_USER_AGENT unset) — never raises."""
    global _cache, _cache_loaded_at
    try:
        cik_int = int(str(cik).strip().lstrip("0") or "0")
    except ValueError:
        return None
    if cik_int == 0:
        return None

    if not _cache or (time.time() - _cache_loaded_at) > _CACHE_TTL_SECONDS:
        try:
            fresh = _fetch_map()
            if fresh:
                _cache = fresh
                _cache_loaded_at = time.time()
        except Exception:
            pass  # keep serving the stale cache rather than failing the caller

    return _cache.get(cik_int)
