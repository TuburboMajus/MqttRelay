#!/usr/bin/env bash
# Start the whole MqttRelay platform locally via docker compose: PostgreSQL + a local
# Mosquitto broker + the `dashboard` and `relay-worker` components, each built from its own
# Dockerfile under components/<name>/docker/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d --build

cat <<'EOF'

MqttRelay is starting locally:
  dashboard : http://localhost:23909  (first start: create an account at /signup — admin)
  mosquitto : localhost:1883
  postgres  : localhost:5432 (db=mqttrelay user=mqttrelay password=mqttrelay)

Stop with: local/docker-compose-stop.sh
EOF
