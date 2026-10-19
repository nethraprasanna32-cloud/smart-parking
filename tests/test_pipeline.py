from datetime import datetime, timedelta

from ai_pipeline.detect_and_ocr import (
    VehicleDetectionManager,
    is_valid_plate,
    normalize_plate,
    snap_plate,
)
from ai_pipeline.forecast import SeasonalBaseline, parse_history, resample, synthetic_history
from backend.app.services.parking import OccupancyManager


def test_plate_helpers():
    assert normalize_plate(" mh-12 ab 1234 ") == "MH12AB1234"
    assert is_valid_plate("MH12AB1234")
    assert is_valid_plate("DL8CAF5031")
    assert not is_valid_plate("HELLO")
    assert snap_plate("MH12A81234", {"MH12AB1234", "KA01AB0001"}) == "MH12AB1234"
    assert snap_plate("TOTALLYDIFF", {"MH12AB1234"}) is None


def test_failed_model_switch_keeps_previous_detector(monkeypatch):
    manager = VehicleDetectionManager("simulated")

    def broken():
        raise FileNotFoundError("weights missing")

    monkeypatch.setitem(
        __import__("ai_pipeline.detect_and_ocr", fromlist=["DETECTORS"]).DETECTORS,
        "yolo11",
        broken,
    )
    try:
        manager.change_model("yolo11")
    except FileNotFoundError:
        pass
    assert manager.model_type == "simulated"


def test_legacy_records_without_slot_do_not_reshuffle():
    manager = OccupancyManager(capacity=3)
    parked = [
        {"plate_number": "A", "slot_id": "A02"},
        {"plate_number": "B"},
    ]
    assert manager.get_slot_assignments(parked) == {"A": "A02", "B": "A01"}
    assert manager.get_available_slot(parked) == "A03"


def test_resample_forward_fills():
    start = datetime(2026, 1, 5, 8, 0)
    points = parse_history([
        {"timestamp": start.isoformat(), "occupied": 1},
        {"timestamp": (start + timedelta(minutes=40)).isoformat(), "occupied": 3},
    ])
    grid = resample(points, 15)
    assert [value for _, value in grid] == [1, 1, 1, 3]


def test_baseline_learns_daily_pattern():
    # Busy at noon, empty at night, for a week.
    start = datetime(2026, 1, 5)
    history = []
    for step in range(7 * 96):
        moment = start + timedelta(minutes=15 * step)
        history.append({
            "timestamp": moment.isoformat(),
            "occupied": 10 if 10 <= moment.hour < 16 else 1,
        })

    model = SeasonalBaseline()
    model.train(history)

    morning = datetime(2026, 1, 12, 9, 0)
    forecast = model.predict(
        [{"timestamp": (morning - timedelta(minutes=5)).isoformat(), "occupied": 1}],
        horizon_minutes=120,
        now=morning,
    )
    assert forecast["predicted"] > 5
    assert forecast["low"] <= forecast["predicted"] <= forecast["high"]


def test_baseline_with_no_history():
    assert SeasonalBaseline().predict([])["predicted"] == 0.0


def test_one_character_misread_is_not_a_second_car(system):
    system.__init__()
    system.database.save_vehicle({"plate_number": "TN09BC4321", "authorized": True, "stolen": False})

    first = system.handle_plate("TN09BC4321", "entry", source="camera")
    assert first["status"] == "entered"
    assert system.handle_plate("TN09BC4351", "entry", source="camera") is None   # misread
    # A different car typed by an operator is never merged.
    assert system.handle_plate("TN09BC4351", "entry", source="manual") is not None


def test_fair_lock_takes_turns():
    import threading
    import time

    from backend.app.services.parking_system import FairLock

    lock = FairLock()
    order = []

    def worker(name):
        for _ in range(4):
            with lock:
                order.append(name)
                time.sleep(0.01)

    threads = [threading.Thread(target=worker, args=(name,)) for name in "ab"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # A plain Lock usually gives "aaaabbbb"; a fair one interleaves.
    assert order.count("a") == order.count("b") == 4
    switches = sum(1 for x, y in zip(order, order[1:]) if x != y)
    assert switches >= 5


def test_region_setting(monkeypatch):
    assert not is_valid_plate("38DMZP")
    monkeypatch.setenv("PLATE_REGION", "ANY")
    assert is_valid_plate("38DMZP")


def test_camera_reads_need_consensus(system):
    system.__init__()
    assert system._confirm_read("entry", "MH12AB1234") is None
    # A near-identical second read confirms; ties go to the earliest read.
    assert system._confirm_read("entry", "MH12AB1284") == "MH12AB1234"
    assert system._confirm_read("exit", "KA01AB0001") is None


def test_synthetic_history_looks_like_a_real_lot():
    end = datetime(2026, 3, 8, 23, 45)  # a Sunday night
    history = synthetic_history(days=28, capacity=40, end=end, seed=1)
    assert history == synthetic_history(days=28, capacity=40, end=end, seed=1)
    assert all(0 <= row["occupied"] <= 40 for row in history)

    def average(weekdays, hours):
        values = [
            row["occupied"] for row in history
            if (t := datetime.fromisoformat(row["timestamp"])).weekday() in weekdays
            and t.hour in hours
        ]
        return sum(values) / len(values)

    weekday_midday = average(range(5), (10, 11, 15, 16))
    assert weekday_midday > 25                         # busy during office hours
    assert average(range(5), (2, 3)) < 6               # nearly empty at night
    assert average((6,), (10, 11, 15, 16)) < weekday_midday / 2   # quiet Sundays
