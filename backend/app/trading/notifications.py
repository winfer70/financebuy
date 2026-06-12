"""
trading/notifications.py — Unified notification dispatcher.

Delivers notifications through three channels:
  1. In-app — inserts into the notifications table.
  2. Email  — sends via the existing SMTP integration (if enabled for event type).
  3. Webhook — POSTs JSON to user-configured webhook URLs.

User preferences are stored in User.preferences JSONB:
  {
      "notifications": {
          "email":   ["signal_entry", "signal_exit", "strategy_decay"],
          "webhook": ["signal_entry", "signal_exit"]
      }
  }
"""

import asyncio
import os
import uuid
import logging
from typing import Optional, Dict, Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trading.notifications")


async def notify(
    db: AsyncSession,
    user_id,
    event_type: str,
    title: str,
    body: str = "",
    metadata: Optional[Dict[str, Any]] = None,
):
    """Send a notification through all enabled channels.

    Always creates an in-app notification. Conditionally sends email and
    webhook based on user preferences.

    Args:
        db:         Async database session.
        user_id:    UUID of the target user.
        event_type: Event identifier (e.g. 'signal_entry', 'backtest_complete').
        title:      Short notification title (max 200 chars).
        body:       Optional longer description text.
        metadata:   Optional JSON-serialisable context (strategy_id, symbol, etc.).
    """
    from ..models import User

    # 1. In-app notification (always)
    await _insert_notification(db, user_id, event_type, title, body, metadata)

    # 2. Load user preferences for conditional channels
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    prefs = (user.preferences or {}).get("notifications", {})

    # 3. Email (if enabled for this event type)
    email_events = prefs.get("email", [])
    if event_type in email_events and user.email:
        await _send_email_notification(user.email, title, body, event_type)

    # 4. Webhook (if configured for this event type)
    webhook_events = prefs.get("webhook", [])
    if event_type in webhook_events:
        await _fire_webhooks(db, user_id, event_type, title, body, metadata)

    # 5. Telegram (always, if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set)
    asyncio.create_task(_send_telegram(title, body))


async def _insert_notification(
    db: AsyncSession,
    user_id,
    event_type: str,
    title: str,
    body: str,
    metadata: Optional[Dict],
):
    """Insert a row into the notifications table.

    Args:
        db:         Async database session.
        user_id:    Target user UUID.
        event_type: Event identifier.
        title:      Notification title.
        body:       Notification body text.
        metadata:   Optional JSON metadata.
    """
    from ..models import Notification

    notif = Notification(
        notification_id=uuid.uuid4(),
        user_id=user_id,
        event_type=event_type,
        title=title,
        body=body,
        metadata_json=metadata,
    )
    db.add(notif)
    await db.flush()
    logger.info("Notification created: user=%s type=%s title=%s", user_id, event_type, title)


async def _send_email_notification(
    email: str, title: str, body: str, event_type: str
):
    """Send an email notification using the existing SMTP setup.

    Args:
        email:      Recipient email address.
        title:      Email subject line.
        body:       Email body text.
        event_type: Event type (used in subject prefix).
    """
    try:
        from ..email import send_email
        subject = f"[TickerTap] {title}"
        html_body = (
            f"<h3>{title}</h3>"
            f"<p>{body}</p>"
            f"<p style='color: #888; font-size: 12px;'>"
            f"Event: {event_type} · "
            f"<a href='https://ticker-tap.com/settings'>Manage preferences</a>"
            f"</p>"
        )
        await send_email(email, subject, html_body)
        logger.info("Email notification sent to %s: %s", email, title)
    except Exception as e:
        logger.warning("Failed to send email to %s: %s", email, e)


async def _fire_webhooks(
    db: AsyncSession,
    user_id,
    event_type: str,
    title: str,
    body: str,
    metadata: Optional[Dict],
):
    """POST notification payload to all active webhooks for this event type.

    Args:
        db:         Async database session.
        user_id:    User UUID.
        event_type: Event identifier.
        title:      Notification title.
        body:       Notification body text.
        metadata:   Optional JSON metadata.
    """
    from ..models import UserWebhook

    result = await db.execute(
        select(UserWebhook).where(
            UserWebhook.user_id == user_id,
            UserWebhook.is_active == True,  # noqa: E712
        )
    )
    webhooks = result.scalars().all()

    payload = {
        "event_type": event_type,
        "title": title,
        "body": body,
        "metadata": metadata or {},
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for wh in webhooks:
            # Check if this webhook subscribes to this event type
            events = wh.events or []
            if event_type not in events:
                continue
            try:
                resp = await client.post(
                    wh.url,
                    json=payload,
                    headers={"User-Agent": "TickerTap-Webhook/1.0"},
                )
                logger.info(
                    "Webhook fired: url=%s status=%d event=%s",
                    wh.url, resp.status_code, event_type,
                )
            except Exception as e:
                logger.warning("Webhook failed: url=%s error=%s", wh.url, e)


async def _send_telegram(title: str, body: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return
    text = f"*{title}*\n{body}" if body else f"*{title}*"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
    except Exception as e:
        logger.warning("Telegram notification failed: %s", e)
