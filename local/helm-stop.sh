#!/usr/bin/env bash
# Stop the whole MqttRelay platform started by helm-start.sh.
# Pass --purge-namespace to also delete the namespace (and its PVCs/data).
set -euo pipefail

NAMESPACE="${MQTTRELAY_NAMESPACE:-mqttrelay-local}"

helm uninstall mqttrelay-worker -n "$NAMESPACE" || true
helm uninstall mqttrelay-dashboard -n "$NAMESPACE" || true
helm uninstall mqttrelay-infra -n "$NAMESPACE" || true

if [ "${1:-}" = "--purge-namespace" ]; then
  kubectl delete namespace "$NAMESPACE"
fi
