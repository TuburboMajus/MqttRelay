#!/usr/bin/env bash
# Stop the whole MqttRelay platform started by docker-compose-start.sh.
# Data (PostgreSQL + parser storage) survives in named volumes; pass -v to also wipe it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.yml" down "$@"
