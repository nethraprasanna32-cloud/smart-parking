"""SQLite storage in one file (DATABASE_PATH, default data/parking.db; :memory: in tests)."""

import json
import os
import sqlite3
import threading
from collections import deque
from datetime import datetime


DEFAULT_PATH = "data/parking.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    plate_number TEXT PRIMARY KEY,
    data         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS currently_parked (
    plate_number TEXT PRIMARY KEY,
    slot_id      TEXT,
    entered_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT NOT NULL,
    gate         TEXT,
    status       TEXT,
    plate_number TEXT,
    data         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_timestamp ON events (timestamp);
CREATE INDEX IF NOT EXISTS events_plate ON events (plate_number);
CREATE TABLE IF NOT EXISTS occupancy (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    occupied  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS occupancy_timestamp ON occupancy (timestamp);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _as_list(status):
    return list(status) if isinstance(status, (list, tuple, set)) else [status]


class DatabaseService:
    def __init__(self, path=None):
        self.path = path or os.getenv("DATABASE_PATH", DEFAULT_PATH)
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)

        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

        self.detections = deque(maxlen=5000)

    @property
    def mode(self):
        return "memory" if self.path == ":memory:" else "sqlite"

    def close(self):
        with self.lock:
            self.conn.close()

    def _query(self, sql, params=()):
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def _write(self, sql, params=()):
        with self.lock:
            cursor = self.conn.execute(sql, params)
            self.conn.commit()
            return cursor

    def is_empty(self):
        return not self._query("SELECT 1 FROM vehicles LIMIT 1")

    def save_vehicle(self, vehicle):
        self._write(
            "INSERT INTO vehicles (plate_number, data) VALUES (?, ?) "
            "ON CONFLICT(plate_number) DO UPDATE SET data = excluded.data",
            (vehicle["plate_number"], json.dumps(vehicle)),
        )

    def update_vehicle(self, plate_number, fields):
        with self.lock:
            vehicle = self.get_vehicle(plate_number)
            if vehicle is None:
                return None
            vehicle.update(fields)
            self.save_vehicle(vehicle)
            return vehicle

    def delete_vehicle(self, plate_number):
        return self._write(
            "DELETE FROM vehicles WHERE plate_number = ?", (plate_number,)
        ).rowcount > 0

    def get_vehicle(self, plate_number):
        rows = self._query("SELECT data FROM vehicles WHERE plate_number = ?", (plate_number,))
        return json.loads(rows[0]["data"]) if rows else None

    def get_all_vehicles(self):
        return [
            json.loads(row["data"])
            for row in self._query("SELECT data FROM vehicles ORDER BY plate_number")
        ]

    def record_entry(self, plate_number, slot_id, entered_at=None):
        return self._write(
            "INSERT OR IGNORE INTO currently_parked (plate_number, slot_id, entered_at) "
            "VALUES (?, ?, ?)",
            (plate_number, slot_id, entered_at or datetime.now().isoformat()),
        ).rowcount == 1

    def record_exit(self, plate_number):
        with self.lock:
            rows = self._query(
                "SELECT * FROM currently_parked WHERE plate_number = ?", (plate_number,)
            )
            if not rows:
                return None
            self._write("DELETE FROM currently_parked WHERE plate_number = ?", (plate_number,))
            return dict(rows[0])

    def update_parked_slot(self, plate_number, slot_id):
        self._write(
            "UPDATE currently_parked SET slot_id = ? WHERE plate_number = ?",
            (slot_id, plate_number),
        )

    def get_currently_parked(self):
        return [
            dict(row)
            for row in self._query("SELECT * FROM currently_parked ORDER BY entered_at")
        ]

    def save_detection(self, detection):
        data = {**detection, "timestamp": datetime.now().isoformat()}
        if data.get("event_type") != "occupancy_event":
            self.detections.append(data)
            return

        self._write(
            "INSERT INTO events (timestamp, gate, status, plate_number, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (data["timestamp"], data.get("gate"), data.get("status"),
             data.get("plate_number", ""), json.dumps(data)),
        )

    @staticmethod
    def _event_filter(gate=None, status=None, plate=None, since=None, until=None):
        clauses, params = [], []
        if gate:
            clauses.append("gate = ?")
            params.append(gate)
        if status:
            statuses = _as_list(status)
            clauses.append(f"status IN ({', '.join('?' * len(statuses))})")
            params.extend(statuses)
        if plate:
            clauses.append("instr(plate_number, ?) > 0")
            params.append(plate)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp < ?")
            params.append(until)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def get_events(self, limit=50, gate=None, status=None, plate=None,
                   since=None, until=None, offset=0):
        where, params = self._event_filter(gate, status, plate, since, until)
        rows = self._query(
            f"SELECT data FROM events{where} ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?",
            (*params, int(limit), int(offset)),
        )
        return [json.loads(row["data"]) for row in rows]

    def count_events(self, gate=None, status=None, plate=None, since=None, until=None):
        where, params = self._event_filter(gate, status, plate, since, until)
        return self._query(f"SELECT COUNT(*) FROM events{where}", params)[0][0]

    def save_occupancy_snapshot(self, occupied, timestamp=None):
        snapshot = {
            "timestamp": timestamp or datetime.now().isoformat(),
            "occupied": int(occupied),
        }
        self._write(
            "INSERT INTO occupancy (timestamp, occupied) VALUES (?, ?)",
            (snapshot["timestamp"], snapshot["occupied"]),
        )
        return snapshot

    def get_occupancy_between(self, since, until=None):
        sql = "SELECT timestamp, occupied FROM occupancy WHERE timestamp >= ?"
        params = [since]
        if until:
            sql += " AND timestamp < ?"
            params.append(until)
        return [dict(row) for row in self._query(sql + " ORDER BY timestamp, id", params)]

    def get_occupancy_history(self, limit=100):
        rows = self._query(
            "SELECT timestamp, occupied FROM occupancy ORDER BY timestamp DESC, id DESC LIMIT ?",
            (max(1, int(limit)),),
        )
        return [dict(row) for row in reversed(rows)]

    def get_setting(self, key, default=None):
        rows = self._query("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def save_setting(self, key, value):
        self._write(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
