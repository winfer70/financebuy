"""
TEST SUITE: Two-stage soft-stop alerts
MODULE UNDER TEST: app.trading.alert_worker, app.trading.notifications
TEST TYPE: Unit (prices and HTTP mocked)
"""

import os
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap",
)

import pytest

from app.trading.alert_worker import (
    _apply_stage_result,
    _check_soft_stops,
    _pending_channels,
    _stage_done,
    evaluate_one_soft_stop,
    reset_soft_stop_stages,
)
from app.trading.notifications import _send_ntfy, _send_telegram, notify_soft_stop


TODAY = date(2026, 9, 2)


class FakePos:
    def __init__(self, soft=150.0):
        self.position_id = uuid.uuid4()
        self.ticker = "AAPL"
        self.soft_stop_loss = soft
        self.soft_stop_intraday_on = None
        self.soft_stop_eod_on = None
        self.soft_stop_delivery_json = None
        self.closed_at = None

    def reset_soft_stop_stages(self):
        self.soft_stop_intraday_on = None
        self.soft_stop_eod_on = None
        self.soft_stop_delivery_json = None


def _session_with(pos, user_id):
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(pos, user_id)]
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return session


def test_stage_done_and_pending_channels():
    pos = FakePos()
    assert _stage_done(pos, "intraday", TODAY) is False
    send_tg, send_ntfy, send_in_app = _pending_channels(pos, "intraday", TODAY)
    assert (send_tg, send_ntfy, send_in_app) == (True, True, True)

    _apply_stage_result(
        pos, "intraday", TODAY,
        {"telegram": True, "ntfy": False},
        send_telegram=True, send_ntfy=True, send_in_app=True,
    )
    assert pos.soft_stop_intraday_on == TODAY
    assert _stage_done(pos, "intraday", TODAY) is False
    send_tg, send_ntfy, send_in_app = _pending_channels(pos, "intraday", TODAY)
    assert send_tg is False
    assert send_ntfy is True
    assert send_in_app is False


def test_reset_clears_stage_dates():
    pos = FakePos()
    pos.soft_stop_intraday_on = TODAY
    pos.soft_stop_eod_on = TODAY
    pos.soft_stop_delivery_json = {"intraday": {"date": TODAY.isoformat()}}
    reset_soft_stop_stages(pos)
    assert pos.soft_stop_intraday_on is None
    assert pos.soft_stop_eod_on is None
    assert pos.soft_stop_delivery_json is None


@pytest.mark.asyncio
async def test_stage1_does_not_clear_stop_and_fires_once():
    pos = FakePos(150.0)
    user_id = uuid.uuid4()
    session = _session_with(pos, user_id)
    notify = AsyncMock(return_value={"telegram": True, "ntfy": True, "in_app": True})

    with (
        patch("app.trading.alert_worker._is_market_open", return_value=True),
        patch("app.trading.alert_worker._is_after_rth_close", return_value=False),
        patch("app.trading.alert_worker._ny_today", return_value=TODAY),
        patch("app.trading.alert_worker._fetch_price", return_value=140.0),
        patch("app.trading.alert_worker.notify_soft_stop", notify),
    ):
        await _check_soft_stops(session)
        await _check_soft_stops(session)

    assert pos.soft_stop_loss == 150.0
    assert pos.soft_stop_intraday_on == TODAY
    assert pos.soft_stop_eod_on is None
    assert notify.await_count == 1
    kwargs = notify.await_args.kwargs
    assert kwargs["event_type"] == "soft_stop_loss"
    assert kwargs["ntfy_priority"] == 3
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_stage2_close_below_fires_eod():
    pos = FakePos(150.0)
    user_id = uuid.uuid4()
    session = _session_with(pos, user_id)
    notify = AsyncMock(return_value={"telegram": True, "ntfy": True, "in_app": True})

    with (
        patch("app.trading.alert_worker._is_market_open", return_value=False),
        patch("app.trading.alert_worker._is_after_rth_close", return_value=True),
        patch("app.trading.alert_worker._ny_today", return_value=TODAY),
        patch("app.trading.alert_worker._fetch_daily_close", return_value=140.0),
        patch("app.trading.alert_worker.notify_soft_stop", notify),
    ):
        await _check_soft_stops(session)

    assert pos.soft_stop_loss == 150.0
    assert pos.soft_stop_eod_on == TODAY
    assert notify.await_count == 1
    assert notify.await_args.kwargs["event_type"] == "soft_stop_eod"
    assert notify.await_args.kwargs["ntfy_priority"] == 5


@pytest.mark.asyncio
async def test_stage2_close_above_is_shakeout():
    pos = FakePos(150.0)
    session = _session_with(pos, uuid.uuid4())
    notify = AsyncMock(return_value={"telegram": True, "ntfy": True, "in_app": True})

    with (
        patch("app.trading.alert_worker._is_market_open", return_value=False),
        patch("app.trading.alert_worker._is_after_rth_close", return_value=True),
        patch("app.trading.alert_worker._ny_today", return_value=TODAY),
        patch("app.trading.alert_worker._fetch_daily_close", return_value=160.0),
        patch("app.trading.alert_worker.notify_soft_stop", notify),
    ):
        await _check_soft_stops(session)

    assert notify.await_count == 0
    assert pos.soft_stop_eod_on is None
    assert pos.soft_stop_loss == 150.0
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_immediate_check_fires_when_market_closed():
    pos = FakePos(150.0)
    pos.position_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = (pos, user_id)
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    notify = AsyncMock(return_value={"telegram": True, "ntfy": True, "in_app": True})

    with (
        patch("app.trading.alert_worker._SessionLocal", return_value=session),
        patch("app.trading.alert_worker._is_market_open", return_value=False),
        patch("app.trading.alert_worker._is_after_rth_close", return_value=False),
        patch("app.trading.alert_worker._ny_today", return_value=TODAY),
        patch("app.trading.alert_worker._fetch_price", return_value=140.0),
        patch("app.trading.alert_worker.notify_soft_stop", notify),
    ):
        await evaluate_one_soft_stop({}, str(pos.position_id))

    assert notify.await_count == 1
    assert pos.soft_stop_loss == 150.0
    assert pos.soft_stop_intraday_on == TODAY
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_immediate_check_skips_when_price_above_stop():
    pos = FakePos(150.0)
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = (pos, uuid.uuid4())
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.close = AsyncMock()
    notify = AsyncMock()

    with (
        patch("app.trading.alert_worker._SessionLocal", return_value=session),
        patch("app.trading.alert_worker._fetch_price", return_value=160.0),
        patch("app.trading.alert_worker.notify_soft_stop", notify),
    ):
        await evaluate_one_soft_stop({}, str(pos.position_id))

    assert notify.await_count == 0
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_failed_channel_without_new_in_app():
    pos = FakePos(150.0)
    session = _session_with(pos, uuid.uuid4())
    notify = AsyncMock(
        side_effect=[
            {"telegram": False, "ntfy": True, "in_app": True},
            {"telegram": True, "ntfy": True, "in_app": False},
        ]
    )

    with (
        patch("app.trading.alert_worker._is_market_open", return_value=True),
        patch("app.trading.alert_worker._is_after_rth_close", return_value=False),
        patch("app.trading.alert_worker._ny_today", return_value=TODAY),
        patch("app.trading.alert_worker._fetch_price", return_value=140.0),
        patch("app.trading.alert_worker.notify_soft_stop", notify),
    ):
        await _check_soft_stops(session)
        await _check_soft_stops(session)

    assert notify.await_count == 2
    first = notify.await_args_list[0].kwargs
    second = notify.await_args_list[1].kwargs
    assert first["send_in_app"] is True
    assert first["send_telegram"] is True
    assert first["send_ntfy"] is True
    assert second["send_in_app"] is False
    assert second["send_telegram"] is True
    assert second["send_ntfy"] is False
    assert _stage_done(pos, "intraday", TODAY) is True


@pytest.mark.asyncio
async def test_both_channels_fail_does_not_mark_date():
    pos = FakePos(150.0)
    session = _session_with(pos, uuid.uuid4())
    notify = AsyncMock(return_value={"telegram": False, "ntfy": False, "in_app": True})

    with (
        patch("app.trading.alert_worker._is_market_open", return_value=True),
        patch("app.trading.alert_worker._is_after_rth_close", return_value=False),
        patch("app.trading.alert_worker._ny_today", return_value=TODAY),
        patch("app.trading.alert_worker._fetch_price", return_value=140.0),
        patch("app.trading.alert_worker.notify_soft_stop", notify),
    ):
        await _check_soft_stops(session)

    assert pos.soft_stop_intraday_on is None
    assert pos.soft_stop_loss == 150.0


@pytest.mark.asyncio
async def test_send_telegram_returns_false_on_http_error():
    os.environ["TELEGRAM_BOT_TOKEN"] = "token"
    os.environ["TELEGRAM_CHAT_ID"] = "123"
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    try:
        with patch("app.trading.notifications.httpx.AsyncClient", return_value=mock_client):
            ok = await _send_telegram("t", "b")
        assert ok is False
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)


@pytest.mark.asyncio
async def test_send_ntfy_posts_to_topic():
    os.environ["NTFY_URL"] = "https://ntfy.example"
    os.environ["NTFY_TOPIC"] = "tickertap-alerts"
    os.environ["NTFY_TOKEN"] = "secret"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    try:
        with patch("app.trading.notifications.httpx.AsyncClient", return_value=mock_client):
            ok = await _send_ntfy("title", "body", priority=5)
        assert ok is True
        args, kwargs = mock_client.post.await_args
        assert args[0] == "https://ntfy.example/tickertap-alerts"
        assert kwargs["headers"]["Priority"] == "5"
        assert kwargs["headers"]["Authorization"] == "Bearer secret"
    finally:
        os.environ.pop("NTFY_URL", None)
        os.environ.pop("NTFY_TOPIC", None)
        os.environ.pop("NTFY_TOKEN", None)


@pytest.mark.asyncio
async def test_notify_soft_stop_awaits_both_channels():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    with (
        patch("app.trading.notifications._send_telegram", AsyncMock(return_value=True)) as tg,
        patch("app.trading.notifications._send_ntfy", AsyncMock(return_value=False)) as ntfy,
    ):
        result = await notify_soft_stop(
            db, uuid.uuid4(), "soft_stop_loss", "t", "b", ntfy_priority=3
        )
    assert result == {"telegram": True, "ntfy": False, "in_app": True}
    tg.assert_awaited_once()
    ntfy.assert_awaited_once()
    db.add.assert_called_once()


def test_changing_soft_stop_value_resets_stage_dates():
    """Mirrors modify_position: any actual soft-stop change clears stage state."""
    from decimal import Decimal

    pos = FakePos()
    pos.soft_stop_loss = Decimal("150.00")
    pos.soft_stop_intraday_on = TODAY
    pos.soft_stop_eod_on = TODAY
    pos.soft_stop_delivery_json = {"intraday": {"date": TODAY.isoformat()}}
    new_soft = Decimal("145.00")
    if new_soft != pos.soft_stop_loss:
        pos.reset_soft_stop_stages()
    pos.soft_stop_loss = new_soft
    assert pos.soft_stop_intraday_on is None
    assert pos.soft_stop_eod_on is None
    assert pos.soft_stop_delivery_json is None
    assert pos.soft_stop_loss == new_soft


def test_patch_soft_stop_resets_stage_dates(auth_client):
    from datetime import datetime, timezone
    from decimal import Decimal

    from tests.conftest import make_scalar_result

    client, db, user = auth_client
    pos = FakePos(150.0)
    pos.soft_stop_intraday_on = TODAY
    pos.soft_stop_eod_on = TODAY
    pos.soft_stop_delivery_json = {"intraday": {"date": TODAY.isoformat()}}
    pos.soft_stop_loss = Decimal("150.00")
    pos.hard_stop_loss = None
    pos.profit_taking = None
    pos.quantity = Decimal("1")
    pos.purchase_price = Decimal("160.00")
    pos.group_tag = None
    pos.is_excluded = False
    pos.asset_type = "stock"
    pos.physical_type = None
    pos.portfolio_id = uuid.uuid4()
    pos.name = "Apple"
    pos.purchase_date = None
    pos.created_at = datetime.now(timezone.utc)

    db.execute.return_value = make_scalar_result(pos)
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = client.patch(
        f"/api/v1/portfolio-manager/positions/{pos.position_id}",
        json={"soft_stop_loss": 145.0},
    )
    assert pos.soft_stop_intraday_on is None
    assert pos.soft_stop_eod_on is None
    assert pos.soft_stop_delivery_json is None
    assert float(pos.soft_stop_loss) == 145.0
    assert resp.status_code == 200
