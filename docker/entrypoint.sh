#!/bin/sh
set -e

CONFIG_FILE="/app/config.toml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "[entrypoint] ${CONFIG_FILE} not found — generating from environment variables..."
    python /app/docker/generate_config.py
fi

exec "$@"
