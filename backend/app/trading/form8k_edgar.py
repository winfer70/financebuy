"""form8k_edgar.py — Parse SEC Form 8-K (Material Events) from the atom feed.

Unlike Form 4/144/3/13D-13G, an 8-K's item codes (which "material event"
triggered it — M&A, executive changes, earnings, bankruptcy, etc.) are
already embedded directly in EDGAR's getcurrent atom <summary>, verified
live during development:

    <title>8-K/A - Vivos Therapeutics, Inc. (0001716166) (Filer)</title>
    <summary type="html">
     <b>Filed:</b> 2026-09-08 <b>AccNo:</b> 0001493152-26-041807 <b>Size:</b> 241 KB
    <br>Item 1.01: Entry into a Material Definitive Agreement
    <br>Item 3.02: Unregistered Sales of Equity Securities
    <br>Item 9.01: Financial Statements and Exhibits
    </summary>

No per-filing XML/document fetch is needed at all for the item codes —
this module works entirely off the atom feed, which matters because 8-K
volume is dozens per 5-minute tick across every US issuer (the ticker
watchlist filter in form8k_monitor.py runs BEFORE any further work, using
only what's already in this parsed dict).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from .insider_edgar import _local, _text

FORM8K_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=8-K&owner=include&count=100&output=atom"
)

_TITLE_RE = re.compile(r"^\S[\S/]*\s*-\s*(.+?)\s*\((\d{10})\)\s*\(([^)]+)\)\s*$")
_ITEM_RE = re.compile(r"Item\s+([\d.]+):\s*([^\n<]+)")
_ACCESSION_RE = re.compile(r"AccNo:</b>\s*(\d{10}-\d{2}-\d{6})")


def _parse_one_entry(entry: ET.Element) -> Optional[dict]:
    """Extract issuer/CIK/item-codes from one atom <entry> — everything
    needed comes from the atom feed itself, no further network call."""
    title = ""
    summary = ""
    term = ""
    index_url = ""
    updated = ""
    for child in list(entry):
        loc = _local(child.tag)
        if loc == "title":
            title = _text(child)
        elif loc == "summary":
            summary = _text(child)
        elif loc == "updated":
            updated = _text(child)
        elif loc == "link":
            index_url = child.attrib.get("href", "") or index_url
        elif loc == "category":
            term = child.attrib.get("term", "") or term

    m = _TITLE_RE.match(title)
    if not m:
        return None
    issuer_name, cik, role = m.group(1), m.group(2), m.group(3)

    acc_m = _ACCESSION_RE.search(summary)
    accession = acc_m.group(1) if acc_m else ""
    if not accession:
        return None

    items = [
        {"code": code.strip(), "description": desc.strip()}
        for code, desc in _ITEM_RE.findall(summary)
    ]

    return {
        "accession": accession,
        "issuer_cik": cik,
        "issuer_name": issuer_name,
        "role": role,
        "is_amendment": "/A" in term,
        "items": items,
        "index_url": index_url,
        "updated": updated,
    }


def parse_8k_atom_feed(atom_xml: str) -> list[dict]:
    """One dict per <entry> in the getcurrent 8-K atom feed. Entries whose
    title doesn't match the expected "TYPE - Name (CIK) (Role)" shape, or
    whose summary has no parseable AccNo, are silently skipped rather than
    raising — a malformed one-off shouldn't sink the whole cycle."""
    root = ET.fromstring(atom_xml)
    out = []
    for el in list(root):
        if _local(el.tag) != "entry":
            continue
        parsed = _parse_one_entry(el)
        if parsed is not None:
            out.append(parsed)
    return out
