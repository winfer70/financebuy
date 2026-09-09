"""
============================================================================
TEST SUITE: insider_edgar.parse_form3_xml (Form 3 XML parser)
============================================================================

Sample XML below is a de-identified copy of a real, live Form 3 filing
fetched from EDGAR during development (First Breach, Inc. / Andrew
Pearlman) — verifies the parser against the actual schema. Form 3 uses the
same ownershipDocument XML family as Form 4, just with nonDerivativeHolding
(a starting position) instead of nonDerivativeTransaction (a trade).
============================================================================
"""
from app.trading.insider_edgar import parse_form3_xml

SAMPLE_FORM3_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <schemaVersion>X0607</schemaVersion>
    <documentType>3</documentType>
    <periodOfReport>2026-08-12</periodOfReport>
    <noSecuritiesOwned>0</noSecuritiesOwned>
    <issuer>
        <issuerCik>0001892704</issuerCik>
        <issuerName>First Breach, Inc.</issuerName>
        <issuerTradingSymbol>FBDT</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0002153290</rptOwnerCik>
            <rptOwnerName>PEARLMAN ANDREW SHAWN</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>true</isDirector>
            <isOfficer>false</isOfficer>
            <isTenPercentOwner>false</isTenPercentOwner>
            <isOther>false</isOther>
            <officerTitle></officerTitle>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeHolding>
            <securityTitle><value>Common Stock</value></securityTitle>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>100</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeHolding>
    </nonDerivativeTable>
    <derivativeTable></derivativeTable>
    <ownerSignature>
        <signatureName>/s/ Andrew S. Pearlman</signatureName>
        <signatureDate>2026-09-08</signatureDate>
    </ownerSignature>
</ownershipDocument>"""


def test_parses_real_sample_shape():
    result = parse_form3_xml(SAMPLE_FORM3_XML, accession="0001213900-26-098148", filing_url="https://x/y.xml")
    assert result is not None
    assert result["accession"] == "0001213900-26-098148"
    assert result["ticker"] == "FBDT"
    assert result["issuer_cik"] == "0001892704"
    assert result["owner_name"] == "PEARLMAN ANDREW SHAWN"
    assert result["owner_cik"] == "0002153290"
    assert result["is_director"] is True
    assert result["is_officer"] is False
    assert result["is_ten_percent"] is False
    assert result["shares_owned"] == 100.0
    assert result["period_of_report"] == "2026-08-12"
    assert result["signature_date"] == "2026-09-08"
    assert result["filing_url"] == "https://x/y.xml"


def test_sums_multiple_holdings():
    """A director might hold both direct and indirect shares — both
    nonDerivativeHolding blocks should be summed into one total."""
    xml = SAMPLE_FORM3_XML.replace(
        "</nonDerivativeTable>",
        """<nonDerivativeHolding>
            <securityTitle><value>Common Stock</value></securityTitle>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>50</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeHolding></nonDerivativeTable>""",
    )
    result = parse_form3_xml(xml, accession="acc-1")
    assert result["shares_owned"] == 150.0


def test_none_when_ticker_missing():
    xml = SAMPLE_FORM3_XML.replace("<issuerTradingSymbol>FBDT</issuerTradingSymbol>", "<issuerTradingSymbol></issuerTradingSymbol>")
    assert parse_form3_xml(xml) is None


def test_none_when_owner_cik_missing():
    xml = SAMPLE_FORM3_XML.replace("<rptOwnerCik>0002153290</rptOwnerCik>", "<rptOwnerCik></rptOwnerCik>")
    assert parse_form3_xml(xml) is None


def test_zero_holdings_when_no_securities_owned():
    """noSecuritiesOwned=1 filings have an empty nonDerivativeTable —
    should parse cleanly to shares_owned=0, not crash."""
    xml = SAMPLE_FORM3_XML.replace(
        """<nonDerivativeTable>
        <nonDerivativeHolding>
            <securityTitle><value>Common Stock</value></securityTitle>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>100</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeHolding>
    </nonDerivativeTable>""",
        "<nonDerivativeTable></nonDerivativeTable>",
    ).replace("<noSecuritiesOwned>0</noSecuritiesOwned>", "<noSecuritiesOwned>1</noSecuritiesOwned>")
    result = parse_form3_xml(xml, accession="acc-2")
    assert result is not None
    assert result["shares_owned"] == 0.0
