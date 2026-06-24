"""Wire camera -> face recognition -> (optional) person detection -> alarm."""

from __future__ import annotations

import cv2

from .alarm import Alarm
from .camera import Camera
from .config import Config
from .faces import FaceEngine
from .persons import build_person_detector

# BGR colours
GREEN = (0, 200, 0)
RED = (0, 0, 255)
YELLOW = (0, 200, 200)


def _draw(frame, faces, persons):
    for f in faces:
        x, y, w, h = f.box
        known = f.name is not None
        color = GREEN if known else RED
        label = f"{f.name} ({f.similarity:.2f})" if known else "UNKNOWN"
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, label, (x, max(0, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    for (x, y, w, h) in persons:
        cv2.rectangle(frame, (x, y), (x + w, y + h), YELLOW, 1)
    return frame


def run(config_path="config.yaml", source_override=None, show=False):
    cfg = Config.load(config_path)
    if source_override is not None:
        cfg.data["camera"]["source"] = source_override

    models_dir = cfg.path(cfg.get("paths.models_dir", "models"))
    engine = FaceEngine(
        models_dir,
        detect_score=cfg.get("faces.detect_score", 0.85),
        match_threshold=cfg.get("faces.match_threshold", 0.36),
    )
    n_people = engine.load_known(cfg.path(cfg.get("paths.encodings_file")))
    print(f"[faces] loaded {n_people} known {'person' if n_people == 1 else 'people'}.")
    if n_people == 0:
        print("[faces] WARNING: no enrolled faces — every face will read as UNKNOWN. "
              "Run enroll.py first.")

    person_detector = build_person_detector(cfg)
    alarm = Alarm(cfg)

    on_unknown = cfg.get("alarm.on_unknown_face", True)
    on_person_no_face = cfg.get("alarm.on_person_no_face", False)
    every_n = max(1, int(cfg.get("camera.process_every_n", 1)))

    cam = Camera(
        source=cfg.get("camera.source", 0),
        width=cfg.get("camera.width"),
        height=cfg.get("camera.height"),
        reconnect=cfg.get("camera.reconnect", True),
        rtsp_transport=cfg.get("camera.rtsp_transport", "tcp"),
    )

    print("[camera] starting. Press 'q' in the window (or Ctrl+C) to stop.")
    frame_idx = 0
    try:
        with cam:
            for frame in cam.frames():
                frame_idx += 1
                run_now = (frame_idx % every_n) == 0

                faces, persons = [], []
                if run_now:
                    faces = engine.recognize_frame(frame)
                    if person_detector is not None:
                        persons = person_detector.detect(frame)

                    unknown_faces = [f for f in faces if f.name is None]
                    if on_unknown and unknown_faces:
                        alarm.trigger(f"{len(unknown_faces)} unrecognized face(s) detected", frame)
                    elif on_person_no_face and persons and not faces:
                        alarm.trigger(f"{len(persons)} person(s) detected, no face visible", frame)

                if show:
                    _draw(frame, faces, persons)
                    cv2.imshow("Camera Alert", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
    except KeyboardInterrupt:
        print("\n[camera] stopped by user.")
    finally:
        if show:
            cv2.destroyAllWindows()
