"""
============================================================================
TEST SUITE: Insider (Form 4) API — routes/insider.py
============================================================================

MODULE UNDER TEST: app.routes.insider
TEST TYPE: Integration (HTTP via TestClient, DB mocked)
FRAMEWORK: pytest + FastAPI TestClient

DESCRIPTION:
    Covers the two read-only endpoints added for the Form 4 browser UI
    (InsiderPage.jsx): paginated/sortable filing listing, and the per-person
    (owner_cik) breakdown used by the "PERSON BREAKDOWN" panel. Neither had
    test coverage — the 35 "insider tests passed" in HANDOFF.md are
    insider_briefing/insider_gate/insider_monitor, not this module.

COVERAGE SCOPE:
    ✓ GET /insider/filings   — happy path shape, unknown sort column falls
                                back to transaction_date instead of raising
    ✓ GET /insider/owners/{cik} — buy/sell aggregation, avg sell interval,
                                   10b5-1 share, 404 on no rows, 400 on blank cik
============================================================================
"""
import os
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest

from tests.conftest import make_scalar_count_result, make_scalars_result


def _mock_filing(**overrides):
    row = MagicMock()
    defaults = dict(
        filing_id=uuid.uuid4(),
        accession="0001214156-26-000123",
        ticker="AAPL",
        owner_name="COOK TIMOTHY",
        owner_cik="0001214156",
        officer_title="CEO",
        is_director=True,
        is_officer=True,
        transaction_code="S",
        acquired_disposed="D",
        shares=Decimal("2000"),
        price=Decimal("150.00"),
        notional=Decimal("300000.00"),
        shares_after=Decimal("3000000"),
        stake_pct=Decimal("0.02"),
        transaction_date=date(2026, 9, 1),
        is_10b5_1=True,
        filing_url="https://sec.gov/example",
        created_at=None,
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: GET /api/v1/insider/filings
# ═══════════════════════════════════════════════════════════════════════════


class TestListFilings:
    def test_returns_items_and_total(self, auth_client):
        client, db, _user = auth_client
        rows = [_mock_filing(), _mock_filing(transaction_code="P", owner_name="JONES SUE")]
        db.execute.side_effect = [make_scalar_count_result(2), make_scalars_result(rows)]

        resp = client.get("/api/v1/insider/filings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert body["items"][0]["ticker"] == "AAPL"
        assert body["items"][0]["transaction_date"] == "2026-09-01"

    def test_unknown_sort_column_falls_back_instead_of_500(self, auth_client):
        """sort=<garbage> must not raise — _SORTABLE.get() falls back to
        transaction_date rather than passing an invalid column to order_by()."""
        client, db, _user = auth_client
        db.execute.side_effect = [make_scalar_count_result(0), make_scalars_result([])]

        resp = client.get("/api/v1/insider/filings", params={"sort": "'; DROP TABLE users; --"})
        assert resp.status_code == 200
        assert resp.json() == {"total": 0, "items": []}

    def test_requires_auth(self):
        from app.main import app
        from app.db import get_db
        from fastapi.testclient import TestClient

        async def override_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.get("/api/v1/insider/filings")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: GET /api/v1/insider/owners/{owner_cik}
# ═══════════════════════════════════════════════════════════════════════════


class TestOwnerBreakdown:
    def test_computes_buy_sell_stats_and_sell_cadence(self, auth_client):
        client, db, _user = auth_client
        rows = [
            _mock_filing(
                transaction_code="P",
                acquired_disposed="A",
                transaction_date=date(2026, 1, 5),
                shares=Decimal("1000"),
                notional=Decimal("100000"),
                is_10b5_1=False,
            ),
            _mock_filing(
                transaction_code="S",
                acquired_disposed="D",
                transaction_date=date(2026, 2, 4),
                shares=Decimal("400"),
                notional=Decimal("60000"),
                is_10b5_1=True,
            ),
            _mock_filing(
                transaction_code="S",
                acquired_disposed="D",
                transaction_date=date(2026, 3, 6),
                shares=Decimal("400"),
                notional=Decimal("62000"),
                is_10b5_1=True,
            ),
        ]
        db.execute.return_value = make_scalars_result(rows)

        resp = client.get("/api/v1/insider/owners/0001214156")
        assert resp.status_code == 200
        body = resp.json()
        assert body["buy_count"] == 1
        assert body["sell_count"] == 2
        assert body["buy_shares"] == 1000
        assert body["sell_shares"] == 800
        assert body["net_shares"] == 200
        # Sells on Feb 4 -> Mar 6 = 30 days apart, single gap.
        assert body["avg_sell_interval_days"] == 30
        # 2 of 3 rows are 10b5-1.
        assert body["pct_10b5_1"] == pytest.approx(2 / 3)
        assert len(body["transactions"]) == 3

    def test_grants_and_withholding_are_not_all_zero(self, auth_client):
        """Regression test: an owner whose window has zero open-market P/S
        trades (routine RSU grant + tax-withholding pair, the common case
        for a compensation-heavy executive) must not show all-zero
        acquired/disposed figures just because neither row is coded P or S.
        acquired_disposed ("A" grant, "D" withholding) is the SEC form's own
        flag and must drive the aggregation instead."""
        client, db, _user = auth_client
        rows = [
            _mock_filing(
                transaction_code="A",  # award/grant
                acquired_disposed="A",
                transaction_date=date(2026, 1, 15),
                shares=Decimal("5000"),
                price=Decimal("0"),
                notional=Decimal("0"),
                is_10b5_1=False,
            ),
            _mock_filing(
                transaction_code="F",  # tax withholding on vest
                acquired_disposed="D",
                transaction_date=date(2026, 1, 15),
                shares=Decimal("1800"),
                price=Decimal("150.00"),
                notional=Decimal("270000"),
                is_10b5_1=False,
            ),
        ]
        db.execute.return_value = make_scalars_result(rows)

        resp = client.get("/api/v1/insider/owners/0001214156")
        assert resp.status_code == 200
        body = resp.json()
        assert body["buy_count"] == 1
        assert body["buy_shares"] == 5000
        assert body["sell_count"] == 1
        assert body["sell_shares"] == 1800
        assert body["net_shares"] == 3200
        # Neither row is transaction_code "S", so sell cadence stays empty —
        # that stat is intentionally scoped to genuine open-market sells.
        assert body["avg_sell_interval_days"] is None

    def test_404_when_no_filings_in_window(self, auth_client):
        client, db, _user = auth_client
        db.execute.return_value = make_scalars_result([])

        resp = client.get("/api/v1/insider/owners/0001214156")
        assert resp.status_code == 404

    def test_400_when_cik_blank(self, auth_client):
        client, _db, _user = auth_client

        resp = client.get("/api/v1/insider/owners/%20")
        assert resp.status_code == 400
