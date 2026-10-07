# Component: relay-worker

Standalone long-running Python loop that turns ingested MQTT messages into normalized
metrics and dispatches them to each client's destination. See
`docs/architecture/ARCHITECTURE.md` for how this fits with `dashboard`, and
`docs/contracts/ingest-to-dispatch-pipeline.md` for the one seam between them.

## Responsibility

- Polls `mqtt_message` for `processed = false` every ~10s (current source:
  `services/mqtt_transfer/mqtt_transfer_sqlalchemy.py`).
- Resolves sender (topic → device → client), selects the matching `routing_rule`
  (`priority` + the `conditions` DSL from `tools/json_conditions.py`), loads and runs the
  rule's parser from `db/parsers/`.
- Persists `extraction` (always) and `parsed_point` (per metric, on success).
- Dispatches to every `route_deposit` destination via `services/mqtt_transfer/dispatchers/`
  (`mysql.py`, `postgres.py`), decrypting `client_destination.password_enc` with
  `core/crypto.py`, and records every attempt in `dispatch`.
- Holds a DB-backed lock (`job` table) so only one live instance processes at a time; a
  stale `RUNNING` row (no heartbeat) is taken over automatically.

## Current source location

Not yet under `src/` in this directory — see `ARCHITECTURE.md` section 7. The real source
today is at the repository root: `services/mqtt_transfer/mqtt_transfer_sqlalchemy.py`,
`services/mqtt_transfer/dispatchers/`.

## Depends on (shared library, not a component)

`core/db.py`, `core/models.py`, `core/repository.py`, `core/crypto.py`,
`tools/crypto_envelopes.py`, `tools/json_conditions.py`.

## Runtime dependencies

- PostgreSQL (reads `mqtt_message` + every config table; writes the result ledger).
- `db/parsers/` — reads parser source `dashboard` writes; must be the same volume/path
  `dashboard` writes to, not a private copy.
- Each client's own destination database (MySQL or PostgreSQL) — external, see
  `ARCHITECTURE.md` section 4. Not reachable locally by default; dispatch attempts against
  a destination that doesn't exist will show as `failed` in the `dispatch` ledger.
- Does **not** connect to the MQTT broker directly — only `dashboard` does.

## Build & run locally

```bash
docker build -f components/relay-worker/docker/Dockerfile -t mqttrelay-worker:local .
```

Or bring up the whole platform (this component + `dashboard` + PostgreSQL + a local
Mosquitto broker) via `local/docker-compose-start.sh` — see the root `local/` directory.

## Packaging state

`docker/Dockerfile` here is real and buildable. `helm/` is an intentionally minimal starting
chart (single-replica Deployment + the env it needs to boot) — the hardened chart (probes,
`securityContext`, Secrets by name) is the Platform Engineer Agent's job at epic close; see
`ARCHITECTURE.md` section 8. Note a hardened chart must still enforce `replicas: 1` (or a
leader-election sidecar) — the `job`-table lock tolerates a brief overlap during rollout, not
sustained multi-replica operation.
