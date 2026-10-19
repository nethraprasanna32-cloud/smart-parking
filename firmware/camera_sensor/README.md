# Gate camera and barrier relay (ESP32-CAM)

One AI-Thinker ESP32-CAM per lane. It streams video to the backend, which
reads the plates, and it drives a relay that opens that lane's barrier.

| Endpoint | Port | What it does |
|---|---|---|
| `GET /stream` | 81 | MJPEG video for the backend |
| `GET /capture` | 80 | One JPEG |
| `GET /status` | 80 | Gate name, uptime, WiFi signal, barrier state |
| `POST /open?ms=4000` | 80 | Pulse the relay (needs `X-Gate-Token` if `GATE_TOKEN` is set) |

The stream has its own port because a stream request never ends. On the same
server it would block `/open` while the backend is watching.

## Flash

1. Arduino IDE → Boards Manager → install **esp32** by Espressif (2.x or 3.x).
2. Board: **AI Thinker ESP32-CAM**, Partition scheme: **Huge APP**, PSRAM: enabled.
3. `cp secrets.example.h secrets.h` and set:
   - your WiFi name and password;
   - `GATE_NAME` (`entry` or `exit`);
   - `GATE_TOKEN`, a random string that you also set as `BARRIER_TOKEN` on the backend.
4. Wire an FTDI adapter (5V, GND, U0R↔TX, U0T↔RX), bridge **IO0 to GND**, reset, upload.
5. Remove the IO0 bridge, reset, and open Serial Monitor at 115200 to get the IP.

## Wire the barrier relay

Use a 5 V relay module with an opto-isolated input:

| Relay module | ESP32-CAM |
|---|---|
| VCC | 5V |
| GND | GND |
| IN | GPIO 13 |

Connect the relay's **COM** and **NO** contacts to the barrier controller's
"open" push-button input (most boom barriers have dry-contact terminals for
this). Never switch mains through a hobby relay board.

GPIO 13 is free as long as no SD card is in use. Don't use GPIO 12: it's a
boot strapping pin and can stop the board from starting. If your relay
triggers on LOW, change `RELAY_ACTIVE` to `LOW` in the sketch.

Test it from a computer on the same network:

```powershell
curl -X POST "http://192.168.1.50/open?ms=2000" -H "X-Gate-Token: change-me"
```

## Connect to the backend

Paste `http://192.168.1.50:81/stream` into **Other source…** in the dashboard's
camera tile, or:

```powershell
curl -X POST localhost:8000/camera/entry/start -H "Content-Type: application/json" -d "{\"source\":\"http://192.168.1.50:81/stream\",\"fps\":2}"
```

Then set `BARRIER_MODE=http` and the `BARRIER_URL_*` variables (see the main
README) so the backend opens the barrier for cars it lets in. If WiFi drops,
the backend reconnects on its own with backoff.

## Mounting

- Point the camera at plate height, 3–5 m from the stop line, and under 30° off-axis.
- Give it a fixed IP or a DHCP reservation so the URL doesn't change.
- At night, add an IR illuminator. Headlights alone wash out plates.
