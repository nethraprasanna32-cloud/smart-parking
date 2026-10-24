def enter(client, plate):
    return client.post("/parking/manual", json={"plate_number": plate, "direction": "entry"})


def leave(client, plate):
    return client.post("/parking/manual", json={"plate_number": plate, "direction": "exit"})


def test_summary_shape(client):
    summary = client.get("/dashboard/summary").json()

    assert summary["parking"]["total_slots"] == 4
    assert summary["parking"]["occupied"] == 2
    assert summary["security"]["stolen_flagged"] == 1
    assert {"model", "predicted_occupancy", "low", "high"} <= summary["forecast"].keys()
    assert 0 <= summary["forecast"]["predicted_occupancy"] <= 4


def test_slots_stay_stable_across_entry_and_exit(client):
    before = {s["plate_number"]: s["slot_id"] for s in client.get("/parking/stats").json()["slots"]}

    assert leave(client, "MH12AB1234").json()["slot_id"] == before["MH12AB1234"]
    entered = enter(client, "TN09BC4321").json()
    assert entered["status"] == "entered"

    after = {s["plate_number"]: s["slot_id"] for s in client.get("/parking/stats").json()["slots"]}
    assert after["KA01AB0001"] == before["KA01AB0001"]
    assert after["TN09BC4321"] == entered["slot_id"]


def test_capacity_full(client):
    client.post("/vehicles/register", json={"plate_number": "TN09ZZ1111"})
    client.post("/vehicles/register", json={"plate_number": "TN09ZZ2222"})
    enter(client, "TN09BC4321")
    enter(client, "TN09ZZ1111")
    full = enter(client, "TN09ZZ2222").json()

    assert full["status"] == "capacity_full"
    assert full["gate_open"] is False


def test_shrinking_the_lot_moves_cars_out_of_removed_slots(client):
    client.post("/vehicles/register", json={"plate_number": "TN09ZZ1111"})
    enter(client, "TN09BC4321")
    enter(client, "TN09ZZ1111")
    leave(client, "MH12AB1234")
    assert client.post("/parking/capacity", json={"capacity": 3}).status_code == 200

    slots = client.get("/parking/stats").json()["slots"]
    shown = {s["plate_number"] for s in slots if s["plate_number"]}
    assert len(slots) == 3 and shown == {"KA01AB0001", "TN09BC4321", "TN09ZZ1111"}

    moved = next(s["slot_id"] for s in slots if s["plate_number"] == "TN09ZZ1111")
    assert leave(client, "TN09ZZ1111").json()["slot_id"] == moved


def test_unauthorized_and_stolen_are_rejected(client):
    assert client.get("/vehicles/MH14XY9087").json()["status"] == "UNAUTHORIZED"

    stolen = enter(client, "DL8CAF5031").json()
    assert stolen["status"] == "entry_rejected"
    assert stolen["security_status"] == "STOLEN"

    client.post("/vehicles/KA01AB0001/flag", json={"stolen": True})
    assert enter(client, "KA01AB0001").json()["security_status"] == "STOLEN"


def test_duplicate_reads_are_suppressed_then_expire(client, system):
    assert enter(client, "KA01AB0001").status_code == 200
    assert enter(client, "KA01AB0001").status_code == 409

    system.event_cooldown_seconds = 0
    assert enter(client, "KA01AB0001").json()["status"] == "already_parked"


def test_unmatched_exit(client):
    assert leave(client, "ZZ00ZZ0000").json()["status"] == "unmatched_exit"


def test_registration_normalizes_plate(client):
    response = client.post("/vehicles/register", json={"plate_number": "ka 01-ab 4321"})
    assert response.status_code == 201
    assert response.json()["plate_number"] == "KA01AB4321"
    assert client.get("/vehicles/KA01AB4321").json()["status"] == "AUTHORIZED"


def test_delete_vehicle(client):
    assert client.delete("/vehicles/KA01AB0001").status_code == 200
    assert client.delete("/vehicles/KA01AB0001").status_code == 404


def test_bad_input_returns_4xx(client):
    assert client.post("/models/vehicle/foo").status_code == 400
    assert client.post("/models/prediction/foo").status_code == 400
    assert client.post("/parking/capacity", json={"capacity": -1}).status_code == 422
    assert client.post("/parking/capacity", json={"capacity": 1}).status_code == 400
    assert client.get("/camera/side/status").status_code == 404


def test_missing_lstm_weights_keeps_baseline(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "ai_pipeline.forecast.LSTMForecaster.__init__.__defaults__",
        (str(tmp_path / "none.pt"), True),
    )
    assert client.post("/models/prediction/lstm").status_code == 503
    assert client.get("/models/").json()["parking_prediction"] == "baseline"


def test_simulated_gate_processing_logs_events(client):
    result = client.post("/camera/entry/process").json()
    assert result["events"]

    events = client.get("/events?gate=entry").json()["events"]
    assert events[0]["plate_number"] == result["events"][0]["plate_number"]


def test_websocket_pushes_summary(client):
    with client.websocket_connect("/dashboard/ws") as socket:
        first = socket.receive_json()
        assert first["parking"]["total_slots"] == 4

        enter(client, "TN09BC4321")
        second = socket.receive_json()
        assert second["version"] > first["version"]
        assert second["parking"]["occupied"] == 3


def test_frontend_is_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "app.js" in page.text


def test_visitors_get_a_space_unless_turned_off(client):
    visitor = enter(client, "TN22QQ7777").json()
    assert visitor["status"] == "entered" and visitor["slot_id"]
    assert visitor["security_status"] == "UNKNOWN"

    settings = client.post("/settings", json={"admit_visitors": False, "plate_region": "ANY"}).json()
    assert settings["admit_visitors"] is False and settings["plate_region"] == "ANY"
    assert enter(client, "TN22QQ8888").json()["status"] == "entry_rejected"
    assert enter(client, "MH14XY9087").json()["status"] == "entry_rejected"
