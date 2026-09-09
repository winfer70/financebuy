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
import ipaddress
import os
import socket
import uuid
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trading.notifications")


# ── Webhook SSRF guards ─────────────────────────────────────────────────────
#
# User-registered webhooks are fetched server-side (see _fire_webhooks below),
# so an unrestricted URL lets a user turn this server into an SSRF proxy
# against internal services (e.g. cloud metadata endpoints, admin APIs on the
# private network). Two checks are needed, not one:
#   1. At registration (routes/trading.py create_webhook/update_webhook) —
#      reject obviously-unsafe URLs up front.
#   2. Immediately before every send (here) — DNS can change between
#      registration and send (DNS rebinding), so a registration-time check
#      alone is not sufficient.


def _is_disallowed_ip(ip_str: str) -> bool:
    """True if this address is private, loopback, link-local (this also
    covers the 169.254.169.254 cloud-metadata endpoint), reserved,
    multicast, or unspecified — i.e. not a normal public address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_webhook_url_shape(url: str) -> str:
    """Reject obviously-invalid webhook URLs (scheme, missing host, localhost).

    Returns the parsed hostname on success. Does not check DNS — callers must
    also call check_webhook_host_safe (async) for the resolve-and-check step.

    Raises:
        ValueError: with a user-facing reason.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use HTTPS.")
    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL must include a hostname.")
    if host.lower() == "localhost":
        raise ValueError("Webhook URL may not target localhost.")
    return host


async def check_webhook_host_safe(host: str) -> bool:
    """Resolve `host` and return False if any resolved address is unsafe
    (see _is_disallowed_ip) or resolution fails."""
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror:
        return False
    addrs = {info[4][0] for info in infos}
    return bool(addrs) and not any(_is_disallowed_ip(a) for a in addrs)


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

    # 5. Telegram — this user's own linked chat if they have one (see
    # telegram_invites.py), else the single configured owner chat. Still
    # only actually sends if TELEGRAM_BOT_TOKEN is set.
    await _send_telegram(title, body, chat_id=user.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID"))


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

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        for wh in webhooks:
            # Check if this webhook subscribes to this event type
            events = wh.events or []
            if event_type not in events:
                continue
            # Re-check the host immediately before sending — DNS may have
            # changed since registration (rebinding). follow_redirects=False
            # above stops a malicious endpoint from redirecting us to an
            # internal address after this check passes.
            host = urlparse(wh.url).hostname
            if not host or not await check_webhook_host_safe(host):
                logger.warning("Webhook skipped — unsafe host: url=%s", wh.url)
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


async def _resolve_telegram_chat_id(db: AsyncSession, user_id) -> Optional[str]:
    """This user's own linked Telegram chat (see telegram_invites.py's /link
    flow), falling back to the single configured owner chat if they haven't
    linked one — preserves existing single-owner behavior for every account
    that never went through the Telegram-invite flow."""
    from ..models import User

    if user_id is not None:
        result = await db.execute(select(User.telegram_chat_id).where(User.user_id == user_id))
        chat_id = result.scalar_one_or_none()
        if chat_id:
            return chat_id
    return os.getenv("TELEGRAM_CHAT_ID")


async def _send_telegram(title: str, body: str, *, chat_id: Optional[str] = None) -> bool:
    """Send a Telegram message. True on 2xx or if Telegram is not configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return True
    text = f"{title}\n{body}" if body else title
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            ok = 200 <= resp.status_code < 300
            if not ok:
                logger.warning("Telegram notification failed: status=%s", resp.status_code)
            return ok
    except Exception as e:
        logger.warning("Telegram notification failed: %s", e)
        return False


async def _send_ntfy(title: str, body: str, priority: int = 3) -> bool:
    """POST to ntfy. True on 2xx or if NTFY_URL is not configured."""
    base = os.getenv("NTFY_URL", "").rstrip("/")
    if not base:
        return True
    topic = os.getenv("NTFY_TOPIC", "tickertap-alerts")
    token = os.getenv("NTFY_TOKEN", "")
    headers = {
        "Title": title,
        "Priority": str(priority),
        "Tags": "warning,chart_with_downwards_trend",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.post(
                f"{base}/{topic}",
                content=(body or title).encode(),
                headers=headers,
            )
            ok = 200 <= resp.status_code < 300
            if not ok:
                logger.warning("ntfy notification failed: status=%s", resp.status_code)
            return ok
    except Exception as e:
        logger.warning("ntfy notification failed: %s", e)
        return False


async def notify_soft_stop(
    db: AsyncSession,
    user_id,
    event_type: str,
    title: str,
    body: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    ntfy_priority: int = 3,
    send_in_app: bool = True,
    send_telegram: bool = True,
    send_ntfy: bool = True,
) -> Dict[str, bool]:
    """Deliver a soft-stop alert. Awaits Telegram + ntfy; returns per-channel success."""
    if send_in_app:
        await _insert_notification(db, user_id, event_type, title, body, metadata)

    telegram_ok = True
    ntfy_ok = True
    if send_telegram:
        chat_id = await _resolve_telegram_chat_id(db, user_id)
        telegram_ok = await _send_telegram(title, body, chat_id=chat_id)
    if send_ntfy:
        ntfy_ok = await _send_ntfy(title, body, ntfy_priority)

    return {"telegram": telegram_ok, "ntfy": ntfy_ok, "in_app": send_in_app}
