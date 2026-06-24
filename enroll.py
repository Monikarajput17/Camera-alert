"""Enroll known household members into the face database.

Two ways to add people:

1) From photos (recommended). Make folders and drop in a few clear photos:

       known_faces/
         Alice/   alice1.jpg  alice2.jpg
         Bob/     bob1.png

   Then run:   python enroll.py

2) From the webcam, capturing on the spot:

       python enroll.py --capture --name Alice

Both write embeddings to the file named in config.yaml (known_faces.npz).
Re-run any time you add or change photos.
"""

import argparse
from pathlib import Path

import cv2

from cameraalert.config import Config
from cameraalert.faces import FaceEngine

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _largest_face(engine: FaceEngine, image):
    """Return the biggest detected face row in an image, or None."""
    faces = engine.detect(image)
    if len(faces) == 0:
        return None
    return max(faces, key=lambda r: r[2] * r[3])  # w * h


def enroll_from_folders(engine: FaceEngine, folder: Path) -> int:
    added = 0
    if not folder.exists():
        print(f"[enroll] folder not found: {folder} — create it and add photos.")
        return 0

    for person_dir in sorted(p for p in folder.iterdir() if p.is_dir()):
        name = person_dir.name
        vecs = []
        for img_path in sorted(person_dir.iterdir()):
            if img_path.suffix.lower() not in IMAGE_EXTS:
                continue
            image = cv2.imread(str(img_path))
            if image is None:
                print(f"  ! could not read {img_path.name}")
                continue
            row = _largest_face(engine, image)
            if row is None:
                print(f"  ! no face found in {img_path.name}")
                continue
            vecs.append(engine.embed(image, row))
            print(f"  + {name}: {img_path.name}")
        if vecs:
            engine.known.setdefault(name, []).extend(vecs)
            added += 1
    return added


def enroll_from_webcam(engine: FaceEngine, name: str, source) -> int:
    cap = cv2.VideoCapture(int(source) if str(source).isdigit() else source)
    if not cap.isOpened():
        print(f"[enroll] could not open camera {source}")
        return 0
    print("[enroll] press SPACE to capture a sample, 'q' when done.")
    captured = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        preview = frame.copy()
        row = _largest_face(engine, frame)
        if row is not None:
            x, y, w, h = (int(v) for v in row[:4])
            cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 200, 0), 2)
        cv2.putText(preview, f"{name}: {captured} captured  [SPACE]=save [q]=quit",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)
        cv2.imshow("Enroll", preview)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" ") and row is not None:
            engine.known.setdefault(name, []).append(engine.embed(frame, row))
            captured += 1
            print(f"  + captured sample {captured}")
        elif key == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    return 1 if captured else 0


def main():
    parser = argparse.ArgumentParser(description="Enroll known faces.")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--capture", action="store_true", help="capture from webcam instead of folders")
    parser.add_argument("--name", help="person name (required with --capture)")
    parser.add_argument("--source", default=0, help="camera source for --capture")
    parser.add_argument("--append", action="store_true",
                        help="add to the existing database instead of rebuilding it")
    args = parser.parse_args()

    cfg = Config.load(args.config)
    engine = FaceEngine(
        cfg.path(cfg.get("paths.models_dir", "models")),
        detect_score=cfg.get("faces.detect_score", 0.85),
        match_threshold=cfg.get("faces.match_threshold", 0.36),
    )

    enc_path = cfg.path(cfg.get("paths.encodings_file"))
    if args.append:
        engine.load_known(enc_path)

    if args.capture:
        if not args.name:
            parser.error("--capture requires --name")
        enroll_from_webcam(engine, args.name, args.source)
    else:
        folder = cfg.path(cfg.get("paths.known_faces_dir", "known_faces"))
        enroll_from_folders(engine, folder)

    total_people = len(engine.known)
    total_samples = sum(len(v) for v in engine.known.values())
    engine.save_known(enc_path)
    print(f"[enroll] saved {total_samples} sample(s) for {total_people} "
          f"{'person' if total_people == 1 else 'people'} -> {enc_path}")


if __name__ == "__main__":
    main()
