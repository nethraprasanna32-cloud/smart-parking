import time
from datetime import datetime, timedelta

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "gate.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (160, 120))
    for index in range(30):
        frame = np.full((120, 160, 3), index * 8, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return str(path)


def wait_until_stopped(camera, timeout=10):
    deadline = time.monotonic() + timeout
    while camera.running and time.monotonic() < deadline:
        time.sleep(0.05)


def test_simulated_detector_only_previews_real_video(client, video):
    from backend.app.state import cameras

    assert client.post("/camera/entry/start", json={"source": video, "fps": 10}).status_code == 200
    wait_until_stopped(cameras["entry"])

    status = client.get("/camera/entry/status").json()
    assert status["state"] == "finished"
    assert status["frames_read"] == 30
    assert status["frames_processed"] == 0          # never invents plates on real footage
    assert status["has_preview"]
    assert client.get("/camera/entry/snapshot.jpg").headers["content-type"] == "image/jpeg"
    assert client.get("/events?gate=entry").json()["total"] == 0


def test_real_pipeline_needs_two_reads_before_an_event(client, system, video, monkeypatch):
    from backend.app.state import cameras

    # Stand in for YOLO + OCR: one car, one plate, every frame.
    monkeypatch.setattr(system.vehicle_detector, "detect_vehicles",
                        lambda frame: [{"type": "car", "confidence": 0.9, "bbox": [0, 0, 100, 100]}])
    monkeypatch.setattr(system.alpr, "simulated", False)
    monkeypatch.setattr(system.alpr, "recognize_plates",
                        lambda frame, known_plates=None: [{"plate_text": "TN09BC4321", "confidence": 0.9, "bbox": [10, 10, 60, 30]}])

    client.post("/camera/entry/start", json={"source": video, "fps": 30})
    wait_until_stopped(cameras["entry"])

    status = client.get("/camera/entry/status").json()
    assert status["frames_processed"] >= 2
    events = client.get("/events?gate=entry").json()["events"]
    # Many frames, one confirmed entry thanks to consensus + cooldown.
    assert [(e["plate_number"], e["status"]) for e in events] == [("TN09BC4321", "entered")]


def test_slow_analysis_skips_frames_instead_of_falling_behind(client, system, video, monkeypatch):
    from backend.app.state import cameras

    def slow_frame(frame, gate):
        time.sleep(0.25)  # slower than the 20 fps video
        return {"timestamp": "", "vehicles": [], "plates": [], "events": []}

    monkeypatch.setattr(system.alpr, "simulated", False)
    monkeypatch.setattr(system, "process_gate_frame", slow_frame)

    started = time.monotonic()
    client.post("/camera/entry/start", json={"source": video, "fps": 30})
    wait_until_stopped(cameras["entry"])
    elapsed = time.monotonic() - started

    status = client.get("/camera/entry/status").json()
    # 30 frames at 20 fps is 1.5 s of video; it must not take 30 x 0.25 s.
    assert elapsed < 4
    assert status["frames_skipped"] > 0
    assert status["frames_processed"] < 30


def test_missing_video_file_is_404(client):
    assert client.post("/camera/exit/start", json={"source": "nope/missing.mp4"}).status_code == 404


def test_lstm_trains_saves_and_predicts(tmp_path):
    pytest.importorskip("torch")
    from ai_pipeline.forecast import LSTMForecaster

    start = datetime(2026, 1, 5)
    history = [
        {
            "timestamp": (start + timedelta(minutes=15 * step)).isoformat(),
            "occupied": 8 if 10 <= (start + timedelta(minutes=15 * step)).hour < 16 else 1,
        }
        for step in range(3 * 96)
    ]

    weights = tmp_path / "lstm.pt"
    model = LSTMForecaster(weights_path=str(weights), load=False)
    result = model.train(history, epochs=40)
    model.save()
    assert result["samples"] > 0 and weights.exists()

    loaded = LSTMForecaster(weights_path=str(weights))
    forecast = loaded.predict(history, now=start + timedelta(days=3))
    assert 0 <= forecast["low"] <= forecast["predicted"] <= forecast["high"]


def test_lstm_needs_enough_history(tmp_path):
    pytest.importorskip("torch")
    from ai_pipeline.forecast import LSTMForecaster

    model = LSTMForecaster(weights_path=str(tmp_path / "x.pt"), load=False)
    with pytest.raises(ValueError):
        model.train([{"timestamp": "2026-01-05T08:00:00", "occupied": 1}])


def test_lstm_trained_on_big_synthetic_lot_scales_to_small_lot(tmp_path):
    pytest.importorskip("torch")
    from ai_pipeline.forecast import LSTMForecaster, synthetic_history

    end = datetime(2026, 3, 2, 10, 0)  # Monday morning: the lot is busy
    model = LSTMForecaster(weights_path=str(tmp_path / "x.pt"), load=False)
    model.train(synthetic_history(days=14, capacity=50, end=end, seed=3), epochs=60, capacity=50)

    small = synthetic_history(days=1, capacity=4, end=end, seed=4)
    forecast = model.predict(small, now=end, capacity=4)
    assert 0 <= forecast["predicted"] <= 5
    assert forecast["high"] - forecast["low"] < 4
