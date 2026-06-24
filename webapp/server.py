"""FastAPI backend for the Camera Alert dashboard.

Run it with:  python -m webapp   (or: uvicorn webapp.server:app)

Routes
------
GET  /                      dashboard (static SPA)
GET  /api/status            live status JSON
GET  /api/stream            MJPEG video stream
GET  /api/events            Server-Sent Events (alerts + state changes)
POST /api/control/start     start the detection loop
POST /api/control/stop      stop the detection loop
POST /api/control/source    change the camera source {"source": ...}
GET  /api/settings          current tunable settings
POST /api/settings          update tunable settings (partial)
GET  /api/people            enrolled people [{name, samples}]
POST /api/people            enroll/append a person (multipart: name + images)
DELETE /api/people/{name}   remove a person and re-enroll
GET  /api/alerts            recent alerts (in-memory) + snapshot names
GET  /api/snapshots/{name}  serve a saved snapshot image
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from cameraalert.faces import FaceEngine
from cameraalert.service import EngineService

# Which config to load — overridable so the cloud demo can use config.demo.yaml.
CONFIG_PATH = os.environ.get("CAMERA_ALERT_CONFIG", "config.yaml")
STATIC_DIR = Path(__file__).parent / "static"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

service: EngineService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    service = EngineService(CONFIG_PATH)
    if service.cfg.get("camera.auto_start", False):
        service.start()  # appliance mode: begin detecting on launch
    try:
        yield
    finally:
        if service:
            service.shutdown()


app = FastAPI(title="Camera Alert", lifespan=lifespan)


def _svc() -> EngineService:
    if service is None:
        raise HTTPException(503, "service not ready")
    return service


# ── status / control ─────────────────────────────────────────────────────────
@app.get("/api/status")
def get_status():
    return _svc().status()


@app.post("/api/control/start")
def control_start():
    _svc().start()
    return {"ok": True}


@app.post("/api/control/stop")
def control_stop():
    _svc().stop()
    return {"ok": True}


@app.post("/api/control/source")
async def control_source(payload: dict):
    source = payload.get("source")
    if source is None or source == "":
        raise HTTPException(400, "source is required")
    # numeric strings -> webcam index
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    _svc().set_source(source)
    return {"ok": True, "source": source}


# ── settings ─────────────────────────────────────────────────────────────────
@app.get("/api/settings")
def get_settings():
    return _svc().status()["settings"]


@app.post("/api/settings")
async def post_settings(patch: dict):
    _svc().update_settings(patch)
    return _svc().status()["settings"]


# ── video stream (MJPEG) ─────────────────────────────────────────────────────
@app.get("/api/stream")
def stream():
    boundary = "frame"

    def gen():
        while True:
            jpeg = _svc().latest_jpeg()
            if jpeg is not None:
                yield (b"--" + boundary.encode() + b"\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                       + jpeg + b"\r\n")
            time.sleep(0.04)  # ~25 fps cap

    return StreamingResponse(
        gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}")


# ── events (SSE) ─────────────────────────────────────────────────────────────
@app.get("/api/events")
async def events():
    q = _svc().subscribe()

    async def gen():
        try:
            # greet new clients with the current status
            yield _sse({"type": "status", **_svc().status()})
            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 15)
                    yield _sse(item)
                except queue.Empty:
                    yield ": keep-alive\n\n"  # comment frame to hold the connection
        finally:
            _svc().unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ── people / enrollment ──────────────────────────────────────────────────────
def _known_faces_dir() -> Path:
    svc = _svc()
    return svc.cfg.path(svc.cfg.get("paths.known_faces_dir", "known_faces"))


def _list_people() -> list[dict]:
    folder = _known_faces_dir()
    people = []
    if folder.exists():
        for d in sorted(p for p in folder.iterdir() if p.is_dir()):
            samples = [f for f in d.iterdir() if f.suffix.lower() in IMAGE_EXTS]
            people.append({"name": d.name, "samples": len(samples)})
    enrolled = set(_svc().engine.known.keys())
    for p in people:
        p["enrolled"] = p["name"] in enrolled
    return people


def _reenroll() -> int:
    """Rebuild the encodings file from every photo folder, then hot-reload it."""
    svc = _svc()
    engine = FaceEngine(
        svc.cfg.path(svc.cfg.get("paths.models_dir", "models")),
        detect_score=svc.cfg.get("faces.detect_score", 0.85),
        match_threshold=svc.cfg.get("faces.match_threshold", 0.36),
    )
    folder = _known_faces_dir()
    if folder.exists():
        for person_dir in sorted(p for p in folder.iterdir() if p.is_dir()):
            vecs = []
            for img_path in sorted(person_dir.iterdir()):
                if img_path.suffix.lower() not in IMAGE_EXTS:
                    continue
                image = cv2.imread(str(img_path))
                if image is None:
                    continue
                faces = engine.detect(image)
                if len(faces) == 0:
                    continue
                row = max(faces, key=lambda r: r[2] * r[3])
                vecs.append(engine.embed(image, row))
            if vecs:
                engine.known[person_dir.name] = vecs
    engine.save_known(svc.cfg.path(svc.cfg.get("paths.encodings_file")))
    return svc.reload_known()


@app.get("/api/people")
def get_people():
    return _list_people()


@app.post("/api/people")
async def add_person(name: str = Form(...), files: list[UploadFile] = File(...)):
    name = name.strip()
    if not name:
        raise HTTPException(400, "name is required")
    person_dir = _known_faces_dir() / name
    person_dir.mkdir(parents=True, exist_ok=True)

    saved, skipped = 0, []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in IMAGE_EXTS:
            skipped.append(f.filename)
            continue
        dest = person_dir / f"{int(time.time()*1000)}_{saved}{ext}"
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        # Reject photos with no detectable face so the database stays clean.
        img = cv2.imread(str(dest))
        if img is None or len(_svc().engine.detect(img)) == 0:
            dest.unlink(missing_ok=True)
            skipped.append(f.filename)
            continue
        saved += 1

    if saved == 0:
        # Don't leave an empty folder behind when every upload was unusable.
        if not any(person_dir.iterdir()):
            person_dir.rmdir()
        raise HTTPException(400, "no usable face found in the uploaded image(s)")
    n_people = _reenroll()
    return {"ok": True, "name": name, "saved": saved, "skipped": skipped,
            "people_enrolled": n_people}


@app.delete("/api/people/{name}")
def delete_person(name: str):
    person_dir = _known_faces_dir() / name
    if not person_dir.exists():
        raise HTTPException(404, "person not found")
    shutil.rmtree(person_dir)
    _reenroll()
    return {"ok": True, "removed": name}


# ── alerts / snapshots ───────────────────────────────────────────────────────
@app.get("/api/alerts")
def get_alerts():
    return _svc().recent_alerts()


@app.get("/api/snapshots/{name}")
def get_snapshot(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "invalid name")
    svc = _svc()
    snap_dir = svc.cfg.path(svc.cfg.get("alarm.methods.snapshot.dir", "alerts"))
    path = snap_dir / name
    if not path.exists():
        raise HTTPException(404, "snapshot not found")
    return FileResponse(path, media_type="image/jpeg")


# ── static frontend (mounted last so /api/* wins) ────────────────────────────
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
