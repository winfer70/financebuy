"""
============================================================================
TEST SUITE: form8k_edgar.parse_8k_atom_feed (Form 8-K atom-only parser)
============================================================================

Sample entries below are trimmed copies of real, live 8-K atom entries
fetched from EDGAR during development — verifies that item codes, CIK, and
issuer name can all be extracted directly from the atom feed with no
per-filing document fetch (unlike every other filing type in this
codebase), since 8-K volume is too high to fetch documents for entries
that get filtered out anyway.
============================================================================
"""
from app.trading.form8k_edgar import parse_8k_atom_feed

SAMPLE_ATOM = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>8-K - Sound Point Meridian Capital, Inc. (0001930147) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1930147/000182912626009903/0001829126-26-009903-index.htm"/>
<summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-09-08 &lt;b&gt;AccNo:&lt;/b&gt; 0001829126-26-009903 &lt;b&gt;Size:&lt;/b&gt; 253 KB
&lt;br&gt;Item 8.01: Other Events
</summary>
<updated>2026-09-08T17:29:43-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0001829126-26-009903</id>
</entry>
<entry>
<title>8-K/A - Vivos Therapeutics, Inc. (0001716166) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1716166/000149315226041807/0001493152-26-041807-index.htm"/>
<summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-09-08 &lt;b&gt;AccNo:&lt;/b&gt; 0001493152-26-041807 &lt;b&gt;Size:&lt;/b&gt; 241 KB
&lt;br&gt;Item 1.01: Entry into a Material Definitive Agreement
&lt;br&gt;Item 3.02: Unregistered Sales of Equity Securities
&lt;br&gt;Item 9.01: Financial Statements and Exhibits
</summary>
<updated>2026-09-08T17:29:33-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K/A"/>
<id>urn:tag:sec.gov,2008:accession-number=0001493152-26-041807</id>
</entry>
<entry>
<title>Malformed title with no CIK</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/x"/>
<summary type="html">&lt;b&gt;AccNo:&lt;/b&gt; 0000000000-26-000000</summary>
<updated>2026-09-08T17:00:00-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0000000000-26-000000</id>
</entry>
</feed>"""


def test_parses_single_item_entry():
    rows = parse_8k_atom_feed(SAMPLE_ATOM)
    first = rows[0]
    assert first["accession"] == "0001829126-26-009903"
    assert first["issuer_cik"] == "0001930147"
    assert first["issuer_name"] == "Sound Point Meridian Capital, Inc."
    assert first["role"] == "Filer"
    assert first["is_amendment"] is False
    assert first["items"] == [{"code": "8.01", "description": "Other Events"}]
    assert first["index_url"].endswith("-index.htm")
    assert first["updated"] == "2026-09-08T17:29:43-04:00"


def test_parses_multi_item_amendment_entry():
    rows = parse_8k_atom_feed(SAMPLE_ATOM)
    second = rows[1]
    assert second["accession"] == "0001493152-26-041807"
    assert second["issuer_cik"] == "0001716166"
    assert second["is_amendment"] is True
    assert len(second["items"]) == 3
    assert second["items"][0] == {
        "code": "1.01",
        "description": "Entry into a Material Definitive Agreement",
    }


def test_malformed_title_entry_is_skipped_not_crashed():
    rows = parse_8k_atom_feed(SAMPLE_ATOM)
    # Only the 2 well-formed entries should survive; the malformed third is dropped.
    assert len(rows) == 2


def test_empty_feed_returns_empty_list():
    empty = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    assert parse_8k_atom_feed(empty) == []
