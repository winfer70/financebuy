"""
============================================================================
TEST SUITE: User preferences — tutorial_done flag
============================================================================

MODULE UNDER TEST: app.routes.auth_routes (GET /auth/me, PATCH /auth/preferences)
TEST TYPE: Integration (HTTP via TestClient, DB mocked)
FRAMEWORK: pytest + FastAPI TestClient

DESCRIPTION:
    Covers the onboarding-tutorial persistence added to the existing
    preferences mechanism: `tutorial_done` defaults to False for
    pre-existing accounts, and PATCH /auth/preferences can set it so the
    tutorial never shows again for that account. Also covers the
    pre-existing `sidebar_collapsed` field, which the PATCH handler
    documented in its schema but never actually merged — first coverage
    for either field.
============================================================================
"""
import os
from unittest.mock import MagicMock

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest


def _fill_profile_fields(user):
    """auth_client's shared mock_user fixture only sets user_id/email/is_active/
    is_admin — GET /auth/me also serializes first_name/last_name/phone/
    kyc_status, which Pydantic rejects as MagicMock auto-attributes rather
    than str. Not an app bug: no other existing test exercises this endpoint."""
    user.first_name = "Test"
    user.last_name = "User"
    user.phone = None
    user.kyc_status = "pending"


class TestGetProfileTutorialDefault:
    def test_tutorial_done_defaults_false_for_existing_accounts(self, auth_client):
        client, _db, user = auth_client
        _fill_profile_fields(user)
        user.preferences = {}  # pre-migration account with no preferences set yet

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        prefs = resp.json()["preferences"]
        assert prefs["tutorial_done"] is False
        assert prefs["sidebar_collapsed"] is False

    def test_tutorial_done_reflects_stored_value(self, auth_client):
        client, _db, user = auth_client
        _fill_profile_fields(user)
        user.preferences = {"tutorial_done": True}

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["preferences"]["tutorial_done"] is True


class TestUpdatePreferencesTutorial:
    def test_marks_tutorial_done(self, auth_client):
        client, _db, user = auth_client
        user.preferences = {}

        resp = client.patch("/api/v1/auth/preferences", json={"tutorial_done": True})
        assert resp.status_code == 200
        assert resp.json()["tutorial_done"] is True
        assert user.preferences["tutorial_done"] is True

    def test_marking_done_does_not_clobber_other_preferences(self, auth_client):
        client, _db, user = auth_client
        user.preferences = {"currency": "EUR", "sidebar_collapsed": True}

        resp = client.patch("/api/v1/auth/preferences", json={"tutorial_done": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tutorial_done"] is True
        assert body["currency"] == "EUR"
        assert body["sidebar_collapsed"] is True

    def test_sidebar_collapsed_is_actually_merged(self, auth_client):
        """Regression: sidebar_collapsed was documented in the schema's
        docstring but never read from the payload in the handler body."""
        client, _db, user = auth_client
        user.preferences = {}

        resp = client.patch("/api/v1/auth/preferences", json={"sidebar_collapsed": True})
        assert resp.status_code == 200
        assert resp.json()["sidebar_collapsed"] is True
        assert user.preferences["sidebar_collapsed"] is True
