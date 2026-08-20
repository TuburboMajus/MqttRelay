# MqttRelay — MQTT Ingest, Parse & Route with a Web Dashboard

MqttRelay is a multi-tenant **IoT data ingestion and distribution platform**. It connects to an
MQTT broker, persists every incoming message, turns raw payloads into **normalized time-series
metrics** through versioned, per-client **parsers**, and finally **dispatches** those metrics to
the correct downstream sink (per client) according to configurable routing rules. A **web
dashboard** lets operators manage the whole pipeline — clients, devices, topics, parsers, metrics,
routes, destinations, users and encryption — and monitor activity.

```
MQTT broker ──► Flask-MQTT ──► mqtt_message (raw)
                                     │
              systemd timer: mqtt_transfer (every ~10s)
                                     ▼
              resolve sender: topic → device → client
                                     ▼
              select routing_rule (priority + conditions DSL)
                                     ▼
              run parser: db/parsers/<name>_<version>.py
                                     ▼
              extraction + parsed_point (normalized)
                                     ▼
              route_deposit → client_destination → dispatcher
                                     ▼
                            client's own database (MySQL)
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
- [Dashboard](#dashboard)
- [REST Endpoints](#rest-endpoints)
- [Known issues / rough edges](#known-issues--rough-edges)
- [License](#license)

---

## What it does

- **MQTT ingestion** — subscribes to the broker (wildcard pattern `+/+/+`) and stores every raw
  message in the `mqtt_message` table.
- **Parsing** — a recurring background job runs a versioned parser against each unprocessed
  message and writes normalized points to `parsed_point`, keyed to a shared `metric_catalog`.
- **Routing** — routing rules map (client, topic, device) to a parser and a list of
  destinations, with optional content-based conditions and priorities.
- **Dispatching** — parsed points are delivered to each client's own `client_destination`
  (currently a **MySQL** sink; pluggable via `services/mqtt_transfer/dispatchers/`).
- **Web dashboard** — Flask + Jinja2 + Bootstrap 5 UI to manage everything, in multiple
  languages (EN/FR/ES/AR).
- **Secrets protection** — reversible encryption for third-party service credentials
  (e.g. destination DB passwords), with key rotation and re-encryption.

---

## Project layout

```
.
├── run.py                        # Flask app factory + dev entrypoint
├── context.py                    # Registers entities/joins/clusters as globals; PARSERS_DB
├── config.toml / .template       # Runtime config (DB, MQTT, Flask) / template used by installer
├── dictionnary.yml               # UI strings per language
├── requirements.txt
├── run.sh                        # gunicorn launcher for the dashboard
├── core/
│   ├── entity/                   # Temod entities = DB tables (mqtt.py, iot.py, client.py,
│   │                             #   parser.py, user.py, app.py)
│   ├── join/                     # Temod joins (client.py, iot.py, mqtt.py, user.py)
│   └── constraints.py            # EqualityConstraint definitions used by joins
├── blueprints/                   # Flask blueprints (one per domain)
│   ├── auth.py  clients.py  dashboard.py  destinations.py  devices.py
│   ├── general.py  metrics.py  mqtt.py  parsers.py  routes.py  topics.py  users.py
│   └── dashboards/               # Metric computations behind dashboard API endpoints
├── services/mqtt_transfer/       # The background ingest→parse→dispatch job
│   ├── mqtt_transfer.py          # MqttTransfer worker (process loop)
│   ├── dispatchers/              # Output sinks (mysql.py)
│   └── mqtt_transfer.{service,timer,sh}  # systemd unit/timer/launcher
├── db/parsers/                   # Parser source modules (DirectoryStorage)
├── tools/
│   ├── crypto_envelopes.py       # AES-GCM / ChaCha20-Poly1305 / AES-CBC+HMAC
│   └── json_conditions.py        # MongoDB-style condition DSL evaluator
├── front/
│   ├── renderers/                # Template rendering helpers (Base/AuthenticatedUser)
│   └── templates/                # Per-language Jinja2 templates (en/, es/, fr/, ar/)
├── install/
│   ├── setup.py                  # Interactive installer (DB, admin, MQTT, crypto, service)
│   ├── common_funcs.py
│   └── storages/dbscheme.sql     # Full MySQL schema
└── logs/                         # Rotating logs (MqttTransfer.log*)
```

---

## Tech stack

| Concern | Choice |
| --- | --- |
| Web framework | Flask 3 (+ `flask_mqtt`, `flask_login`) |
| ORM / persistence | [`temod`](https://pypi.org/project/temod/) + `temod_flask` (entity/join/cluster holders) |
| Database | MySQL 8 (`PyMySQL`, `mysql.connector`) |
| Realtime ingestion | `flask-mqtt` (broker subscribe, `on_message` hook) |
| Background job | Python worker driven by a `systemd` **oneshot** service + **timer** |
| Crypto | `cryptography` (AES-GCM, ChaCha20-Poly1305, AES-CBC+HMAC) |
| Frontend | Jinja2 + Bootstrap 5 + Bootstrap Icons + fetch API |
| i18n | `dictionnary.yml` + per-language template folders |
| Server | `gunicorn` (via `run.sh`) or Flask dev server (`run.py`) |

> Django is listed in `requirements.txt` but is used **only** for the
> `url_has_allowed_host_and_scheme` / `iri_to_uri` utilities in `blueprints/auth.py`.

---

## Data flow (end to end)

1. **Ingest** — `blueprints/mqtt.py` registers `on_connect` (subscribes to `+/+/+`) and
   `on_message`. Each MQTT message is written to `mqtt_message` with
   `client` (first topic segment), `topic`, `payload`, `qos`, `at`, and `processed=False`.
2. **Poll** — the `mqtt_transfer.timer` fires `mqtt_transfer.service` every ~10 s, which runs
   `services/mqtt_transfer/mqtt_transfer.py`. A `job` row prevents concurrent runs.
3. **Resolve sender** — `retrieve_sender()` looks up the `mqtt_topic` (must be `active`), then the
   `device` and its `client`.
4. **Select route** — `select_route()` collects `routing_rule`s matching the client/topic/device,
   evaluates the optional Mongo-style `conditions` DSL (see below), then picks the lowest
   `priority`, breaking ties by newest `created_at`.
5. **Parse** — the rule's `parser` is loaded (`db/parsers/<name>_<version>`), and its
   `parse(payload, **parser_config)` is executed. The result is a dict keyed by **metric catalog
   IDs** (integer keys) plus an optional `at` timestamp; non-integer keys become `meta_json`.
6. **Persist** — one `extraction` row is written per message, plus one `parsed_point` per metric
   (typed as `num/str/bool/json` with a `unit` and `quality`).
7. **Dispatch** — for each `route_deposit` of the rule, the corresponding `client_destination` is
   loaded, its dispatcher instantiated (keyed by `destination.type`), and the points are sent. A
   `dispatch` row records the outcome (`queued/sent/failed/…`).
8. **Ack** — on success the `mqtt_message` row is marked `processed`.

---

## Data model

Defined in `core/entity/` and instantiated in `install/storages/dbscheme.sql`.

| Domain | Tables |
| --- | --- |
| App | `mqtt_relay`, `language`, `job` |
| Users | `privilege`, `user` (password is **bcrypt**) |
| Tenants | `client`, `client_destination` |
| Devices | `device_type`, `device`, `latest_value` |
| MQTT | `mqtt_topic`, `mqtt_broker`, `mqtt_message` |
| Parsing | `parser`, `extraction`, `metric_catalog`, `parsed_point` |
| Routing | `routing_rule`, `route_deposit`, `dispatch` |
| Crypto | `crypto_config`, `crypto_key` |

Joins (`core/join/`) provide the composite views used by the UI and the worker, e.g.
`RoutingRuleFile` (rule + topic + client + device + parser), `MqttTopicFile`
(topic + client + device), `DeviceFile` (device + device type) and `UserAccount`
(user + privilege).

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

See `db/parsers/lse01_parser_1_0_0.py` for a minimal real example.

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
passwords, which remain **bcrypt** (`BCryptedAttribute` on `user.password`).

- Algorithms (configured in Settings → System → Secrets & Encryption):
  - **AES-256-GCM** (recommended)
  - **ChaCha20-Poly1305**
  - **AES-256-CBC + HMAC-SHA256** (encrypt-then-MAC, HKDF-derived subkeys)
- Keys are 32 bytes and live **outside** the DB for `key_source=env`:
  - `MQTT_RELAY_ENC_KEY_<KEY_ID>` (e.g. `MQTT_RELAY_ENC_KEY_PRIMARY`)
- Token format: `v1.<algorithm>.<base64 parts…>`
- Rotation: bump config version, replace the key, then **Re-encrypt** existing rows from the
  Settings page (`crypto_config`, `crypto_key` and the `/crypto*` endpoints).
- Implementation: `tools/crypto_envelopes.py`, wrapped by the `CryptoConfig` / `CryptoKey`
  entities in `core/entity/app.py`.

---

## Installation

1. **Prerequisites**
   - Python 3.10+
   - MySQL 8.0+
   - `venv`
   - `systemd` (for the background service/timer)
   - Build tooling for native wheels in `requirements.txt`

2. **Create the database**
   ```bash
   mysql -u root -p
   CREATE DATABASE mqttrelay CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
   CREATE USER 'mqttrelay'@'localhost' IDENTIFIED BY 'your-strong-password';
   GRANT ALL PRIVILEGES ON mqttrelay.* TO 'mqttrelay'@'localhost';
   FLUSH PRIVILEGES;
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
   sudo venv/bin/python install/setup.py
   ```
   The installer prompts for, and then applies:
   - **MySQL** connection info (it drops/recreates the database — confirm if it already exists),
   - an **admin user** (email + password),
   - the **MQTT broker** (URL, port, credentials, TLS),
   - the **crypto key source** (`env` recommended) and master key,
   - the **systemd** unit + timer (installed as `mqtt_transfer.service` / `mqtt_transfer.timer`).

   It writes `config.toml` from `config.toml.template`, and (for `key_source=env`) a `.env` file
   containing `MQTT_RELAY_ENC_KEY_PRIMARY`.

5. **Enable and start the background job**
   ```bash
   sudo systemctl enable --now mqtt_transfer.timer
   systemctl list-timers mqtt_transfer.timer
   ```

---

## Configuration

`config.toml` (generated from `config.toml.template`) has four sections:

```toml
[app]
host = "0.0.0.0"
port = 23909
threaded = true
debug = true
ssl = false                    # serve HTTPS directly if true
ssl_key = "resources/key.pem"
ssl_cert = "resources/cert.pem"
ssl_encapsulated = false       # true when behind a reverse proxy
templates_folder = "front/templates"
static_folder = "front/static"
secret_key = ""                # empty → generated at launch
default_language = "fr"

[mqtt]
broker_url = "localhost"
broker_port = 1883
username = ""
password = ""
keepalive = 0
tls_enabled = false

[temod]
bound_database = "mysql"
core_directory = "core"

[storage.credentials]
host = "127.0.0.1"
port = 3306
database = "mqtt"
user = "..."
password = "..."
```

> `config.toml` and `.env` contain secrets and must **never** be committed. The installer
> generates them locally.

---

## Running

- **Web dashboard** (production, via gunicorn):
  ```bash
  source venv/bin/activate
  ./run.sh                 # reads app.prod/port/ssl from config.toml
  ```
  For development you can also run `python run.py` directly (Flask dev server).

- **Background ingest→parse→dispatch** (systemd timer):
  ```bash
  sudo systemctl enable --now mqtt_transfer.timer
  journalctl -u mqtt_transfer -f
  # or one-shot, manually:
  venv/bin/python services/mqtt_transfer/mqtt_transfer.py --root-dir . --logging-dir logs
  ```

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

## Known issues / rough edges

- `blueprints/destinations.py` and `blueprints/users.py` have **no Jinja templates**
  (`front/templates/<lang>/destinations/` and `front/templates/<lang>/users/` don't exist), so
  their list/new/view pages still fail with `TemplateNotFound`; only the JSON/redirect routes
  work. `front/templates/<lang>/topics/view.html` and the `metrics/` templates are also missing.
- `blueprints/clients.py` (`viewClient`) uses the `DeviceFile` **join** with `.storage`, which
  may not expose a storage like entities do.
- `blueprints/dashboards/*.py` contain vestigial raw-SQL code after early returns; the active
  implementations use Temod storage queries.
- `config.toml`, `.env` and `logs/` are already excluded by `.gitignore`. Note that `db/` is
  also ignored, so the parser source files under `db/parsers/` are **not** version-controlled —
  decide whether that is intended for your workflow.
- `core/join/` has no `__init__.py`; joins are discovered by Temod's `init_holders` instead.

---

## License

MIT. See `LICENSE` file.