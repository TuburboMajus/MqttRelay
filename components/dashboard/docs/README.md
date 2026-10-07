# Component: dashboard

Flask process serving the web UI + REST API, and the MQTT ingestion point. See
`docs/architecture/ARCHITECTURE.md` for how this fits with `relay-worker`, and
`docs/contracts/ingest-to-dispatch-pipeline.md` for the one seam between them.

## Responsibility

- Serves the operator-facing dashboard (Jinja2 + Bootstrap 5) and its REST endpoints (see
  `README.md` → REST Endpoints) for clients, devices, topics, parsers, metrics, routes,
  destinations, users, and crypto settings.
- Subscribes to the MQTT broker (`+/+/+`) via `flask-mqtt` and writes every message to
  `mqtt_message` with `processed = false`.
- Is the single writer for every configuration table `relay-worker` reads.
- Reads `relay-worker`'s result ledger (`extraction`, `parsed_point`, `dispatch`) to compute
  the KPIs behind `/dashboard/api/critical/*`.
- Writes parser source files under `db/parsers/` from the Parsers page.

## Current source location

Not yet under `src/` in this directory — see `ARCHITECTURE.md` section 7. The real source
today is at the repository root: `run.py`, `context.py`, `blueprints/`, `front/`.

## Depends on (shared library, not a component)

`core/db.py`, `core/models.py`, `core/repository.py`, `core/auth.py`, `core/crypto.py`,
`core/pagination.py`, `tools/crypto_envelopes.py`, `tools/json_conditions.py`.

## Runtime dependencies

- PostgreSQL (all config tables + `mqtt_message` + the result ledger it reads back).
- An MQTT broker (ingestion source).
- `db/parsers/` — a directory it writes to and that `relay-worker` reads from; must be a
  volume shared with `relay-worker`, not local-only storage, in any deployment.

## Build & run locally

```bash
docker build -f components/dashboard/docker/Dockerfile -t mqttrelay-dashboard:local .
```

Or bring up the whole platform (this component + `relay-worker` + PostgreSQL + a local
Mosquitto broker) via `local/docker-compose-start.sh` — see the root `local/` directory.

## Packaging state

`docker/Dockerfile` here is real and buildable. `helm/` is an intentionally minimal starting
chart (Deployment + Service + the env it needs to boot) — the hardened chart (probes,
`securityContext`, NetworkPolicies, Secrets by name) is the Platform Engineer Agent's job at
epic close; see `ARCHITECTURE.md` section 8.
