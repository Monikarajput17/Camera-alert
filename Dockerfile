# Container image for the public cloud demo (Render / Railway / Fly.io).
# NOTE: this runs the bundled demo feed, not a real camera — a cloud server
# cannot see your home camera. For your real camera, run it locally (see README).
FROM python:3.12-slim

# OpenCV needs these shared libraries at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

# App source (models/ is git-ignored, so download them into the image).
COPY . .
RUN python download_models.py

ENV CAMERA_ALERT_CONFIG=config.demo.yaml
EXPOSE 8000

# Cloud hosts inject $PORT; bind 0.0.0.0 so it's reachable.
CMD ["sh", "-c", "uvicorn webapp.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
