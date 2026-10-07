# syntax=docker/dockerfile:1
#
# MqttRelay — `dashboard` component image.
#
# Build context is the REPOSITORY ROOT, not this directory — the component's source has
# not been migrated into components/dashboard/src/ yet (see ARCHITECTURE.md section 7), it
# still lives at the repo root (run.py, context.py, blueprints/, front/, core/, tools/):
#
#   docker build -f components/dashboard/docker/Dockerfile -t mqttrelay-dashboard:local .
#
# No secrets are baked in. The entrypoint generates /app/config.toml from environment
# variables on first start if it is not already present — see docker/generate_config.py
# (reused as-is; it is packaging, not component source) and local/docker-compose.yml.

FROM python:3.10-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 23909

# Single worker is intentional: flask-mqtt subscribes to the broker from this process, and
# multiple gunicorn workers would each ingest the same message.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn --workers 1 --bind 0.0.0.0:${APP_PORT:-23909} --timeout 120 'run:build_app()'"]
