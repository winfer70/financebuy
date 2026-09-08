"""form13f_edgar.py — Parse SEC Form 13F-HR (quarterly institutional holdings).

Institutional managers with >$100M AUM disclose long equity positions
quarterly, 45 days after quarter-end — a positioning signal, not a trading
one (verified live: filings roll in as a burst around the deadline, not
evenly through the quarter). The information table reports holdings by
CUSIP (verified live it also carries a <figi> field in newer filings, but
that's the share-class-level FIGI, not the composite/exchange-level ID
OpenFIGI's default lookup expects — CUSIP is the reliable key, resolved
via cusip_ticker_map.py).

Filer name/CIK come from the atom entry's title (same "TYPE - Name (CIK)
(Role)" shape as Form 8-K) — no need to fetch primary_doc.xml at all, only
the information table itself.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from .insider_edgar import _find, _local, _num, _text

FORM13F_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=13F-HR&owner=include&count=40&output=atom"
)

_TITLE_RE = re.compile(r"^\S[\S/]*\s*-\s*(.+?)\s*\((\d{10})\)\s*\(([^)]+)\)\s*$")
_ACCESSION_RE = re.compile(r"AccNo:</b>\s*(\d{10}-\d{2}-\d{6})")


def parse_13f_atom_entry_title(title: str, summary: str, term: str) -> Optional[dict]:
    """Filer CIK/name + accession from one atom <entry> — mirrors
    form8k_edgar's title parsing (same underlying EDGAR title convention)."""
    m = _TITLE_RE.match(title.strip())
    if not m:
        return None
    filer_name, filer_cik, role = m.group(1), m.group(2), m.group(3)
    acc_m = _ACCESSION_RE.search(summary)
    accession = acc_m.group(1) if acc_m else ""
    if not accession:
        return None
    return {
        "accession": accession,
        "filer_cik": filer_cik,
        "filer_name": filer_name,
        "role": role,
        "is_amendment": "/A" in term,
    }


def parse_13f_atom_feed(atom_xml: str) -> list[dict]:
    """One dict per <entry> in the getcurrent 13F-HR atom feed, each
    including index_url (needed to later fetch the information table) —
    entries whose title doesn't match the expected shape are skipped."""
    root = ET.fromstring(atom_xml)
    out = []
    for el in list(root):
        if _local(el.tag) != "entry":
            continue
        title = summary = term = index_url = ""
        for child in list(el):
            loc = _local(child.tag)
            if loc == "title":
                title = _text(child)
            elif loc == "summary":
                summary = _text(child)
            elif loc == "link":
                index_url = child.attrib.get("href", "") or index_url
            elif loc == "category":
                term = child.attrib.get("term", "") or term
        parsed = parse_13f_atom_entry_title(title, summary, term)
        if parsed is not None:
            parsed["index_url"] = index_url
            out.append(parsed)
    return out


def infotable_xml_url_from_index_html(index_html: str, index_url: str = "") -> str:
    """Pick the information-table .xml href from a 13F filing's EDGAR index
    page — unlike Form 4/144/3, a 13F index has *two* non-xsl .xml files
    (primary_doc.xml, the cover page, and infotable.xml, the actual
    holdings), so xml_doc_url_from_index_html's generic "first .xml" rule
    would grab the wrong one. This looks for "infotable" in the filename
    specifically."""
    hrefs = re.findall(r'href="([^"]+\.xml)"', index_html, flags=re.I)
    hrefs += re.findall(r"href='([^']+\.xml)'", index_html, flags=re.I)
    for h in hrefs:
        if "xsl" in h.lower():
            continue
        if "infotable" not in h.lower():
            continue
        if h.startswith("http"):
            return h
        if h.startswith("/"):
            return "https://www.sec.gov" + h
        if index_url:
            from urllib.parse import urljoin

            return urljoin(index_url, h)
    return ""


def parse_13f_infotable_xml(xml_text: str) -> list[dict]:
    """One dict per <infoTable> holding: cusip, issuer_name, shares, value
    (value is reported in whole dollars as of 2023 schema changes — see
    SEC's Form 13F EDGAR technical spec; older filings report in thousands,
    not distinguished here since this only targets current filings)."""
    root = ET.fromstring(xml_text)
    rows = []
    for el in list(root):
        if _local(el.tag) != "infoTable":
            continue
        cusip = _text(_find(el, "cusip")).strip().upper()
        if not cusip:
            continue
        issuer_name = _text(_find(el, "nameOfIssuer"))
        value = _num(_find(el, "value"))
        shares_el = _find(el, "shrsOrPrnAmt")
        shares = _num(_find(shares_el, "sshPrnamt")) if shares_el is not None else 0.0
        rows.append(
            {
                "cusip": cusip,
                "issuer_name": issuer_name,
                "shares": shares,
                "value": value,
            }
        )
    return rows
