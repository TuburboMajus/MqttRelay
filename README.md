# MqttRelay — MQTT Ingest, Parse & Route with a Web Dashboard

MqttRelay is a multi-tenant **IoT data ingestion and distribution platform**. It connects to an
MQTT broker, persists every incoming message, turns raw payloads into **normalized time-series
metrics** through versioned, per-client **parsers**, and routes those metrics toward each
client's downstream sink according to configurable routing rules. A **web dashboard** lets
operators manage the whole pipeline — clients, devices, topics, parsers, metrics, routes,
destinations, users and encryption — and monitor activity.

> **Migration note** — MqttRelay recently migrated from the `temod` ORM + MySQL to
> **SQLAlchemy 2.0 + PostgreSQL**. The web dashboard and the background worker run entirely on
> the new stack. Some legacy temod-based modules are still present in the tree (see
> [Legacy code](#legacy-code-pre-migration)) but are **not** used by the running application and
> cannot even be imported with the pinned `requirements.txt`. See `MIGRATION_STATUS.md` and
> `POSTGRES_MIGRATION_GUIDE.md` for the full migration history.

```
MQTT broker ──► Flask-MQTT ──► mqtt_message (raw, processed = false)
                                     │
        background worker: mqtt_transfer_sqlalchemy.py (loop, every ~10s)
                                     ▼
              resolve sender: topic → device → client
                                     ▼
              select routing_rule (priority + conditions DSL)
                                     ▼
              run parser: db/parsers/<name>_<version>.py
                                     ▼
              extraction + parsed_point (normalized)
                                     ▼
              route_deposit → client_destination → dispatcher (mysql/postgres)
                                     ▼
                       client's own database (dispatch ledger kept)
```

---

## Table of Contents

- [What it does](#what-it-does)
- [Project layout](#project-layout)
- [Tech stack](#tech-stack)
- [Data flow (end to end)](#data-flow-end-to-end)
- [Data model](#data-model)
- [Authoring parsers](#authoring-parsers)
- [Routing rules & condition DSL](#routing-rules--condition-dsl)
- [Security & Encryption](#security--encryption-reversible)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [Migrating from the MySQL/temod version](#migrating-from-the-mysqltemod-version)
- [Tests](#tests)
- [Dashboard](#dashboard)
- [REST Endpoints](#rest-endpoints)
- [Legacy code (pre-migration)](#legacy-code-pre-migration)
- [Known issues / rough edges](#known-issues--rough-edges)
- [License](#license)

---

## What it does

- **MQTT ingestion** — subscribes to the broker (wildcard pattern `+/+/+`) and stores every raw
  message in the `mqtt_message` table.
- **Parsing** — a background worker runs a versioned parser against each unprocessed message and
  writes normalized points to `parsed_point`, keyed to a shared `metric_catalog`.
- **Routing** — routing rules map (client, topic, device) to a parser and a list of
  destinations, with optional content-based conditions and priorities.
- **Dispatching** — parsed points are delivered to each client's own `client_destination`
  (**MySQL** and **PostgreSQL** sinks via `services/mqtt_transfer/dispatchers/`), with every
  attempt recorded in the `dispatch` ledger.
- **Web dashboard** — Flask + Jinja2 + Bootstrap 5 UI to manage everything (fully wired
  languages: EN/FR; see Known issues for ES/AR status).
- **Secrets protection** — reversible encryption for third-party service credentials
  (e.g. destination DB passwords), with key rotation and re-encryption.

---

## Project layout

```
.
├── run.py                        # Flask app factory + dev entrypoint
├── context.py                    # init_context(): DB init, registers models/repos as globals;
│                                 #   PARSERS_DB (DirectoryStorage for parser files)
├── config.toml / .template       # Runtime config (DB, MQTT, Flask) / template used by installer
├── dictionnary.yml               # UI strings per language
├── requirements.txt
├── run.sh                        # gunicorn launcher for the dashboard
├── pytest.ini                    # Test collection config (services/mqtt_transfer/tests)
├── core/
│   ├── db.py                     # SQLAlchemy engine/session management (init_db, get_session)
│   ├── models.py                 # SQLAlchemy declarative models (all tables)
│   ├── repository.py             # Generic Repository layer + `repos` registry
│   ├── auth.py                   # Password hashing (bcrypt) + user lookup helpers
│   ├── crypto.py                 # Encrypt/decrypt helpers over crypto_config
│   ├── pagination.py             # List pagination helpers for the UI
│   ├── entity/, join/,           # LEGACY temod modules — unused by the running app
│   └── constraints.py            #   (see "Legacy code" below)
├── blueprints/                   # Flask blueprints (one per domain)
│   ├── auth.py  clients.py  dashboard.py  destinations.py  devices.py
│   ├── general.py  metrics.py  mqtt.py  parsers.py  routes.py  topics.py  users.py
│   └── dashboards/               # Metric computations behind dashboard API endpoints
├── services/mqtt_transfer/       # The background ingest→parse(→dispatch) job
│   ├── mqtt_transfer_sqlalchemy.py  # CURRENT worker (SQLAlchemy, continuous loop, job lock)
│   ├── mqtt_transfer.py          # LEGACY worker (temod/MySQL — cannot run with current deps)
│   ├── dispatchers/              # Output sinks (mysql.py, postgres.py)
│   ├── mqtt_transfer.{service,sh}   # systemd unit (long-running) + launcher; timer obsolete
│   ├── tests/                    # Pytest suite (targets the legacy worker)
│   └── README.md                 # Detailed worker docs (partially outdated, pre-migration)
├── db/parsers/                   # Parser source modules (DirectoryStorage; git-ignored)
├── tools/
│   ├── crypto_envelopes.py       # AES-GCM / ChaCha20-Poly1305 / AES-CBC+HMAC
│   └── json_conditions.py        # MongoDB-style condition DSL evaluator
├── front/
│   ├── renderers/                # Template rendering helpers (BaseTemplate)
│   └── templates/                # Per-language Jinja2 templates (en/, es/, fr/, common/)
├── docker/
│   ├── Dockerfile                # Web dashboard image
│   ├── docker-compose.yml        # Web app (expects an external PostgreSQL)
│   ├── docker-compose.dev.yml    # Dev stack: PostgreSQL 16 + web app, schema auto-applied
│   ├── entrypoint.sh             # Generates /app/config.toml from env vars on first start
│   ├── generate_config.py        # The env-var → config.toml generator
│   ├── .env.example              # All supported environment variables
│   └── migrate_mysql_to_postgres.py  # One-shot MySQL → PostgreSQL data migration
├── install/
│   ├── setup_sqlalchemy.py       # CURRENT interactive installer (PostgreSQL-first)
│   ├── setup.py                  # LEGACY installer (temod/MySQL — cannot run, kept for reference)
│   └── storages/
│       ├── dbscheme_postgresql.sql   # CURRENT full PostgreSQL schema + seed data
│       └── dbscheme.sql              # LEGACY MySQL schema
└── logs/                         # Rotating logs (MqttTransfer.log*; git-ignored)
```

---

## Tech stack

| Concern | Choice |
| --- | --- |
| Web framework | Flask 3 (+ `flask_mqtt`, `flask_login`) |
| ORM / persistence | SQLAlchemy 2.0 (`core/models.py`) + a generic repository layer (`core/repository.py`, `repos` registry) |
| Database | PostgreSQL (`psycopg2-binary`); MySQL selectable in the installer but deprecated |
| Realtime ingestion | `flask-mqtt` (broker subscribe, `on_message` hook) |
| Background job | Standalone Python worker (`mqtt_transfer_sqlalchemy.py`), continuous loop with a ~10 s sleep |
| Crypto | `cryptography` (AES-GCM, ChaCha20-Poly1305, AES-CBC+HMAC); `bcrypt` for login passwords |
| Frontend | Jinja2 + Bootstrap 5 + Bootstrap Icons + fetch API |
| i18n | `dictionnary.yml` + per-language template folders |
| Server | `gunicorn` (via `run.sh`) or Flask dev server (`run.py`) |
| Containers | Docker + docker-compose (`docker/`) |
| Tests | `pytest` (`services/mqtt_transfer/tests/`) |

> Django is listed in `requirements.txt` but is used **only** for the
> `url_has_allowed_host_and_scheme` / `iri_to_uri` utilities in `blueprints/auth.py`.

---

## Data flow (end to end)

1. **Ingest** — `blueprints/mqtt.py` registers `on_connect` (subscribes to `+/+/+`) and
   `on_message`. Each MQTT message is written to `mqtt_message` with
   `client` (first topic segment), `topic`, `payload`, `qos`, `at`, and `processed=False`.
2. **Poll** — `services/mqtt_transfer/mqtt_transfer_sqlalchemy.py` runs as a standalone
   long-lived process: every ~10 s it lists all `mqtt_message` rows with `processed=False`.
3. **Resolve sender** — `retrieve_sender()` looks up the `mqtt_topic` (must be `active`), then
   the `device` and its `client`.
4. **Select route** — `select_route()` collects `routing_rule`s matching the client/topic/device,
   evaluates the optional Mongo-style `conditions` DSL (see below), then picks the lowest
   `priority`, breaking ties by newest `created_at`.
5. **Parse** — the rule's `parser` is loaded (`db/parsers/<name>_<version>`), and its
   `parse(payload, **parser_config)` is executed. The result is a dict keyed by **metric catalog
   IDs** (integer keys) plus an optional `at` timestamp; non-integer keys become `meta_json`.
6. **Persist** — one `extraction` row is written per message, plus one `parsed_point` per metric
   (typed as `num/str/bool/json` with a `unit` and `quality`).
7. **Ack** — the `mqtt_message` row is marked `processed`. This happens **even when
   processing fails** (to avoid reprocessing loops); every failure is recorded as an
   `extraction` row (`success=false`, `error_text`) pointing back to the message.
8. **Dispatch** — for each `route_deposit` of the rule, the corresponding
   `client_destination` is loaded, its dispatcher instantiated (keyed by `destination.type`:
   `mysql`, `postgres`), `password_enc` is decrypted with the crypto envelope, and the points
   are delivered. A `dispatch` row records each attempt (`queued/sent/failed`). Dispatch
   failures do **not** unmark the message (points are already persisted); they stay visible
   in the ledger.

---

## Data model

Defined as SQLAlchemy models in `core/models.py` and instantiated by
`install/storages/dbscheme_postgresql.sql` (which also seeds languages, privileges, the default
crypto config and the `MqttTransfer` job row).

| Domain | Tables |
| --- | --- |
| App | `mqtt_relay`, `language`, `job` |
| Users | `privilege`, `user` (password is **bcrypt**) |
| Tenants | `client`, `client_destination` |
| Devices | `device_type`, `device` |
| MQTT | `mqtt_topic`, `mqtt_broker`, `mqtt_message` |
| Parsing | `parser`, `extraction`, `metric_catalog`, `parsed_point` |
| Routing | `routing_rule`, `route_deposit`, `dispatch` |
| Crypto | `crypto_config`, `crypto_key` |

Data access goes through the generic `Repository` layer: `repos['Client'].get(id=...)`,
`repos['MqttMessage'].list(processed=False)`, etc. `context.init_context()` also attaches each
repository as `<Model>.storage` and registers the models as builtins for the blueprints.

---

## Authoring parsers

A parser is a row in `parser` (`name`, `version`, `language`, optional `config_schema`) whose
**code lives in `db/parsers/`** as a file named:

```
<name lowercase, spaces → _>_<version, dots → _>
```

For example, parser `LSE01 Soil` v`1.0.0` maps to `db/parsers/lse01_soil_1_0_0.py`.
The dashboard writes both `lse01_soil_1_0_0` (source kept by `DirectoryStorage`) and
`lse01_soil_1_0_0.py` (importable Python module).

The module must export a single function:

```python
def parse(data, **config):
    """
    data    : decoded payload (dict) of the MQTT message
    config  : route.parser_config (JSON object)
    returns : dict {<metric_catalog_id>: <value>, ...}  # integer keys = metrics
              optional "at" key overrides the point timestamp
              non-integer keys are stored in meta_json
    """
    return {
        1: data.get("Temp_SOIL"),      # 1 = metric_catalog id (e.g. soil temperature)
        2: data.get("Water_SOIL"),
    }
```

The only supported language today is `python` (`load_parse_function` raises otherwise).

See `db/parsers/lse01_parser_1_0_0.py` for a minimal real example (note: `db/` is git-ignored,
so this file only exists on machines where it was created through the dashboard).

---

## Routing rules & condition DSL

A `routing_rule` targets a `client`, optionally a `topic` and/or `device`, a `parser`, a
`parser_config`, a numeric `priority` (lower wins) and an optional `conditions` JSON. It is linked
to one or more `client_destination`s through `route_deposit`.

`conditions` is evaluated by `tools/json_conditions.py` against this context:

```json
{
  "device":       { ...device row... },
  "device_type":  { ...device_type row... },
  "topic":        { ...mqtt_topic row... },
  "message":      { ...mqtt_message row... }
}
```

Supported operators (MongoDB-style): `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`,
`$exists`, `$regex`, `$contains`, `$startswith`, `$endswith`, `$between`, `$elemMatch`, plus
`$and`, `$or`, `$not` and shorthand equality (`{"field": value}`). Dotted paths
(`device.metadata.foo`) are supported.

---

## Security & Encryption (reversible)

Used **only** for *external* credentials (destination DBs/services) — **never** for user login
passwords, which remain **bcrypt** (`core/auth.py`).

- Algorithms (configured in Settings → System → Secrets & Encryption):
  - **AES-256-GCM** (recommended, installer default)
  - **ChaCha20-Poly1305**
  - **AES-256-CBC + HMAC-SHA256** (encrypt-then-MAC, HKDF-derived subkeys)
- Key sources: `env` (recommended), `db`, or `kms`. Keys are 32 bytes; for `key_source=env`
  they live **outside** the DB:
  - `MQTT_RELAY_ENC_KEY_<KEY_ID>` (e.g. `MQTT_RELAY_ENC_KEY_PRIMARY`)
- Token format: `v1.<algorithm>.<base64 parts…>`
- Rotation: bump config version, replace the key, then **Re-encrypt** existing rows from the
  Settings page (`crypto_config`, `crypto_key` and the `/crypto*` endpoints).
- Implementation: `tools/crypto_envelopes.py`, wrapped by `core/crypto.py` and the
  `CryptoConfig` / `CryptoKey` models.

---

## Installation

### Option A — Docker (recommended for a quick start)

The dev compose file brings up **PostgreSQL 16 + the dashboard**, applies the schema and seed
data automatically, and generates `config.toml` inside the container from environment variables:

```bash
cd docker
cp .env.example .env         # fill in MQTT broker, secrets, etc.
docker compose -f docker-compose.dev.yml up -d --build
# first start only: create your first account on /signup — it gets admin
```

For a deployment against an **existing** PostgreSQL server, use `docker/docker-compose.yml`
from the repository root instead:

```bash
cp docker/.env.example .env  # set DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
docker compose --project-directory . -f docker/docker-compose.yml up -d --build
```

See the comments in both compose files for the optional worker container and host-gateway
database access. All supported variables are documented in `docker/.env.example`.

### Option B — Bare metal

1. **Prerequisites**
   - Python 3.10+
   - PostgreSQL (tested with 16; MySQL is selectable in the installer but deprecated)
   - `venv`
   - Build tooling for native wheels in `requirements.txt`

2. **Create the database**
   ```bash
   sudo -u postgres psql
   CREATE DATABASE mqttrelay;
   CREATE USER mqttrelay WITH PASSWORD 'your-strong-password';
   GRANT ALL PRIVILEGES ON DATABASE mqttrelay TO mqttrelay;
   ```
   Then either let the installer create the tables (next step), or apply the full schema + seed
   data manually:
   ```bash
   psql -U mqttrelay -d mqttrelay -f install/storages/dbscheme_postgresql.sql
   ```

3. **Clone and bootstrap**
   ```bash
   git clone https://github.com/TuburboMajus/MqttRelay.git
   cd MqttRelay
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Run the installer**
   ```bash
   venv/bin/python install/setup_sqlalchemy.py
   ```
   The installer prompts for, and then applies:
   - **PostgreSQL** connection info (creates all tables via SQLAlchemy),
   - an **admin user** (email + password),
   - the **crypto key source** (`env`/`kms`/`db`, `env` recommended) and master key,
   - and writes `config.toml` (from `config.toml.template`) and, for `key_source=env`, a
     `.env` file containing `MQTT_RELAY_ENC_KEY_PRIMARY`.

   > ⚠️ Do **not** use `install/setup.py` — that is the legacy temod/MySQL installer and its
   > dependencies are no longer installed.

5. **Run the background worker** — see [Running](#running). The bundled systemd unit files
   still reference the legacy worker and need editing before use (see Known issues).

---

## Configuration

`config.toml` (generated from `config.toml.template` by the installer, or from environment
variables by `docker/generate_config.py`) has these sections:

```toml
[app]
prod = true                    # run.sh: false → Flask dev server, true → gunicorn
host = "0.0.0.0"
port = 23909
threaded = true
debug = true
log_level = "INFO"             # Flask app logger level
ssl = false                    # serve HTTPS directly if true
ssl_key = "resources/key.pem"
ssl_cert = "resources/cert.pem"
ssl_encapsulated = false       # true when behind a reverse proxy
templates_folder = "front/templates"
static_folder = "front/static"
secret_key = ""                # empty → generated at launch
default_language = "fr"        # optional; falls back to "en"

[mqtt]
broker_url = "localhost"
broker_port = 1883
username = ""
password = ""
keepalive = 60
tls_enabled = false

[temod]                        # vestigial (pre-migration); kept for compatibility, unused
bound_database = "mysql"
core_directory = "core"

[storage.credentials]          # interpreted as PostgreSQL credentials
host = "127.0.0.1"
port = 5432
database = "mqttrelay"
user = "..."
password = "..."
```

Alternatively, a top-level `database_url = "postgresql://user:pass@host:port/db"` key overrides
`[storage.credentials]` entirely (see `context.init_context`).

> ⚠️ `config.toml.template` still contains pre-migration defaults (`port = 3306` under
> `[storage.credentials]`). Since those credentials are now used to build a **PostgreSQL**
> connection string, make sure the port is your PostgreSQL port (usually 5432) after
> installation.

> `config.toml` and `.env` contain secrets and must **never** be committed. The installer
> generates them locally (both are git-ignored).

---

## Running

- **Web dashboard** (production, via gunicorn):
  ```bash
  source venv/bin/activate
  ./run.sh                 # reads app.prod/port/ssl from config.toml
  ```
  For development you can also run `python run.py` directly (Flask dev server).

- **Background ingest→parse worker** (current, SQLAlchemy):
  ```bash
  venv/bin/python services/mqtt_transfer/mqtt_transfer_sqlalchemy.py \
      --root-dir . --logging-dir logs
  ```
  This is a **long-running process** (it loops every ~10 s, with a `job`-table lock against
  double-starts); run it under your process supervisor of choice. The bundled
  `mqtt_transfer.service` (simple, `Restart=on-failure`) and `mqtt_transfer.sh` launch it;
  `mqtt_transfer.timer` is obsolete and no longer needed.

---

## Migrating from the MySQL/temod version

If you have data in a pre-migration MySQL instance, `docker/migrate_mysql_to_postgres.py`
copies it into PostgreSQL. The overall procedure (backup, schema creation, data copy,
verification) is documented step by step in `POSTGRES_MIGRATION_GUIDE.md`, with current
progress tracked in `MIGRATION_STATUS.md`.

---

## Tests

```bash
pytest          # collection is limited to services/mqtt_transfer/tests (see pytest.ini)
```

> ⚠️ The test suite currently targets the **legacy** worker
> (`services/mqtt_transfer/mqtt_transfer.py`) and imports `core.entity` / the temod-based
> dispatchers, so it does not run against the pinned `requirements.txt`. It needs to be ported
> to `mqtt_transfer_sqlalchemy.py` alongside the dispatch stage.

---

## Dashboard

The dashboard is split across the following pages (all behind login):

- **Dashboard** — operational KPIs exposed as JSON endpoints:
  `ingest_rate`, `parse_success`, `dispatch_success`, `processing_backlog`,
  `throughput_series`, `dispatch_series` (computed in `blueprints/dashboards/`).
- **Clients** — list/create/view/edit/delete clients; per client: devices, destinations and
  simple availability stats.
- **Devices** — manage **device types** (`vendor`, `model`, `kind`, `capabilities`,
  `payload_schema`, `defaults_json`). Individual devices are managed from their client page.
- **Topics** — declare/link MQTT topics (`topic`, `description`, `qos_default`, `active`,
  `client_id`, `device_id`) and list unlinked topics.
- **Parsers** — versioned parser registry; view/edit the parser source code (stored in
  `db/parsers/`).
- **Metrics** — the shared `metric_catalog` (`key_name`, `default_unit`, `description`).
- **Routes** — routing rules: client/topic/device, parser + parser config, priority,
  conditions DSL, and linked destinations (via `route_deposit`).
- **Destinations** — per-client sinks (`type`, host/port/database/credentials, `options_json`).
- **Users** — user management.
- **Settings** — profile (email, language) + password change; and **System**:
  - Metric Catalog add/delete
  - **Secrets & Encryption**: choose algorithm/key source/key id, test, rotate, re-encrypt.

---

## REST Endpoints

> Blueprint endpoint names (function names) referenced by templates/scripts.

- **Auth**: `GET/POST /login`, `GET/POST /signup`, `GET/POST /logout`
- **Clients**: `GET /clients`, `GET/POST /client`, `GET/PUT/DELETE /client/<id>`,
  `POST /client/<id>/device`, `PUT/DELETE /client/<id>/device/<device_id>`,
  `POST /client/<id>/destination`, `PUT/DELETE /client/<id>/destination/<destination_id>`
- **Devices (device types)**: `GET /devices`, `GET/POST /device`, `GET/PUT/DELETE /device/<id>`,
  `GET /device/<id>/example`, `GET /device/unique`
- **Topics**: `GET /topics`, `GET /unlinked_topics`, `GET/POST /topic`, `GET/PUT/DELETE /topic/<id>`
- **Parsers**: `GET /parsers`, `GET/POST /parser`, `GET/PUT/DELETE /parser/<id>`
- **Metrics**: `GET /metrics`, `GET/POST /metric`, `GET/PUT/DELETE /metric/<id>`
- **Routes**: `GET /routes`, `GET/POST /route`, `GET/PUT/DELETE /route/<uuid>`
- **Destinations**: `GET /client_destinations`, `GET/POST /client_destination`,
  `GET/PUT/DELETE /client_destination/<id>`, `GET /client_destination/<id>/example`
- **Users**: `GET /users`, `GET/POST /user`, `GET/PUT/DELETE /user/<uuid>`,
  `PUT /user/<uuid>/password`
- **Settings/Crypto**: `GET /settings`, `GET /crypto`, `PUT /crypto/update`, `POST /crypto/test`,
  `POST /crypto/rotate_key`, `POST /crypto`
- **Dashboard API**: `GET /dashboard/api/critical/{ingest_rate,parse_success,dispatch_success,processing_backlog,throughput_series,dispatch_series}`

---

## Legacy code (pre-migration)

These modules are kept in the tree for reference and for the MySQL→PostgreSQL data migration,
but are **not importable** with the pinned `requirements.txt` (they depend on `temod`,
`mysql.connector` and/or `pymysql`, which are no longer installed):

- `core/entity/`, `core/join/`, `core/constraints.py` — temod entity/join definitions
- `front/renderers/users.py` — temod-based renderer (only `front/renderers/base.py` is used)
- `services/mqtt_transfer/mqtt_transfer.py` — the legacy worker (its dispatch stage has been
  ported to `mqtt_transfer_sqlalchemy.py`)
- `install/setup.py` + `install/storages/dbscheme.sql` — the legacy installer and MySQL schema
- `services/mqtt_transfer/README.md` — documents the legacy worker in depth

---

## Known issues / rough edges

- **Failed messages are acknowledged (no retry).** The worker marks
  `mqtt_message.processed = true` even when sender resolution, routing or parsing fails, to
  avoid infinite reprocessing. Every failure is audited as an `extraction` row
  (`success=false`, `error_text`), but there is no automatic retry; failed dispatches are
  recorded in the `dispatch` ledger (`status=failed`) and likewise not retried yet.
- **`mqtt_transfer.timer` is obsolete.** The worker is now a long-running loop guarded by the
  `job` lock; `mqtt_transfer.service` runs it as a simple service and the timer is no longer
  needed (enabling it anyway is a harmless no-op while the service is active).
- **The test suite targets the legacy worker** and cannot run with current dependencies.
- **Language support is inconsistent.** Templates exist for `en/es/fr` but `dictionnary.yml`
  only defines `en/fr/ar`: Spanish pages have no dictionary strings and Arabic has no
  templates. Only **EN** and **FR** are fully functional.
- `blueprints/destinations.py` and `blueprints/users.py` have **no Jinja templates**
  (`front/templates/<lang>/destinations/` and `front/templates/<lang>/users/` don't exist), so
  their list/new/view pages fail with `TemplateNotFound`; only the JSON/redirect routes work.
  `front/templates/<lang>/topics/view.html` and the `metrics/` templates are also missing.
- `config.toml.template` still carries pre-migration defaults: a vestigial `[temod]` section
  and `[storage.credentials] port = 3306` even though the credentials now feed a PostgreSQL
  connection string.
- `db/` is git-ignored, so the parser source files under `db/parsers/` are **not**
  version-controlled — decide whether that is intended for your workflow (the Docker setup
  persists them in a named volume instead).

---

## License

Intended license: MIT. **No `LICENSE` file is currently committed** — one should be added
before distributing the project.
