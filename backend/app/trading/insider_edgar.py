"""insider_edgar.py — Parse SEC Form 4 atom + ownership XML (no network in tests)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urljoin

import httpx

FORM4_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=4&owner=include&count=40&output=atom"
)


class EdgarFetcher:
    """Shared async HTTP fetcher for any EDGAR atom/XML/index page — not
    Form-4-specific despite living alongside the Form 4 parser; form144_edgar
    and any future filing-type module reuse this rather than each opening
    their own httpx client (and each needing the SEC User-Agent contact
    requirement wired in separately)."""

    def __init__(self, user_agent: str):
        self.user_agent = user_agent

    async def get(self, url: str) -> str:
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _text(el: Optional[ET.Element]) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _find(el: ET.Element, *names: str) -> Optional[ET.Element]:
    want = set(names)
    for child in list(el):
        if _local(child.tag) in want:
            return child
        nested = _find(child, *names)
        if nested is not None:
            return nested
    return None


def _findall(el: ET.Element, name: str) -> list[ET.Element]:
    out = []
    if _local(el.tag) == name:
        out.append(el)
    for child in list(el):
        out.extend(_findall(child, name))
    return out


def parse_atom_accessions(atom_xml: str) -> list[dict]:
    """Extract accession numbers and index URLs from EDGAR current-filings atom."""
    root = ET.fromstring(atom_xml)
    entries = []
    for el in list(root):
        if _local(el.tag) != "entry":
            continue
        title = ""
        href = ""
        updated = ""
        for child in list(el):
            loc = _local(child.tag)
            if loc == "title":
                title = _text(child)
            elif loc == "updated":
                updated = _text(child)
            elif loc == "link":
                href = child.attrib.get("href", "") or href
        acc = _accession_from_href(href) or _accession_from_title(title)
        if not acc:
            continue
        entries.append(
            {
                "accession": acc,
                "title": title,
                "index_url": href,
                "updated": updated,
            }
        )
    return entries


def _accession_from_href(href: str) -> str:
    m = re.search(r"(\d{10,})-(\d{2})-(\d{6})", href or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"/(\d{18})/", href or "")
    if m:
        raw = m.group(1)
        return f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"
    return ""


def _accession_from_title(title: str) -> str:
    m = re.search(r"(\d{10}-\d{2}-\d{6})", title or "")
    return m.group(1) if m else ""


def accession_to_archives_stem(accession: str, cik: str) -> str:
    compact = accession.replace("-", "")
    cik_n = str(int(cik)) if cik.isdigit() else cik
    return f"https://www.sec.gov/Archives/edgar/data/{cik_n}/{compact}"


def _doc_level_10b5(root: ET.Element) -> Optional[bool]:
    """SEC 2023 checkbox aff10b5One on ownershipDocument; footnotes as fallback."""
    for name in ("aff10b5One", "aff10b51", "Aff10b5One"):
        el = _find(root, name)
        if el is not None:
            return _text(el) in ("1", "true", "True")
    footnotes = " ".join(_text(f) for f in _findall(root, "footnote")).lower()
    if "10b5-1" in footnotes or "10b5–1" in footnotes or "rule 10b5" in footnotes:
        return True
    return None


def _shares_after(txn: ET.Element) -> Optional[float]:
    post = _find(txn, "postTransactionAmounts")
    if post is None:
        return None
    owned = _find(post, "sharesOwnedFollowingTransaction")
    if owned is None:
        return None
    val = _num(owned)
    return val


def stake_pct_sold(shares: float, shares_after: Optional[float]) -> Optional[float]:
    """shares / (shares + remaining). None if remaining unknown."""
    if shares_after is None or shares <= 0:
        return None
    total = shares + shares_after
    if total <= 0:
        return None
    return shares / total


def parse_form4_xml(xml_text: str, accession: str = "", filing_url: str = "") -> list[dict]:
    """Parse ownership XML into one dict per non-derivative transaction."""
    root = ET.fromstring(xml_text)
    ticker = _text(_find(root, "issuerTradingSymbol")).upper()
    cik = _text(_find(root, "issuerCik")) or _text(_find(root, "cik"))
    owner_name = _text(_find(root, "rptOwnerName"))
    owner_cik = _text(_find(root, "rptOwnerCik"))
    rel = _find(root, "reportingOwnerRelationship")
    is_director = _flag(rel, "isDirector")
    is_officer = _flag(rel, "isOfficer")
    is_ten = _flag(rel, "isTenPercentOwner")
    officer_title = ""
    if rel is not None:
        officer_title = _text(_find(rel, "officerTitle")) or _text(_find(root, "officerTitle"))
    is_10b5 = _doc_level_10b5(root)

    rows = []
    for txn in _findall(root, "nonDerivativeTransaction"):
        code = _text(_find(txn, "transactionCode"))
        shares = _num(_find(txn, "transactionShares"))
        price = _num(_find(txn, "transactionPricePerShare"))
        ad = _text(_find(txn, "transactionAcquiredDisposedCode"))
        date_el = _find(txn, "transactionDate")
        tdate = ""
        if date_el is not None:
            tdate = _text(_find(date_el, "value")) or _text(date_el)
        after = _shares_after(txn)
        stake = None
        if (code or "").upper() == "S" or (ad or "").upper() == "D":
            stake = stake_pct_sold(shares, after)
        rows.append(
            {
                "accession": accession,
                "ticker": ticker,
                "issuer_cik": cik,
                "owner_name": owner_name,
                "owner_cik": owner_cik,
                "is_director": is_director,
                "is_officer": is_officer,
                "is_ten_percent": is_ten,
                "officer_title": officer_title,
                "transaction_code": code or "",
                "acquired_disposed": ad or "",
                "shares": shares,
                "price": price,
                "shares_after": after,
                "stake_pct": stake,
                "transaction_date": tdate,
                "is_10b5_1": is_10b5,
                "filing_url": filing_url,
            }
        )
    return rows


def _flag(rel: Optional[ET.Element], name: str) -> bool:
    if rel is None:
        return False
    el = _find(rel, name)
    return _text(el) in ("1", "true", "True")


def _num(el: Optional[ET.Element]) -> float:
    if el is None:
        return 0.0
    raw = _text(_find(el, "value")) or _text(el)
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return 0.0


def xml_doc_url_from_index_html(index_html: str, accession: str, index_url: str = "") -> str:
    """Pick the primary Form 4 ownership .xml href from an EDGAR index page."""
    hrefs = re.findall(r'href="([^"]+\.xml)"', index_html, flags=re.I)
    hrefs += re.findall(r"href='([^']+\.xml)'", index_html, flags=re.I)
    for h in hrefs:
        if "xsl" in h.lower():
            continue
        if h.startswith("http"):
            return h
        if h.startswith("/"):
            return "https://www.sec.gov" + h
        if index_url:
            return urljoin(index_url, h)
    return ""
