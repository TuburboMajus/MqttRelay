# FEATURE-1 — Hardening fixes for risks identified by code review

**Source:** Known risk areas listed in [QA_TEST_PLAN.md](QA_TEST_PLAN.md) (pre-execution code review).
**Scope:** 7 fixes. Each section gives the risk, affected code, and the concrete fix to apply.

---

## F1.1 — Add CSRF protection (HIGH)

**Risk:** No CSRF tokens anywhere. Flask-WTF is not even a dependency (`requirements.txt`). Every state-changing route (`POST /client`, `DELETE /user/<id>`, `POST /crypto/rotate_key`, …) can be triggered cross-site against a logged-in session cookie.

**Fix:**
1. Add to `requirements.txt`:
   ```
   Flask-WTF==1.2.2
   ```
2. In `run.py`, after app creation:
   ```python
   from flask_wtf import CSRFProtect
   csrf = CSRFProtect(app)
   ```
3. In every HTML form (all `front/templates/{en,fr,es}/**/new.html`, `login.html`, `signup.html`, dialogs):
   ```html
   <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
   ```
4. For the fetch/XHR calls used by dialogs and dashboards, expose the token in `base.html`:
   ```html
   <meta name="csrf-token" content="{{ csrf_token() }}">
   ```
   and send it on every mutating fetch:
   ```javascript
   headers: {'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content}
   ```
5. Additionally set session-cookie hardening in config:
   ```python
   app.config.update(
       SESSION_COOKIE_HTTPONLY=True,
       SESSION_COOKIE_SAMESITE='Lax',
       SESSION_COOKIE_SECURE=config['app'].get('ssl', False),
   )
   ```

---

## F1.2 — Stop granting admin to every signup; enforce roles (HIGH)

**Risk:** `blueprints/auth.py:109-121` (`doSignup`) assigns the **admin** privilege to every self-registered account, and no route checks privileges at all. Anyone who can reach the server owns it (create/delete users, rotate crypto keys, read all client data).

**Fix (two parts):**

1. **Bootstrap-only open signup** in `blueprints/auth.py` — the first account becomes admin; afterwards self-signup is disabled (admins create users via `/user`):
   ```python
   @auth_blueprint.route('/signup', methods=['POST'])
   def doSignup():
       if repos['User'].count() > 0:
           current_app.logger.warning("Route [auth.doSignup] signup disabled: users already exist")
           return redirect(url_for('auth.signup', error="signup_disabled"))
       ...  # existing creation logic, admin privilege is then legitimate
   ```
   Apply the same guard to `GET /signup` (render a "contact your administrator" message) and hide the signup link on `login.html` when users exist. Add the `signup_disabled` error string to the three language templates.

2. **Role enforcement decorator** in `core/auth.py`, applied to privileged routes:
   ```python
   from functools import wraps
   from flask import abort
   from flask_login import current_user

   def roles_required(*roles):
       def decorator(fn):
           @wraps(fn)
           def wrapper(*args, **kwargs):
               user_roles = set((current_user.privilege_roles or "").split(";"))
               if not set(roles) & user_roles:
                   abort(403)
               return fn(*args, **kwargs)
           return wrapper
       return decorator
   ```
   Expose `privilege_roles` on `SQLAlchemyUserProxy` (join `user.privilege_id → privilege.roles`). Apply `@roles_required('admin')` at minimum to: all `/user*` management routes (except own password change / own profile), `/crypto*` routes, and DELETE routes on clients/parsers/routes/destinations.

---

## F1.3 — Server-side password policy at signup and user creation (HIGH)

**Risk:** `doSignup` (`blueprints/auth.py:100-121`) and `createUser` (`blueprints/users.py:56`) accept any password, including empty. Only `changePassword` enforces ≥ 8 chars.

**Fix:** Centralize in `core/auth.py`:
```python
MIN_PASSWORD_LENGTH = 8

def validate_password(pwd: str) -> str | None:
    """Return an error code, or None if the password is acceptable."""
    if not pwd or len(pwd) < MIN_PASSWORD_LENGTH:
        return "password_too_short"
    return None
```
Call it in `doSignup` before hashing (redirect with `error="password_too_short"`, add the message to templates) and in `createUser` (return `jsonify(status="error", error="password_too_short"), 400`). Keep `changePassword` using the same constant instead of its hardcoded `8`.

---

## F1.4 — Bounds validation for `qos_default` and `priority` (MEDIUM)

**Risk:**
- `blueprints/topics.py:74,120` — `int(data.get('qos_default', 0))` accepts `-1`, `5`, and raises an unhandled `ValueError` (→ 500) on `"abc"`.
- `blueprints/routes.py:69,132` — same for `priority`; also note the server default is `0` while the form default is `100` (inconsistent).

**Fix:** Add a helper (e.g. `core/validation.py`):
```python
def parse_int_bounded(value, field, lo, hi, default=None):
    if value in (None, ""):
        if default is None:
            raise ValueError(f"{field}_required")
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}_not_integer")
    if not (lo <= n <= hi):
        raise ValueError(f"{field}_out_of_range")
    return n
```
Use in topics create/update:
```python
qos_default = parse_int_bounded(data.get('qos_default'), 'qos_default', 0, 2, default=0)
```
and in routes create/update:
```python
priority = parse_int_bounded(data.get('priority'), 'priority', 0, 100000, default=100)
```
Wrap in `try/except ValueError` → `jsonify(status="error", error=str(e)), 400`. Apply the same helper to `port` in `blueprints/destinations.py` / `blueprints/clients.py` destination handlers (`1–65535`) and `emission_rate` on devices (`>= 0`).

---

## F1.5 — Pagination: clamp `per_page`, kill the division-by-zero (MEDIUM)

**Risk:** `core/pagination.py:23` — `pages = (total + per_page - 1) // per_page` raises `ZeroDivisionError` when `per_page=0` (reachable via `?per_page=0` on every list route → HTTP 500). Negative `per_page` yields negative offsets/limits passed to SQL. Huge `per_page` allows unbounded result dumps.

**Fix:** Clamp once in `paginate()` (`core/pagination.py:63`):
```python
MAX_PER_PAGE = 500

def paginate(repo, page: int = 1, per_page: int = 20, **filters) -> Pagination:
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 1
    elif per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE
    ...
```
And defend the property itself (`core/pagination.py:23`):
```python
@property
def pages(self) -> int:
    if self.per_page <= 0:
        return 0
    return (self.total + self.per_page - 1) // self.per_page
```

---

## F1.6 — Server-side JSON validation for all JSON text fields (MEDIUM)

**Risk:** `config_schema` (parsers), `parser_config` + `conditions` (routes), `options_json` (destinations), `metadata_json` / `capabilities` / `payload_schema` / `defaults_json` (devices, device types) are validated only in browser JS. A direct POST stores malformed JSON; the worker and `/client_destination/<id>/example` then fail or silently fall back at read time.

**Fix:** Add to `core/validation.py`:
```python
import json

def clean_json_field(value, field):
    """Normalize an optional JSON text field. Returns None for empty, canonical JSON text otherwise."""
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    try:
        json.loads(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}_invalid_json")
    return value
```
Call it in every create/update handler that persists one of these fields, inside the same `try/except ValueError → 400` wrapper as F1.4. This keeps client-side validation as UX and makes the server the source of truth.

---

## F1.7 — Rate-limit authentication endpoints (MEDIUM)

**Risk:** `POST /login` (`blueprints/auth.py:42`) has no throttling; bcrypt slows brute force but does not stop credential stuffing. `POST /signup` (when enabled) and `PUT /user/<id>/password` are also unthrottled.

**Fix:**
1. Add to `requirements.txt`:
   ```
   Flask-Limiter==3.12
   ```
2. In `run.py`:
   ```python
   from flask_limiter import Limiter
   from flask_limiter.util import get_remote_address
   limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")
   ```
3. Decorate the sensitive routes:
   ```python
   @limiter.limit("10 per minute; 100 per hour")   # dologin
   @limiter.limit("5 per minute")                  # doSignup
   @limiter.limit("10 per minute")                 # changePassword
   ```
   (Import the `limiter` object into the blueprints, or register limits by endpoint name from `run.py` to avoid circular imports: `limiter.limit("10/minute")(app.view_functions['auth.dologin'])`.)
4. Memory storage is fine for the single-container deployment; switch `storage_uri` to Redis if the web service is ever scaled horizontally.

---

## Rollout order & verification

| Step | Fix | Verify with test-plan item |
|------|-----|---------------------------|
| 1 | F1.5 pagination clamp | §14.7 |
| 2 | F1.4 + F1.6 input validation | §7.5, §9.10, §8.7, §5.19, §5.26–27 |
| 3 | F1.3 password policy | §2.4 |
| 4 | F1.1 CSRF | §14.1 (after: all forms still submit, dialogs still save) |
| 5 | F1.7 rate limiting | §1.11 |
| 6 | F1.2 signup/roles | §2.5, §14.4 (biggest behavioral change — do last, needs admin-creates-users flow in place) |

Regression risk: F1.1 and F1.2 touch every form/template and the auth flow — rerun test plan §1–3, §5, §8, §9, §11, §12 after applying.
