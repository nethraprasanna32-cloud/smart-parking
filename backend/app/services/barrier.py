import os
import threading
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen


class BarrierController:
    """Opens a gate barrier. BARRIER_MODE=simulated only records; http calls the ESP32 relay."""

    def __init__(self):
        self.mode = os.getenv("BARRIER_MODE", "simulated").lower()
        self.urls = {
            "entry": os.getenv("BARRIER_URL_ENTRY"),
            "exit": os.getenv("BARRIER_URL_EXIT"),
        }
        self.token = os.getenv("BARRIER_TOKEN")
        self.open_ms = int(os.getenv("BARRIER_OPEN_MS", "4000"))
        self.auto_open = os.getenv("BARRIER_AUTO_OPEN", "1") != "0"
        self.last = {"entry": None, "exit": None}
        self._lock = threading.Lock()

        if self.mode not in ("simulated", "http"):
            raise ValueError("BARRIER_MODE must be simulated or http.")

    def status(self):
        return {
            "mode": self.mode,
            "auto_open": self.auto_open,
            "open_ms": self.open_ms,
            "configured": {
                gate: self.mode == "simulated" or bool(url)
                for gate, url in self.urls.items()
            },
            "last": self.last,
        }

    def open(self, gate, reason, plate_number=None, wait=False):
        if gate not in self.urls:
            raise ValueError("Gate must be entry or exit.")

        record = {
            "gate": gate,
            "reason": reason,
            "plate_number": plate_number,
            "requested_at": datetime.now().isoformat(),
            "result": "pending" if self.mode == "http" else "opened (simulated)",
        }
        with self._lock:
            self.last[gate] = record

        if self.mode == "http":
            # Never block a camera thread on a slow relay.
            thread = threading.Thread(target=self._send, args=(record,), daemon=True)
            thread.start()
            if wait:
                thread.join(timeout=5)

        return record

    def _send(self, record):
        url = self.urls[record["gate"]]
        if not url:
            record["result"] = f"failed: BARRIER_URL_{record['gate'].upper()} is not set"
            return

        separator = "&" if "?" in url else "?"
        request = Request(f"{url}{separator}ms={self.open_ms}", method="POST")
        if self.token:
            request.add_header("X-Gate-Token", self.token)

        try:
            with urlopen(request, timeout=3) as response:
                record["result"] = "opened" if response.status < 300 else f"failed: HTTP {response.status}"
        except (URLError, OSError) as exc:
            record["result"] = f"failed: {getattr(exc, 'reason', exc)}"
