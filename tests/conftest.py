import os

# Tests never touch the real data/parking.db; set before the app is imported.
os.environ["DATABASE_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.state import cameras, parking_system


@pytest.fixture
def client(monkeypatch):
    # The plate-format setting writes PLATE_REGION; undo it after each test.
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
