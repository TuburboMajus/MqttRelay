# MqttRelay — Architecture

Source of truth for the component decomposition of MqttRelay. Written from `README.md`
(the project's own description) at a point where the implementation already exists at the
repository root but had never been formally decomposed. This document records the target
decomposition; it does not itself move any code.

## 1. What the platform does

MqttRelay ingests MQTT messages, persists them, parses them into normalized time-series
metrics with versioned per-client parsers, routes those metrics through configurable rules,
and dispatches them to each client's own destination database. A web dashboard lets
operators manage every part of that pipeline. Full behavioral detail lives in `README.md`;
this document only covers *who does what* and *how the pieces talk to each other*.

## 2. Component decomposition

Two components. The boundary is drawn exactly where the running system already has a
process boundary — not an artificial split:

| Component | Directory | What it is |
|---|---|---|
| `dashboard` | `components/dashboard/` | The Flask process: serves the web UI + REST API, ingests MQTT messages into `mqtt_message` via `flask-mqtt`, and is the single writer for all configuration (clients, devices, topics, parsers, metrics, routes, destinations, users, crypto settings). |
| `relay-worker` | `components/relay-worker/` | The standalone long-running Python loop (`mqtt_transfer_sqlalchemy.py`): polls `mqtt_message`, resolves sender, selects a routing rule, runs the matching parser, persists `extraction`/`parsed_point`, and dispatches to each client's destination(s). |

Both are independently deployable processes today (one is a gunicorn/Flask server, the
other is a standalone script with its own restart policy and a DB-backed job lock against
double-starts), so both get `docker/` and `helm/` — neither is omitted.

No third "backend" or "API" component was introduced: `dashboard` already *is* the backend
for the UI, and splitting ingestion out of it would require moving the MQTT client off the
Flask process it currently lives in, which is an implementation change, not a decomposition
decision. If that split is ever made, it is a new component and this file must be updated
per section 3 of the Architect rules.

## 3. Shared code that is *not* a component

`core/` (`models.py`, `repository.py`, `db.py`, `auth.py`, `crypto.py`, `pagination.py`) and
`tools/` (`crypto_envelopes.py`, `json_conditions.py`) are imported directly by both
`dashboard` and `relay-worker`. They are a shared library, not a component:

- They have no network seam and no independent release — there is nothing to version or
  contract separately from the monorepo they ship in.
- They are not independently deployable: there is no process whose entire job is "run
  `core/`".

They are documented, not decomposed: each component's `docs/README.md` names which shared
modules it depends on. If this library ever grows a seam of its own (e.g. extracted into a
separately-versioned package consumed over a registry), it becomes a component and gets its
own entry here, per section 3 of the Architect rules — do not pre-build that split now.

## 4. External dependencies (not components — we do not own or build these)

| Dependency | Role | Local stand-in |
|---|---|---|
| PostgreSQL | System of record: every config table, `mqtt_message` inbox, and the `extraction`/`parsed_point`/`dispatch` result ledger. Shared by both components — see section 6. | `postgres:16-alpine`, started by `local/` |
| MQTT broker | Source of ingestion; `dashboard` subscribes to `+/+/+`. The platform never ships its own broker. | `eclipse-mosquitto`, started by `local/` (anonymous access, dev only) |
| Per-client destination database (MySQL or PostgreSQL) | One per `client_destination` row; owned by the client, not by this platform. `relay-worker` only ever writes to it through a dispatcher. | none — out of scope for local bring-up; dispatch to a destination that doesn't exist locally will simply show as `failed` in the `dispatch` ledger, which is expected |

## 5. How the two components talk to each other

They never call each other directly — no HTTP, no RPC, no shared memory. The seam between
them is entirely **data at rest**, in two forms, both documented in
`docs/contracts/ingest-to-dispatch-pipeline.md`:

1. **Shared PostgreSQL tables.** `dashboard` writes `mqtt_message` rows (ingestion) and all
   config rows (`routing_rule`, `parser`, `route_deposit`, `client_destination`,
   `metric_catalog`); `relay-worker` reads both on every poll cycle and writes
   `extraction`/`parsed_point`/`dispatch`, which `dashboard`'s `/dashboard/api/critical/*`
   endpoints read back out for the operator-facing KPIs.
2. **Shared filesystem (`db/parsers/`).** `dashboard` writes parser source files through the
   Parsers page; `relay-worker` loads and executes them. This is a second, independent seam
   from the database one — a parser can exist on disk with no `parser` row pointing at it yet,
   and vice versa only briefly during a save.

Because there is no RPC between them, there is no exception to raise across the seam: every
failure mode is a row, not a thrown error (see the contract file for the exact shapes).
This is a deliberate property of the existing system, not a conscious choice made for this
decomposition — it is called out here because it shapes what "the contract" even means for
this pair of components.

## 6. Legacy code — assigned, not orphaned

Per `README.md`'s own "Legacy code" section, these modules are unused by the running
application and cannot be imported with the pinned `requirements.txt`. They are still
assigned to a component so future work on them (most likely: delete) has an owner:

| Legacy path | Assigned to |
|---|---|
| `core/entity/`, `core/join/`, `core/constraints.py` | shared library (section 3) — temod-era replacement for what `core/models.py` + `core/repository.py` now do |
| `front/renderers/users.py` | `dashboard` |
| `services/mqtt_transfer/mqtt_transfer.py`, `services/mqtt_transfer/README.md` | `relay-worker` |
| `install/setup.py`, `install/storages/dbscheme.sql` | `relay-worker`'s install story is shared with `dashboard`'s; assigned to `dashboard` since the installer also writes `dashboard`'s `config.toml` |
| `services/mqtt_transfer/tests/` (targets the legacy worker, cannot run with current deps) | `relay-worker` |

## 7. Source location (current state, not final state)

`components/dashboard/src/` and `components/relay-worker/src/` are intentionally empty
(`.gitkeep` only) as of this document. The real, running source for both components still
lives at the repository root (`run.py`, `blueprints/`, `front/`, `context.py` for
`dashboard`; `services/mqtt_transfer/` for `relay-worker`), predating this decomposition.

Moving that source into the `components/<name>/src/` layout is an implementation change —
import paths, packaging, CI — and is explicitly out of scope for this document (the
Architect records the decomposition; it does not write application code). It is the kind of
work Senior Dev should ticket explicitly against one of the two components above, rather
than something a future Architect run should silently assume has already happened.

## 8. Packaging state: Docker now, Helm deliberately minimal

Each component's `docker/Dockerfile` is real and buildable today, using the repository root
as build context (see section 7 — the source it copies still lives there). `local/`'s
compose file uses them to actually bring the whole platform up locally (`dashboard` +
`relay-worker` + PostgreSQL + a local Mosquitto broker).

Each component's `helm/` chart is intentionally minimal (a Deployment + the env a container
needs to boot, nothing hardened) rather than absent, because both components are
independently deployable and `local/helm-start.sh` needs something real to install so the
whole platform can actually come up locally via Helm too. The *hardened* chart — ConfigMaps,
Secrets by name, liveness/readiness probes, `securityContext`, NetworkPolicies mirroring the
compose topology, resource requests — is the Platform Engineer Agent's job, derived from
each component's Docker packaging at epic close
(`.milkyflow/prompts/platform_engineer/helm_reconciliation.md.j2`). Treat the charts in
`components/*/helm/` as a working starting point for that reconciliation, not as the final
chart.

## 9. Contracts index

| Seam | Contract file |
|---|---|
| `dashboard` ↔ `relay-worker` | `docs/contracts/ingest-to-dispatch-pipeline.md` |

No other cross-component seam exists. External dependencies (section 4) are not
components, so they get no contract file — their interface is whatever PostgreSQL,
MQTT, and the client's own database already guarantee, not something this platform defines.
