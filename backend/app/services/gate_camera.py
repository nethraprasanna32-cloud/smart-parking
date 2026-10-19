import os
import threading
import time
from datetime import datetime


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}


def parse_source(source):
    source = "0" if source is None else str(source).strip()
    return int(source) if source.isdigit() else source


def is_video_file(source):
    return (
        isinstance(source, str)
        and not source.startswith(("http://", "https://", "rtsp://"))
        and os.path.splitext(source)[1].lower() in VIDEO_EXTENSIONS
    )


class GateCamera:
    """One gate's capture loop: read frames, run the pipeline, keep a preview."""

    def __init__(self, gate, system):
        self.gate = gate
        self.system = system
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None

        self.source = None
        self.fps = 2.0
        self.state = "idle"
        self.error = None
        self.started_at = None
        self.frames_read = 0
        self.frames_processed = 0
        self.frames_skipped = 0
        self.last_result = None
        self.latest_frame = None
        self.latest_jpeg = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def status(self):
        last = self.last_result or {}
        return {
            "gate": self.gate,
            "running": self.running,
            "state": self.state,
            "source": None if self.source is None else str(self.source),
            "fps": self.fps,
            "error": self.error,
            "note": self.note(),
            "started_at": self.started_at,
            "frames_read": self.frames_read,
            "frames_processed": self.frames_processed,
            "frames_skipped": self.frames_skipped,
            "last_processed_at": last.get("timestamp"),
            "last_plates": [plate["plate_text"] for plate in last.get("plates", [])],
            "has_preview": self.latest_jpeg is not None,
        }

    def note(self):
        if self.running and self.system.alpr.simulated:
            return "Showing video only. To read plates, set Plate reading to Camera AI in Settings"
        return None

    def start(self, source, fps=2.0):
        import cv2

        self.stop()

        source = parse_source(source)
        if isinstance(source, str) and is_video_file(source) and not os.path.isfile(source):
            raise FileNotFoundError(f"Video file not found: {source}")

        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Could not open {self.gate} camera source: {source}")

        self.source = source
        self.fps = max(0.2, float(fps))
        self.error = None
        self.state = "running"
        self.started_at = datetime.now().isoformat()
        self.frames_read = 0
        self.frames_processed = 0
        self.frames_skipped = 0
        self.latest_frame = None
        self.latest_jpeg = None
        self.stop_event.clear()

        self.thread = threading.Thread(
            target=self._run,
            args=(capture,),
            name=f"gate-{self.gate}",
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.thread = None
        if self.state == "running":
            self.state = "stopped"

    def process_once(self):
        """Run the pipeline on the newest frame, or a simulated read with no source."""
        with self.lock:
            frame = self.latest_frame
        result = self.system.process_gate_frame(frame, self.gate)
        self._remember(frame, result)
        return result

    def _run(self, capture):
        import cv2

        file_source = is_video_file(self.source)
        video_fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        process_every = 1.0 / self.fps
        last_processed = 0.0
        failures = 0
        started = time.monotonic()

        if not file_source:
            # Keep only the newest frame so slow analysis never builds a backlog.
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        try:
            while not self.stop_event.is_set():
                if file_source:
                    # Files follow a real-time clock: wait when ahead, and when
                    # analysis is slower than playback, skip frames (grab()
                    # doesn't decode) instead of falling ever further behind.
                    due = int((time.monotonic() - started) * video_fps)
                    if self.frames_read > due:
                        self.stop_event.wait((self.frames_read - due) / video_fps)
                        continue
                    caught_up = True
                    while self.frames_read < due - 1:
                        if not capture.grab():
                            caught_up = False
                            break
                        self.frames_read += 1
                        self.frames_skipped += 1
                    if not caught_up:
                        self.state = "finished"
                        return

                ok, frame = capture.read()

                if not ok:
                    if file_source:
                        self.state = "finished"
                        return
                    # Network streams drop; reconnect with capped backoff.
                    failures += 1
                    self.state = "reconnecting"
                    self.error = f"Stream read failed ({failures}x), reconnecting"
                    capture.release()
                    if self.stop_event.wait(min(30, 2 ** min(failures, 5))):
                        return
                    capture = cv2.VideoCapture(self.source)
                    continue

                failures = 0
                self.state = "running"
                self.frames_read += 1
                with self.lock:
                    self.latest_frame = frame

                now = time.monotonic()
                # The simulated ALPR invents plates; never apply that to real footage.
                if self.system.alpr.simulated:
                    if self.frames_read % 5 == 0:
                        self._remember(frame, None)
                elif now - last_processed >= process_every:
                    last_processed = now
                    try:
                        result = self.system.process_gate_frame(frame, self.gate)
                        self.error = None
                    except Exception as exc:  # keep the gate alive on a bad frame
                        result = None
                        self.error = f"{type(exc).__name__}: {exc}"
                    self._remember(frame, result)
                elif self.frames_read % 5 == 0:
                    self._remember(frame, None)
        finally:
            capture.release()

    def _remember(self, frame, result):
        if result is not None:
            self.frames_processed += 1
            self.last_result = result
        if frame is None:
            return

        import cv2

        preview = frame.copy()
        last = self.last_result or {}
        for vehicle in last.get("vehicles", []):
            x1, y1, x2, y2 = vehicle["bbox"]
            cv2.rectangle(preview, (x1, y1), (x2, y2), (200, 120, 40), 2)
        for plate in last.get("plates", []):
            x1, y1, x2, y2 = plate["bbox"]
            cv2.rectangle(preview, (x1, y1), (x2, y2), (40, 180, 240), 2)
            cv2.putText(
                preview, plate["plate_text"], (x1, max(14, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 180, 240), 2
            )

        height, width = preview.shape[:2]
        if width > 960:
            preview = cv2.resize(preview, (960, int(height * 960 / width)))

        ok, jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            self.latest_jpeg = jpeg.tobytes()
