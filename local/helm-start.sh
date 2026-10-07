#!/usr/bin/env bash
# Start the whole MqttRelay platform locally via Helm: local infra (PostgreSQL + a
# Mosquitto broker, local/helm/infra) + the `dashboard` and `relay-worker` component
# charts (components/<name>/helm), all into one local Kubernetes cluster/namespace.
#
# Charts in components/<name>/helm are intentionally minimal (see ARCHITECTURE.md
# section 8) — this script is only as capable as those charts are today.
#
# Assumes a local cluster is already current-context (kind/minikube/k3d/Docker Desktop).
# Builds and, if a `kind` cluster is detected, loads the two component images into it;
# for other local cluster types, load the images yourself first (e.g.
# `minikube image load mqttrelay-dashboard:local`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NAMESPACE="${MQTTRELAY_NAMESPACE:-mqttrelay-local}"

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

echo "[helm-start] Building component images..."
docker build -f "$REPO_ROOT/components/dashboard/docker/Dockerfile" -t mqttrelay-dashboard:local "$REPO_ROOT"
docker build -f "$REPO_ROOT/components/relay-worker/docker/Dockerfile" -t mqttrelay-worker:local "$REPO_ROOT"

if command -v kind >/dev/null 2>&1 && kind get clusters >/dev/null 2>&1; then
  KIND_CLUSTER="$(kubectl config current-context | sed -e 's/^kind-//')"
  if kind get clusters | grep -qx "$KIND_CLUSTER"; then
    echo "[helm-start] Loading images into kind cluster '$KIND_CLUSTER'..."
    kind load docker-image mqttrelay-dashboard:local mqttrelay-worker:local --name "$KIND_CLUSTER"
  fi
else
  echo "[helm-start] No kind cluster detected — if your cluster can't see the local"
  echo "             Docker image store, load mqttrelay-dashboard:local and"
  echo "             mqttrelay-worker:local into it yourself before continuing."
fi

echo "[helm-start] Installing local infra (PostgreSQL + Mosquitto)..."
helm upgrade --install mqttrelay-infra "$SCRIPT_DIR/helm/infra" -n "$NAMESPACE" --wait

echo "[helm-start] Installing dashboard..."
helm upgrade --install mqttrelay-dashboard "$REPO_ROOT/components/dashboard/helm" -n "$NAMESPACE" --wait

echo "[helm-start] Installing relay-worker..."
helm upgrade --install mqttrelay-worker "$REPO_ROOT/components/relay-worker/helm" -n "$NAMESPACE" --wait

cat <<EOF

MqttRelay is starting in namespace '$NAMESPACE'. Reach the dashboard with:
  kubectl -n $NAMESPACE port-forward svc/mqttrelay-dashboard-dashboard 23909:23909

Stop with: local/helm-stop.sh
EOF
