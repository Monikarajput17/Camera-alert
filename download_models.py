"""Pre-download the face models (otherwise they download on first run)."""

from cameraalert.config import Config
from cameraalert.models import ensure_all


def main():
    cfg = Config.load("config.yaml")
    paths = ensure_all(cfg.path(cfg.get("paths.models_dir", "models")))
    print("[models] ready:")
    for name, path in paths.items():
        print(f"  - {name}: {path}")


if __name__ == "__main__":
    main()
