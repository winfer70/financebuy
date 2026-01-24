import os
from argon2 import PasswordHasher
from datetime import datetime, timedelta
from jose import jwt

PWD_HASher = PasswordHasher()
JWT_SECRET = os.getenv("JWT_SECRET", "please-change-me")
JWT_ALG = "HS256"


def hash_password(password: str) -> str:
    return PWD_HASher.hash(password)


def verify_password(hash: str, password: str) -> bool:
    try:
        return PWD_HASher.verify(hash, password)
    except Exception:
        return False


def create_access_token(subject: str, expires_minutes: int = 15) -> str:
    to_encode = {
        "sub": subject,
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


# NOTE: Implement rotating refresh tokens and revocation lists in production.
