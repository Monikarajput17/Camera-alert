"""Threaded detection service that the web backend drives.

Owns the camera loop in a background thread and exposes thread-safe access to:
  * the latest annotated JPEG frame (for MJPEG streaming),
  * a live status snapshot,
  * a fan-out event stream (alarms + state changes) for Server-Sent Events.

Keeping this separate from the FastAPI app means the detection logic has no web
dependencies and the CLI (`pipeline.run`) and web UI share one engine.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque

import cv2
import numpy as np

from .alarm import Alarm
from .camera import Camera
from .config import Config
from .faces import FaceEngine
from .persons import build_person_detector

GREEN = (0, 200, 0)
RED = (0, 0, 255)
YELLOW = (0, 200, 200)
GREY = (60, 60, 60)


def _placeholder(text: str) -> np.ndarray:
    """A 'no signal' frame shown when the camera is stopped or unavailable."""
    img = np.full((480, 640, 3), 18, dtype=np.uint8)
    cv2.putText(img, text, (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2)
    return img


class EngineService:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.cfg = Config.load(config_path)

        models_dir = self.cfg.path(self.cfg.get("paths.models_dir", "models"))
        self.engine = FaceEngine(
            models_dir,
            detect_score=self.cfg.get("faces.detect_score", 0.85),
            match_threshold=self.cfg.get("faces.match_threshold", 0.36),
        )
        self.engine.load_known(self.cfg.path(self.cfg.get("paths.encodings_file")))
        self.person_detector = build_person_detector(self.cfg)
        self.alarm = Alarm(self.cfg)

        # Shared state, guarded by _lock.
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._error: str | None = None
        self._fps = 0.0
        self._faces_in_view = 0
        self._persons_in_view = 0
        self._recent_alerts: deque[dict] = deque(maxlen=50)

        # Event fan-out for SSE subscribers.
        self._subscribers: list[queue.Queue] = []

        self._render_idle()  # show a placeholder until started

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self):
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._error = None
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        self._emit("status", {"running": True})

    def stop(self):
        thread = None
        with self._lock:
            if not self._running:
                return
            self._stop.set()
            thread = self._thread
        if thread:
            thread.join(timeout=5)
        with self._lock:
            self._running = False
            self._thread = None
            self._faces_in_view = 0
            self._persons_in_view = 0
        self._render_idle()
        self._emit("status", {"running": False})

    def shutdown(self):
        self.stop()

    # ── the detection loop (background thread) ───────────────────────────────
    def _loop(self):
        every_n = max(1, int(self.cfg.get("camera.process_every_n", 1)))
        cam = Camera(
            source=self.cfg.get("camera.source", 0),
            width=self.cfg.get("camera.width"),
            height=self.cfg.get("camera.height"),
            reconnect=self.cfg.get("camera.reconnect", True),
            rtsp_transport=self.cfg.get("camera.rtsp_transport", "tcp"),
        )
        if not cam.open():
            with self._lock:
                self._error = f"Could not open camera source: {self.cfg.get('camera.source')!r}"
                self._running = False
            self._render_idle("Camera unavailable")
            self._emit("status", {"running": False, "error": self._error})
            return

        frame_idx = 0
        t_prev = time.monotonic()
        try:
            while not self._stop.is_set():
                ok, frame = cam.cap.read()
                if not ok or frame is None:
                    if not self.cfg.get("camera.reconnect", True):
                        break
                    time.sleep(0.5)
                    cam.release()
                    cam.open()
                    continue

                frame_idx += 1
                self._apply_runtime_settings()

                faces, persons = [], []
                if frame_idx % every_n == 0:
                    faces = self.engine.recognize_frame(frame)
                    if self.person_detector is not None:
                        persons = self.person_detector.detect(frame)
                    self._evaluate_alarm(faces, persons, frame)

                annotated = self._annotate(frame.copy(), faces, persons)
                ok_enc, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])

                now = time.monotonic()
                fps = 1.0 / max(1e-6, now - t_prev)
                t_prev = now
                with self._lock:
                    if ok_enc:
                        self._latest_jpeg = buf.tobytes()
                    self._fps = round(0.8 * self._fps + 0.2 * fps, 1)
                    self._faces_in_view = len(faces)
                    self._persons_in_view = len(persons)
        finally:
            cam.release()

    def _evaluate_alarm(self, faces, persons, frame):
        unknown = [f for f in faces if f.name is None]
        event = None
        if self.cfg.get("alarm.on_unknown_face", True) and unknown:
            event = self.alarm.trigger(f"{len(unknown)} unrecognized face(s) detected", frame)
        elif self.cfg.get("alarm.on_person_no_face", False) and persons and not faces:
            event = self.alarm.trigger(f"{len(persons)} person(s) detected, no face visible", frame)
        if event:
            with self._lock:
                self._recent_alerts.appendleft(event)
            self._emit("alert", event)

    @staticmethod
    def _annotate(frame, faces, persons):
        for (x, y, w, h) in persons:
            cv2.rectangle(frame, (x, y), (x + w, y + h), YELLOW, 1)
        for f in faces:
            x, y, w, h = f.box
            known = f.name is not None
            color = GREEN if known else RED
            label = f"{f.name} {f.similarity:.2f}" if known else "UNKNOWN"
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.rectangle(frame, (x, y - 22), (x + max(70, 9 * len(label)), y), color, -1)
            cv2.putText(frame, label, (x + 4, y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        return frame

    # ── runtime config ───────────────────────────────────────────────────────
    def _apply_runtime_settings(self):
        self.engine.set_detect_score(self.cfg.get("faces.detect_score", 0.85))
        self.engine.set_match_threshold(self.cfg.get("faces.match_threshold", 0.36))
        self.alarm.cooldown = self.cfg.get("alarm.cooldown_seconds", 30)

    def update_settings(self, patch: dict):
        """Apply a partial settings update (thresholds, cooldown, alarm toggles)."""
        merge = {
            "faces": ["detect_score", "match_threshold"],
            "alarm": ["cooldown_seconds", "on_unknown_face", "on_person_no_face"],
        }
        for section, keys in merge.items():
            for key in keys:
                if section in patch and key in patch[section]:
                    self.cfg.data[section][key] = patch[section][key]
        if "methods" in patch.get("alarm", {}):
            for method, vals in patch["alarm"]["methods"].items():
                self.cfg.data["alarm"]["methods"].setdefault(method, {}).update(vals)
        self._emit("status", {"settings_updated": True})

    def set_source(self, source):
        was_running = self._running
        if was_running:
            self.stop()
        self.cfg.data["camera"]["source"] = source
        if was_running:
            self.start()

    def reload_known(self) -> int:
        n = self.engine.load_known(self.cfg.path(self.cfg.get("paths.encodings_file")))
        self._emit("status", {"known_reloaded": n})
        return n

    # ── readers (web layer) ──────────────────────────────────────────────────
    def _render_idle(self, text: str = "Camera stopped"):
        ok, buf = cv2.imencode(".jpg", _placeholder(text))
        if ok:
            with self._lock:
                self._latest_jpeg = buf.tobytes()

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "error": self._error,
                "source": self.cfg.get("camera.source"),
                "fps": self._fps,
                "faces_in_view": self._faces_in_view,
                "persons_in_view": self._persons_in_view,
                "known_people": list(self.engine.known.keys()),
                "person_detection": self.person_detector is not None,
                "cooldown_remaining": round(self.alarm.seconds_until_ready(), 1),
                "settings": {
                    "faces": {
                        "detect_score": self.cfg.get("faces.detect_score"),
                        "match_threshold": self.cfg.get("faces.match_threshold"),
                    },
                    "alarm": {
                        "cooldown_seconds": self.cfg.get("alarm.cooldown_seconds"),
                        "on_unknown_face": self.cfg.get("alarm.on_unknown_face"),
                        "on_person_no_face": self.cfg.get("alarm.on_person_no_face"),
                        "methods": {
                            m: self.cfg.get(f"alarm.methods.{m}.enabled")
                            for m in ("log", "snapshot", "sound", "email")
                        },
                    },
                },
            }

    def recent_alerts(self) -> list[dict]:
        with self._lock:
            return list(self._recent_alerts)

    # ── event fan-out ────────────────────────────────────────────────────────
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _emit(self, event_type: str, data: dict):
        payload = {"type": event_type, **data}
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass
