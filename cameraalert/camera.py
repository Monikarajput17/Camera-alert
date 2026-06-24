"""Camera feed input: webcam index, RTSP/IP stream, or a video/image file."""

from __future__ import annotations

import os
import time
from pathlib import Path

import cv2


def _parse_source(source):
    """Accept an int, a numeric string (webcam index), or a path/URL string."""
    if isinstance(source, int):
        return source
    s = str(source)
    return int(s) if s.isdigit() else s


def _is_network_stream(source) -> bool:
    return isinstance(source, str) and source.lower().startswith(
        ("rtsp://", "rtsps://", "http://", "https://", "rtmp://")
    )


class Camera:
    def __init__(self, source, width=None, height=None, reconnect=True,
                 rtsp_transport="tcp"):
        self.source = _parse_source(source)
        self.width = width
        self.height = height
        self.reconnect = reconnect
        self.rtsp_transport = rtsp_transport  # "tcp" (reliable) or "udp" (lower latency)
        self.cap: cv2.VideoCapture | None = None
        # A still image is read once then looped, so callers always get a frame.
        self._is_image = isinstance(self.source, str) and Path(self.source).suffix.lower() in {
            ".jpg", ".jpeg", ".png", ".bmp", ".webp"
        }

    def open(self) -> bool:
        if _is_network_stream(self.source):
            # OpenCV/FFmpeg defaults to UDP, which drops packets and corrupts
            # frames on busy networks. Force the chosen transport (TCP by default)
            # and a short timeout so a dead camera fails fast instead of hanging.
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;{self.rtsp_transport}|stimeout;5000000"
            )
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            # Keep only the newest frame so detection works on live, not stale, video.
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            self.cap = cv2.VideoCapture(self.source)
        if self.width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return self.cap.isOpened()

    def frames(self):
        """Yield frames forever (or until a file ends and reconnect is off)."""
        if not self.open():
            raise RuntimeError(f"Could not open camera source: {self.source!r}")

        if self._is_image:
            ok, frame = self.cap.read()
            while ok:
                yield frame
            return

        while True:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                if not self.reconnect:
                    break
                # Stream dropped — back off and try to reopen.
                self.release()
                time.sleep(2.0)
                if not self.open():
                    time.sleep(3.0)
                continue
            yield frame

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
