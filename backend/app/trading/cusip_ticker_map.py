"""cusip_ticker_map.py — CUSIP -> ticker resolution via the free OpenFIGI API.

Form 13F's information table reports holdings by CUSIP (plus a FIGI field
in newer filings, verified live — but that FIGI is share-class-level, not
the composite/exchange-level ID OpenFIGI's default lookup expects, so
CUSIP is the more reliable key to resolve on). This is exactly the "CUSIP
isn't free/trivial to resolve from EDGAR alone" gap FREE_FILINGS_RESEARCH.md
flagged — OpenFIGI's /mapping endpoint is the free, unauthenticated (though
rate-limited) resolver.

Batched: OpenFIGI accepts up to 100 mapping jobs per POST. No persistent
cache (unlike cik_ticker_map.py's company_tickers.json, which is one small
file worth caching whole) — CUSIPs are resolved per-poll-cycle since a 13F
filing's holdings list is itself the input, not a lookup key reused often
enough to justify a standing cache here.
"""
from __future__ import annotations

from typing import Optional

import requests

_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 100
_FETCH_TIMEOUT = 30
_PREFERRED_EXCH_CODES = ("US",)


def _best_ticker(entries: list[dict]) -> Optional[str]:
    for code in _PREFERRED_EXCH_CODES:
        for entry in entries:
            if entry.get("exchCode") == code and entry.get("ticker"):
                return str(entry["ticker"]).upper()
    if entries and entries[0].get("ticker"):
        return str(entries[0]["ticker"]).upper()
    return None


def resolve_cusips(cusips: list[str]) -> dict[str, str]:
    """Best-effort CUSIP -> ticker for a list of CUSIPs. Skips (rather than
    raising for) any that don't resolve — invalid CUSIP, no US listing,
    delisted/no-longer-indexed instrument, or a transient API error all
    just mean that entry is missing from the returned dict.
    """
    out: dict[str, str] = {}
    unique = [c for c in dict.fromkeys(c.strip() for c in cusips if c and c.strip())]
    for start in range(0, len(unique), _BATCH_SIZE):
        batch = unique[start : start + _BATCH_SIZE]
        jobs = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            resp = requests.post(_URL, json=jobs, timeout=_FETCH_TIMEOUT)
            resp.raise_for_status()
            results = resp.json()
        except (requests.RequestException, ValueError):
            continue
        if not isinstance(results, list) or len(results) != len(batch):
            continue
        for cusip, result in zip(batch, results):
            if not isinstance(result, dict):
                continue
            data = result.get("data")
            if not data:
                continue
            ticker = _best_ticker(data)
            if ticker:
                out[cusip] = ticker
    return out
