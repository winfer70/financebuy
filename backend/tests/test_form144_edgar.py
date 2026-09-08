"""
============================================================================
TEST SUITE: form144_edgar.parse_form144_xml (Form 144 XML parser)
============================================================================

Sample XML below is a de-identified copy of a real, live Form 144 filing
fetched from EDGAR during development (Circle Internet Group / J.P. Morgan
as agent) — verifies the parser against the actual schema, not a guess at
what it might look like.
============================================================================
"""
from app.trading.form144_edgar import _mdy_to_iso, parse_form144_xml

SAMPLE_144_XML = """<?xml version="1.0" encoding="UTF-8"?><own:edgarSubmission xmlns:com="http://www.sec.gov/edgar/common" xmlns:own="http://www.sec.gov/edgar/ownership">
  <own:headerData>
    <own:submissionType>144</own:submissionType>
    <own:filerInfo>
      <own:filer>
        <own:filerCredentials>
          <own:cik>0001539940</own:cik>
          <own:ccc>XXXXXXXX</own:ccc>
        </own:filerCredentials>
      </own:filer>
      <own:liveTestFlag>LIVE</own:liveTestFlag>
    </own:filerInfo>
  </own:headerData>
  <own:formData>
    <own:issuerInfo>
      <own:issuerCik>0001876042</own:issuerCik>
      <own:issuerName>Circle Internet Group, Inc.</own:issuerName>
      <own:secFileNumber>001-42671</own:secFileNumber>
      <own:nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>Jeremy Allaire</own:nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
      <own:relationshipsToIssuer>
        <own:relationshipToIssuer>Officer</own:relationshipToIssuer>
        <own:relationshipToIssuer>Director</own:relationshipToIssuer>
      </own:relationshipsToIssuer>
    </own:issuerInfo>
    <own:securitiesInformation>
      <own:securitiesClassTitle>Class A Common Stock</own:securitiesClassTitle>
      <own:brokerOrMarketmakerDetails>
        <own:name>J.P. Morgan Securities LLC</own:name>
      </own:brokerOrMarketmakerDetails>
      <own:noOfUnitsSold>177701</own:noOfUnitsSold>
      <own:aggregateMarketValue>18134387</own:aggregateMarketValue>
      <own:noOfUnitsOutstanding>234685190</own:noOfUnitsOutstanding>
      <own:approxSaleDate>09/08/2026</own:approxSaleDate>
      <own:securitiesExchangeName>NYSE</own:securitiesExchangeName>
    </own:securitiesInformation>
    <own:noticeSignature>
      <own:noticeDate>09/08/2026</own:noticeDate>
      <own:signature>/s/ J.P. Morgan Securities LLC as agent and attorney-in-fact for Jeremy Allaire</own:signature>
    </own:noticeSignature>
  </own:formData>
</own:edgarSubmission>"""


def test_parses_real_sample_shape():
    result = parse_form144_xml(SAMPLE_144_XML, accession="0001968582-26-000933", filing_url="https://x/y.xml")
    assert result is not None
    assert result["accession"] == "0001968582-26-000933"
    assert result["issuer_cik"] == "0001876042"
    assert result["issuer_name"] == "Circle Internet Group, Inc."
    assert result["owner_cik"] == "0001539940"
    assert result["owner_name"] == "Jeremy Allaire"
    assert result["relationships"] == "Officer, Director"
    assert result["broker"] == "J.P. Morgan Securities LLC"
    assert result["shares"] == 177701.0
    assert result["aggregate_value"] == 18134387.0
    assert result["approx_sale_date"] == "2026-09-08"
    assert result["notice_date"] == "2026-09-08"
    assert result["filing_url"] == "https://x/y.xml"


def test_none_when_issuer_info_missing():
    xml = """<?xml version="1.0"?><own:edgarSubmission xmlns:own="http://www.sec.gov/edgar/ownership">
      <own:headerData><own:filerInfo><own:filer><own:filerCredentials>
        <own:cik>0001539940</own:cik>
      </own:filerCredentials></own:filer></own:filerInfo></own:headerData>
      <own:formData></own:formData>
    </own:edgarSubmission>"""
    assert parse_form144_xml(xml) is None


def test_none_when_filer_cik_missing():
    xml = """<?xml version="1.0"?><own:edgarSubmission xmlns:own="http://www.sec.gov/edgar/ownership">
      <own:headerData><own:filerInfo></own:filerInfo></own:headerData>
      <own:formData><own:issuerInfo>
        <own:issuerCik>0001876042</own:issuerCik>
      </own:issuerInfo></own:formData>
    </own:edgarSubmission>"""
    assert parse_form144_xml(xml) is None


def test_missing_securities_information_leaves_defaults_not_a_crash():
    xml = """<?xml version="1.0"?><own:edgarSubmission xmlns:own="http://www.sec.gov/edgar/ownership">
      <own:headerData><own:filerInfo><own:filer><own:filerCredentials>
        <own:cik>0001539940</own:cik>
      </own:filerCredentials></own:filer></own:filerInfo></own:headerData>
      <own:formData><own:issuerInfo>
        <own:issuerCik>0001876042</own:issuerCik>
        <own:issuerName>Test Co</own:issuerName>
      </own:issuerInfo></own:formData>
    </own:edgarSubmission>"""
    result = parse_form144_xml(xml, accession="acc-1")
    assert result is not None
    assert result["shares"] == 0.0
    assert result["broker"] == ""
    assert result["approx_sale_date"] is None


class TestMdyToIso:
    def test_converts_valid_date(self):
        assert _mdy_to_iso("09/08/2026") == "2026-09-08"

    def test_empty_string_returns_empty(self):
        assert _mdy_to_iso("") == ""

    def test_malformed_value_returns_empty(self):
        assert _mdy_to_iso("not-a-date") == ""
