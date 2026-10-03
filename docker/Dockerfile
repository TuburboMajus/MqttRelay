# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# MqttRelay — Flask web dashboard image.
#
# Build from the repository root (the build context is the repo root):
#   docker build -f docker/Dockerfile -t mqttrelay:latest .
#
# The image does NOT contain secrets. On startup the entrypoint generates
# /app/config.toml from environment variables (injected from a .env file) if it
# does not already exist — see docker/docker-compose.yml and .env.example.
# ---------------------------------------------------------------------------

FROM python:3.10-slim

# Build tools are only needed in case a dependency has no prebuilt wheel
# (e.g. cryptography / cffi). They are purged right after `pip install`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the application source (config.toml / .env are excluded via .dockerignore).
COPY . .

# Make the entrypoint executable.
RUN chmod +x /app/docker/entrypoint.sh

# Flask dashboard port — must match [app].port in the generated config.toml.
EXPOSE 23909

# The entrypoint generates /app/config.toml from environment variables when it
# is missing, then execs the command below. gunicorn binds to ${APP_PORT:-23909}
# (the same value written into config.toml). A single worker is intentional:
# Flask-MQTT subscribes to the broker from the worker process, and multiple
# workers would each ingest the same messages.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn --workers 1 --bind 0.0.0.0:${APP_PORT:-23909} --timeout 120 'run:build_app()'"]
