"""schedule13_edgar.py — Parse SEC Schedule 13D/13G (beneficial ownership >5%).

13D = "activist" intent (may seek control/board seats, states a purpose).
13G = passive investor (index funds, most institutions), same 5% threshold,
no intent language. Both use structured XML cover pages (like Form 4/144),
but with genuinely different tag names for equivalent concepts — verified
against two real live filings during development (Sono Group N.V. 13D,
Metalla Royalty & Streaming Ltd. 13G):

  concept              13D tag                              13G tag
  ------------------------------------------------------------------------
  issuer CIK           issuerInfo/issuerCIK (uppercase K)   issuerInfo/issuerCik
  event date           dateOfEvent                          eventDateRequiresFilingThisStatement
  reporting persons     reportingPersons/reportingPersonInfo  coverPageHeaderReportingPersonDetails
                        (repeated, wrapped)                   (repeated, unwrapped siblings)
  person CIK           reportingPersonCIK (may be absent)    not present at all — falls back to
                                                              the top-level filer CIK
  shares owned         aggregateAmountOwned                  reportingPersonBeneficiallyOwnedAggregateNumberOfShares
  % of class           percentOfClass                        classPercent
  purpose narrative    item4/transactionPurpose               n/a (13G filers don't state activist intent)

Neither embeds issuerTradingSymbol — only CUSIP — so ticker resolution goes
through cik_ticker_map.py, same as Form 144.

EDGAR's getcurrent type= filter does prefix matching: "SCHEDULE 13D" also
matches "SCHEDULE 13D/A" (amendments) in the same feed — is_amendment is
derived from the "/A" suffix on submissionType rather than a separate feed.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from .form144_edgar import _mdy_to_iso
from .insider_edgar import _find, _findall, _num, _text

FORM_13D_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=SCHEDULE+13D&owner=include&count=40&output=atom"
)
FORM_13G_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=SCHEDULE+13G&owner=include&count=40&output=atom"
)

_MAX_PURPOSE_CHARS = 2000


def parse_schedule13d_xml(xml_text: str, accession: str = "", filing_url: str = "") -> list[dict]:
    """One record per reportingPersonInfo — a 13D can be a joint "group"
    filing with multiple reporting persons sharing one cover page."""
    root = ET.fromstring(xml_text)
    submission_type = _text(_find(root, "submissionType"))
    is_amendment = "/A" in submission_type

    cover = _find(root, "coverPageHeader")
    issuer_info = _find(cover, "issuerInfo") if cover is not None else None
    issuer_cik = _text(_find(issuer_info, "issuerCIK")) if issuer_info is not None else ""
    issuer_name = _text(_find(issuer_info, "issuerName")) if issuer_info is not None else ""
    event_date = _mdy_to_iso(_text(_find(cover, "dateOfEvent"))) if cover is not None else ""

    item4 = _find(root, "item4")
    purpose_text = ""
    if item4 is not None:
        purpose_text = _text(_find(item4, "transactionPurpose"))[:_MAX_PURPOSE_CHARS]

    if not issuer_cik:
        return []

    rows = []
    persons_wrapper = _find(root, "reportingPersons")
    persons = _findall(persons_wrapper, "reportingPersonInfo") if persons_wrapper is not None else []
    for i, p in enumerate(persons):
        rows.append(
            {
                "accession": accession,
                "person_index": i,
                "is_13d": True,
                "is_amendment": is_amendment,
                "issuer_cik": issuer_cik,
                "issuer_name": issuer_name,
                "filer_cik": _text(_find(p, "reportingPersonCIK")),
                "filer_name": _text(_find(p, "reportingPersonName")),
                "shares_owned": _num(_find(p, "aggregateAmountOwned")),
                "pct_owned": _num(_find(p, "percentOfClass")),
                "event_date": event_date,
                "purpose_text": purpose_text,
                "filing_url": filing_url,
            }
        )
    return rows


def parse_schedule13g_xml(xml_text: str, accession: str = "", filing_url: str = "") -> list[dict]:
    """One record per coverPageHeaderReportingPersonDetails block. No
    per-person CIK in this schema — falls back to the top-level filer CIK
    (13G is almost always a single institutional filer per filing, unlike
    13D's occasional multi-person "group")."""
    root = ET.fromstring(xml_text)
    submission_type = _text(_find(root, "submissionType"))
    is_amendment = "/A" in submission_type
    filer_cik = _text(_find(root, "cik"))

    cover = _find(root, "coverPageHeader")
    issuer_info = _find(cover, "issuerInfo") if cover is not None else None
    issuer_cik = _text(_find(issuer_info, "issuerCik")) if issuer_info is not None else ""
    issuer_name = _text(_find(issuer_info, "issuerName")) if issuer_info is not None else ""
    event_date = (
        _mdy_to_iso(_text(_find(cover, "eventDateRequiresFilingThisStatement")))
        if cover is not None
        else ""
    )

    if not issuer_cik:
        return []

    rows = []
    persons = _findall(root, "coverPageHeaderReportingPersonDetails")
    for i, p in enumerate(persons):
        rows.append(
            {
                "accession": accession,
                "person_index": i,
                "is_13d": False,
                "is_amendment": is_amendment,
                "issuer_cik": issuer_cik,
                "issuer_name": issuer_name,
                "filer_cik": filer_cik,
                "filer_name": _text(_find(p, "reportingPersonName")),
                "shares_owned": _num(_find(p, "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")),
                "pct_owned": _num(_find(p, "classPercent")),
                "event_date": event_date,
                "purpose_text": "",
                "filing_url": filing_url,
            }
        )
    return rows
