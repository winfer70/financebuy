"""
auth.py — Core authentication utilities for TickerTap.

Provides password hashing (argon2), JWT token creation/decoding, and
startup validation that the JWT secret has been changed from its default.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

pwd_hasher = PasswordHasher()

# ── JWT configuration ────────────────────────────────────────────────────────
_DEFAULT_SECRET = "please-change-me"
JWT_SECRET = os.getenv("JWT_SECRET", _DEFAULT_SECRET)
JWT_ALG = "HS256"
# Default token lifetime: 60 minutes (was 1440 / 24h — too long for security)
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


def validate_jwt_config() -> None:
    """Raise on startup if the JWT secret is still the insecure default.

    Called from main.py on_event("startup") so the app refuses to boot with
    a known-weak secret.
    """
    if JWT_SECRET == _DEFAULT_SECRET:
        raise RuntimeError(
            "FATAL: JWT_SECRET is still set to the default value. "
            "Set a strong, unique JWT_SECRET environment variable before starting."
        )
    if len(JWT_SECRET) < 32:
        logger.warning("JWT_SECRET is shorter than 32 characters — consider using a longer secret.")


def hash_password(password: str) -> str:
    """Hash a plaintext password using argon2.

    Args:
        password: The plaintext password to hash.

    Returns:
        The argon2 hash string.
    """
    return pwd_hasher.hash(password)


def verify_password(hash: str, password: str) -> bool:
    """Verify a plaintext password against an argon2 hash.

    Args:
        hash: The stored argon2 hash.
        password: The plaintext password to verify.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    try:
        return pwd_hasher.verify(hash, password)
    except Exception:
        return False


def create_access_token(
    subject: str, expires_minutes: Optional[int] = None
) -> str:
    """Create a signed JWT access token.

    Args:
        subject: The token subject (typically user_id as a string).
        expires_minutes: Override for token lifetime in minutes.

    Returns:
        The encoded JWT string.
    """
    lifetime = expires_minutes or JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    to_encode = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=lifetime),
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> Optional[str]:
    """Decode a JWT and return the subject claim.

    Args:
        token: The encoded JWT string.

    Returns:
        The subject string (user_id) if valid, None otherwise.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return payload.get("sub")
    except JWTError:
        return None
