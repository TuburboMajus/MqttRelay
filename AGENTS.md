# AGENTS.md — Guidance for AI agents working on MqttRelay

> This file is the authoritative "how to work in this repo" guide. Read it before making changes.

## 1. What this project is

MqttRelay is a multi-tenant **IoT data pipeline**:

1. Ingests MQTT messages (via `flask-mqtt`) and stores them raw in MySQL.
2. A recurring background job (`mqtt_transfer`) parses unprocessed messages into normalized
   time-series points using **versioned, per-client parsers**.
3. Routes each message to a **routing rule** and **dispatches** the parsed points to the client's
   own destination sink (currently MySQL).

A Flask **web dashboard** manages clients, devices, topics, parsers, metrics, routes,
destinations, users, and encryption.

## 2. The two runtimes (very important)

The codebase has **two separate Python processes** that share entities but boot differently:

| | Web dashboard | Background worker |
| --- | --- | --- |
| Entrypoint | `run.py` → `build_app()` | `services/mqtt_transfer/mqtt_transfer.py` |
| Launcher | `run.sh` (gunicorn) or `python run.py` | systemd timer → `mqtt_transfer.sh` |
| Entity access | **bare names** registered as **builtins** (`Client`, `MqttMessage`, …) | `entities.X` via `import core.entity as entities` |
| Boot | `init_holders(...)` + `init_context(config)` | `import core.entity as entities` + `setattr(__builtins__, 'LOGGER', …)` |

**Consequence:**
- In **blueprints** (`blueprints/*.py`) and anything imported from `run.py`, entity/join/cluster
  classes are already available as global names. **Do not `from core.entity import ...` there** —
  reference them bare (`Client.storage`, `MqttMessage`, `RoutingRuleFile`).
- In the **worker**, use `entities.X` (the module already does `import core.entity as entities`).

## 3. Architecture map

```
core/entity/*.py        # Temod Entity = one DB table. Source of truth for fields/types.
core/join/*.py          # Temod Join = composite views (used by UI and worker).
core/constraints.py     # EqualityConstraint definitions that joins wire together.
blueprints/*.py         # Flask blueprints, one per domain (auth, clients, ...).
blueprints/dashboards/  # Pure computation modules behind dashboard API endpoints.
services/mqtt_transfer/ # The ingest→parse→dispatch worker + dispatchers + systemd files.
tools/                  # crypto_envelopes.py, json_conditions.py (routing condition DSL).
install/storages/dbscheme.sql  # The MySQL schema (must stay in sync with core/entity).
front/templates/<lang>/ # Per-language Jinja2 templates (en/es/fr/ar).
dictionnary.yml         # Per-language UI strings.
```

## 4. Temod ORM conventions (used everywhere)

Temod (`temod`, `temod_flask`) provides the persistence layer. Patterns you will see and should
follow:

- **Entities** (`core/entity/`) declare `ENTITY_NAME` and `ATTRIBUTES` (each attribute has a
  `type` from `temod.base.attribute`, e.g. `IntegerAttribute`, `StringAttribute`,
  `EnumAttribute`, `DateTimeAttribute`, `BooleanAttribute`, `BCryptedAttribute`,
  `UUID4Attribute`, `RealAttribute`). `UPDATABLE_FIELDS` lists fields safe to bulk-update.
- **Storage access** via `Entity.storage`:
  - `Entity.storage.get(id=…)` / `.get(<field>=value)`
  - `Entity.storage.list(<conditions…>, orderby=…, limit=…)`
  - `Entity.storage.count(<conditions…>)`
  - `Entity.storage.create(entity)`
  - `Entity.storage.delete(entity)` / `.delete(id=…)`
  - `Entity.storage.generate_value('id')`
- **Updates use snapshots**:
  ```python
  row = Entity.storage.get(id=...)
  row.takeSnapshot().setAttributes(**updates)   # or row['field'] = value after takeSnapshot()
  Entity.storage.updateOnSnapshot(row)
  ```
- **Conditions** (`temod.base.condition`): `Equals`, `Contains`, `Not`, `And`, `Or`,
  `Superior`, `Inferior`, … combined with attributes, e.g.
  `Equals(StringAttribute("name", value=x))`.
- **Joins** (`core/join/`) wrap constraints and a `DEFAULT_ENTRY`; the UI uses them for joined
  listings (e.g. `MqttTopicFile`, `RoutingRuleFile`, `DeviceFile`).
- `context.py::init_context` registers entities/joins/clusters into `__builtins__` **and** into
  Temod's `_FormReaders`, which is what `body_content('form'|'json')` and `Paginator` rely on.

> Rule of thumb: **never import `core.entity.*` inside blueprint modules.** Reference them as
> globals. If a blueprint name resolves oddly, it's because of this builtin registration, not an
> import bug.

## 5. Keeping entity ↔ schema ↔ UI in sync

When adding or changing a field/table, update **all** of:

1. `core/entity/<module>.py` (the Entity definition),
2. `install/storages/dbscheme.sql` (the DDL),
3. any template forms in `front/templates/<lang>/<domain>/` that touch that field,
4. optionally a join in `core/join/` + constraint in `core/constraints.py` if it participates in
   a joined view.

## 6. Parser contract (do not break)

A parser = one `parser` row + one source file in `db/parsers/`:

- Filename: `<name lower, spaces→_>_<version, dots→_>` (e.g. `lse01_soil_1_0_0.py`).
- The dashboard stores **two** files: `lse01_soil_1_0_0` (DirectoryStorage source) and
  `lse01_soil_1_0_0.py` (importable module). Keep this dual-write behavior in
  `blueprints/parsers.py::editParser`.
- The module must export `def parse(data, **config):` returning a dict where **integer keys are
  `metric_catalog` ids** and values are the typed point values; an optional `"at"` key overrides
  the timestamp; non-integer keys land in `meta_json`.
- Only `language == "python"` is supported by `services/mqtt_transfer/mqtt_transfer.py`
  (`load_parse_function`). Adding a language means implementing its loader **and** registering its
  source file extension in `Parser.FILE_EXTENSIONS`.

## 7. Routing & conditions DSL

- `routing_rule` = client + optional topic/device + parser + parser_config + `priority`
  (lower wins) + optional `conditions` JSON. Linked to destinations via `route_deposit`.
- `conditions` are evaluated by `tools/json_conditions.py::eval_mongo_dsl(rule, ctx)` with ctx:
  `{device, device_type, topic, message}`. Operators: `$eq $ne $gt $gte $lt $lte $in $nin
  $exists $regex $contains $startswith $endswith $between $elemMatch` and `$and/$or/$not`,
  plus shorthand equality. Dotted paths supported.

## 8. Secrets & crypto rules

- **Reversible crypto is only for destination credentials** (e.g. `client_destination` DB
  passwords). It is implemented in `tools/crypto_envelopes.py` (AES-GCM / ChaCha20-Poly1305 /
  AES-CBC+HMAC) and wrapped by `CryptoConfig`/`CryptoKey` in `core/entity/app.py`.
- **User passwords are bcrypt** (`BCryptedAttribute` on `user.password`). Never route them through
  the reversible crypto.
- For `key_source=env`, the 32-byte key comes from `MQTT_RELAY_ENC_KEY_<KEY_ID>`
  (e.g. `MQTT_RELAY_ENC_KEY_PRIMARY`). `.env` is written by the installer.
- **Never commit `config.toml`, `.env`, or `logs/`.** `config.toml` contains plaintext DB
  credentials.

## 9. i18n

- UI strings live in `dictionnary.yml` keyed by language code (`en`, `fr`, `es`, `ar`).
- Templates live under `front/templates/<lang>/<domain>/`. Blueprints use `MultiLanguageBlueprint`
  with a `"{language}/<domain>"` `templates_folder` and select templates via `g.language['code']`.
- `Language` table (`app.config['LANGUAGES']`) drives the language list.

## 10. Commands

```bash
# Install (interactive: DB, admin, MQTT, crypto, systemd)
sudo venv/bin/python install/setup.py

# Web dashboard (production)
source venv/bin/activate && ./run.sh

# Web dashboard (dev)
python run.py

# Background worker (one-shot, useful when debugging)
venv/bin/python services/mqtt_transfer/mqtt_transfer.py --root-dir . --logging-dir logs

# Background worker (service/timer)
sudo systemctl enable --now mqtt_transfer.timer
journalctl -u mqtt_transfer -f
```

## 11. Known issues / rough edges (awareness — fix or avoid)

- `blueprints/destinations.py` and `blueprints/users.py` have **no Jinja templates** —
  `front/templates/<lang>/destinations/` and `front/templates/<lang>/users/` don't exist, so
  their list/new/view pages still fail with `TemplateNotFound` (only the JSON/redirect routes
  work). `front/templates/<lang>/topics/view.html` and the `metrics/` templates are also missing.
- `blueprints/clients.py::viewClient` uses the `DeviceFile` join with `.storage`, which is
  suspicious — verify joins expose `.storage` the same way entities do before relying on it.
- `blueprints/dashboards/*.py` contain dead raw-SQL code after early `return`s; the live paths use
  Temod storage queries. Don't copy the dead SQL.
- `db/` is gitignored, so parser source under `db/parsers/` is not version-controlled — verify
  this matches your intended workflow (`config.toml`, `.env` and `logs/` are also gitignored).

## 12. Definition of done for a change

- Entity fields ↔ `dbscheme.sql` ↔ templates are consistent (see §5).
- New blueprint routes are behind `@login_required` and use `MultiLanguageBlueprint` where a page
  is rendered.
- Any new parser/dispatcher follows the contracts in §6 / §7.
- No secrets are committed; reversible crypto is used only for destination credentials.
- The worker still boots standalone (`python services/mqtt_transfer/mqtt_transfer.py --root-dir .`).
