import os

# Keep tests away from the real data/parking.db and .env (no real alerts).
os.environ["DATABASE_PATH"] = ":memory:"
os.environ["LOAD_DOTENV"] = "0"

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.state import cameras, parking_system


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PLATE_REGION", "IN")
    # Routes hold a reference to the shared system, so reset it in place.
    for camera in cameras.values():
        camera.stop()
    parking_system.database.close()
    parking_system.__init__()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def system():
    return parking_system
