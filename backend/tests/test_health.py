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


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docker_compose():
    r = client.get("/docker-compose")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
