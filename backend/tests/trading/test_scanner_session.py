"""
TEST SUITE: Scanner Session Detection
MODULE UNDER TEST: app.trading.scanner_session
TEST TYPE: Unit

Verifies session label, elapsed weight, and projection helpers using fixed
Eastern-time datetime objects — no live clock or network calls required.
"""
from __future__ import annotations

from datetime import datetime

import pytz
import pytest

_ET = pytz.timezone("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    """Build a timezone-aware datetime in US/Eastern for use in tests.

    Args:
        year, month, day, hour, minute, second: Date/time components.

    Returns:
        Timezone-aware datetime in US/Eastern.
    """
    return _ET.localize(datetime(year, month, day, hour, minute, second))


# ── Import module under test ──────────────────────────────────────────────────

from app.trading.scanner_session import (
    get_elapsed_weight,
    get_market_session,
    project_daily_volume,
)


# ── get_market_session tests ──────────────────────────────────────────────────


def test_should_return_closed_when_saturday():
    """Saturday noon ET must yield 'closed' regardless of time."""
    # 2024-01-06 is a Saturday
    dt = _et(2024, 1, 6, 12, 0)
    assert get_market_session(dt) == "closed"


def test_should_return_pre_when_before_930_weekday():
    """Monday 8:00 AM ET is within pre-market hours (4:00–9:30 AM)."""
    # 2024-01-08 is a Monday
    dt = _et(2024, 1, 8, 8, 0)
    assert get_market_session(dt) == "pre"


def test_should_return_open_when_930_to_11():
    """Monday 10:00 AM ET falls in the opening session (9:30–11:00 AM)."""
    dt = _et(2024, 1, 8, 10, 0)
    assert get_market_session(dt) == "open"


def test_should_return_mid_when_11_to_1430():
    """Monday 1:00 PM ET is in the mid-session band (11:00 AM–2:30 PM)."""
    dt = _et(2024, 1, 8, 13, 0)
    assert get_market_session(dt) == "mid"


def test_should_return_power_when_1430_to_1600():
    """Monday 3:00 PM ET falls in the power-hour region (2:30–4:00 PM)."""
    dt = _et(2024, 1, 8, 15, 0)
    assert get_market_session(dt) == "power"


def test_should_return_after_when_after_1600():
    """Monday 5:00 PM ET is after-hours (4:00–8:00 PM)."""
    dt = _et(2024, 1, 8, 17, 0)
    assert get_market_session(dt) == "after"


# ── get_elapsed_weight tests ──────────────────────────────────────────────────


def test_should_return_zero_elapsed_before_open():
    """9:00 AM ET is before the regular session; elapsed weight must be 0.0."""
    dt = _et(2024, 1, 8, 9, 0)
    assert get_elapsed_weight(dt) == 0.0


def test_should_return_correct_elapsed_at_midday():
    """1:00 PM ET = 210 of 390 regular session minutes → ~0.538."""
    dt = _et(2024, 1, 8, 13, 0)
    expected = round(210 / 390, 4)  # 0.5385
    result = get_elapsed_weight(dt)
    # Allow small floating-point tolerance
    assert abs(result - expected) < 0.001, f"Expected ~{expected}, got {result}"


def test_should_return_one_elapsed_at_close():
    """4:00 PM ET is at/after the regular close; elapsed weight must be 1.0."""
    dt = _et(2024, 1, 8, 16, 0)
    assert get_elapsed_weight(dt) == 1.0


# ── project_daily_volume tests ────────────────────────────────────────────────


def test_should_not_divide_by_zero_in_project_daily_volume():
    """project_daily_volume must return intraday_vol unchanged when elapsed_weight == 0."""
    result = project_daily_volume(intraday_vol=500_000, elapsed_weight=0)
    assert result == 500_000


def test_project_daily_volume_scales_correctly():
    """At 50% session elapsed, projected volume should be double the intraday volume."""
    result = project_daily_volume(intraday_vol=1_000_000, elapsed_weight=0.5)
    assert result == pytest.approx(2_000_000, rel=1e-6)
