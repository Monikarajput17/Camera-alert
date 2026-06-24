"""Smoke test for the detection + recognition engine.

Runnable two ways:
    python -m tests.test_engine        # plain run, prints PASS/FAIL
    pytest tests/test_engine.py        # if pytest is installed

Downloads two standard public CV test faces (Lena, Messi) to a temp cache and
checks: face detection, self-recognition, rejection of a different face, and
the save/load round-trip of the known-face database.
"""

import sys
import tempfile
import urllib.request
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cameraalert.faces import FaceEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(tempfile.gettempdir()) / "camera_alert_test_assets"
FACES = {
    "lena.jpg": "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg",
    "messi5.jpg": "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/messi5.jpg",
}


def _asset(name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / name
    if not dest.exists():
        urllib.request.urlretrieve(FACES[name], dest)
    return dest


def test_detect_recognize_roundtrip():
    engine = FaceEngine(ROOT / "models", detect_score=0.85, match_threshold=0.36)
    lena = cv2.imread(str(_asset("lena.jpg")))
    messi = cv2.imread(str(_asset("messi5.jpg")))

    lena_faces = engine.detect(lena)
    assert len(lena_faces) >= 1, "no face detected in lena"

    row = max(lena_faces, key=lambda r: r[2] * r[3])
    engine.known["Lena"] = [engine.embed(lena, row)]

    name, sim = engine.identify(engine.embed(lena, row))
    assert name == "Lena", f"lena not self-recognized (got {name}, sim={sim:.3f})"

    messi_faces = engine.detect(messi)
    if len(messi_faces) >= 1:
        mrow = max(messi_faces, key=lambda r: r[2] * r[3])
        mname, _ = engine.identify(engine.embed(messi, mrow))
        assert mname is None, f"different face wrongly matched to {mname}"

    out = CACHE / "known.npz"
    engine.save_known(out)
    engine.known = {}
    assert engine.load_known(out) == 1 and "Lena" in engine.known


if __name__ == "__main__":
    try:
        test_detect_recognize_roundtrip()
        print("PASS: engine detect/recognize/roundtrip")
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
