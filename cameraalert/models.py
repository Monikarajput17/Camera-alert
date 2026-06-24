"""Download (and locate) the small ONNX models YuNet + SFace need."""

from __future__ import annotations

import urllib.request
from pathlib import Path

# OpenCV Zoo model files. Pinned filenames so behaviour is reproducible.
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"

_BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
URLS = {
    YUNET_FILE: f"{_BASE}/face_detection_yunet/{YUNET_FILE}",
    SFACE_FILE: f"{_BASE}/face_recognition_sface/{SFACE_FILE}",
}


def ensure_model(models_dir: Path, filename: str) -> Path:
    """Return the local path to ``filename``, downloading it if missing."""
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    dest = models_dir / filename
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    url = URLS.get(filename)
    if url is None:
        raise ValueError(f"Unknown model file: {filename}")

    print(f"[models] downloading {filename} ...")
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)
    print(f"[models] saved -> {dest}")
    return dest


def ensure_all(models_dir: Path) -> dict[str, Path]:
    return {name: ensure_model(models_dir, name) for name in URLS}
