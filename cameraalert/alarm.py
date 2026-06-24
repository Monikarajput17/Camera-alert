"""Alarm triggers: log to file, save a snapshot, beep, and/or send email."""

from __future__ import annotations

import platform
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import cv2


class Alarm:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cooldown = cfg.get("alarm.cooldown_seconds", 30)
        self._last_fire = 0.0

    def _ready(self) -> bool:
        """Debounce so a lingering intruder doesn't spam alerts every frame."""
        return (time.monotonic() - self._last_fire) >= self.cooldown

    def seconds_until_ready(self) -> float:
        """How long until the cooldown allows the next alarm (0 if ready)."""
        return max(0.0, self.cooldown - (time.monotonic() - self._last_fire))

    def trigger(self, reason: str, frame=None) -> dict | None:
        """Fire all enabled alarm methods, respecting the cooldown.

        Returns an event dict when it actually fired, else None (cooling down).
        """
        if not self._ready():
            return None
        self._last_fire = time.monotonic()

        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"[{stamp}] ALERT: {reason}"
        print(message)

        snapshot_path = None
        if frame is not None and self.cfg.get("alarm.methods.snapshot.enabled", False):
            snapshot_path = self._save_snapshot(frame)

        if self.cfg.get("alarm.methods.log.enabled", False):
            self._log(message, snapshot_path)
        if self.cfg.get("alarm.methods.sound.enabled", False):
            self._beep()
        if self.cfg.get("alarm.methods.email.enabled", False):
            self._email(message, snapshot_path)

        return {
            "time": stamp,
            "reason": reason,
            "snapshot": Path(snapshot_path).name if snapshot_path else None,
        }

    # ── individual methods ───────────────────────────────────────────────────
    def _save_snapshot(self, frame) -> Path | None:
        out_dir = self.cfg.path(self.cfg.get("alarm.methods.snapshot.dir", "alerts"))
        out_dir.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("alert_%Y%m%d_%H%M%S.jpg")
        path = out_dir / name
        cv2.imwrite(str(path), frame)
        return path

    def _log(self, message, snapshot_path):
        log_path = self.cfg.path(self.cfg.get("alarm.methods.log.file", "alerts/alerts.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = message + (f"  (snapshot: {snapshot_path})" if snapshot_path else "")
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _beep(self):
        if platform.system() == "Windows":
            try:
                import winsound
                winsound.Beep(880, 600)
                return
            except Exception:
                pass
        print("\a", end="", flush=True)  # terminal bell fallback

    def _email(self, message, snapshot_path):
        m = "alarm.methods.email."
        try:
            msg = EmailMessage()
            msg["Subject"] = "Camera Alert: unrecognized person"
            msg["From"] = self.cfg.get(m + "username")
            msg["To"] = self.cfg.get(m + "to")
            msg.set_content(message)

            if snapshot_path and self.cfg.get(m + "attach_snapshot", True):
                data = Path(snapshot_path).read_bytes()
                msg.add_attachment(data, maintype="image", subtype="jpeg",
                                   filename=Path(snapshot_path).name)

            with smtplib.SMTP(self.cfg.get(m + "smtp_host"),
                              self.cfg.get(m + "smtp_port", 587), timeout=20) as smtp:
                smtp.starttls()
                smtp.login(self.cfg.get(m + "username"), self.cfg.get(m + "password"))
                smtp.send_message(msg)
        except Exception as exc:
            print(f"[alarm] email failed: {exc}")
