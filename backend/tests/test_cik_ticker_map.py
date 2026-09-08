"""
============================================================================
TEST SUITE: cik_ticker_map.resolve_ticker (CIK -> ticker resolution)
============================================================================

Form 144's XML only carries the issuer's CIK, not the ticker (unlike Form
4's embedded issuerTradingSymbol) — this module is the standalone lookup
that makes a 144 notice joinable against the rest of the ticker-keyed
schema. Network is mocked throughout; the cache is reset between tests
since it's module-level state.
============================================================================
"""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("SEC_USER_AGENT", "TickerTap Test test@example.com")

import pytest

from app.trading import cik_ticker_map


@pytest.fixture(autouse=True)
def _reset_cache():
    cik_ticker_map._cache = {}
    cik_ticker_map._cache_loaded_at = 0.0
    yield
    cik_ticker_map._cache = {}
    cik_ticker_map._cache_loaded_at = 0.0


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


SAMPLE_PAYLOAD = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "2": {"cik_str": 1876042, "ticker": "CRCL", "title": "Circle Internet Group, Inc."},
}


def test_resolves_ticker_for_known_cik():
    with patch("app.trading.cik_ticker_map.requests.get", return_value=_mock_response(SAMPLE_PAYLOAD)):
        assert cik_ticker_map.resolve_ticker("0001876042") == "CRCL"


def test_strips_leading_zeros_from_cik():
    with patch("app.trading.cik_ticker_map.requests.get", return_value=_mock_response(SAMPLE_PAYLOAD)):
        assert cik_ticker_map.resolve_ticker("320193") == "AAPL"
        assert cik_ticker_map.resolve_ticker("0000320193") == "AAPL"


def test_unknown_cik_returns_none():
    with patch("app.trading.cik_ticker_map.requests.get", return_value=_mock_response(SAMPLE_PAYLOAD)):
        assert cik_ticker_map.resolve_ticker("9999999999") is None


def test_non_numeric_cik_returns_none_without_network_call():
    mock_get = MagicMock()
    with patch("app.trading.cik_ticker_map.requests.get", mock_get):
        assert cik_ticker_map.resolve_ticker("not-a-cik") is None
    mock_get.assert_not_called()


def test_missing_user_agent_returns_none(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert cik_ticker_map.resolve_ticker("0001876042") is None


def test_network_error_falls_back_to_stale_cache_instead_of_raising():
    with patch("app.trading.cik_ticker_map.requests.get", return_value=_mock_response(SAMPLE_PAYLOAD)):
        assert cik_ticker_map.resolve_ticker("0001876042") == "CRCL"

    with patch("app.trading.cik_ticker_map.requests.get", side_effect=ConnectionError("boom")):
        # Cache is fresh (just populated above) so this shouldn't even
        # attempt a refetch, but even if it did, it must not raise.
        assert cik_ticker_map.resolve_ticker("0001876042") == "CRCL"


def test_second_call_within_ttl_does_not_refetch():
    mock_get = MagicMock(return_value=_mock_response(SAMPLE_PAYLOAD))
    with patch("app.trading.cik_ticker_map.requests.get", mock_get):
        cik_ticker_map.resolve_ticker("0001876042")
        cik_ticker_map.resolve_ticker("0000320193")
    assert mock_get.call_count == 1
