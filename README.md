# Smart Parking

Gate-camera parking: an entry camera and an exit camera read number plates.
Occupancy is the set of plates currently inside, access is checked against a
vehicle registry, and the barrier opens for cars that are let in.

```text
smart-parking/
+-- backend/app/            FastAPI app (routes/, services/)
+-- ai_pipeline/
|   +-- detect_and_ocr.py   Vehicle + plate detection, OCR, plate helpers
|   +-- forecast.py         Seasonal baseline + optional LSTM
+-- frontend/               Dashboard, served by the backend at / (rules in DESIGN.md)
+-- firmware/camera_sensor/ ESP32-CAM: MJPEG stream + barrier relay
+-- docs/                   Project paper (Smart_Parking_Paper.pdf) and build_paper.py
+-- tests/
```

## Run

```powershell
pip install -r requirements.txt                 # API + demo mode
pip install -r ai_pipeline/requirements.txt     # real cameras/models (optional)
$env:DASHBOARD_PASSWORD = "pick-a-password"     # recommended
uvicorn backend.app.main:app --reload
```

Open http://localhost:8000/ for the dashboard, or http://localhost:8000/docs for the API.

The dashboard has five pages: **Overview** (free spaces, the lot, latest
activity), **Gates** (cameras, barriers, recording a car by hand),
**Activity** (search, CSV export, weekly report), **Vehicles** and
**Settings**. Press **Present** (or the `P` key) to show the overview
full-screen for a projector or TV, or open http://localhost:8000/?present on
a kiosk screen.

It starts in **demo mode**: demo vehicles, two parked cars, two weeks of
synthetic occupancy history, and made-up plate reads when you press
**Try a reading**. No camera, model weights or database server is needed.

## Data storage

Everything (vehicles, parked cars, the gate log, occupancy history and the
settings you change in the dashboard) is saved in one SQLite file,
`data/parking.db`. SQLite is built into Python, so there's nothing to install,
and the data survives restarts. Back it up by copying the file while the
server is stopped.

- The demo data is added only the first time, when the database is empty.
- To start clean for real use: stop the server, delete `data/parking.db`, and
  start it with `$env:DEMO_DATA = "0"`.
- `DATABASE_PATH` puts the file somewhere else; `DATABASE_PATH=:memory:` keeps
  nothing between runs.

## Using real cameras

1. In **Settings → Plate reading**, choose **Camera AI: YOLO11**. This needs
   `yolo11n.pt` and `license_plate_detector.pt` in the project root. The
   first switch also downloads the plate OCR model (a few MB) and warms the
   models up, which takes 10–20 s.
2. On the **Gates** page, pick a source for a camera: a webcam, a file in `test_videos/`, or an
   ESP32-CAM stream like `http://<ip>:81/stream` (see `firmware/camera_sensor/README.md`).
3. Press **Start**. A background worker analyses frames at the chosen rate and
   logs entries and exits. Video files play at real speed; if analysis is
   slower than the video, frames are skipped rather than falling behind.

How reads become events:
- Plates are read by [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr),
  a model trained only on plates. EasyOCR is used if it isn't installed.
- A plate must be read twice within 10 s before it counts.
- A read that's close to a registered or parked plate snaps to it.
- Repeat reads of the same car at the same gate are ignored for 15 s
  (configurable in Settings). This includes one-character misreads.
- In demo mode, a running camera only shows a preview: made-up plates are
  never applied to real footage.

## Security

Set `DASHBOARD_PASSWORD` before using this anywhere but your own computer.
Without it, the dashboard shows a warning and anyone on the network can use it.
With it:
- the dashboard asks for the password and keeps you signed in for 12 hours
  (`SESSION_HOURS`);
- every API call, the live updates and the camera streams require sign-in;
- scripts can send `Authorization: Bearer <password>`.

Set `SESSION_SECRET` too if you don't want restarts to sign everyone out.

## Barrier control

When a car is let in or leaves, the backend opens that gate's barrier.
Operators can also open it with **Open barrier** on the **Gates** page.

- `BARRIER_MODE=simulated` (default) only records the command.
- `BARRIER_MODE=http` calls the relay on each gate's ESP32-CAM:

```powershell
$env:BARRIER_MODE = "http"
$env:BARRIER_URL_ENTRY = "http://192.168.1.50/open"
$env:BARRIER_URL_EXIT = "http://192.168.1.51/open"
$env:BARRIER_TOKEN = "same-as-GATE_TOKEN-in-secrets.h"
```

## Alerts

Stolen cars, blocked cars and "lot full" turn-aways show in the dashboard. To
get them on your phone too, set a webhook (Slack, Discord, Google Chat,
[ntfy](https://ntfy.sh), …) and/or email. Use **Send test** to check delivery.

```powershell
$env:ALERT_WEBHOOK_URL = "https://ntfy.sh/your-private-topic"
$env:SMTP_HOST = "smtp.gmail.com"; $env:SMTP_USER = "you@gmail.com"
$env:SMTP_PASSWORD = "app-password"; $env:ALERT_EMAIL_TO = "guard@example.com"
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DASHBOARD_PASSWORD` | unset | Turns on sign-in for the dashboard and API. |
| `SESSION_SECRET` | random | Keeps sessions valid across restarts. |
| `SESSION_HOURS` | `12` | How long a sign-in lasts. |
| `DATABASE_PATH` | `data/parking.db` | SQLite file for all data; `:memory:` for nothing saved. |
| `DEMO_DATA` | `1` | Set `0` so an empty database stays empty instead of getting demo data. |
| `PLATE_REGION` | `IN` | Plate format check: `IN` (Indian) or `ANY` (4–10 letters/digits; for foreign test footage). |
| `OCR_ENGINE` | `auto` | `fast-plate-ocr`, `easyocr`, or `auto` (fast-plate-ocr if installed). |
| `OCR_MODEL` | `cct-s-v2-global-model` | fast-plate-ocr model name. |
| `DETECTOR_MODEL` | `yolo11n.pt` | Vehicle detector weights. |
| `PLATE_MODEL_PATH` | `license_plate_detector.pt` | Plate detector weights. |
| `EVENT_COOLDOWN_SECONDS` | `15` | Ignore repeat reads of a plate at a gate for this long. |
| `MIN_CAMERA_READS` | `2` | Reads needed before a camera plate counts. |
| `BARRIER_MODE` | `simulated` | `simulated` or `http`. |
| `BARRIER_URL_ENTRY` / `BARRIER_URL_EXIT` | unset | Relay endpoints for `http` mode. |
| `BARRIER_TOKEN` | unset | Sent as `X-Gate-Token` to the relay. |
| `BARRIER_OPEN_MS` | `4000` | How long the barrier stays open. |
| `BARRIER_AUTO_OPEN` | `1` | Set `0` to only open barriers by hand. |
| `ALERT_WEBHOOK_URL` | unset | JSON POST target for alerts. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | unset / `587` | Email alerts (STARTTLS). |
| `ALERT_ON` | `stolen,unauthorized,full` | Which events alert: also `unknown`, `unmatched`. |
| `SNAPSHOT_INTERVAL_SECONDS` | `300` | How often occupancy is recorded for forecasting. |
| `FORECAST_LSTM_WEIGHTS` | `models/forecast_lstm.pt` | Optional LSTM weights. |

## Forecasting

The default **typical daily pattern** model blends the current level with the
usual occupancy for that weekday and time. It improves as history builds up.

The **LSTM** is optional (`pip install torch`). It learns occupancy as a
fraction of capacity, so weights trained on one lot size work on another.

Until you have a few weeks of real history, train it on synthetic data. The
generator makes weekday commute peaks, a lunch dip, quieter weekends,
occasional holidays and day-to-day variation:

```powershell
python -m ai_pipeline.forecast train --synthetic --days 56 --capacity 50
# Trained on 4685 windows, loss 0.0021 -> models/forecast_lstm.pt
# 1-hour-ahead error on the held-out 7 days (average spaces off): lstm 1.92, baseline 3.25
```

Once the lot has real history, retrain from the running server instead:

```powershell
python -m ai_pipeline.forecast train --from-api http://localhost:8000 --epochs 300
python -m ai_pipeline.forecast synthetic --days 28 --out fake.json   # just write the data
```

Training holds back the last 7 days and scores both models on them
(`--holdout-days 0` to turn off). Then switch to **LSTM** in **Settings**.
Until it has a full input window, it falls back to the baseline. Demo mode
seeds two weeks of the same synthetic data, so the chart has a realistic shape.

Synthetic data only teaches a generic office-lot pattern. Retrain on real
history before trusting the LSTM over the baseline for your lot.

## API overview

| Route | What it does |
|---|---|
| `GET /dashboard/summary`, `WS /dashboard/ws` | Occupancy, bays, security counts, forecast (the socket pushes on change) |
| `GET /events?plate=&gate=&status=&since=&until=&limit=&offset=` | Search the gate log (`status=problems` for issues) |
| `GET /events.csv?…` | Same filters, as a CSV download |
| `GET /reports/daily?days=7` | Per-day entries, exits, turn-aways, busiest time, average stay |
| `POST /parking/manual` | Operator entry/exit for a missed read |
| `POST /parking/capacity` | Set the number of spaces |
| `GET/POST/DELETE /vehicles/…` | Registry; `POST /vehicles/{plate}/flag` for stolen/allowed |
| `POST /camera/{gate}/start\|stop\|process`, `GET …/status\|stream\|snapshot.jpg` | Gate cameras |
| `POST /barrier/{gate}/open` | Open a barrier by hand |
| `GET /alerts`, `POST /alerts/test` | Recent alerts, test delivery |
| `GET/POST /settings` | Cooldown, reads needed, alert types; barrier and alert status |
| `POST /auth/login\|logout`, `GET /auth/status` | Dashboard sign-in |
| `GET/POST /models/…` | Switch detector and forecast models |

## Tests

```powershell
pytest -q   # uses an in-memory database; never touches data/parking.db
```
