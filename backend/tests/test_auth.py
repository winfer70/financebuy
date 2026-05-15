"""
============================================================================
TEST SUITE: Authentication — Core utilities and HTTP endpoints
============================================================================

MODULE UNDER TEST: app.auth, app.routes.auth_routes
TEST TYPE: Unit + Integration
FRAMEWORK: pytest + httpx (via FastAPI TestClient)

DESCRIPTION:
    Covers password hashing/verification, JWT creation/decoding, startup
    validation, and the /auth/register + /auth/login HTTP endpoints.
    Database interactions are mocked with AsyncMock so tests run without
    a live PostgreSQL instance.

COVERAGE SCOPE:
    ✓ hash_password / verify_password
    ✓ create_access_token / decode_access_token
    ✓ validate_jwt_config
    ✓ POST /auth/register — success, duplicate email
    ✓ POST /auth/login    — success, wrong password, inactive user

EXECUTION REQUIREMENTS:
    - No external services required (DB mocked)
    - Run: pytest backend/tests/test_auth.py -v
============================================================================
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── PYTHONPATH setup so `app` package resolves ─────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Patch JWT secret BEFORE importing app modules so validate_jwt_config
#    doesn't raise during test collection.
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-validation")

from app.auth import (  # noqa: E402
    create_access_token,
    decode_access_token,
    hash_password,
    validate_jwt_config,
    verify_password,
)


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: Password hashing utilities
# ═══════════════════════════════════════════════════════════════════════════

class TestPasswordHashing:
    """Unit tests for hash_password and verify_password."""

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_hash_password_returns_non_empty_string(self):
        """hash_password should return a non-empty string for any input."""
        # ARRANGE
        password = "SecurePassword123!"

        # ACT
        result = hash_password(password)

        # ASSERT
        assert isinstance(result, str), "Expected a string hash"
        assert len(result) > 0, "Hash must not be empty"

    def test_hash_password_produces_different_hashes_for_same_input(self):
        """argon2 uses a random salt — two hashes of the same password differ."""
        # ARRANGE
        password = "SamePassword!"

        # ACT
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # ASSERT
        assert hash1 != hash2, "Argon2 hashes should be unique (random salt)"

    def test_verify_password_returns_true_for_correct_password(self):
        """verify_password should return True when the password matches the hash."""
        # ARRANGE
        password = "CorrectPassword!"
        h = hash_password(password)

        # ACT
        result = verify_password(h, password)

        # ASSERT
        assert result is True, f"Expected True for correct password, got {result}"

    def test_verify_password_returns_false_for_wrong_password(self):
        """verify_password should return False for a non-matching password."""
        # ARRANGE
        password = "CorrectPassword!"
        wrong    = "WrongPassword!"
        h = hash_password(password)

        # ACT
        result = verify_password(h, wrong)

        # ASSERT
        assert result is False, f"Expected False for wrong password, got {result}"

    # ── Edge cases ─────────────────────────────────────────────────────────

    def test_verify_password_returns_false_for_empty_hash(self):
        """verify_password should not raise and return False for a corrupt hash."""
        result = verify_password("not-a-valid-hash", "password")
        assert result is False

    def test_hash_password_handles_unicode(self):
        """Passwords with unicode characters should hash and verify correctly."""
        password = "pässwörð🔑"
        h = hash_password(password)
        assert verify_password(h, password) is True

    def test_hash_password_handles_empty_string(self):
        """An empty password is valid input — hash and verify should work."""
        h = hash_password("")
        assert verify_password(h, "") is True


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: JWT utilities
# ═══════════════════════════════════════════════════════════════════════════

class TestJwtUtilities:
    """Unit tests for create_access_token and decode_access_token."""

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_create_access_token_returns_string(self):
        """create_access_token should return a non-empty JWT string."""
        token = create_access_token("user-id-123")
        assert isinstance(token, str) and len(token) > 0

    def test_decode_access_token_recovers_subject(self):
        """decode_access_token should return the subject used to create the token."""
        # ARRANGE
        subject = "user-uuid-abc123"

        # ACT
        token   = create_access_token(subject)
        decoded = decode_access_token(token)

        # ASSERT
        assert decoded == subject, f"Expected '{subject}', got '{decoded}'"

    def test_token_has_correct_default_expiry(self):
        """Decoded token should expire approximately 60 minutes from creation."""
        from jose import jwt as jose_jwt
        from app.auth import JWT_ALG, JWT_SECRET

        # ACT
        token   = create_access_token("subject")
        payload = jose_jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

        # ASSERT — allow ±5s leeway for test execution time
        expected_exp = datetime.now(timezone.utc) + timedelta(minutes=60)
        actual_exp   = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta        = abs((actual_exp - expected_exp).total_seconds())
        assert delta < 5, f"Expiry delta too large: {delta}s"

    def test_custom_expiry_is_respected(self):
        """create_access_token should honour the expires_minutes override."""
        from jose import jwt as jose_jwt
        from app.auth import JWT_ALG, JWT_SECRET

        token   = create_access_token("subject", expires_minutes=15)
        payload = jose_jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

        expected_exp = datetime.now(timezone.utc) + timedelta(minutes=15)
        actual_exp   = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta        = abs((actual_exp - expected_exp).total_seconds())
        assert delta < 5

    # ── Edge / error cases ─────────────────────────────────────────────────

    def test_decode_access_token_returns_none_for_invalid_token(self):
        """decode_access_token should return None for a garbage string."""
        result = decode_access_token("this.is.not.a.valid.jwt")
        assert result is None

    def test_decode_access_token_returns_none_for_empty_string(self):
        result = decode_access_token("")
        assert result is None

    def test_decode_access_token_returns_none_for_expired_token(self):
        """A token with a past expiry should be rejected."""
        token = create_access_token("user", expires_minutes=-1)
        result = decode_access_token(token)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3: JWT config validation
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateJwtConfig:
    """Unit tests for the startup safety check in validate_jwt_config."""

    def test_raises_if_secret_is_default(self):
        """validate_jwt_config should raise RuntimeError for the default secret."""
        with patch("app.auth.JWT_SECRET", "please-change-me"):
            with pytest.raises(RuntimeError, match="FATAL"):
                validate_jwt_config()

    def test_passes_for_strong_secret(self):
        """validate_jwt_config should not raise for a strong, unique secret."""
        with patch("app.auth.JWT_SECRET", "a-very-long-and-unique-secret-value-xyz123"):
            # Should not raise
            validate_jwt_config()

    def test_warns_for_short_secret(self, caplog):
        """A secret shorter than 32 chars should log a warning but not raise."""
        import logging
        with patch("app.auth.JWT_SECRET", "short-secret"):
            with caplog.at_level(logging.WARNING, logger="app.auth"):
                validate_jwt_config()
        assert "shorter than 32 characters" in caplog.text


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 4: HTTP endpoint — /auth/register
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def client():
    """TestClient with DB dependency overridden by an async mock session."""
    from app.main import app
    from app.db import get_db

    async def override_get_db():
        import uuid as _uuid
        result = MagicMock()
        # scalar_one_or_none() returns None by default (no existing user)
        result.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()

        async def _refresh(obj):
            # Simulate DB populating server defaults after commit
            if getattr(obj, "user_id", None) is None:
                obj.user_id = _uuid.uuid4()
            if getattr(obj, "kyc_status", None) is None:
                obj.kyc_status = "not_verified"
            if getattr(obj, "is_active", None) is None:
                obj.is_active = True

        session.refresh = AsyncMock(side_effect=_refresh)
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestRegisterEndpoint:
    """Integration tests for POST /auth/register."""

    def test_register_returns_201_for_valid_payload(self, client):
        """Valid registration payload should return HTTP 201."""
        # ARRANGE
        payload = {
            "email":      "newuser@example.com",
            "password":   "StrongPass123!",
            "first_name": "Jane",
            "last_name":  "Doe",
        }

        # ACT
        response = client.post("/api/v1/auth/register", json=payload)

        # ASSERT
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

    def test_register_returns_201_for_duplicate_email(self, client):
        """Duplicate email returns 201 to prevent email enumeration (anti-fingerprinting)."""
        # ARRANGE — mock returns an existing user
        from app.models import User
        mock_user = MagicMock(spec=User)

        from app.db import get_db
        async def override_with_existing():
            result = MagicMock()
            result.scalar_one_or_none.return_value = mock_user
            session = AsyncMock()
            session.execute = AsyncMock(return_value=result)
            yield session

        from app.main import app
        app.dependency_overrides[get_db] = override_with_existing

        payload = {
            "email":    "existing@example.com",
            "password": "AnyPassword123!",
        }

        # ACT
        response = client.post("/api/v1/auth/register", json=payload)

        # ASSERT — returns 201 (same as success) to prevent email enumeration
        assert response.status_code == 201
        assert "email" in response.json().get("message", "")

        # restore
        from app.db import get_db as _get_db

        async def _default():
            import uuid as _uuid
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            session = AsyncMock()
            session.execute = AsyncMock(return_value=result)
            session.commit = AsyncMock()
            session.refresh = AsyncMock()
            yield session

        app.dependency_overrides[get_db] = _default

    def test_register_requires_email_field(self, client):
        """Missing email should trigger a 422 Unprocessable Entity."""
        response = client.post("/api/v1/auth/register", json={"password": "pass"})
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 5: HTTP endpoint — /auth/login
# ═══════════════════════════════════════════════════════════════════════════

class TestLoginEndpoint:
    """Integration tests for POST /auth/login."""

    @pytest.fixture(autouse=True)
    def _mock_db_with_active_user(self, monkeypatch):
        """Override get_db to return an active user whose password matches."""
        from app.models import User
        from app.auth import hash_password as _hash
        from app.db import get_db
        from app.main import app
        import uuid

        mock_user = MagicMock(spec=User)
        mock_user.user_id    = uuid.uuid4()
        mock_user.email      = "login@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name  = "User"
        mock_user.is_active  = True
        mock_user.password_hash = _hash("GoodPassword123!")
        # Explicitly clear fields checked by login endpoint
        mock_user.locked_until           = None
        mock_user.deactivated_at         = None
        mock_user.deletion_scheduled_at  = None
        mock_user.failed_login_attempts  = 0

        async def override():
            result = MagicMock()
            result.scalar_one_or_none.return_value = mock_user
            session = AsyncMock()
            session.execute = AsyncMock(return_value=result)
            session.commit = AsyncMock()
            yield session

        app.dependency_overrides[get_db] = override
        self._app   = app
        self._user  = mock_user

    def teardown_method(self):
        self._app.dependency_overrides.clear()

    def test_login_returns_200_and_access_token_for_valid_credentials(self):
        """Correct credentials should return 200 with an access_token."""
        tc       = TestClient(self._app)
        response = tc.post("/api/v1/auth/login", json={
            "email":    "login@example.com",
            "password": "GoodPassword123!",
        })
        assert response.status_code == 200, response.text
        body = response.json()
        assert "access_token" in body, "Response missing access_token"
        assert len(body["access_token"]) > 0

    def test_login_returns_401_for_wrong_password(self):
        """Wrong password should return 401 Unauthorized."""
        tc       = TestClient(self._app)
        response = tc.post("/api/v1/auth/login", json={
            "email":    "login@example.com",
            "password": "WrongPassword!",
        })
        assert response.status_code == 401

    def test_login_returns_401_for_inactive_user(self):
        """Inactive users should not be able to log in."""
        from app.db import get_db

        self._user.is_active = False

        async def override_inactive():
            result = MagicMock()
            result.scalar_one_or_none.return_value = self._user
            session = AsyncMock()
            session.execute = AsyncMock(return_value=result)
            session.commit = AsyncMock()
            yield session

        self._app.dependency_overrides[get_db] = override_inactive

        tc       = TestClient(self._app)
        response = tc.post("/api/v1/auth/login", json={
            "email":    "login@example.com",
            "password": "GoodPassword123!",
        })
        assert response.status_code == 401

    def test_login_returns_422_for_missing_fields(self):
        """Missing email/password fields should return 422."""
        tc       = TestClient(self._app)
        response = tc.post("/api/v1/auth/login", json={"email": "only@email.com"})
        assert response.status_code == 422
