"""telegram_invites.py — Invite-gated Telegram chat linking for /register.

An admin generates a one-time invite link; /register only shows a "connect
your Telegram" step when it was opened with a valid, unused code (see
check_telegram_invite). The bot token never needs to be shared with anyone
this is used for — a friend only needs the bot's public @username plus a
short-lived code. Telegram reports the chat_id automatically the moment
they message the bot with that code, which the bot then posts to
link_telegram_chat below.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import TelegramInvite, User
from .auth_routes import get_current_admin, get_current_user_or_bot

router = APIRouter(tags=["telegram-invites"])

_INVITE_TTL_DAYS = 14
LINK_CODE_TTL_MINUTES = 30


async def _require_bot(current: Union[User, dict] = Depends(get_current_user_or_bot)):
    """Only the tickerTap Telegram bot (X-Bot-Api-Key) may call this — not a
    regular user's JWT, even their own."""
    is_bot = current.get("is_bot") if isinstance(current, dict) else getattr(current, "is_bot", False)
    if not is_bot:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bot credentials required")
    return current


class InviteOut(BaseModel):
    code: str
    expires_at: datetime
    register_url: str


class InviteCheckOut(BaseModel):
    valid: bool


class TelegramLinkRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=16)
    chat_id: str = Field(..., min_length=1, max_length=64)


class TelegramLinkOut(BaseModel):
    linked: bool
    first_name: Optional[str] = None


@router.post("/admin/telegram-invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def create_telegram_invite(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """Admin-only: mint a one-time registration invite that unlocks the
    Telegram-connect step on /register. The code works exactly once —
    share the returned register_url, not the bare code.
    """
    code = secrets.token_urlsafe(9)
    expires_at = datetime.now(timezone.utc) + timedelta(days=_INVITE_TTL_DAYS)
    invite = TelegramInvite(created_by=current_admin.user_id, code=code, expires_at=expires_at)
    db.add(invite)
    await db.commit()

    app_url = os.getenv("APP_URL", "https://localhost").rstrip("/")
    return InviteOut(
        code=code,
        expires_at=expires_at,
        register_url=f"{app_url}/register?invite={code}",
    )


@router.get("/telegram-invites/{code}", response_model=InviteCheckOut)
async def check_telegram_invite(code: str, db: AsyncSession = Depends(get_db)):
    """Public, unauthenticated: does this code currently unlock the
    Telegram-connect step on /register? Called by the register page before
    it shows that UI — never reveals who created the invite or any other
    detail, just a boolean.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(select(TelegramInvite).where(TelegramInvite.code == code[:32]))
    invite = result.scalar_one_or_none()
    valid = bool(invite and invite.used_by is None and invite.expires_at > now)
    return InviteCheckOut(valid=valid)


@router.post("/internal/telegram/link", response_model=TelegramLinkOut)
async def link_telegram_chat(
    payload: TelegramLinkRequest,
    db: AsyncSession = Depends(get_db),
    _bot: Union[User, dict] = Depends(_require_bot),
):
    """Bot-only: called by the /link <code> Telegram command handler with
    the chat_id Telegram reported on that update. The bot token is checked
    by the X-Bot-Api-Key dependency above — it never appears in this
    payload, and the caller (a Telegram user) never sees it either.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User).where(
            User.telegram_link_code == payload.code[:16],
            User.telegram_link_code_expires_at.is_not(None),
            User.telegram_link_code_expires_at > now,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        return TelegramLinkOut(linked=False)

    user.telegram_chat_id = payload.chat_id[:64]
    user.telegram_link_code = None
    user.telegram_link_code_expires_at = None
    await db.commit()
    return TelegramLinkOut(linked=True, first_name=user.first_name)
