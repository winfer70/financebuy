"""
============================================================================
TEST SUITE: insider_track_record.compute_track_record (shared module)
============================================================================

Both routes/insider.py (web API/UI) and insider_monitor.py (Telegram) call
this same function so the two surfaces never disagree about an owner's
track record. See test_insider_routes.py::TestOwnerBreakdownTrackRecord and
test_insider_monitor.py's Telegram-body tests for the integration-level
coverage on each caller; this file covers the computation itself directly.
============================================================================
"""
import os
from datetime import date, timedelta

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest

from app.trading.insider_track_record import compute_track_record


def test_none_with_fewer_than_two_trades():
    rows = [{"transaction_code": "P", "transaction_date": date(2026, 1, 1), "shares": 100}]
    assert compute_track_record(rows, [("2026-01-01", 100.0)]) is None


def test_none_with_no_price_bars():
    rows = [
        {"transaction_code": "P", "transaction_date": date(2026, 1, 1), "shares": 100},
        {"transaction_code": "S", "transaction_date": date(2026, 2, 1), "shares": 50},
    ]
    assert compute_track_record(rows, []) is None


def test_favorable_track_record_win_rate_and_label():
    today = date(2026, 6, 1)
    d_p, d_p_future = today - timedelta(days=60), today - timedelta(days=30)
    d_s, d_s_future = today - timedelta(days=45), today - timedelta(days=15)
    rows = [
        {"transaction_code": "P", "transaction_date": d_p, "shares": 1000},
        {"transaction_code": "S", "transaction_date": d_s, "shares": 500},
    ]
    bars = [
        (d_p.isoformat(), 100.0),
        (d_p_future.isoformat(), 110.0),  # buy +10% -> hit
        (d_s.isoformat(), 105.0),
        (d_s_future.isoformat(), 95.0),   # sell, price fell -> hit
    ]
    tr = compute_track_record(rows, bars, today=today)
    assert tr is not None
    assert tr.evaluated == 2
    assert tr.win_rate == 1.0
    assert tr.avg_aligned_return_pct == pytest.approx(9.76, abs=0.01)
    assert "Favorable" in tr.label


def test_unfavorable_when_both_trades_go_the_wrong_way():
    today = date(2026, 6, 1)
    d_p, d_p_future = today - timedelta(days=60), today - timedelta(days=30)
    d_s, d_s_future = today - timedelta(days=45), today - timedelta(days=15)
    rows = [
        {"transaction_code": "P", "transaction_date": d_p, "shares": 1000},
        {"transaction_code": "S", "transaction_date": d_s, "shares": 500},
    ]
    bars = [
        (d_p.isoformat(), 100.0),
        (d_p_future.isoformat(), 90.0),   # buy then price fell -> miss
        (d_s.isoformat(), 100.0),
        (d_s_future.isoformat(), 110.0),  # sell then price rose -> miss
    ]
    tr = compute_track_record(rows, bars, today=today)
    assert tr.win_rate == 0.0
    assert "Unfavorable" in tr.label


def test_too_recent_trades_return_explanatory_label_not_none():
    today = date(2026, 6, 1)
    rows = [
        {"transaction_code": "P", "transaction_date": today - timedelta(days=5), "shares": 100},
        {"transaction_code": "S", "transaction_date": today - timedelta(days=2), "shares": 50},
    ]
    bars = [(today.isoformat(), 100.0)]
    tr = compute_track_record(rows, bars, today=today)
    assert tr is not None
    assert tr.evaluated == 0
    assert tr.win_rate is None
    assert "Not enough time" in tr.label


def test_non_ps_codes_are_ignored():
    """Grants/withholding (A/F) shouldn't count toward sample_size or be
    scored — only genuine open-market P/S trades carry directional intent."""
    rows = [
        {"transaction_code": "A", "transaction_date": date(2026, 1, 1), "shares": 5000},
        {"transaction_code": "F", "transaction_date": date(2026, 1, 1), "shares": 1800},
    ]
    assert compute_track_record(rows, [("2026-01-01", 100.0)]) is None
