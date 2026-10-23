import pytest

from backend.app.routes import plate_test


class FakeEngine:
    def readtext(self, image):
        return "ka 01 ab 1234", 0.91


def jpeg():
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    return cv2.imencode(".jpg", np.full((60, 200, 3), 255, dtype=np.uint8))[1].tobytes()


def test_plate_test_reads_without_touching_the_lot(client, monkeypatch):
    monkeypatch.setattr(plate_test, "get_engine", lambda: FakeEngine())
    before = client.get("/dashboard/summary").json()

    result = client.post("/plate-test/read", content=jpeg(), headers={"content-type": "image/jpeg"}).json()
    assert result == {"plate_number": "KA01AB1234", "raw": "KA01AB1234", "confidence": 0.91, "looks_like_plate": True}

    after = client.get("/dashboard/summary").json()
    assert after["version"] == before["version"]
    assert after["parking"]["occupied"] == before["parking"]["occupied"]


def test_plate_test_rejects_bad_input(client, monkeypatch):
    pytest.importorskip("cv2")
    monkeypatch.setattr(plate_test, "get_engine", lambda: FakeEngine())
    assert client.post("/plate-test/read", content=b"").status_code == 400
    assert client.post("/plate-test/read", content=b"not an image").status_code == 400


def test_standalone_pages_are_served(client):
    for path in ("/arrival.html", "/arrival.js", "/plate-test.html", "/plate-test.js", "/screens.css"):
        assert client.get(path).status_code == 200, path


def test_browsers_recheck_the_dashboard_files(client):
    # Otherwise an update leaves browsers running an old app.js on a new page.
    for path in ("/", "/app.js", "/app.css"):
        assert client.get(path).headers["cache-control"] == "no-cache", path


def test_paper_plate_mode_reads_without_a_car(client, system, monkeypatch):
    np = pytest.importorskip("numpy")
    frame = np.full((120, 320, 3), 255, dtype=np.uint8)
    paper_read = [{"plate_text": "MH14AB1234", "raw_text": "MH14AB1234", "confidence": 0.8, "bbox": [0, 0, 320, 120]}]

    # Camera AI mode with nothing found by the car and plate models.
    monkeypatch.setattr(system.alpr, "simulated", False)
    monkeypatch.setattr(system.vehicle_detector, "detect_vehicles", lambda frame: [])
    monkeypatch.setattr(system.alpr, "recognize_plates", lambda frame, known_plates=None: [])
    monkeypatch.setattr(system.alpr, "read_paper_plate", lambda frame: paper_read)

    for _ in range(system.min_camera_reads):
        assert system.process_gate_frame(frame, "entry")["events"] == []

    assert client.post("/settings", json={"paper_plates": True}).json()["paper_plates"] is True
    assert client.get("/settings").json()["paper_plates"] is True
    events = []
    for _ in range(system.min_camera_reads):
        events += system.process_gate_frame(frame, "entry")["events"]
    assert [event["plate_number"] for event in events] == ["MH14AB1234"]


def test_best_plate_skips_stray_text(monkeypatch):
    from backend.app.services.alpr_service import best_plate

    monkeypatch.setenv("PLATE_REGION", "IN")
    assert best_plate([("HELLO", 0.9), ("MH1Z", 0.7), ("AB1234", 0.8), ("X", 0.95)]) == ("MH1ZAB1234", "MH12AB1234", 0.7)
    assert best_plate([("HELLO", 0.9)]) is None
    assert best_plate([]) is None
