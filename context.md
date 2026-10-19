# Project Context

## Goal

Smart Parking tracks occupancy from entry/exit gate cameras that read number
plates. It does not use a wide-angle lot camera or per-slot sensors. Occupied
means the unique plates currently inside.

The demo path must always work, so the dashboard shows useful data without
cameras, model weights or a database server. Real components are optional adapters.

## Structure

```text
backend/app/main.py                 App, auth middleware, lifespan (demo seed, snapshot task), serves frontend at /
backend/app/state.py                Shared SmartParkingSystem, one GateCamera per gate, Auth
backend/app/services/parking_system.py   Orchestration: handle_plate(), process_gate_frame(), summary(); FairLock for inference
backend/app/services/gate_camera.py      Per-gate capture thread; real-time playback with frame skipping; preview JPEG
backend/app/services/parking.py          Bays: stable slot assignment and statistics
backend/app/services/security.py         Access decision, read from the registry
backend/app/services/database_service.py SQLite storage (data/parking.db; :memory: in tests), incl. saved settings
backend/app/services/barrier.py          Barrier relay: simulated or HTTP (ESP32 /open)
backend/app/services/alerts.py           Webhook / SMTP alerts for rejected entries etc.
backend/app/services/auth.py             Optional password: signed cookie or Bearer, pure ASGI middleware
backend/app/services/reports.py          Daily report from events and occupancy snapshots
backend/app/services/prediction_manager.py  baseline | lstm
ai_pipeline/detect_and_ocr.py       Detectors, plate detector, OCR (fast-plate-ocr, EasyOCR fallback), plate helpers
ai_pipeline/forecast.py             SeasonalBaseline, LSTMForecaster, synthetic_history(), training CLI
frontend/                           index.html + app.css + app.js (no build step); DESIGN.md = visual rules
firmware/camera_sensor/             ESP32-CAM: MJPEG on :81, /capture /status /open on :80
tests/                              pytest; conftest resets the shared system per test; in-memory SQLite (test_storage.py uses a real file)
```

## Rules

- Keep the demo path as the default working mode.
- Never require hardware, model files or torch at startup; import them lazily.
- Model switches load the new model first and keep the old one on failure (503 to the client).
- Demo plate reads are never applied to real camera frames.
- All plate strings go through `normalize_plate()`.
- Barrier and alert calls run in background threads, never inside the state lock.
- Keep files small and flat. Don't rebuild deep module trees.
- Frontend: follow `frontend/DESIGN.md` (five pages, one job each; colour only for
  status; no icons, gradients or shadows). Insert data with `textContent`, never `innerHTML`.
- Never commit or push; the user handles git.

## Verify

```powershell
pytest -q
uvicorn backend.app.main:app --reload   # then open http://localhost:8000/
```

## Remaining (needs hardware or real-world data)

- Flash and mount the ESP32-CAMs; the firmware hasn't been compiled or run on a board yet.
- Record footage at the real gate to measure plate-reading accuracy.
- Collect a few weeks of real occupancy history, then retrain the LSTM on it. The
  current `models/forecast_lstm.pt` is trained on synthetic data (`train --synthetic`).
