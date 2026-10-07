# Contract: ingest-to-dispatch pipeline (`dashboard` ↔ `relay-worker`)

Seam between `components/dashboard/` and `components/relay-worker/`. There is no network
call between these two components — the contract is entirely data at rest, in two
independent forms. Either side changing its half of this contract without the other is how
this seam breaks; that is the thing this file exists to prevent.

## 1. Seam A — shared PostgreSQL tables

### 1.1 Inbox: `mqtt_message`

- **Producer:** `dashboard` (`blueprints/mqtt.py`, on every MQTT `on_message`).
- **Consumer:** `relay-worker` (polls `processed = false` every ~10s).
- **Fields `relay-worker` depends on:** `client` (first topic segment), `topic`, `payload`,
  `qos`, `at`, `processed`.
- **State machine:** `processed` starts `false`. `relay-worker` sets it `true` exactly once,
  on both success *and* failure (see 1.3) — `dashboard` must never flip it back to `false`,
  that would make `relay-worker` reprocess a message it already produced
  `extraction`/`dispatch` rows for.
- **Ordering:** none guaranteed or required. `relay-worker` processes whatever is
  `processed = false` on each poll in whatever order the query returns.

### 1.2 Config: `routing_rule`, `parser`, `route_deposit`, `client_destination`,
`metric_catalog`, `mqtt_topic`, `device`, `device_type`, `client`

- **Producer:** `dashboard` (every write path behind the Clients/Devices/Topics/Parsers/
  Metrics/Routes/Destinations pages).
- **Consumer:** `relay-worker`, read fresh on every poll cycle (no caching) — a config change
  made in `dashboard` takes effect on the worker's *next* cycle, not immediately.
- **`relay-worker`'s read contract on `routing_rule`:** must match on `client` and optionally
  `topic`/`device`; `conditions` (if present) is evaluated via `tools/json_conditions.py`
  against `{device, device_type, topic, message}`; among matches, lowest `priority` wins,
  ties broken by newest `created_at`. `dashboard` must not assume any other tie-break when
  presenting "which rule will fire" in the UI.
- **`relay-worker`'s read contract on `parser`:** `language` must be `python`; anything else
  is a hard error for that message (recorded per 1.3), not a silent skip. `dashboard` must
  not allow creating a `parser` row with an unsupported `language` without surfacing that it
  will never successfully run.

### 1.3 Result ledger: `extraction`, `parsed_point`, `dispatch`

- **Producer:** `relay-worker`, once per processed message (`extraction` always;
  `parsed_point` per metric key on success; `dispatch` per `route_deposit` attempted).
- **Consumer:** `dashboard` (`/dashboard/api/critical/*` endpoints: `ingest_rate`,
  `parse_success`, `dispatch_success`, `processing_backlog`, `throughput_series`,
  `dispatch_series`).
- **Error semantics (no exceptions cross this seam, only rows):**
  - Sender-resolution, routing, or parse failure → `extraction.success = false`,
    `extraction.error_text` set, `mqtt_message.processed = true` regardless. No retry.
  - Dispatch failure → `dispatch.status = "failed"`; `parsed_point` rows are **not** rolled
    back (they were already committed) and `mqtt_message` stays `processed = true`. No
    retry.
  - `dashboard` must treat `status = "failed"` in `dispatch` and `success = false` in
    `extraction` as terminal, not "pending" — there is currently no retry mechanism on
    either side of this seam (tracked as a known gap in `README.md` / `ARCHITECTURE.md`
    section 6, not fixed by this contract).

## 2. Seam B — shared filesystem (`db/parsers/`)

- **Producer:** `dashboard` (Parsers page writes the source file on save).
- **Consumer:** `relay-worker` (`load_parse_function`, imports the module by path on the
  cycle that needs it — not cached across the parser's lifetime beyond that).
- **Filename contract:** `<name lowercase, spaces→_>_<version, dots→_>.py`, e.g. parser
  `LSE01 Soil` v`1.0.0` → `lse01_soil_1_0_0.py`. `dashboard` owns this naming function; if it
  ever changes, every existing `routing_rule.parser` binding and every file already on disk
  must still resolve, or `relay-worker` will fail every message routed through that rule.
- **Module contract:** must export `def parse(data, **config) -> dict`. Integer keys in the
  returned dict are `metric_catalog` ids; a non-integer `"at"` key overrides the point
  timestamp; any other non-integer key is folded into `meta_json`. `dashboard` validates
  parser source at save time against this shape only as far as it can statically (it cannot
  guarantee the function doesn't raise at runtime — that failure is caught by `relay-worker`
  and recorded per 1.3).
- **Only `language = "python"` is supported** — this is enforced by `relay-worker`
  (`load_parse_function`), not by `dashboard`; see 1.2.

## 3. Versioning rules for this seam

- Columns may be **added** to any table in section 1 without coordinating a deploy order
  between the two components (both read with named columns, not `SELECT *`-by-position).
  Columns must not be **removed or repurposed** without updating both components in the same
  change, since there is no schema version negotiation between them.
- A parser's on-disk contract (its `parse` signature or its expected `config` shape) must be
  changed by creating a **new `parser` row with a bumped `version`** and a new file, not by
  editing an existing version's file in place — existing `routing_rule` rows pin a specific
  `parser` row, and in-flight messages may still be routed to the old version while the
  change is being made.
