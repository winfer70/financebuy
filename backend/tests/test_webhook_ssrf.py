"""
============================================================================
TEST SUITE: Webhook SSRF guards
============================================================================

MODULES UNDER TEST: app.trading.notifications, app.routes.trading
TEST TYPE: Unit (DNS + HTTP mocked)
FRAMEWORK: pytest + pytest-asyncio + unittest.mock

DESCRIPTION:
    Regression tests for an SSRF hole: user-registered webhooks were only
    checked for an "https://" prefix, and the server then POSTs to that URL
    itself (_fire_webhooks) with no restriction on destination — a user
    could register a webhook pointed at an internal service (e.g. a cloud
    metadata endpoint at 169.254.169.254, or an admin API on the private
    network) and use the notification path as an SSRF proxy.

    Two independent checks were added:
      1. validate_webhook_url_shape + check_webhook_host_safe, enforced at
         registration time via routes/trading.py's _require_safe_webhook_url
         (create_webhook / update_webhook).
      2. check_webhook_host_safe re-run immediately before every send in
         _fire_webhooks, since DNS can change between registration and send
         (rebinding) — a registration-time check alone is not sufficient.
    _fire_webhooks' httpx client also now sets follow_redirects=False, since
    a malicious endpoint could otherwise redirect the request to an internal
    address after the host check passes.

COVERAGE SCOPE:
    ✓ _is_disallowed_ip        — private/loopback/link-local(incl. cloud
                                  metadata)/unparseable rejected; public allowed
    ✓ validate_webhook_url_shape — scheme + localhost rejected
    ✓ check_webhook_host_safe  — DNS-resolved private IP rejected; DNS
                                  failure treated as unsafe
    ✓ _require_safe_webhook_url — the route-level guard combines both checks
    ✓ _fire_webhooks           — skips sending when the send-time check fails
============================================================================
"""
import os
import socket
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "memory://")

import pytest
from fastapi import HTTPException

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: _is_disallowed_ip
# ═══════════════════════════════════════════════════════════════════════════


class TestIsDisallowedIp:
    def test_private_ipv4_ranges_rejected(self):
        from app.trading.notifications import _is_disallowed_ip

        assert _is_disallowed_ip("10.0.0.5") is True
        assert _is_disallowed_ip("192.168.1.1") is True
        assert _is_disallowed_ip("172.16.0.1") is True

    def test_loopback_rejected(self):
        from app.trading.notifications import _is_disallowed_ip

        assert _is_disallowed_ip("127.0.0.1") is True
        assert _is_disallowed_ip("::1") is True

    def test_cloud_metadata_link_local_address_rejected(self):
        from app.trading.notifications import _is_disallowed_ip

        # 169.254.169.254 — AWS/GCP/Azure instance metadata endpoint.
        assert _is_disallowed_ip("169.254.169.254") is True

    def test_public_ip_allowed(self):
        from app.trading.notifications import _is_disallowed_ip

        assert _is_disallowed_ip("8.8.8.8") is False

    def test_unparseable_address_treated_as_unsafe(self):
        from app.trading.notifications import _is_disallowed_ip

        assert _is_disallowed_ip("not-an-ip") is True


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: validate_webhook_url_shape
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateWebhookUrlShape:
    def test_rejects_non_https_scheme(self):
        from app.trading.notifications import validate_webhook_url_shape

        with pytest.raises(ValueError, match="HTTPS"):
            validate_webhook_url_shape("http://example.com/hook")

    def test_rejects_localhost(self):
        from app.trading.notifications import validate_webhook_url_shape

        with pytest.raises(ValueError, match="localhost"):
            validate_webhook_url_shape("https://localhost/hook")

    def test_accepts_public_https_url_and_returns_hostname(self):
        from app.trading.notifications import validate_webhook_url_shape

        assert validate_webhook_url_shape("https://example.com/hook") == "example.com"


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3: check_webhook_host_safe (DNS resolve + check)
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckWebhookHostSafe:
    @pytest.mark.asyncio
    async def test_rejects_host_resolving_to_private_ip(self):
        from app.trading.notifications import check_webhook_host_safe

        fake_infos = [(socket.AF_INET, None, None, "", ("10.0.0.5", 443))]
        with patch("app.trading.notifications.socket.getaddrinfo", return_value=fake_infos):
            assert await check_webhook_host_safe("internal.example") is False

    @pytest.mark.asyncio
    async def test_accepts_host_resolving_to_public_ip(self):
        from app.trading.notifications import check_webhook_host_safe

        fake_infos = [(socket.AF_INET, None, None, "", ("93.184.216.34", 443))]
        with patch("app.trading.notifications.socket.getaddrinfo", return_value=fake_infos):
            assert await check_webhook_host_safe("example.com") is True

    @pytest.mark.asyncio
    async def test_dns_resolution_failure_is_treated_as_unsafe(self):
        from app.trading.notifications import check_webhook_host_safe

        with patch(
            "app.trading.notifications.socket.getaddrinfo",
            side_effect=socket.gaierror,
        ):
            assert await check_webhook_host_safe("nonexistent.invalid") is False


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 4: routes/trading.py — _require_safe_webhook_url (registration-time)
# ═══════════════════════════════════════════════════════════════════════════


class TestRequireSafeWebhookUrl:
    @pytest.mark.asyncio
    async def test_rejects_http_scheme(self):
        from app.routes.trading import _require_safe_webhook_url

        with pytest.raises(HTTPException) as exc_info:
            await _require_safe_webhook_url("http://example.com/hook")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_url_whose_host_resolves_unsafe(self):
        from app.routes import trading as trading_module

        with patch.object(trading_module, "check_webhook_host_safe", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await trading_module._require_safe_webhook_url("https://internal.example/hook")
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_accepts_safe_public_url(self):
        from app.routes import trading as trading_module

        with patch.object(trading_module, "check_webhook_host_safe", AsyncMock(return_value=True)):
            # Should not raise.
            await trading_module._require_safe_webhook_url("https://example.com/hook")


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 5: trading/notifications.py — _fire_webhooks send-time re-check
# ═══════════════════════════════════════════════════════════════════════════


class TestFireWebhooksSendTimeCheck:
    @pytest.mark.asyncio
    async def test_skips_send_when_host_is_currently_unsafe(self):
        from app.trading import notifications as notifications_module

        db = AsyncMock()
        wh = MagicMock()
        wh.url = "https://rebound.example/hook"
        wh.events = ["signal_entry"]
        wh.is_active = True

        result = MagicMock()
        result.scalars.return_value.all.return_value = [wh]
        db.execute = AsyncMock(return_value=result)

        mock_client = AsyncMock()
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(
            notifications_module, "check_webhook_host_safe", AsyncMock(return_value=False)
        ), patch.object(notifications_module.httpx, "AsyncClient", return_value=mock_client_cm):
            await notifications_module._fire_webhooks(
                db, uuid.uuid4(), "signal_entry", "Title", "Body", None
            )

        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_when_host_is_safe(self):
        from app.trading import notifications as notifications_module

        db = AsyncMock()
        wh = MagicMock()
        wh.url = "https://example.com/hook"
        wh.events = ["signal_entry"]
        wh.is_active = True

        result = MagicMock()
        result.scalars.return_value.all.return_value = [wh]
        db.execute = AsyncMock(return_value=result)

        mock_response = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(
            notifications_module, "check_webhook_host_safe", AsyncMock(return_value=True)
        ), patch.object(notifications_module.httpx, "AsyncClient", return_value=mock_client_cm):
            await notifications_module._fire_webhooks(
                db, uuid.uuid4(), "signal_entry", "Title", "Body", None
            )

        mock_client.post.assert_called_once()
