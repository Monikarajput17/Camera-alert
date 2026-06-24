"""Generate a self-contained demo for the public cloud deployment.

Produces:
  assets/demo_feed.mp4   a looping video that cycles through several faces
  assets/demo_known.npz  one of those faces enrolled as a known person

The faces are public-domain portraits from Wikimedia Commons (US federal
official portraits are public domain), so they are safe to bundle in a public
repo. They stand in for a real camera feed, which a cloud server can't see.

Run:  python -m tools.make_demo_feed
"""

import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cameraalert.faces import FaceEngine  # noqa: E402

ASSETS = ROOT / "assets"
W, H = 640, 480
SECONDS_PER_FACE = 3
FPS = 12

UA = "CameraAlertDemo/1.0 (https://github.com/Monikarajput17/Camera-alert)"

# Public-domain portraits on Wikimedia Commons (Special:FilePath redirects to
# the file). US presidential official portraits are federal works -> PD.
CANDIDATES = [
    "Official_portrait_of_Barack_Obama.jpg",
    "Joe_Biden_presidential_portrait.jpg",
    "George-W-Bush.jpeg",
    "Bill_Clinton.jpg",
    "Official_Portrait_of_President_Reagan_1981.jpg",
    "JimmyCarterPortrait2.jpg",
    "Gerald_Ford_presidential_portrait_(cropped).jpg",
    "John_F._Kennedy,_White_House_color_photo_portrait.jpg",
]
WANT = 4


def fetch_faces(engine: FaceEngine):
    """Download candidate portraits, letterbox to the demo frame, and keep the
    ones whose face detects at that scale (what the running demo will see)."""
    faces = []
    for name in CANDIDATES:
        if len(faces) >= WANT:
            break
        url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + name
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            data = urllib.request.urlopen(req, timeout=30).read()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                print(f"  ! {name}: not a decodable image")
                continue
            frame = letterbox(img)
            if len(engine.detect(frame)) >= 1:
                faces.append(frame)
                print(f"  + {name} ({len(data)//1024} KB)")
            else:
                print(f"  ! {name}: no detectable face at demo scale")
        except Exception as exc:
            print(f"  ! {name}: {type(exc).__name__} {exc}")
    return faces


def letterbox(img):
    """Fit a face image into the WxH demo frame on a dark background."""
    h, w = img.shape[:2]
    scale = min(W / w, H / h) * 0.9
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (nw, nh))
    canvas = np.full((H, W, 3), 22, dtype=np.uint8)
    y, x = (H - nh) // 2, (W - nw) // 2
    canvas[y:y + nh, x:x + nw] = resized
    return canvas


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    # Slightly relaxed threshold so portraits detect reliably at demo scale.
    engine = FaceEngine(ROOT / "models", detect_score=0.7)

    print("Fetching public-domain portraits from Wikimedia Commons…")
    faces = fetch_faces(engine)
    if len(faces) < 2:
        print("FAILED: need at least 2 faces for a meaningful demo.")
        sys.exit(1)

    # Build a looping video: each face held for SECONDS_PER_FACE.
    out = cv2.VideoWriter(str(ASSETS / "demo_feed.mp4"),
                          cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for frame in faces:
        for _ in range(SECONDS_PER_FACE * FPS):
            out.write(frame)
    out.release()
    print(f"wrote {ASSETS / 'demo_feed.mp4'} ({len(faces)} faces)")

    # Enroll the FIRST face as a known person ("Alex"); the rest stay unknown,
    # so the demo shows one green (recognized) and several red (alarm) faces.
    row = max(engine.detect(faces[0]), key=lambda r: r[2] * r[3])
    engine.known["Alex (demo)"] = [engine.embed(faces[0], row)]
    engine.save_known(ASSETS / "demo_known.npz")
    print(f"enrolled 'Alex (demo)' -> {ASSETS / 'demo_known.npz'}")


if __name__ == "__main__":
    main()
