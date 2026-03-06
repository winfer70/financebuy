"""
email.py — Email sending utilities for TickerTap.

Provides a generic send_email() base function and purpose-specific senders
for password reset, email verification, account reactivation, deletion
cancellation, email change, and admin report notifications.

All emails use the TickerTap Bloomberg-terminal HTML template aesthetic.

Configuration (environment variables):
    SMTP_HOST           — SMTP server hostname (default: smtp.example.com)
    SMTP_PORT           — SMTP server port (default: 587)
    SMTP_USER           — SMTP authentication username
    SMTP_PASS           — SMTP authentication password
    SMTP_FROM           — From address (default: same as SMTP_USER)
    SMTP_SKIP_TLS_VERIFY — Disable TLS cert verification (dev only)
    ENVIRONMENT         — Blocks SMTP_SKIP_TLS_VERIFY in production
    ADMIN_EMAIL         — Address for admin notifications (bug reports)
"""

import html
import logging
import os
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

logger = logging.getLogger(__name__)


# ── SMTP Configuration ──────────────────────────────────────────────────────

def _smtp_config():
    """Return SMTP connection parameters from environment variables.

    Returns:
        dict: Keys hostname, port, username, password, from_addr, tls_context.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.example.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", smtp_user)

    tls_context = ssl.create_default_context()
    _env = os.getenv("ENVIRONMENT", "development").lower()
    _skip_verify = os.getenv("SMTP_SKIP_TLS_VERIFY", "").lower() in ("1", "true", "yes")

    if _skip_verify and _env == "production":
        import sys
        print(
            "FATAL: SMTP_SKIP_TLS_VERIFY must not be enabled in production — "
            "this disables certificate verification and exposes tokens. "
            "Remove SMTP_SKIP_TLS_VERIFY from your production environment.",
            file=sys.stderr,
        )
        raise RuntimeError("SMTP_SKIP_TLS_VERIFY is disallowed in production")

    if _skip_verify:
        tls_context.check_hostname = False
        tls_context.verify_mode = ssl.CERT_NONE

    return {
        "hostname": smtp_host,
        "port": smtp_port,
        "username": smtp_user,
        "password": smtp_pass,
        "from_addr": from_addr,
        "tls_context": tls_context,
    }


# ── HTML Template ────────────────────────────────────────────────────────────

def _wrap_html(body_html: str) -> str:
    """Wrap email body in the TickerTap Bloomberg-terminal HTML template.

    Args:
        body_html: Inner HTML content for the email body.

    Returns:
        Full HTML string with header, body, and footer styled in the terminal theme.
    """
    return f"""
    <div style="font-family:monospace;background:#0d0e11;color:#c8ccd4;padding:32px;max-width:480px">
      <div style="font-size:18px;font-weight:700;color:#f0b429;letter-spacing:2px;margin-bottom:8px">
        TICKER-TAP
      </div>
      <div style="font-size:12px;color:#6b7280;margin-bottom:24px">
        Professional Investment Terminal
      </div>
      {body_html}
      <p style="margin-top:24px;font-size:11px;color:#6b7280">
        If you didn't request this action, you can safely ignore this email.
      </p>
    </div>
    """


def _action_button(url: str, label: str) -> str:
    """Generate a styled call-to-action button for emails.

    Args:
        url: Target URL for the button link.
        label: Display text on the button.

    Returns:
        HTML string for the button element.
    """
    return (
        f'<a href="{url}" '
        f'style="display:inline-block;background:#f0b429;color:#0d0e11;font-weight:700;'
        f'letter-spacing:1px;padding:12px 24px;text-decoration:none;border-radius:2px">'
        f'{label}</a>'
    )


# ── Generic Sender ───────────────────────────────────────────────────────────

async def send_email(to_email: str, subject: str, plain: str, html: str) -> None:
    """Send an email via the configured SMTP server.

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        plain: Plain-text body content.
        html: HTML body content.

    Raises:
        aiosmtplib.SMTPException: If the SMTP server rejects the email.
    """
    cfg = _smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=cfg["hostname"],
        port=cfg["port"],
        username=cfg["username"],
        password=cfg["password"],
        start_tls=True,
        tls_context=cfg["tls_context"],
    )


# ── Purpose-Specific Senders ────────────────────────────────────────────────

async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    """Send a password reset email with a one-time link.

    Args:
        to_email: Recipient email address.
        reset_url: Full URL with reset token for the password reset page.
    """
    plain = (
        f"You requested a password reset for your Ticker-Tap account.\n\n"
        f"Click the link below to set a new password (expires in 1 hour):\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, ignore this email."
    )
    html = _wrap_html(
        f"<p style='margin-bottom:16px'>"
        f"You requested a password reset. Click the button below — the link expires in <strong>1 hour</strong>."
        f"</p>"
        f"{_action_button(reset_url, 'RESET PASSWORD')}"
        f"<p style='margin-top:16px;font-size:11px;color:#6b7280'>Link: {reset_url}</p>"
    )
    await send_email(to_email, "Reset your Ticker-Tap password", plain, html)


async def send_verification_email(to_email: str, verify_url: str) -> None:
    """Send an email verification link for new account registration.

    Args:
        to_email: Recipient email address.
        verify_url: Full URL with verification token.
    """
    plain = (
        f"Welcome to Ticker-Tap! Please verify your email address.\n\n"
        f"Click the link below to activate your account (expires in 24 hours):\n\n"
        f"{verify_url}\n\n"
        f"If you did not create this account, ignore this email."
    )
    html = _wrap_html(
        f"<p style='margin-bottom:16px'>"
        f"Welcome to Ticker-Tap! Please verify your email to activate your account. "
        f"This link expires in <strong>24 hours</strong>."
        f"</p>"
        f"{_action_button(verify_url, 'VERIFY EMAIL')}"
        f"<p style='margin-top:16px;font-size:11px;color:#6b7280'>Link: {verify_url}</p>"
    )
    await send_email(to_email, "Verify your Ticker-Tap email", plain, html)


async def send_email_change_verification(to_email: str, verify_url: str) -> None:
    """Send a verification email to the NEW email address for an email change.

    Args:
        to_email: The new email address to verify.
        verify_url: Full URL with email change confirmation token.
    """
    plain = (
        f"You requested to change your Ticker-Tap email to this address.\n\n"
        f"Click the link below to confirm (expires in 1 hour):\n\n"
        f"{verify_url}\n\n"
        f"If you did not request this, ignore this email."
    )
    html = _wrap_html(
        f"<p style='margin-bottom:16px'>"
        f"You requested to change your Ticker-Tap email to this address. "
        f"Click below to confirm — the link expires in <strong>1 hour</strong>."
        f"</p>"
        f"{_action_button(verify_url, 'CONFIRM EMAIL CHANGE')}"
        f"<p style='margin-top:16px;font-size:11px;color:#6b7280'>Link: {verify_url}</p>"
    )
    await send_email(to_email, "Confirm your new Ticker-Tap email", plain, html)


async def send_reactivation_email(to_email: str, reactivate_url: str) -> None:
    """Send an account reactivation email with a one-time link.

    Args:
        to_email: Recipient email address.
        reactivate_url: Full URL with reactivation token.
    """
    plain = (
        f"You requested to reactivate your Ticker-Tap account.\n\n"
        f"Click the link below to reactivate (expires in 1 hour):\n\n"
        f"{reactivate_url}\n\n"
        f"If you did not request this, ignore this email."
    )
    html = _wrap_html(
        f"<p style='margin-bottom:16px'>"
        f"You requested to reactivate your Ticker-Tap account. "
        f"Click below to confirm — the link expires in <strong>1 hour</strong>."
        f"</p>"
        f"{_action_button(reactivate_url, 'REACTIVATE ACCOUNT')}"
        f"<p style='margin-top:16px;font-size:11px;color:#6b7280'>Link: {reactivate_url}</p>"
    )
    await send_email(to_email, "Reactivate your Ticker-Tap account", plain, html)


async def send_deletion_cancellation_email(to_email: str, cancel_url: str) -> None:
    """Send an email to cancel a scheduled account deletion.

    Args:
        to_email: Recipient email address.
        cancel_url: Full URL with deletion cancellation token.
    """
    plain = (
        f"Your Ticker-Tap account is scheduled for deletion.\n\n"
        f"If you want to cancel the deletion and keep your account, "
        f"click the link below (expires in 30 days):\n\n"
        f"{cancel_url}\n\n"
        f"If you intended to delete your account, no action is needed."
    )
    html = _wrap_html(
        f"<p style='margin-bottom:16px'>"
        f"Your Ticker-Tap account is scheduled for deletion in <strong>30 days</strong>. "
        f"Click below to cancel and keep your account."
        f"</p>"
        f"{_action_button(cancel_url, 'CANCEL DELETION')}"
        f"<p style='margin-top:16px;font-size:11px;color:#6b7280'>Link: {cancel_url}</p>"
    )
    await send_email(to_email, "Cancel Ticker-Tap account deletion", plain, html)


async def send_admin_report_notification(report_type: str, subject: str, reporter_email: str) -> None:
    """Notify the admin of a new user-submitted report (fire-and-forget).

    Args:
        report_type: Type of report (bug, suggestion, activation_bug).
        subject: Report subject line.
        reporter_email: Email of the user who submitted the report.
    """
    admin_email = os.getenv("ADMIN_EMAIL", "")
    if not admin_email:
        logger.debug("ADMIN_EMAIL not configured — skipping report notification.")
        return

    plain = (
        f"New {report_type} report submitted on Ticker-Tap.\n\n"
        f"From: {reporter_email}\n"
        f"Subject: {subject}\n\n"
        f"Log in to the admin panel to review."
    )
    # html.escape() prevents XSS via user-supplied fields rendered in admin email.
    _safe_email = html.escape(reporter_email)
    _safe_subject = html.escape(subject)
    html_body = _wrap_html(
        f"<p style='margin-bottom:8px;color:#f0b429;font-weight:700'>NEW {report_type.upper()} REPORT</p>"
        f"<p style='margin-bottom:4px'>From: <strong>{_safe_email}</strong></p>"
        f"<p style='margin-bottom:16px'>Subject: {_safe_subject}</p>"
        f"<p style='font-size:11px;color:#6b7280'>Log in to the admin panel to review and respond.</p>"
    )
    try:
        await send_email(admin_email, f"[TickerTap] New {report_type}: {subject}", plain, html_body)
    except Exception:
        logger.warning("Failed to send admin report notification to %s", admin_email)
