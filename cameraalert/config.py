"""Load and access the YAML configuration with sane defaults."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

# Defaults mirror config.yaml so the app still runs if keys are missing.
DEFAULTS = {
    "camera": {
        "source": 0,
        "width": 1280,
        "height": 720,
        "reconnect": True,
        "process_every_n": 1,
        "rtsp_transport": "tcp",
        "auto_start": False,
    },
    "faces": {
        "detect_score": 0.85,
        "match_threshold": 0.36,
    },
    "person_detection": {
        "enabled": False,
        "model": "yolov8n.pt",
        "conf": 0.40,
    },
    "alarm": {
        "cooldown_seconds": 30,
        "on_unknown_face": True,
        "on_person_no_face": False,
        "methods": {
            "log": {"enabled": True, "file": "alerts/alerts.log"},
            "snapshot": {"enabled": True, "dir": "alerts"},
            "sound": {"enabled": True},
            "email": {
                "enabled": False,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "to": "",
                "attach_snapshot": True,
            },
        },
    },
    "paths": {
        "models_dir": "models",
        "known_faces_dir": "known_faces",
        "encodings_file": "known_faces.npz",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into a copy of ``base``."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Thin wrapper around the merged config dict with dotted lookups."""

    def __init__(self, data: dict, root: Path):
        self.data = data
        self.root = root  # project root, used to resolve relative paths

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Config":
        path = Path(path)
        user_cfg = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                user_cfg = yaml.safe_load(fh) or {}
        merged = _deep_merge(DEFAULTS, user_cfg)
        root = path.resolve().parent
        return cls(merged, root)

    def get(self, dotted: str, default=None):
        """Look up ``"alarm.methods.sound.enabled"`` style keys."""
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def path(self, value: str | Path) -> Path:
        """Resolve a config path relative to the project root."""
        p = Path(value)
        return p if p.is_absolute() else self.root / p
