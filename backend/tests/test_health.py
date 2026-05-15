import os
import sys
from fastapi.testclient import TestClient

# Ensure repo root is on PYTHONPATH so `app` package is importable
# when tests run inside container
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_returns_200():
    """GET /health should return 200 when DB and Redis are reachable."""
    r = client.get("/health")
    assert r.status_code == 200


def test_health_response_shape():
    """GET /health response body should contain status, db, redis, and timestamp."""
    r = client.get("/health")
    body = r.json()
    assert "status" in body
    assert "db" in body
    assert "redis" in body
    assert "timestamp" in body
    assert body["db"]["status"] in ("ok", "error")
    assert body["redis"]["status"] in ("ok", "error")
