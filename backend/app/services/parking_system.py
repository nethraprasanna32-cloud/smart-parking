import os
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from ai_pipeline.detect_and_ocr import normalize_plate
from ai_pipeline.forecast import synthetic_history
from backend.app.services.alerts import AlertService
from backend.app.services.alpr_service import ALPRManager
from backend.app.services.barrier import BarrierController
from backend.app.services.database_service import DatabaseService
from backend.app.services.parking import OccupancyManager
from backend.app.services.prediction_manager import PredictionManager
from backend.app.services.security import SecurityService
from backend.app.services.vehicle_detection import VehicleDetectionService


DEMO_VEHICLES = [
    {
        "plate_number": "MH12AB1234",
        "owner_name": "Demo Driver",
        "vehicle_type": "car",
        "authorized": True,
        "stolen": False,
    },
    {
        "plate_number": "KA01AB0001",
        "owner_name": "Staff",
        "vehicle_type": "car",
        "authorized": True,
        "stolen": False,
    },
    {
        "plate_number": "TN09BC4321",
        "owner_name": "Resident",
        "vehicle_type": "car",
        "authorized": True,
        "stolen": False,
    },
    {
        "plate_number": "MH14XY9087",
        "owner_name": "Visitor",
        "vehicle_type": "motorcycle",
        "authorized": False,
        "stolen": False,
    },
    {
        "plate_number": "DL8CAF5031",
        "owner_name": "",
        "vehicle_type": "car",
        "authorized": True,
        "stolen": True,
    },
]

GATE_OPEN_STATUSES = {"entered", "exited"}


class FairLock:
    """A lock handed to waiters in arrival order.

    threading.Lock lets the releasing thread grab it straight back, so a gate
    that loops quickly could keep the model to itself.
    """

    def __init__(self):
        self._guard = threading.Lock()
        self._held = False
        self._waiters = deque()

    def __enter__(self):
        with self._guard:
            if not self._held and not self._waiters:
                self._held = True
                return self
            turn = threading.Event()
            self._waiters.append(turn)
        turn.wait()  # ownership is handed over directly by __exit__
        return self

    def __exit__(self, *exc_info):
        with self._guard:
            if self._waiters:
                self._waiters.popleft().set()
            else:
                self._held = False


class SmartParkingSystem:

    def __init__(self, capacity=4):
        # Entry and exit workers run in separate threads; occupancy changes
        # and model inference are serialised through this lock.
        self.lock = threading.RLock()
        self.inference_lock = FairLock()
        self.state_version = 0

        self.vehicle_detector = VehicleDetectionService(model_type="simulated")
        self.parking = OccupancyManager(capacity=capacity)
        self.database = DatabaseService()
        self.security = SecurityService(self.database)

        self.alpr = ALPRManager()
        self.alpr.configure(simulated=True)

        self.prediction = PredictionManager(horizon_minutes=60)
        self.barrier = BarrierController()
        self.alerts = AlertService()

        self.event_cooldown_seconds = int(os.getenv("EVENT_COOLDOWN_SECONDS", "15"))
        self.recent_events = {}

        # A camera plate must be read this many times within the window
        # before it counts, so single-frame OCR misreads never open the gate.
        self.min_camera_reads = int(os.getenv("MIN_CAMERA_READS", "2"))
        self.read_window_seconds = 10

        # Cars not in the registry: let in as visitors (public lot) or turn
        # away (members only). Registered-but-blocked and stolen cars are
        # always turned away.
        self.admit_visitors = os.getenv("ADMIT_VISITORS", "1") != "0"

        # For testing with plates written on paper: read text anywhere in the
        # frame, with no car in view. Off for real gates.
        self.paper_plates = os.getenv("PAPER_PLATES", "0") == "1"
        self.recent_reads = {"entry": deque(), "exit": deque()}

        self._load_saved_settings()

    # ----------------------------------------------------------------- setup

    def _load_saved_settings(self):
        """Settings changed in the dashboard override the env defaults."""
        saved = self.database.get_setting
        self.parking.set_capacity(saved("capacity", self.parking.capacity))
        self.event_cooldown_seconds = saved("event_cooldown_seconds", self.event_cooldown_seconds)
        self.min_camera_reads = saved("min_camera_reads", self.min_camera_reads)
        self.admit_visitors = saved("admit_visitors", self.admit_visitors)
        self.paper_plates = saved("paper_plates", self.paper_plates)
        region = saved("plate_region")
        if region:
            os.environ["PLATE_REGION"] = region
        kinds = saved("alert_kinds")
        if kinds is not None:
            self.alerts.set_enabled(kinds)

    def seed_demo_data(self):
        """First run only: demo vehicles, two parked cars and synthetic history.
        Set DEMO_DATA=0 to start with an empty database instead."""
        if os.getenv("DEMO_DATA", "1") == "0" or not self.database.is_empty():
            return

        for vehicle in DEMO_VEHICLES:
            self.database.save_vehicle(vehicle)

        now = datetime.now()
        self.database.record_entry(
            "MH12AB1234", "A01", (now - timedelta(hours=3)).isoformat()
        )
        self.database.record_entry(
            "KA01AB0001", "A02", (now - timedelta(minutes=40)).isoformat()
        )

        self._seed_demo_history(now)

    def _seed_demo_history(self, now):
        """Two weeks of synthetic occupancy so charts and forecasts have shape."""
        capacity = max(1, self.parking.capacity)
        for row in synthetic_history(days=14, capacity=capacity, end=now, seed=7)[:-1]:
            self.database.save_occupancy_snapshot(row["occupied"], timestamp=row["timestamp"])

        self.database.save_occupancy_snapshot(
            len(self.database.get_currently_parked())
        )

    def bump(self):
        self.state_version += 1

    # -------------------------------------------------------------- settings

    def set_capacity(self, capacity):
        with self.lock:
            occupied = len(self.database.get_currently_parked())
            if int(capacity) < occupied:
                raise ValueError(
                    f"Capacity cannot be lower than current occupancy ({occupied})."
                )
            self.parking.set_capacity(capacity)
            self.database.save_setting("capacity", self.parking.capacity)
            # Cars in slots that no longer exist move into free ones, so the
            # map and later exit events name the slot the car is shown in.
            parked = self.database.get_currently_parked()
            for plate_number, slot_id in self.parking.get_slot_assignments(parked).items():
                stored = next(v for v in parked if v["plate_number"] == plate_number)
                if stored.get("slot_id") != slot_id:
                    self.database.update_parked_slot(plate_number, slot_id)
            self.bump()

    def change_detection_model(self, model_type):
        # Wait for any in-flight inference before swapping models.
        with self.inference_lock, self.lock:
            previous = self.vehicle_detector.get_current_model()
            self.vehicle_detector.change_model(model_type)
            try:
                self.alpr.configure(simulated=model_type == "simulated")
            except Exception:
                self.vehicle_detector.change_model(previous)
                raise
            self._warm_up()
            self.bump()

    def _warm_up(self):
        """Run models once on a blank frame: the first real inference is ~8 s slower."""
        if self.alpr.simulated:
            return
        try:
            import numpy as np

            blank = np.zeros((640, 640, 3), dtype=np.uint8)
            self.vehicle_detector.detect_vehicles(blank)
            self.alpr.alpr.plate_detector.detect(blank)
            self.alpr.alpr.ocr.readtext(blank[:64, :192])
        except Exception:
            pass  # warm-up is best effort; real frames will surface real errors

    def get_detection_model(self):
        return self.vehicle_detector.get_current_model()

    def change_prediction_model(self, model_type):
        self.prediction.change_model(model_type)
        self.bump()

    def get_prediction_model(self):
        return self.prediction.get_current_model()

    def train_prediction_model(self, history=None, epochs=200):
        if history is None:
            history = self.database.get_occupancy_history(20000)
        return self.prediction.train(history, epochs=epochs, capacity=self.parking.capacity)

    def get_settings(self):
        return {
            "event_cooldown_seconds": self.event_cooldown_seconds,
            "min_camera_reads": self.min_camera_reads,
            "admit_visitors": self.admit_visitors,
            "paper_plates": self.paper_plates,
            "plate_region": os.getenv("PLATE_REGION", "IN").upper(),
            "capacity": self.parking.capacity,
            "ocr_engine": self.alpr.alpr.ocr.engine if self.alpr.alpr else None,
            "barrier": self.barrier.status(),
            "alerts": self.alerts.status(),
        }

    def update_settings(self, event_cooldown_seconds=None, min_camera_reads=None, alert_kinds=None,
                        admit_visitors=None, plate_region=None, paper_plates=None):
        if alert_kinds is not None:
            self.alerts.set_enabled(alert_kinds)
            self.database.save_setting("alert_kinds", sorted(self.alerts.enabled))
        if event_cooldown_seconds is not None:
            self.event_cooldown_seconds = int(event_cooldown_seconds)
            self.database.save_setting("event_cooldown_seconds", self.event_cooldown_seconds)
        if min_camera_reads is not None:
            self.min_camera_reads = int(min_camera_reads)
            self.database.save_setting("min_camera_reads", self.min_camera_reads)
        if admit_visitors is not None:
            self.admit_visitors = bool(admit_visitors)
            self.database.save_setting("admit_visitors", self.admit_visitors)
        if paper_plates is not None:
            self.paper_plates = bool(paper_plates)
            self.database.save_setting("paper_plates", self.paper_plates)
        if plate_region is not None:
            os.environ["PLATE_REGION"] = plate_region.upper()
            self.database.save_setting("plate_region", plate_region.upper())
        self.bump()
        return self.get_settings()

    def check_vehicle(self, plate_number):
        return self.security.check_vehicle(plate_number)

    # --------------------------------------------------------------- events

    def _is_duplicate_event(self, plate_number, direction, fuzzy=False):
        now = time.monotonic()
        self.recent_events = {
            key: seen
            for key, seen in self.recent_events.items()
            if now - seen < self.event_cooldown_seconds
        }
        if (plate_number, direction) in self.recent_events:
            return True
        # Camera reads: a one-character misread of a plate just seen at this
        # gate is the same car, not a new one (7 chars, 1 differs = 0.857).
        return fuzzy and any(
            gate == direction and SequenceMatcher(None, plate, plate_number).ratio() >= 0.85
            for plate, gate in self.recent_events
        )

    def _mark_event(self, plate_number, direction):
        self.recent_events[(plate_number, direction)] = time.monotonic()

    def _confirm_read(self, gate, plate_number):
        """Return the consensus plate once it has enough similar recent reads."""
        now = time.monotonic()
        reads = self.recent_reads[gate]
        while reads and now - reads[0][0] > self.read_window_seconds:
            reads.popleft()
        reads.append((now, plate_number))

        similar = [
            plate for _, plate in reads
            if SequenceMatcher(None, plate, plate_number).ratio() >= 0.75
        ]
        if len(similar) < self.min_camera_reads:
            return None
        return Counter(similar).most_common(1)[0][0]

    def known_plates(self):
        plates = {vehicle["plate_number"] for vehicle in self.database.get_all_vehicles()}
        plates.update(
            vehicle["plate_number"] for vehicle in self.database.get_currently_parked()
        )
        return plates

    def handle_plate(self, plate_number, direction, source="camera", confidence=None):
        """Apply one plate read at a gate. Returns the event, or None for a duplicate."""
        if direction not in ("entry", "exit"):
            raise ValueError("Gate direction must be entry or exit.")

        plate_number = normalize_plate(plate_number)
        if not plate_number:
            raise ValueError("Plate number is empty.")

        with self.lock:
            if self._is_duplicate_event(plate_number, direction, fuzzy=source == "camera"):
                return None
            self._mark_event(plate_number, direction)

            security = self.security.check_vehicle(plate_number)
            currently_parked = self.database.get_currently_parked()
            parked_plates = {vehicle["plate_number"] for vehicle in currently_parked}
            slot_id = None

            if direction == "entry":
                visitor = self.admit_visitors and security["status"] == "UNKNOWN"
                if not (security["access_granted"] or visitor):
                    status = "entry_rejected"
                elif plate_number in parked_plates:
                    status = "already_parked"
                elif len(parked_plates) >= self.parking.capacity:
                    status = "capacity_full"
                else:
                    slot_id = self.parking.get_available_slot(currently_parked)
                    added = self.database.record_entry(plate_number, slot_id)
                    status = "entered" if added else "already_parked"
            else:
                removed = self.database.record_exit(plate_number)
                if removed:
                    status = "exited"
                    slot_id = removed.get("slot_id")
                else:
                    status = "unmatched_exit"

            event = {
                "plate_number": plate_number,
                "direction": direction,
                "gate": direction,
                "status": status,
                "slot_id": slot_id,
                "gate_open": status in GATE_OPEN_STATUSES,
                "security_status": security["status"],
                "source": source,
                "confidence": confidence,
            }
            self.database.save_detection({**event, "event_type": "occupancy_event"})

            if status in GATE_OPEN_STATUSES:
                self.database.save_occupancy_snapshot(
                    len(self.database.get_currently_parked())
                )
            self.bump()

        # Outside the lock: both hand off to background threads.
        if event["gate_open"] and self.barrier.auto_open:
            self.barrier.open(direction, reason=status, plate_number=plate_number)
        self.alerts.notify_event(event)

        return event

    def process_gate_frame(self, frame, direction):
        if direction not in ("entry", "exit"):
            raise ValueError("Gate direction must be entry or exit.")

        known_plates = self.known_plates()

        # Models aren't thread-safe, so inference is serialised, but first come
        # first served, so one busy gate can't starve the other.
        with self.inference_lock:
            simulated = self.alpr.simulated
            paper = self.paper_plates and not simulated
            vehicles = self.vehicle_detector.detect_vehicles(frame)

            # A real plate read without a vehicle in view is almost always
            # noise, unless plates written on paper are being tested.
            if vehicles or simulated or paper:
                plates = self.alpr.recognize_plates(frame, known_plates=known_plates)
            else:
                plates = []
            if paper and not plates:
                plates = self.alpr.read_paper_plate(frame)

        with self.lock:
            events = []
            for plate_number in dict.fromkeys(plate["plate_text"] for plate in plates):
                confidence = next(
                    plate["confidence"] for plate in plates
                    if plate["plate_text"] == plate_number
                )
                if not simulated:
                    plate_number = self._confirm_read(direction, plate_number)
                    if plate_number is None:
                        continue
                event = self.handle_plate(
                    plate_number,
                    direction,
                    source="simulated" if simulated else "camera",
                    confidence=confidence,
                )
                if event:
                    events.append(event)

            statistics = self.parking.get_statistics(
                self.database.get_currently_parked()
            )

        return {
            "timestamp": datetime.now().isoformat(),
            "model": self.vehicle_detector.get_current_model(),
            "gate": direction,
            "vehicles": vehicles,
            "plates": plates,
            "events": events,
            "statistics": statistics,
        }

    # -------------------------------------------------------------- summary

    def record_snapshot(self):
        with self.lock:
            return self.database.save_occupancy_snapshot(
                len(self.database.get_currently_parked())
            )

    def summary(self):
        currently_parked = self.database.get_currently_parked()
        statistics = self.parking.get_statistics(currently_parked)
        vehicles = self.database.get_all_vehicles()
        history = self.database.get_occupancy_history(2000)

        today = datetime.now().date().isoformat()
        rejected_today = sum(
            1 for event in self.database.get_events(500, status="entry_rejected")
            if str(event.get("timestamp", "")).startswith(today)
        )

        return {
            "version": self.state_version,
            "parking": statistics,
            "vehicles": {
                "total": len(vehicles),
            },
            "security": {
                "stolen_flagged": sum(1 for v in vehicles if v.get("stolen")),
                "unauthorized": sum(
                    1 for v in vehicles
                    if not v.get("authorized") and not v.get("stolen")
                ),
                "rejected_today": rejected_today,
            },
            "forecast": self.prediction.forecast(history, self.parking.capacity),
        }
