"""
============================================================================
TEST SUITE: Telegram invite-gated registration + per-user chat linking
============================================================================

MODULES UNDER TEST:
    app.routes.telegram_invites (admin create, public check, bot-only link)
    app.routes.auth_routes.register_user (telegram_invite_code handling)
    app.trading.notifications (_resolve_telegram_chat_id, _send_telegram)

DESCRIPTION:
    A friend can register via an invite-gated link and connect their own
    Telegram chat for notifications without ever seeing TELEGRAM_BOT_TOKEN:
      1. Admin mints a one-time code (POST /admin/telegram-invites).
      2. Register page checks it (GET /telegram-invites/{code}) before
         showing the Telegram-connect step.
      3. POST /auth/register with that code marks it used and hands the new
         account a short-lived telegram_link_code + the bot's public
         @username.
      4. The user DMs the bot "/link <code>"; the bot (X-Bot-Api-Key) posts
         to POST /internal/telegram/link with the chat_id Telegram reported;
         this is the only place chat_id is ever recorded — the friend never
         sends or sees the bot token.
      5. Notification delivery (_send_telegram / _resolve_telegram_chat_id)
         then targets that user's own chat_id instead of the global one.
============================================================================
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest
from fastapi import HTTPException

from tests.conftest import make_scalar_result


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: POST /admin/telegram-invites (admin-only)
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateTelegramInvite:
    @pytest.mark.asyncio
    async def test_admin_can_create_an_invite(self):
        from app.routes.telegram_invites import create_telegram_invite

        db = AsyncMock()
        db.add = MagicMock()
        admin = MagicMock(user_id=uuid.uuid4())

        result = await create_telegram_invite(db=db, current_admin=admin)

        assert result.code
        assert result.register_url.endswith(f"/register?invite={result.code}")
        assert db.add.called
        assert db.commit.await_count == 1

    def test_non_admin_cannot_create_an_invite(self, auth_client):
        client, _db, _user = auth_client
        # get_current_admin isn't overridden by auth_client — the plain
        # get_current_user override doesn't satisfy the admin dependency,
        # so this should be rejected before touching the DB at all.
        resp = client.post("/api/v1/admin/telegram-invites")
        assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: GET /telegram-invites/{code} (public)
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckTelegramInvite:
    def test_valid_unused_unexpired_code_is_valid(self, auth_client):
        client, db, _user = auth_client
        invite = MagicMock(used_by=None, expires_at=datetime.now(timezone.utc) + timedelta(days=1))
        db.execute.return_value = make_scalar_result(invite)

        resp = client.get("/api/v1/telegram-invites/some-code")
        assert resp.status_code == 200
        assert resp.json() == {"valid": True}

    def test_used_code_is_invalid(self, auth_client):
        client, db, _user = auth_client
        invite = MagicMock(used_by=uuid.uuid4(), expires_at=datetime.now(timezone.utc) + timedelta(days=1))
        db.execute.return_value = make_scalar_result(invite)

        resp = client.get("/api/v1/telegram-invites/some-code")
        assert resp.status_code == 200
        assert resp.json() == {"valid": False}

    def test_expired_code_is_invalid(self, auth_client):
        client, db, _user = auth_client
        invite = MagicMock(used_by=None, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        db.execute.return_value = make_scalar_result(invite)

        resp = client.get("/api/v1/telegram-invites/some-code")
        assert resp.status_code == 200
        assert resp.json() == {"valid": False}

    def test_unknown_code_is_invalid(self, auth_client):
        client, db, _user = auth_client
        db.execute.return_value = make_scalar_result(None)

        resp = client.get("/api/v1/telegram-invites/does-not-exist")
        assert resp.status_code == 200
        assert resp.json() == {"valid": False}

    def test_requires_no_auth(self, auth_client):
        """This endpoint must work for a not-yet-registered visitor."""
        client, db, _user = auth_client
        db.execute.return_value = make_scalar_result(None)
        # auth_client still overrides get_current_user, but check_telegram_invite
        # has no auth dependency at all — verify it doesn't 401 regardless.
        resp = client.get("/api/v1/telegram-invites/anything")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3: POST /internal/telegram/link (bot-only)
# ═══════════════════════════════════════════════════════════════════════════


class TestLinkTelegramChat:
    @pytest.mark.asyncio
    async def test_valid_code_links_chat_id(self):
        from app.routes.telegram_invites import link_telegram_chat, TelegramLinkRequest

        db = AsyncMock()
        target_user = MagicMock(first_name="Alex")
        db.execute.return_value = make_scalar_result(target_user)

        result = await link_telegram_chat(
            TelegramLinkRequest(code="abc123", chat_id="999888777"),
            db=db,
            _bot={"is_bot": True, "user_id": ""},
        )

        assert result.linked is True
        assert result.first_name == "Alex"
        assert target_user.telegram_chat_id == "999888777"
        assert target_user.telegram_link_code is None
        assert target_user.telegram_link_code_expires_at is None

    @pytest.mark.asyncio
    async def test_unknown_or_expired_code_does_not_link(self):
        from app.routes.telegram_invites import link_telegram_chat, TelegramLinkRequest

        db = AsyncMock()
        db.execute.return_value = make_scalar_result(None)

        result = await link_telegram_chat(
            TelegramLinkRequest(code="expired", chat_id="1"),
            db=db,
            _bot={"is_bot": True, "user_id": ""},
        )
        assert result.linked is False

    def test_endpoint_rejects_non_bot_caller(self):
        """A regular user's own JWT must not be able to call this — only
        the bot's X-Bot-Api-Key should work, even to link their own chat."""
        from app.main import app
        from app.db import get_db
        from app.routes.auth_routes import get_current_user_or_bot
        from fastapi.testclient import TestClient

        real_user = MagicMock(is_bot=False)

        async def override_db():
            yield AsyncMock()

        async def override_user_or_bot():
            return real_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user_or_bot] = override_user_or_bot
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.post(
                "/api/v1/internal/telegram/link", json={"code": "x", "chat_id": "1"}
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 4: notifications.py — per-user chat_id resolution
# ═══════════════════════════════════════════════════════════════════════════


class TestRegisterWithTelegramInvite:
    def test_valid_invite_generates_link_code_and_bot_username(self, monkeypatch):
        import uuid as _uuid
        from app.main import app
        from app.db import get_db
        from fastapi.testclient import TestClient

        monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "MyTickerTapBot")
        invite = MagicMock(used_by=None, expires_at=datetime.now(timezone.utc) + timedelta(days=1))

        async def override_db():
            existing_user_result = MagicMock()
            existing_user_result.scalar_one_or_none.return_value = None  # no duplicate email
            invite_result = MagicMock()
            invite_result.scalar_one_or_none.return_value = invite

            session = AsyncMock()
            session.execute = AsyncMock(side_effect=[existing_user_result, invite_result])
            session.commit = AsyncMock()

            async def _refresh(obj):
                if getattr(obj, "user_id", None) is None:
                    obj.user_id = _uuid.uuid4()
                if getattr(obj, "kyc_status", None) is None:
                    obj.kyc_status = "not_verified"
                if getattr(obj, "is_active", None) is None:
                    obj.is_active = True

            session.refresh = AsyncMock(side_effect=_refresh)
            yield session

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        try:
            resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "friend@example.com",
                    "password": "StrongPass123!",
                    "telegram_invite_code": "some-code",
                },
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["telegram_link_code"]
            assert body["telegram_bot_username"] == "MyTickerTapBot"
            # Regression: user.user_id relied on the column's default=uuid.uuid4,
            # which only fires at flush/INSERT — reading it this early (before
            # db.add/commit) returned None, so the invite recorded "used by
            # nobody" instead of the actual new account.
            assert invite.used_by is not None
            assert str(invite.used_by) == body["user_id"]
            assert invite.used_at is not None
        finally:
            app.dependency_overrides.clear()

    def test_registration_without_invite_code_has_no_telegram_fields(self):
        import uuid as _uuid
        from app.main import app
        from app.db import get_db
        from fastapi.testclient import TestClient

        async def override_db():
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            session = AsyncMock()
            session.execute = AsyncMock(return_value=result)
            session.commit = AsyncMock()

            async def _refresh(obj):
                if getattr(obj, "user_id", None) is None:
                    obj.user_id = _uuid.uuid4()
                if getattr(obj, "kyc_status", None) is None:
                    obj.kyc_status = "not_verified"
                if getattr(obj, "is_active", None) is None:
                    obj.is_active = True

            session.refresh = AsyncMock(side_effect=_refresh)
            yield session

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        try:
            resp = client.post(
                "/api/v1/auth/register",
                json={"email": "nobody@example.com", "password": "StrongPass123!"},
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["telegram_link_code"] is None
            assert body["telegram_bot_username"] is None
        finally:
            app.dependency_overrides.clear()


class TestResolveTelegramChatId:
    @pytest.mark.asyncio
    async def test_uses_users_own_linked_chat_when_set(self, monkeypatch):
        from app.trading.notifications import _resolve_telegram_chat_id

        monkeypatch.setenv("TELEGRAM_CHAT_ID", "owner-chat")
        db = AsyncMock()
        db.execute.return_value = make_scalar_result("friend-chat")

        chat_id = await _resolve_telegram_chat_id(db, uuid.uuid4())
        assert chat_id == "friend-chat"

    @pytest.mark.asyncio
    async def test_falls_back_to_owner_chat_when_user_has_none_linked(self, monkeypatch):
        from app.trading.notifications import _resolve_telegram_chat_id

        monkeypatch.setenv("TELEGRAM_CHAT_ID", "owner-chat")
        db = AsyncMock()
        db.execute.return_value = make_scalar_result(None)

        chat_id = await _resolve_telegram_chat_id(db, uuid.uuid4())
        assert chat_id == "owner-chat"

    @pytest.mark.asyncio
    async def test_falls_back_to_owner_chat_when_user_id_is_none(self, monkeypatch):
        from app.trading.notifications import _resolve_telegram_chat_id

        monkeypatch.setenv("TELEGRAM_CHAT_ID", "owner-chat")
        db = AsyncMock()

        chat_id = await _resolve_telegram_chat_id(db, None)
        assert chat_id == "owner-chat"
        db.execute.assert_not_called()


class TestSendTelegramChatIdOverride:
    @pytest.mark.asyncio
    async def test_uses_provided_chat_id_over_env_default(self, monkeypatch):
        from app.trading import notifications as notif_module

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "owner-chat")

        mock_response = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(notif_module.httpx, "AsyncClient", lambda *a, **k: mock_client_cm)
            ok = await notif_module._send_telegram("title", "body", chat_id="friend-chat")

        assert ok is True
        sent_json = mock_client.post.call_args.kwargs["json"]
        assert sent_json["chat_id"] == "friend-chat"
