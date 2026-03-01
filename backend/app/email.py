import os
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", smtp_user)

    # Build TLS context — full certificate verification is the default.
    # SMTP_SKIP_TLS_VERIFY is provided only for local dev/Proton Bridge.
    # In production this flag is explicitly blocked (P6.1 security guard).
    tls_context = ssl.create_default_context()
    _env = os.getenv("ENVIRONMENT", "development").lower()
    _skip_verify = os.getenv("SMTP_SKIP_TLS_VERIFY", "").lower() in ("1", "true", "yes")

    if _skip_verify and _env == "production":
        import sys
        print(
            "FATAL: SMTP_SKIP_TLS_VERIFY must not be enabled in production — "
            "this disables certificate verification and exposes password-reset tokens. "
            "Remove SMTP_SKIP_TLS_VERIFY from your production environment.",
            file=sys.stderr,
        )
        raise RuntimeError("SMTP_SKIP_TLS_VERIFY is disallowed in production")

    if _skip_verify:
        tls_context.check_hostname = False
        tls_context.verify_mode = ssl.CERT_NONE

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your Ticker-Tap password"
    msg["From"] = from_addr
    msg["To"] = to_email

    plain = (
        f"You requested a password reset for your Ticker-Tap account.\n\n"
        f"Click the link below to set a new password (expires in 1 hour):\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, ignore this email."
    )
    html = f"""
    <div style="font-family:monospace;background:#0d0e11;color:#c8ccd4;padding:32px;max-width:480px">
      <div style="font-size:18px;font-weight:700;color:#f0b429;letter-spacing:2px;margin-bottom:8px">
        TICKER-TAP
      </div>
      <div style="font-size:12px;color:#6b7280;margin-bottom:24px">
        Professional Investment Terminal
      </div>
      <p style="margin-bottom:16px">
        You requested a password reset. Click the button below — the link expires in <strong>1 hour</strong>.
      </p>
      <a href="{reset_url}"
         style="display:inline-block;background:#f0b429;color:#0d0e11;font-weight:700;
                letter-spacing:1px;padding:12px 24px;text-decoration:none;border-radius:2px">
        RESET PASSWORD
      </a>
      <p style="margin-top:24px;font-size:11px;color:#6b7280">
        If you didn't request this, you can safely ignore this email.<br>
        Link: {reset_url}
      </p>
    </div>
    """

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=smtp_user,
        password=smtp_pass,
        start_tls=True,
        tls_context=tls_context,
    )
