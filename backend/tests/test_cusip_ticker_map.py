"""
============================================================================
TEST SUITE: cusip_ticker_map.resolve_cusips (OpenFIGI CUSIP -> ticker)
============================================================================

Network is mocked throughout — real network verification against actual
CUSIPs from a live 13F filing (Abbott/AbbVie/Air Products) was done during
development to confirm the real OpenFIGI response shape these mocks
reproduce.
============================================================================
"""
from unittest.mock import MagicMock, patch

from app.trading import cusip_ticker_map


def _mock_response(payload: list) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_resolves_multiple_cusips_preferring_us_exchange():
    payload = [
        {
            "data": [
                {"ticker": "ABT", "exchCode": "UA"},
                {"ticker": "ABT", "exchCode": "US"},
            ]
        },
        {"data": [{"ticker": "ABBV", "exchCode": "US"}]},
    ]
    with patch("app.trading.cusip_ticker_map.requests.post", return_value=_mock_response(payload)):
        result = cusip_ticker_map.resolve_cusips(["002824100", "00287Y109"])
    assert result == {"002824100": "ABT", "00287Y109": "ABBV"}


def test_falls_back_to_first_entry_without_us_listing():
    payload = [{"data": [{"ticker": "FOO", "exchCode": "UK"}]}]
    with patch("app.trading.cusip_ticker_map.requests.post", return_value=_mock_response(payload)):
        result = cusip_ticker_map.resolve_cusips(["123456789"])
    assert result == {"123456789": "FOO"}


def test_skips_cusips_with_warning_response():
    payload = [{"warning": "No identifier found."}]
    with patch("app.trading.cusip_ticker_map.requests.post", return_value=_mock_response(payload)):
        result = cusip_ticker_map.resolve_cusips(["000000000"])
    assert result == {}


def test_skips_cusips_with_error_response():
    payload = [{"error": "Invalid idValue format"}]
    with patch("app.trading.cusip_ticker_map.requests.post", return_value=_mock_response(payload)):
        result = cusip_ticker_map.resolve_cusips(["bad"])
    assert result == {}


def test_empty_input_returns_empty_without_network_call():
    mock_post = MagicMock()
    with patch("app.trading.cusip_ticker_map.requests.post", mock_post):
        result = cusip_ticker_map.resolve_cusips([])
    assert result == {}
    mock_post.assert_not_called()


def test_dedupes_repeated_cusips_into_one_batch():
    payload = [{"data": [{"ticker": "ABT", "exchCode": "US"}]}]
    mock_post = MagicMock(return_value=_mock_response(payload))
    with patch("app.trading.cusip_ticker_map.requests.post", mock_post):
        cusip_ticker_map.resolve_cusips(["002824100", "002824100", "002824100"])
    # One POST, and its job list has exactly one entry despite 3 duplicate inputs.
    mock_post.assert_called_once()
    jobs = mock_post.call_args.kwargs["json"]
    assert len(jobs) == 1


def test_network_error_skips_batch_instead_of_raising():
    import requests as _requests

    with patch(
        "app.trading.cusip_ticker_map.requests.post",
        side_effect=_requests.RequestException("boom"),
    ):
        result = cusip_ticker_map.resolve_cusips(["002824100"])
    assert result == {}


def test_batches_over_100_cusips_into_multiple_requests():
    payload = [{"data": [{"ticker": "X", "exchCode": "US"}]}] * 100
    mock_post = MagicMock(return_value=_mock_response(payload))
    cusips = [f"{i:09d}" for i in range(150)]
    with patch("app.trading.cusip_ticker_map.requests.post", mock_post):
        cusip_ticker_map.resolve_cusips(cusips)
    assert mock_post.call_count == 2
