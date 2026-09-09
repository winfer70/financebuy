"""
============================================================================
TEST SUITE: form13f_edgar (Form 13F-HR atom + information-table parsers)
============================================================================

Samples below are trimmed copies of a real, live 13F-HR filing fetched from
EDGAR during development (Willow Creek Capital Management, Inc.) —
verifies atom title parsing, the information-table XML shape (cusip/
issuer/shares/value), and the infotable-vs-primary_doc index-page
disambiguation a 13F filing needs that other filing types here don't.
============================================================================
"""
from app.trading.form13f_edgar import (
    infotable_xml_url_from_index_html,
    parse_13f_atom_entry_title,
    parse_13f_atom_feed,
    parse_13f_infotable_xml,
)

SAMPLE_ATOM = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>13F-HR - Willow Creek Capital Management, Inc. (0002152085) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/2152085/000108514626000764/0001085146-26-000764-index.htm"/>
<summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-09-08 &lt;b&gt;AccNo:&lt;/b&gt; 0001085146-26-000764 &lt;b&gt;Size:&lt;/b&gt; 52 KB
</summary>
<updated>2026-09-08T16:18:42-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="13F-HR"/>
<id>urn:tag:sec.gov,2008:accession-number=0001085146-26-000764</id>
</entry>
<entry>
<title>Malformed title with no CIK</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/x"/>
<summary type="html">&lt;b&gt;AccNo:&lt;/b&gt; 0000000000-26-000000</summary>
<updated>2026-09-08T17:00:00-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="13F-HR"/>
<id>urn:tag:sec.gov,2008:accession-number=0000000000-26-000000</id>
</entry>
</feed>"""

SAMPLE_INFOTABLE_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>ABBOTT LABORATORIES</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>002824100</cusip>
    <figi>BBG001S5N9M6</figi>
    <value>806225</value>
    <shrsOrPrnAmt>
      <sshPrnamt>8885</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
  <infoTable>
    <nameOfIssuer>ABBVIE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>00287Y109</cusip>
    <figi>BBG0025Y4RZ3</figi>
    <value>1654597</value>
    <shrsOrPrnAmt>
      <sshPrnamt>6575</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
</informationTable>"""

SAMPLE_INDEX_HTML = """
<a href="/Archives/edgar/data/2152085/000108514626000764/xslForm13F_X02/primary_doc.xml">x</a>
<a href="/Archives/edgar/data/2152085/000108514626000764/primary_doc.xml">x</a>
<a href="/Archives/edgar/data/2152085/000108514626000764/xslForm13F_X02/infotable.xml">x</a>
<a href="/Archives/edgar/data/2152085/000108514626000764/infotable.xml">x</a>
"""


class TestParse13fAtomEntryTitle:
    def test_parses_real_sample(self):
        result = parse_13f_atom_entry_title(
            "13F-HR - Willow Creek Capital Management, Inc. (0002152085) (Filer)",
            "<b>Filed:</b> 2026-09-08 <b>AccNo:</b> 0001085146-26-000764 <b>Size:</b> 52 KB",
            "13F-HR",
        )
        assert result == {
            "accession": "0001085146-26-000764",
            "filer_cik": "0002152085",
            "filer_name": "Willow Creek Capital Management, Inc.",
            "role": "Filer",
            "is_amendment": False,
        }

    def test_amendment_detected(self):
        result = parse_13f_atom_entry_title(
            "13F-HR/A - Willow Creek Capital Management, Inc. (0002152085) (Filer)",
            "<b>AccNo:</b> 0001085146-26-000764",
            "13F-HR/A",
        )
        assert result["is_amendment"] is True

    def test_none_when_title_malformed(self):
        assert parse_13f_atom_entry_title("Malformed title", "<b>AccNo:</b> 0001-26-000001", "13F-HR") is None

    def test_none_when_accession_missing(self):
        result = parse_13f_atom_entry_title(
            "13F-HR - Some Fund (0002152085) (Filer)", "no accno here", "13F-HR"
        )
        assert result is None


class TestParse13fAtomFeed:
    def test_parses_well_formed_entry_and_skips_malformed(self):
        rows = parse_13f_atom_feed(SAMPLE_ATOM)
        assert len(rows) == 1
        assert rows[0]["filer_name"] == "Willow Creek Capital Management, Inc."
        assert rows[0]["index_url"].endswith("-index.htm")

    def test_empty_feed(self):
        empty = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        assert parse_13f_atom_feed(empty) == []


class TestParse13fInfotableXml:
    def test_parses_real_sample_holdings(self):
        rows = parse_13f_infotable_xml(SAMPLE_INFOTABLE_XML)
        assert len(rows) == 2
        assert rows[0] == {
            "cusip": "002824100",
            "issuer_name": "ABBOTT LABORATORIES",
            "shares": 8885.0,
            "value": 806225.0,
        }
        assert rows[1]["cusip"] == "00287Y109"

    def test_empty_table_returns_empty_list(self):
        xml = '<?xml version="1.0"?><informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable"></informationTable>'
        assert parse_13f_infotable_xml(xml) == []

    def test_holding_without_cusip_is_skipped(self):
        xml = SAMPLE_INFOTABLE_XML.replace("<cusip>00287Y109</cusip>", "<cusip></cusip>")
        rows = parse_13f_infotable_xml(xml)
        assert len(rows) == 1
        assert rows[0]["cusip"] == "002824100"


class TestInfotableXmlUrlFromIndexHtml:
    def test_picks_infotable_not_primary_doc(self):
        url = infotable_xml_url_from_index_html(SAMPLE_INDEX_HTML)
        assert url.endswith("/infotable.xml")
        assert "xsl" not in url
        assert "primary_doc" not in url

    def test_empty_when_no_infotable_present(self):
        html = '<a href="/Archives/edgar/data/x/primary_doc.xml">x</a>'
        assert infotable_xml_url_from_index_html(html) == ""
