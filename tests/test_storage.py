"""SQLite storage on a real file: persistence across restarts, search, reports."""

from datetime import date

import pytest

from backend.app.services.database_service import DatabaseService


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "parking.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    return path


@pytest.fixture
def file_client(client, system, db_file):
    system.database.close()
    system.__init__()
    system.seed_demo_data()
    yield client


def restart(system):
    """Simulate a server restart: reopen the same database file."""
    system.database.close()
    system.__init__()
    system.seed_demo_data()


def test_file_mode_reported(file_client, db_file):
    assert file_client.get("/health").json()["storage"] == "sqlite"
    assert db_file.exists()


def test_data_and_settings_survive_restart(file_client, system):
    file_client.post("/vehicles/register", json={"plate_number": "GJ01AA0001"})
    file_client.post("/vehicles/GJ01AA0001/flag", json={"stolen": True})
    entered = file_client.post(
        "/parking/manual", json={"plate_number": "TN09BC4321", "direction": "entry"}
    ).json()
    file_client.post("/parking/capacity", json={"capacity": 12})
    file_client.post("/settings", json={"event_cooldown_seconds": 40, "alert_kinds": ["stolen"]})

    restart(system)

    assert file_client.get("/vehicles/GJ01AA0001").json()["status"] == "STOLEN"
    parked = {v["plate_number"]: v for v in system.database.get_currently_parked()}
    assert parked["TN09BC4321"]["slot_id"] == entered["slot_id"]
    assert file_client.get("/events?plate=TN09").json()["total"] == 1

    settings = file_client.get("/settings").json()
    assert settings["capacity"] == 12
    assert settings["event_cooldown_seconds"] == 40
    assert settings["alerts"]["enabled"] == ["stolen"]

    # Demo data is only seeded on the first run: nothing was duplicated.
    assert sum(v["plate_number"] == "MH12AB1234" for v in system.database.get_all_vehicles()) == 1


def test_registry_and_entry_time_kept(file_client, system):
    file_client.post("/vehicles/register", json={"plate_number": "GJ01AA0001"})
    assert file_client.delete("/vehicles/GJ01AA0001").status_code == 200
    assert file_client.delete("/vehicles/GJ01AA0001").status_code == 404

    first = file_client.post(
        "/parking/manual", json={"plate_number": "TN09BC4321", "direction": "entry"}
    ).json()
    entered_at = {v["plate_number"]: v for v in system.database.get_currently_parked()}[
        "TN09BC4321"]["entered_at"]
    # A second insert must not overwrite the original entry time or slot.
    assert system.database.record_entry("TN09BC4321", "A04") is False
    again = {v["plate_number"]: v for v in system.database.get_currently_parked()}["TN09BC4321"]
    assert (again["entered_at"], again["slot_id"]) == (entered_at, first["slot_id"])

    left = file_client.post(
        "/parking/manual", json={"plate_number": "TN09BC4321", "direction": "exit"}
    ).json()
    assert left["status"] == "exited" and left["slot_id"] == first["slot_id"]
    assert system.database.record_exit("TN09BC4321") is None


def test_event_search_csv_and_report(file_client, system):
    system.event_cooldown_seconds = 0
    for plate, direction in [("TN09BC4321", "entry"), ("TN09BC4321", "exit"), ("DL8CAF5031", "entry")]:
        file_client.post("/parking/manual", json={"plate_number": plate, "direction": direction})

    assert file_client.get("/events?plate=TN09").json()["total"] == 2
    assert file_client.get("/events?status=problems").json()["total"] == 1
    assert "DL8CAF5031" in file_client.get("/events.csv").text

    today = file_client.get("/reports/daily?days=1").json()["days"][0]
    assert today["date"] == date.today().isoformat()
    assert (today["entries"], today["exits"], today["turned_away"]) == (1, 1, 1)
    assert today["average_stay_minutes"] == 0


def test_demo_data_can_be_turned_off(tmp_path, monkeypatch, system):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "empty.db"))
    monkeypatch.setenv("DEMO_DATA", "0")
    system.__init__()
    system.seed_demo_data()
    assert system.database.get_all_vehicles() == []
    assert system.database.get_occupancy_history() == []
    system.database.close()


def test_plate_search_treats_input_literally():
    db = DatabaseService(":memory:")
    db.save_detection({"event_type": "occupancy_event", "plate_number": "AB12", "status": "entered"})
    assert db.count_events(plate="%") == 0
    assert db.count_events(plate="B1") == 1
