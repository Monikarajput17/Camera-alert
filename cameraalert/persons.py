"""Optional YOLOv8 person detection. Degrades gracefully if ultralytics is absent."""

from __future__ import annotations


class PersonDetector:
    """Wraps ultralytics YOLO to find people (COCO class 0)."""

    def __init__(self, model="yolov8n.pt", conf=0.40):
        from ultralytics import YOLO  # imported lazily so it's a soft dependency

        self.model = YOLO(model)
        self.conf = conf

    def detect(self, frame) -> list[tuple[int, int, int, int]]:
        """Return a list of (x, y, w, h) person boxes."""
        results = self.model(frame, classes=[0], conf=self.conf, verbose=False)
        boxes = []
        for res in results:
            for b in res.boxes.xyxy.cpu().numpy():
                x1, y1, x2, y2 = (int(v) for v in b[:4])
                boxes.append((x1, y1, x2 - x1, y2 - y1))
        return boxes


def build_person_detector(cfg):
    """Create a PersonDetector if enabled and installable, else return None."""
    if not cfg.get("person_detection.enabled", False):
        return None
    try:
        detector = PersonDetector(
            model=cfg.get("person_detection.model", "yolov8n.pt"),
            conf=cfg.get("person_detection.conf", 0.40),
        )
        print("[persons] YOLO person detection enabled.")
        return detector
    except Exception as exc:  # ImportError, weights download failure, etc.
        print(f"[persons] person detection unavailable ({exc}); "
              "continuing face-only. Install requirements-optional.txt to enable.")
        return None
