"""form144_edgar.py — Parse SEC Form 144 (Notice of Proposed Sale) atom + XML.

An insider/affiliate must file this before or on the day of selling
restricted/control stock above a threshold. It states the exact issuer,
share count, and *intended* sale date — a leading indicator for the Form 4
sale that typically follows within days. See FREE_FILINGS_RESEARCH.md.

Reuses insider_edgar.py's atom-feed parsing (form-type-agnostic) and its
generic namespace-stripping XML helpers — only the per-filing shape here
is Form-144-specific.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from .insider_edgar import _find, _findall, _num, _text

FORM144_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=144&owner=include&count=40&output=atom"
)


def parse_form144_xml(xml_text: str, accession: str = "", filing_url: str = "") -> Optional[dict]:
    """One proposed-sale notice per filing (unlike Form 4's multi-row shape).

    Returns None if the document doesn't parse as the expected shape —
    callers should skip the accession rather than store a half-populated row.
    """
    root = ET.fromstring(xml_text)

    filer_cik = _text(_find(root, "cik"))
    issuer_info = _find(root, "issuerInfo")
    if issuer_info is None:
        return None
    issuer_cik = _text(_find(issuer_info, "issuerCik"))
    issuer_name = _text(_find(issuer_info, "issuerName"))
    seller_name = _text(_find(issuer_info, "nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold"))
    relationships = [
        _text(el) for el in _findall(issuer_info, "relationshipToIssuer") if _text(el)
    ]

    sec_info = _find(root, "securitiesInformation")
    broker = ""
    shares = 0.0
    aggregate_value = 0.0
    approx_sale_date = ""
    if sec_info is not None:
        broker_el = _find(sec_info, "brokerOrMarketmakerDetails")
        if broker_el is not None:
            broker = _text(_find(broker_el, "name"))
        shares = _num(_find(sec_info, "noOfUnitsSold"))
        aggregate_value = _num(_find(sec_info, "aggregateMarketValue"))
        approx_sale_date = _mdy_to_iso(_text(_find(sec_info, "approxSaleDate")))

    notice_date = ""
    signature = _find(root, "noticeSignature")
    if signature is not None:
        notice_date = _mdy_to_iso(_text(_find(signature, "noticeDate")))

    if not issuer_cik or not filer_cik:
        return None

    return {
        "accession": accession,
        "issuer_cik": issuer_cik,
        "issuer_name": issuer_name,
        "owner_cik": filer_cik,
        "owner_name": seller_name,
        "relationships": ", ".join(relationships),
        "broker": broker,
        "shares": shares,
        "aggregate_value": aggregate_value,
        "approx_sale_date": approx_sale_date or None,
        "notice_date": notice_date or None,
        "filing_url": filing_url,
    }


def _mdy_to_iso(value: str) -> str:
    """EDGAR's ownership XML dates are MM/DD/YYYY, unlike Form 4's ISO dates."""
    value = (value or "").strip()
    if not value or "/" not in value:
        return ""
    parts = value.split("/")
    if len(parts) != 3:
        return ""
    mm, dd, yyyy = parts
    try:
        return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
    except ValueError:
        return ""
