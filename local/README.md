# local/

Launches/stops the whole MqttRelay platform (`dashboard` + `relay-worker` + the local infra
they need: PostgreSQL and a Mosquitto broker) on one machine, two ways:

| | Start | Stop | Backing files |
|---|---|---|---|
| Docker Compose | `docker-compose-start.sh` | `docker-compose-stop.sh` | `docker-compose.yml`, `mosquitto.conf` |
| Helm (local k8s) | `helm-start.sh` | `helm-stop.sh` | `helm/infra/` (PostgreSQL + Mosquitto chart) + `components/*/helm/` |

Both paths build the two components from their own `components/<name>/docker/Dockerfile`
(build context: the repository root — see `docs/architecture/ARCHITECTURE.md` section 7)
and use fixed, local-only, non-secret credentials (`mqttrelay`/`mqttrelay`,
anonymous-access MQTT). Never reuse these defaults anywhere reachable off your machine.

The Helm charts under `components/*/helm/` are intentionally minimal starting charts (see
`ARCHITECTURE.md` section 8) — `helm-start.sh` is only as capable as they are today.

These scripts are checked in without the executable bit (the environment that produced
them couldn't `chmod`); run them with `bash local/<script>.sh` or `chmod +x` them once
locally.
