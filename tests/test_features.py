import http.server
import json
import threading
import time
from datetime import date, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.state import auth


def enter(client, plate):
    return client.post("/parking/manual", json={"plate_number": plate, "direction": "entry"})


def leave(client, plate):
    return client.post("/parking/manual", json={"plate_number": plate, "direction": "exit"})


@pytest.fixture
def locked(client):
    auth.password = "s3cret"
    yield client
    auth.password = None


def test_api_is_open_without_password(client):
    assert client.get("/auth/status").json() == {"required": False, "signed_in": True}
    assert client.get("/vehicles/").status_code == 200


def test_password_protects_api_but_not_page(locked):
    assert locked.get("/").status_code == 200
    assert locked.get("/health").status_code == 200
    assert locked.get("/vehicles/").status_code == 401
    assert locked.post("/parking/manual", json={"plate_number": "X1", "direction": "entry"}).status_code == 401
    assert locked.get("/auth/status").json() == {"required": True, "signed_in": False}


def test_login_sets_cookie_and_logout_clears_it(locked):
    assert locked.post("/auth/login", json={"password": "nope"}).status_code == 401

    assert locked.post("/auth/login", json={"password": "s3cret"}).status_code == 200
    assert locked.get("/vehicles/").status_code == 200

    locked.post("/auth/logout")
    locked.cookies.clear()
    assert locked.get("/vehicles/").status_code == 401


def test_bearer_password_works_for_scripts(locked):
    response = locked.get("/vehicles/", headers={"Authorization": "Bearer s3cret"})
    assert response.status_code == 200


def test_websocket_rejected_without_login(locked):
    with pytest.raises(WebSocketDisconnect):
        with locked.websocket_connect("/dashboard/ws") as socket:
            socket.receive_json()


def test_forged_or_expired_tokens_fail():
    assert not auth.valid_token("9999999999.deadbeef")
    assert not auth.valid_token("garbage")
    signature = auth.make_token().split(".")[1]
    assert not auth.valid_token(f"1.{signature}")


def test_entry_opens_barrier_and_rejection_does_not(client, system):
    enter(client, "TN09BC4321")
    assert system.barrier.last["entry"]["plate_number"] == "TN09BC4321"

    system.barrier.last["entry"] = None
    enter(client, "DL8CAF5031")
    assert system.barrier.last["entry"] is None


def test_manual_barrier_open(client):
    record = client.post("/barrier/exit/open").json()
    assert record["gate"] == "exit"
    assert record["result"] == "opened (simulated)"
    assert client.post("/barrier/side/open").status_code == 422


def test_http_barrier_reports_failure(client, system):
    system.barrier.mode = "http"
    system.barrier.urls["entry"] = "http://127.0.0.1:9/open"
    record = client.post("/barrier/entry/open").json()
    assert record["result"].startswith("failed")


def test_http_barrier_calls_relay(client, system):
    calls = []

    class Relay(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append((self.path, self.headers.get("X-Gate-Token")))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Relay)
    threading.Thread(target=server.handle_request, daemon=True).start()
    system.barrier.mode = "http"
    system.barrier.token = "gate-token"
    system.barrier.urls["exit"] = f"http://127.0.0.1:{server.server_port}/open"

    record = client.post("/barrier/exit/open").json()
    server.server_close()
    assert record["result"] == "opened"
    assert calls == [(f"/open?ms={system.barrier.open_ms}", "gate-token")]


def test_alerts_recorded_for_enabled_kinds(client):
    enter(client, "DL8CAF5031")
    enter(client, "ZZ99ZZ9999")
    kinds = [alert["kind"] for alert in client.get("/alerts").json()["recent"]]
    assert kinds == ["stolen"]


def test_alert_settings_and_test_endpoint(client):
    settings = client.post("/settings", json={"alert_kinds": ["unknown"]}).json()
    assert settings["alerts"]["enabled"] == ["unknown"]
    assert client.post("/settings", json={"alert_kinds": ["bogus"]}).status_code == 400
    assert client.post("/alerts/test").status_code == 400


def test_webhook_delivery(client, system):
    received = []

    class Hook(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=server.handle_request, daemon=True).start()
    system.alerts.webhook_url = f"http://127.0.0.1:{server.server_port}/hook"

    record = client.post("/alerts/test").json()
    server.server_close()
    assert record["delivery"]["webhook"] == "sent"
    assert "Test alert" in received[0]["text"]


def test_cooldown_setting(client):
    client.post("/settings", json={"event_cooldown_seconds": 0})
    enter(client, "TN09BC4321")
    assert enter(client, "TN09BC4321").json()["status"] == "already_parked"


def test_event_search_and_paging(client):
    enter(client, "TN09BC4321")
    leave(client, "MH12AB1234")
    enter(client, "DL8CAF5031")

    found = client.get("/events?plate=tn09").json()
    assert found["total"] == 1 and found["events"][0]["plate_number"] == "TN09BC4321"

    problems = client.get("/events?status=problems").json()
    assert [event["plate_number"] for event in problems["events"]] == ["DL8CAF5031"]

    page = client.get("/events?limit=1&offset=1").json()
    assert page["total"] == 3 and page["events"][0]["plate_number"] == "MH12AB1234"

    today = date.today().isoformat()
    assert client.get(f"/events?since={today}&until={today}").json()["total"] == 3
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert client.get(f"/events?since={tomorrow}").json()["total"] == 0
    assert client.get("/events?since=yesterday").status_code == 422


def test_csv_export(client):
    enter(client, "TN09BC4321")
    response = client.get("/events.csv?gate=entry")
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("timestamp,gate,plate_number,status")
    assert "TN09BC4321" in lines[1]


def test_daily_report(client, system):
    system.event_cooldown_seconds = 0
    enter(client, "TN09BC4321")
    leave(client, "TN09BC4321")
    enter(client, "DL8CAF5031")

    report = client.get("/reports/daily?days=3").json()
    assert len(report["days"]) == 3
    today = report["days"][-1]
    assert today["date"] == date.today().isoformat()
    assert (today["entries"], today["exits"], today["turned_away"], today["stolen_seen"]) == (1, 1, 1, 1)
    assert today["average_stay_minutes"] == 0
    assert today["peak_occupancy"] >= 2
    assert report["totals"]["entries"] == 1


def test_ntfy_webhook_gets_plain_text(client, system, monkeypatch):
    received = []

    class Hook(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            received.append((dict(self.headers), body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=server.handle_request, daemon=True).start()
    monkeypatch.setenv("ALERT_WEBHOOK_FORMAT", "ntfy")
    system.alerts.webhook_url = f"http://127.0.0.1:{server.server_port}/my-topic"

    enter(client, "DL8CAF5031")
    for _ in range(50):
        if received:
            break
        time.sleep(0.1)
    server.server_close()

    headers, body = received[0]
    assert headers["Title"] == "Stolen vehicle at the gate"
    assert headers["Priority"] == "urgent"
    assert "Plate: DL8CAF5031" in body and "Gate: Entry gate" in body
    assert not body.startswith("{")
