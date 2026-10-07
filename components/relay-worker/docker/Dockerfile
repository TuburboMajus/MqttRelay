# syntax=docker/dockerfile:1
#
# MqttRelay — `relay-worker` component image.
#
# Build context is the REPOSITORY ROOT, not this directory — the component's source has
# not been migrated into components/relay-worker/src/ yet (see ARCHITECTURE.md section 7),
# it still lives at the repo root (services/mqtt_transfer/, core/, tools/):
#
#   docker build -f components/relay-worker/docker/Dockerfile -t mqttrelay-worker:local .
#
# Same dependency set as the `dashboard` image today (both import core/ and tools/
# directly); the two images differ only in CMD. No secrets are baked in — config.toml is
# generated from environment variables by docker/generate_config.py, reused as packaging
# shared with `dashboard`, not component source.

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

# Long-running loop (~10s cycle), no inbound port.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["python", "services/mqtt_transfer/mqtt_transfer_sqlalchemy.py", "--root-dir", "/app", "--logging-dir", "/app/logs"]
