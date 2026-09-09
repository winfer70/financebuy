"""
============================================================================
TEST SUITE: schedule13_edgar (Schedule 13D/13G XML parsers)
============================================================================

Samples below are trimmed copies of two real, live filings fetched from
EDGAR during development (Sono Group N.V. 13D — a 9-person joint "group"
filing; Metalla Royalty & Streaming Ltd. 13G — a single institutional
filer) — verifies both parsers against their actual (and genuinely
different) schemas, not a guess at what they might look like.
============================================================================
"""
from app.trading.schedule13_edgar import parse_schedule13d_xml, parse_schedule13g_xml

SAMPLE_13D_XML = """<?xml version="1.0" encoding="UTF-8"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D" xmlns:com="http://www.sec.gov/edgar/common">
  <headerData>
    <submissionType>SCHEDULE 13D</submissionType>
    <filerInfo><filer><filerCredentials><cik>0001842872</cik></filerCredentials></filer></filerInfo>
  </headerData>
  <formData>
    <coverPageHeader>
      <dateOfEvent>08/31/2026</dateOfEvent>
      <issuerInfo>
        <issuerCIK>0001840416</issuerCIK>
        <issuerName>Sono Group N.V.</issuerName>
      </issuerInfo>
    </coverPageHeader>
    <reportingPersons>
      <reportingPersonInfo>
        <reportingPersonCIK>0001842872</reportingPersonCIK>
        <reportingPersonName>Christopher Kelly</reportingPersonName>
        <aggregateAmountOwned>93633.00</aggregateAmountOwned>
        <percentOfClass>5.5</percentOfClass>
        <typeOfReportingPerson>IN</typeOfReportingPerson>
      </reportingPersonInfo>
      <reportingPersonInfo>
        <reportingPersonNoCIK>Y</reportingPersonNoCIK>
        <reportingPersonName>Kelly Ventures I LP</reportingPersonName>
        <aggregateAmountOwned>37453.00</aggregateAmountOwned>
        <percentOfClass>2.2</percentOfClass>
        <typeOfReportingPerson>PN</typeOfReportingPerson>
      </reportingPersonInfo>
    </reportingPersons>
    <items1To7>
      <item4>
        <transactionPurpose>The Reporting Persons are acquiring the Ordinary Shares in connection with a proposed business combination.</transactionPurpose>
      </item4>
    </items1To7>
  </formData>
</edgarSubmission>"""

SAMPLE_13G_XML = """<?xml version="1.0" encoding="UTF-8"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g" xmlns:com="http://www.sec.gov/edgar/common">
  <headerData>
    <submissionType>SCHEDULE 13G</submissionType>
    <filerInfo><filer><filerCredentials><cik>0001796651</cik></filerCredentials></filer></filerInfo>
  </headerData>
  <formData>
    <coverPageHeader>
      <eventDateRequiresFilingThisStatement>08/31/2026</eventDateRequiresFilingThisStatement>
      <issuerInfo>
        <issuerCik>0001722606</issuerCik>
        <issuerName>Metalla Royalty &amp; Streaming Ltd.</issuerName>
      </issuerInfo>
    </coverPageHeader>
    <coverPageHeaderReportingPersonDetails>
      <reportingPersonName>Euro Pacific Asset Management, LLC</reportingPersonName>
      <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>5830289.00</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
      <classPercent>6.2</classPercent>
      <typeOfReportingPerson>IA</typeOfReportingPerson>
    </coverPageHeaderReportingPersonDetails>
  </formData>
</edgarSubmission>"""


class TestParseSchedule13D:
    def test_parses_real_sample_multi_person(self):
        rows = parse_schedule13d_xml(SAMPLE_13D_XML, accession="acc-13d", filing_url="https://x/13d.xml")
        assert len(rows) == 2
        first = rows[0]
        assert first["accession"] == "acc-13d"
        assert first["person_index"] == 0
        assert first["is_13d"] is True
        assert first["is_amendment"] is False
        assert first["issuer_cik"] == "0001840416"
        assert first["issuer_name"] == "Sono Group N.V."
        assert first["filer_cik"] == "0001842872"
        assert first["filer_name"] == "Christopher Kelly"
        assert first["shares_owned"] == 93633.0
        assert first["pct_owned"] == 5.5
        assert first["event_date"] == "2026-08-31"
        assert "business combination" in first["purpose_text"]

    def test_second_person_has_no_cik_but_still_parses(self):
        rows = parse_schedule13d_xml(SAMPLE_13D_XML, accession="acc-13d")
        second = rows[1]
        assert second["person_index"] == 1
        assert second["filer_cik"] == ""
        assert second["filer_name"] == "Kelly Ventures I LP"
        assert second["shares_owned"] == 37453.0

    def test_amendment_detected_from_submission_type_suffix(self):
        xml = SAMPLE_13D_XML.replace("SCHEDULE 13D<", "SCHEDULE 13D/A<")
        rows = parse_schedule13d_xml(xml, accession="acc-amend")
        assert rows[0]["is_amendment"] is True

    def test_empty_list_when_issuer_cik_missing(self):
        xml = SAMPLE_13D_XML.replace("<issuerCIK>0001840416</issuerCIK>", "<issuerCIK></issuerCIK>")
        assert parse_schedule13d_xml(xml) == []

    def test_empty_list_when_no_reporting_persons(self):
        xml = SAMPLE_13D_XML.replace(
            SAMPLE_13D_XML[SAMPLE_13D_XML.index("<reportingPersons>"):SAMPLE_13D_XML.index("</reportingPersons>") + len("</reportingPersons>")],
            "<reportingPersons></reportingPersons>",
        )
        assert parse_schedule13d_xml(xml, accession="acc-empty") == []


class TestParseSchedule13G:
    def test_parses_real_sample_single_filer(self):
        rows = parse_schedule13g_xml(SAMPLE_13G_XML, accession="acc-13g", filing_url="https://x/13g.xml")
        assert len(rows) == 1
        row = rows[0]
        assert row["is_13d"] is False
        assert row["is_amendment"] is False
        assert row["issuer_cik"] == "0001722606"
        assert row["issuer_name"] == "Metalla Royalty & Streaming Ltd."
        assert row["filer_name"] == "Euro Pacific Asset Management, LLC"
        assert row["shares_owned"] == 5830289.0
        assert row["pct_owned"] == 6.2
        assert row["event_date"] == "2026-08-31"
        assert row["purpose_text"] == ""

    def test_falls_back_to_top_level_filer_cik(self):
        """13G's per-person cover-page block has no CIK field at all —
        must fall back to the top-level filerInfo/filer/filerCredentials/cik."""
        rows = parse_schedule13g_xml(SAMPLE_13G_XML, accession="acc-13g")
        assert rows[0]["filer_cik"] == "0001796651"

    def test_amendment_detected_from_submission_type_suffix(self):
        xml = SAMPLE_13G_XML.replace("SCHEDULE 13G<", "SCHEDULE 13G/A<")
        rows = parse_schedule13g_xml(xml, accession="acc-amend")
        assert rows[0]["is_amendment"] is True

    def test_empty_list_when_issuer_cik_missing(self):
        xml = SAMPLE_13G_XML.replace("<issuerCik>0001722606</issuerCik>", "<issuerCik></issuerCik>")
        assert parse_schedule13g_xml(xml) == []
