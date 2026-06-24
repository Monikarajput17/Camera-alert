"""Face detection (YuNet) + recognition (SFace), and the known-face database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .models import SFACE_FILE, YUNET_FILE, ensure_model


@dataclass
class FaceResult:
    box: tuple[int, int, int, int]   # x, y, w, h
    score: float                     # detector confidence
    name: str | None                 # matched identity, or None if unknown
    similarity: float                # best cosine similarity to known faces


class FaceEngine:
    """Detects faces, extracts SFace embeddings, and matches against known people."""

    def __init__(self, models_dir, detect_score=0.85, match_threshold=0.36):
        yunet_path = ensure_model(models_dir, YUNET_FILE)
        sface_path = ensure_model(models_dir, SFACE_FILE)

        self.detector = cv2.FaceDetectorYN.create(
            str(yunet_path), "", (320, 320),
            score_threshold=detect_score, nms_threshold=0.3, top_k=5000,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(sface_path), "")
        self.match_threshold = match_threshold

        # name -> list of embedding vectors (one per enrollment photo)
        self.known: dict[str, list[np.ndarray]] = {}

    # ── runtime tuning (used by the web UI) ──────────────────────────────────
    def set_detect_score(self, value: float):
        self.detector.setScoreThreshold(float(value))

    def set_match_threshold(self, value: float):
        self.match_threshold = float(value)

    # ── detection / embedding ────────────────────────────────────────────────
    def detect(self, frame) -> np.ndarray:
        """Return an Nx15 array of face rows (or empty). Cols 0-3 = x,y,w,h."""
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        return faces if faces is not None else np.empty((0, 15), dtype=np.float32)

    def embed(self, frame, face_row) -> np.ndarray:
        """Align the detected face and return its L2-normalizable embedding."""
        aligned = self.recognizer.alignCrop(frame, face_row)
        return self.recognizer.feature(aligned)

    # ── known-face database ──────────────────────────────────────────────────
    def identify(self, embedding) -> tuple[str | None, float]:
        """Return (best_name_or_None, best_similarity) for an embedding."""
        best_name, best_sim = None, -1.0
        for name, vecs in self.known.items():
            for ref in vecs:
                sim = self.recognizer.match(embedding, ref, cv2.FaceRecognizerSF_FR_COSINE)
                if sim > best_sim:
                    best_name, best_sim = name, sim
        if best_sim >= self.match_threshold:
            return best_name, best_sim
        return None, best_sim

    def recognize_frame(self, frame) -> list[FaceResult]:
        """Full pass: detect every face and label each known/unknown."""
        results = []
        for row in self.detect(frame):
            x, y, w, h = (int(v) for v in row[:4])
            score = float(row[-1])
            name, sim = self.identify(self.embed(frame, row)) if self.known else (None, -1.0)
            results.append(FaceResult((x, y, w, h), score, name, sim))
        return results

    # ── persistence ──────────────────────────────────────────────────────────
    def save_known(self, path):
        """Save all enrolled embeddings to a single .npz file."""
        flat, names = [], []
        for name, vecs in self.known.items():
            for v in vecs:
                flat.append(np.asarray(v).ravel())
                names.append(name)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, embeddings=np.array(flat, dtype=np.float32),
                 names=np.array(names))

    def load_known(self, path) -> int:
        """Load enrolled embeddings. Returns the number of people loaded."""
        path = Path(path)
        self.known = {}
        if not path.exists():
            return 0
        data = np.load(path, allow_pickle=True)
        embeddings, names = data["embeddings"], data["names"]
        for vec, name in zip(embeddings, names):
            self.known.setdefault(str(name), []).append(vec.reshape(1, -1))
        return len(self.known)
