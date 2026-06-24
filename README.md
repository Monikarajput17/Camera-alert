# Camera Alert

A lightweight home-camera alarm: it watches a camera feed, recognizes known
household members, and raises an alert when it sees an **unrecognized** person.

```
Camera feed → detect faces → recognize → unknown face? → alarm
                           ↘ (optional) detect people with no visible face
```

Built on OpenCV's **YuNet** (face detection) and **SFace** (face recognition) —
small ONNX models that run in real time on a CPU, with no GPU and no C++
compiler required. Optional **YOLOv8** person detection can be enabled to catch
people whose face isn't visible.

It ships two ways to use it:

- **Web dashboard** (recommended) — a browser UI with live video, real-time
  alert feed, click-to-enroll faces, and live tuning. See below.
- **CLI** — `main.py` / `enroll.py` for a headless / scripted setup.

## 1. Install Python

This project needs a real Python install (3.10–3.12 recommended; on Windows the
default `python` command may be a Microsoft Store placeholder).

- Download from https://www.python.org/downloads/ and **check "Add Python to PATH"**
  during setup.
- Verify in a new terminal: `python --version`

## 2. Set up

```powershell
cd "E:\Camera alert"
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # PowerShell  (use activate.bat in cmd.exe)
pip install -r requirements.txt

# Optional — only if you want YOLO person detection:
# pip install -r requirements-optional.txt
```

Download the face models (also happens automatically on first run):

```powershell
python download_models.py
```

## 3. Enroll known faces

Add a folder of photos per person under `known_faces/` (see
`known_faces/README.txt`), then:

```powershell
python enroll.py
```

Or capture from the webcam directly:

```powershell
python enroll.py --capture --name Alice
```

## 4a. Run the web dashboard (recommended)

```powershell
python -m webapp            # then open http://127.0.0.1:8000
```

The dashboard gives you:

- **Live video** with recognition boxes (green = known, red = UNKNOWN).
- **Real-time alert feed** (Server-Sent Events) with clickable snapshot thumbnails.
- **People** — enroll a household member by typing a name and uploading photos;
  remove anyone with one click. Photos with no detectable face are rejected.
- **Settings** — tune match strictness, detect confidence, alarm cooldown, and
  toggle alarm actions (log / snapshot / sound / email) live, no restart.
- **Controls** — Start/Stop and change the camera source on the fly.

Start the camera, then enroll yourself, and a different face will trip an alert.

## 4b. Run the CLI instead

```powershell
python main.py --show            # live preview with boxes
python main.py                   # headless (logs + alarms only)
python main.py --source test.mp4 --show   # test against a video file
```

Green box = recognized person · Red box = **UNKNOWN** (triggers the alarm)
· Yellow box = person detected (YOLO).

Press `q` in the preview window, or `Ctrl+C` in the terminal, to stop.

## Verify the install

```powershell
python -m tests.test_engine      # downloads 2 sample faces, checks the engine
```

## Run it 24/7 (auto-start at logon, Windows)

This app runs on a machine **at home** (it needs to see your camera) — it is not
a cloud/Vercel app. To have it launch automatically and run in the background:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\install-autostart.ps1
```

This drops a hidden shortcut in your Startup folder (no admin needed) that runs
the dashboard with `pythonw.exe` (no console window) at every logon, serving
http://localhost:8000. With `camera.auto_start: true` in `config.yaml`, it also
begins detecting on its own. Remove it any time with:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\uninstall-autostart.ps1
```

To **view the dashboard from your phone or away from home**, keep it running at
home and add a secure tunnel (e.g. [Tailscale](https://tailscale.com) or
Cloudflare Tunnel) rather than exposing port 8000 to the internet.

## Configuration

Everything is in [`config.yaml`](config.yaml):

| Setting | What it does |
|---|---|
| `camera.source` | `0` for webcam, an `rtsp://…` URL, or a file path |
| `faces.match_threshold` | Higher = stricter matching (more "unknown") |
| `person_detection.enabled` | Turn on optional YOLOv8 person detection |
| `alarm.cooldown_seconds` | Minimum gap between alarms (anti-spam) |
| `alarm.methods.*` | Toggle log / snapshot / sound / email |

### Email alerts

Set `alarm.methods.email.enabled: true` and fill in your SMTP details. For
Gmail, create an **App Password** (not your normal password) and use that.

## Project layout

```
config.yaml            # all settings
main.py                # CLI: run the live alarm
enroll.py              # CLI: register known faces
download_models.py     # fetch YuNet + SFace models
cameraalert/           # detection engine (no web deps)
  camera.py            # webcam / RTSP / file input (with reconnect)
  faces.py             # YuNet detect + SFace recognize + known-face DB
  persons.py           # optional YOLOv8 person detection
  alarm.py             # log / snapshot / sound / email triggers
  service.py           # threaded engine the web backend drives
  pipeline.py          # CLI loop
  models.py            # model download helper
  config.py            # config loader with defaults
webapp/                # web dashboard
  server.py            # FastAPI backend (REST + MJPEG + SSE)
  __main__.py          # `python -m webapp` launcher
  static/              # index.html · style.css · app.js (no build step)
tests/
  test_engine.py       # detect / recognize / round-trip smoke test
deploy/
  install-autostart.ps1   # auto-start at logon (Windows, no admin)
  uninstall-autostart.ps1
```

## Notes & tuning

- **False positives:** raise `faces.detect_score` and/or `faces.match_threshold`
  if strangers are wrongly cleared or family is wrongly flagged.
- **CPU load:** raise `camera.process_every_n` to run detection less often.
- **Privacy:** `known_faces.npz` and enrollment photos are biometric data — they
  stay local and are git-ignored. Keep them that way.
- **Lighting/angles:** recognition is best with good light and near-frontal faces.
```
