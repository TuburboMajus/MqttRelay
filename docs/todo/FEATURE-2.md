# FEATURE-2 — Fixes for bugs found during QA execution

**Execution date:** 2026-10-06
**Target tested:** http://localhost:23909 (`mqttrelay-dev-web-1`, PostgreSQL `mqttrelay-dev-postgres-1`)
**Method:** Every section of [QA_TEST_PLAN.md](QA_TEST_PLAN.md) executed against the live deployment via authenticated HTTP, direct DB inspection, and real MQTT publishes.

This document covers **bugs observed during testing**. Pre-existing hardening risks (CSRF, roles, rate limiting, generic input-validation strategy) are in [FEATURE-1.md](FEATURE-1.md); where a QA bug overlaps a FEATURE-1 item it is cross-referenced rather than duplicated.

---

## Results summary

| Area | Result |
|------|--------|
| Smoke / auth redirects (§0, §1.9 open-redirect, §1.10 SQLi) | ✅ Pass |
| Login / logout core flow (§1, §3.1) | ✅ Pass (except §3.2–3.3, see **B9**) |
| Signup (§2) | ⚠️ Works; weak-password & admin-for-all confirmed → FEATURE-1 |
| XSS escaping (§14.2) | ✅ Pass — Jinja2 autoescape confirmed on list & view |
| Users mgmt (§11) | ✅ Pass (403 cross-user, disabled-login block all correct) |
| Crypto (§12.8–12.12) | ✅ Pass — encrypt/decrypt round-trip + stale-key guard work |
| Metrics / Device-types / Topics / Parsers / Routes / Destinations CRUD | ⚠️ Functional but multiple bugs below |
| Dashboard APIs (§4) | ✅ All 200, JSON shapes correct |
| **MQTT ingest→parse→dispatch E2E (§13)** | ❌ **Blocked — no ingestion (B1)** |
| Internationalization (§14.15) | ❌ fr/es pages 500 (B6, B7) |
| Security headers (§14.6) | ❌ None present (B10) |

**Bugs found: 11** (2 critical, 4 high, 3 medium, 2 low).

---

## B1 — MQTT subscriber stops consuming; no messages ingested (CRITICAL)

**Observed:** `mqtt_message` row count froze at 136 with `max(at) = 13:48:56`. Real device topics (`edb1…/SECTEUR*/data`, previously arriving every ~5 min) stopped. I published three QoS-1 messages to `qa-client-1/sensor1/data` and `qa-unknown-slug/devx/data` from inside the web container — all confirmed delivered to the broker (`is_published: True`, rc 0) — yet **zero** rows appeared, before and after a container restart. The broker TCP connection (`:8883`) is ESTABLISHED and `handle_connect` logs `result code 0`, but `handle_mqtt_message` never fires.

**Impact:** The entire product function — ingest MQTT → parse → dispatch — is dead. §13 could not be executed at all. This is the top-priority fix.

**Root cause (most likely):** Flask-MQTT's Paho network loop does not run reliably under Gunicorn. The web process is `gunicorn --workers 1 … run:build_app()`; the MQTT client loop is started at import/app-build time but the Paho background thread is not surviving in the forked Gunicorn worker (classic Flask-MQTT + Gunicorn fork issue — the loop thread belongs to the master, not the worker, or is never `loop_start()`ed post-fork).

**Fix:**
1. **Stop coupling ingestion to the web server.** Move the MQTT subscriber into its own long-running process (the repo already has a `mqtt_transfer`/worker container pattern — add a dedicated `mqtt_ingest` entrypoint that runs a plain Paho client with `loop_forever()`), so it does not depend on Gunicorn's worker lifecycle. Verify in `run.py` / `docker/entrypoint.sh` which process owns the subscription.
2. If ingestion must stay in-process, ensure the Paho loop is started **after** fork using a Gunicorn `post_fork` hook, and run Gunicorn with a single worker + threaded worker class; add a connection-watchdog that re-subscribes and logs on `on_disconnect` (the handler currently only logs a warning and I never saw it fire — confirm it is actually wired).
3. Add a liveness check: log at INFO every N received messages, and expose last-ingest timestamp on `/dashboard/api/critical/processing_backlog` or a `/healthz` endpoint so a silent stall is detectable.

**Verification:** publish a test message, assert a new `mqtt_message` row within 5 s; kill the broker connection and assert `on_disconnect` logs and auto-reconnect occurs.

---

## B2 — Database integrity errors surface as raw 500s / SQL in redirect URLs (HIGH)

**Observed:**
- Duplicate device type (vendor+model) → **HTTP 500** (`blueprints/devices.py:72`).
- Duplicate topic → **HTTP 500** (`blueprints/topics.py` create).
- Duplicate parser (name+version) → **HTTP 500** (`blueprints/parsers.py:72`).
- Duplicate client slug and slug-too-long → **302 to `/client?error=<full psycopg2 message incl. the entire SQL statement and parameters>`** (`blueprints/clients.py`). The raw SQL, column list, and bound parameter values are echoed into the URL/error banner.

**Impact:** Unhandled `IntegrityError`/`DataError` crash the request (500) or leak schema internals into the UI/URL (information disclosure, terrible UX). Every create endpoint is affected.

**Fix:** Wrap each create/update in a handler for `sqlalchemy.exc.IntegrityError` and `DataError`, roll back the session, and return a clean domain error — JSON endpoints: `jsonify(status="error", error="duplicate_<entity>"), 409`; form endpoints: `redirect(url_for(...form..., error="duplicate_<entity>"))` with a human string in the template. Never pass `str(exc)` into a redirect. Centralize as a small helper or a Flask `errorhandler(IntegrityError)`.

---

## B3 — Routing-rule view page crashes with 500 (HIGH)

**Observed:** `GET /route/<valid-id>` → 500. Traceback:
```
front/templates/en/routes/view.html line 102:
  {{ d.type.name|upper }}
jinja2.exceptions.UndefinedError: 'dict object' has no attribute 'type'
```
The view passes each linked destination (`d`) as a **dict**, but the template accesses `d.type.name` as if `d` were an ORM object with a related `type` object. A valid, correctly-created rule cannot be viewed.

**Fix:** Make the data and template agree. Either pass destination ORM objects to the template, or change the template to `{{ d.type|upper }}` (the dict key is a string `type`, e.g. `"mysql"`). Audit `routes/view.html` for other `d.<rel>.<attr>` accesses (host/database likely have the same shape) and fix across `en`/`fr`/`es`. Add a smoke test that renders the view for a seeded rule.

---

## B4 — Negative `per_page` crashes list endpoints with 500 (HIGH)

**Observed:** `GET /clients?per_page=-5` → **500**, `psycopg2.errors.InvalidRowCountInLimitClause: LIMIT must not be negative`. Affects every paginated list (same `paginate()` helper). `page=0/-1/huge` and `per_page=0` are handled (200), so only the negative-`per_page` path is live, but it is reachable on all lists.

**Fix:** This is exactly **FEATURE-1 §F1.5** — clamp `per_page` to `[1, MAX_PER_PAGE]` in `core/pagination.py:paginate()` and guard the `pages` property against `per_page <= 0`. Applying F1.5 closes B4.

---

## B5 — No server-side validation on numeric & enum fields (HIGH)

**Observed via direct POST (bypassing browser validation):**
| Field | Input | Result |
|-------|-------|--------|
| topic `qos_default` | `5`, `-1` | accepted & stored (out of MQTT 0–2 range) |
| topic `qos_default` | `abc` | **500** (`int('abc')` ValueError) |
| route `priority` | `-5` | accepted |
| route `priority` | `abc` | **500** |
| client `slug` | `QA CLIENT UPPER` (spaces+caps) | accepted (pattern `^[a-z0-9-]{1,64}$` not enforced server-side) |
| destination `type` | `carrier-pigeon` | accepted (enum not enforced) |
| route `destination_ids` | omitted entirely | rule created with **zero** destinations (dispatches nowhere) |
| device/parser/route JSON fields | `{broken`, `{{{bad` | stored verbatim |

**Impact:** Garbage persists and either breaks the worker later or produces 500s on malformed numerics. Browser validation is the only guard.

**Fix:** Apply **FEATURE-1 §F1.4** (`parse_int_bounded` for `qos_default` 0–2, `priority` 0–100000, `port` 1–65535, `emission_rate` ≥0) and **§F1.6** (`clean_json_field` for all JSON text columns), each wrapped in `try/except ValueError → 400`. Additionally:
- Enforce the client `slug` regex server-side (`re.fullmatch(r'[a-z0-9-]{1,64}', slug)`).
- Enforce the destination `type` against the allowed set `{mysql, postgres, http, kafka, file, other}`.
- Reject route creation with an empty `destination_ids` list (`400 no_destinations`).

---

## B6 — Spanish dashboard template is broken (missing `endblock`) (MEDIUM)

**Observed:** `GET /dashboard` as an `es` user → **500**:
```
front/templates/es/dashboard/dashboard.html line 17:
  TemplateSyntaxError: Unexpected end of template. Jinja was looking for 'endblock'.
```
The file is **357 lines vs 611** for `en`, and contains **1** `endblock` vs **2** in `en` — it was truncated/left unfinished during the i18n port. This is a source bug (present on host, not just the image).

**Fix:** Re-port `es/dashboard/dashboard.html` from the `en` version (translate strings, keep block structure intact). Add a CI check that every template compiles: iterate `app.jinja_env.get_template(name)` over all templates and fail on `TemplateSyntaxError`.

---

## B7 — French/Spanish pages 500 because the running image is stale vs. source templates (MEDIUM)

**Observed:** As `fr`/`es` users, `/users`, `/client_destinations`, `/metrics` → **500 `TemplateNotFound: fr/users/list.html`** (and `es/...`). But those files **do exist on the host** (`find` shows full parity with `en`; `comm` reports none missing). Inside the container they are absent — the deployed `mqttrelay:latest` image predates these templates. `en` has 32 templates; the container is missing several `fr`/`es` equivalents that exist in source.

**Impact:** Any non-English user hits 500s on multiple core pages. Also a process smell: templates are baked into the image with no bind-mount, so source edits don't reach the running container without a rebuild.

**Fix:**
1. Rebuild and redeploy the image so it includes current templates (`docker compose -f docker/docker-compose.dev.yml build web && … up -d`). After rebuild, re-run §14.15 — all `fr`/`es` pages except the B6 dashboard should pass.
2. For the dev workflow, bind-mount `front/templates` into the container in `docker-compose.dev.yml` so template edits are picked up without a rebuild (and reduce "works on host, 500 in container" drift).
3. Combine with the B6 CI template-compile check so missing/broken localized templates fail the build, not production.

---

## B8 — Update (PUT/PATCH) responses echo stale pre-update values (LOW)

**Observed:** `PUT /client/<id>`, `PUT /user/<id>`, `PUT /route/<id>` return `status: updated` with a `data` body showing the **old** field values, even though the DB is correctly updated (verified by re-reading). E.g. renaming client 2 returned the previous name in the response while the row was in fact changed.

**Root cause:** The handler serializes the in-memory object before the repository refreshes/commits, or serializes a pre-mutation copy (`user.to_dict()` captured before `repos[...].update(...)` takes effect on the instance).

**Impact:** Minor, but any front-end that trusts the response to repaint the row shows stale data until reload.

**Fix:** Re-fetch (or `session.refresh(obj)`) after the update and serialize the fresh instance; return that. Audit all `editX` handlers in `clients.py`, `users.py`, `routes.py`, `topics.py`, `metrics.py`.

---

## B9 — Logout does not invalidate the session server-side (MEDIUM, security)

**Observed:** Captured a session cookie while logged in, called `/logout` (302 to login, confirmed), then replayed the **pre-logout** cookie against `/dashboard` → **200 (still authenticated)**. Flask-Login's `logout_user()` only clears the client-side cookie; the signed session remains valid because there is no server-side session/identity invalidation.

**Impact:** A leaked/intercepted session cookie remains usable after the user logs out. Relevant on shared machines and after token theft.

**Fix:** Adopt Flask-Login session protection and a rotating identifier:
- Set `login_manager.session_protection = "strong"`.
- Store a per-user `session_token` (or `alternative_id`) in the DB, return it from `get_id()`, and rotate it on logout and password change so old cookies fail `user_loader` validation.
- Pairs with the cookie-hardening in **FEATURE-1 §F1.1** (`SESSION_COOKIE_HTTPONLY/SAMESITE/SECURE`).

---

## B10 — No security response headers (MEDIUM)

**Observed:** `curl -I /login` returns none of `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`. The app is clickjackable and has no CSP.

**Fix:** Add an `after_request` hook (or Flask-Talisman) in `run.py` setting at minimum:
```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src https://cdn.jsdelivr.net
Strict-Transport-Security: max-age=31536000  (only when served over TLS)
```
Note the UI loads Bootstrap/Chart.js from `cdn.jsdelivr.net`, so the CSP must allow that host (or vendor the assets locally and tighten to `'self'`).

---

## B11 — Generic/opaque error on over-long signup email (LOW)

**Observed:** Signup with a 346-char email → `302 /signup?error=email_error` (the catch-all exception branch, `blueprints/auth.py:131`), triggered by the DB length constraint rather than a validated message.

**Fix:** Validate email format and length (RFC max 254) before insert and return a specific `error=invalid_email`; reserve `email_error` for genuinely unexpected failures. Low priority, rolls in naturally with the FEATURE-1 §F1.3 signup-validation work.

---

## Suggested fix order

1. **B1** — restore ingestion (product is non-functional without it).
2. **B4/B5** (= FEATURE-1 F1.4/F1.5/F1.6) + **B2** — stop 500s and raw-SQL leaks on every create/list endpoint.
3. **B3, B6, B7** — restore the route view page and non-English pages (rebuild image + fix `es` dashboard + template-compile CI).
4. **B9, B10** — session invalidation and security headers (with FEATURE-1 F1.1).
5. **B8, B11** — stale-response and signup-email polish.

After fixes, re-run the full [QA_TEST_PLAN.md](QA_TEST_PLAN.md), with special attention to §13 (now executable) and §14.15 (i18n).

---

## Test fixtures left in the environment

Valid QA data retained for re-testing (invalid/junk rows created during destructive tests were cleaned up): client `qa-client-1` (id 2) with device id 9, destinations id 3 & 5, parser `QA Json Parser` 1.0.0 (id 2, with working code), topic id 9, two routing rules (client 2), and users `qa.tester@example.com` / `qa.created@example.com` / `qa.weak@example.com` (disabled). Delete these when no longer needed.
