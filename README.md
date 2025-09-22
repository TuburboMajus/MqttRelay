# MqttRelay — MQTT Ingest, Parse & Route with a Web Dashboard

MqttRelay is a small platform that:

- Subscribes to **MQTT topics** and stores incoming messages.
- **Parses** those messages into normalized metrics (time series).
- **Routes** results to the right client/pipeline based on **client, topic, device, and/or content** rules.
- Ships with a **web dashboard** to manage clients, devices, parsers, metrics, and crypto settings—and to monitor activity.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Security & Encryption (reversible)](#security--encryption-reversible)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [Dashboard](#dashboard)
  - [Clients & Devices](#clients--devices)
  - [Parsers](#parsers)
  - [Settings](#settings)
- [REST Endpoints (selected)](#rest-endpoints-selected)
- [Development Notes](#development-notes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **MQTT ingestion**: subscribe to one or more topics, store raw messages.
- **Routing**: forward parsed outputs to the correct client/pipeline based on client/topic/device/content.
- **Parsers**:
  - Versioned parser registry (`name`, `version`, `language`, `config_schema`, `active`).
  - Execution records (`extractions`) and normalized points (`parsed_points`) to a known catalog of metrics.
- **Dashboard** (Flask + Jinja + Bootstrap 5):
  - Clients (view/edit), Devices (CRUD)
  - Parsers (list, create, view/edit/delete)
  - Settings:
    - **User**: edit profile (email with confirmation), language, analytics tracking, change password
    - **System**: Metric Catalog (add/delete), **Secrets & Encryption** (choose reversible encryption and re-encrypt stored secrets)
- **Crypto**: Reversible encryption for third-party service credentials (e.g., DB logins), with key rotation and re-encrypt tooling.

---

## Architecture

- **Ingestor**: Subscribes to MQTT broker(s); persists messages (table `mqtt_message`).
- **Parser layer**: Executes the configured parser (Python/JS/SQL, etc.) and writes:
  - `extractions` (one per parsed message, with success/error info)
  - `parsed_points` (normalized time series with metric IDs/units/quality, etc.)
- **Router**: Uses client/topic/device/content to route outputs to the correct downstream pipeline.
- **Dashboard**: Flask app with Jinja2 pages & Bootstrap 5/Icons.

---


## Security & Encryption (reversible)

Used **only** for *external* credentials (DBs/services), not for user login passwords.

- Algorithms (configurable in Settings → System → Secrets & Encryption):
  - **AES-256-GCM** (recommended)
  - **ChaCha20-Poly1305**
  - **AES-256-CBC + HMAC-SHA256** (Encrypt-then-MAC)
- Keys: 32-byte keys (outside DB). For `key_source=env`, set keys via env var:
  - `TECHDASH_ENC_KEY_<KEY_ID>` (e.g., `TECHDASH_ENC_KEY_PRIMARY`)
- Token format: `v<cfg_version>.<algorithm>.<parts…>`
- Rotation: bump config version, update key material, **Re-encrypt** existing rows from the Settings page.
- Sample Python module: `crypto_envelopes.py` with `encrypt_data/decrypt_data` and specific helpers.

> User login passwords in the `user` table should remain **one-way hashed** (e.g., bcrypt). The reversible crypto here is **not** for user authentication passwords.

---

## Installation

1. **Prerequisites**
   - Python 3.10+ (recommended)
   - MySQL 8.0+
   - `virtualenv` / `venv`
   - `systemd` (for the service)
   - Build essentials for any native wheels in `requirements.txt`

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
   # The installer prompts for DB credentials and sets up schema/config/service
   sudo venv/bin/python install/setup.py
   ```
   During install you will:
   - Provide **MySQL** connection info.
   - Seed core tables (incl. `crypto_config`).
   - Register a systemd service named **`mqtt_transfer`**.

5. **Enable and start the service**
   ```bash
   sudo systemctl enable mqtt_transfer
   sudo systemctl start mqtt_transfer
   sudo systemctl status mqtt_transfer
   ```

---

## Configuration

The installer will create a config.toml file in MqttRelay's root directory. Here are the main configuration:

```toml
# Flask
host = "0.0.0.0"
port = #web app port
ssl = false # set to true if directly served with ssl 
ssl_key = "resources/key.pem"
ssl_cert = "resources/cert.pem"
ssl_encapsulated = # set to true if served behind a reverse proxy 
secret_key = # leaving it empty will generate a new one each server launch
default_language="fr"

[mqtt]
broker_url = # Mqtt Broker url
broker_port = # Mqtt Broker port
username = # Mqtt Broker user
password = # Mqtt Broker password
```

> The installer can persist these in a systemd environment file for `mqtt_transfer` (or you can manage them with your secrets manager).

---

## Running

- **Service** (for parsed data distribution on clients):
  ```bash
  sudo systemctl enable --now mqtt_transfer
  journalctl -u mqtt_transfer -f
  ```

- **Web dashboard**:
  ```bash
  source venv/bin/activate
  ./run.sh
  ```

---

## Dashboard

### Clients & Devices

- **Clients page**: list/view/edit client profile.
- **Client view**:
  - Edit client details (AJAX PUT to `clients.editClient`).
  - Devices table with add/delete:
    - Fields include `name`, `device_type_id`, `external_ref`, `topic`, `installed`, `working`, **emission_rate (seconds)**, optional `metadata_json`.
    - Device types are fetched from `devices.listDevices`.
    - Endpoints used: `clients.addDevice` (POST), `clients.deleteDevice` (DELETE).
  - Stats widgets: Projects, Latest Data Point, Invoices.

### Parsers

- **List parsers**: ID, name, version, language, active status, description.
- **Create parser** (`parsers.createParser`):
  - Name **alphanumeric + spaces only**.
  - Version **`x.x.x`** (semantic: digits only).
  - Optional `language` (`python`, `javascript`, `sql`, …).
  - Optional `config_schema` (JSON) to drive UI validation/auditing.
- **View/Edit/Delete parser**:
  - Edit modal enforces same name/version rules, formats JSON, toggles Active.
  - Delete uses `parsers.deleteParser`.

Schema recap:
- `parsers`, `extractions`, `parsed_points`, `metric_catalog` (see [Database Schema](#database-schema-high-level)).

### Settings

Two tabs:

1. **User**
   - Profile: email (with **Confirm Email** when changed), language, “Allow analytics tracking”.
   - Change Password: current, new (min 8), confirm.

2. **System**
   - **Metric Catalog**: add/delete known metrics:
     - `key_name` (alphanumeric/underscore), `default_unit`, `digupagri_ref` (3 chars), `description`.
     - Endpoints: `metrics.createMetric` (POST), `metrics.deleteMetric` (DELETE).
   - **Secrets & Encryption**:
     - Choose algorithm: **AES-256-GCM**, **ChaCha20-Poly1305**, **AES-256-CBC+HMAC**.
     - Choose key source: `env` (recommended), `kms` (custom integration), or `db`.
     - Set key alias/ID, IV/tag sizes, encoding.
     - **Test** encrypt/decrypt, **Rotate** key, **Re-encrypt** stored secrets.
     - Endpoints:
       - `GET  /crypto/config`          → `crypto.getConfig`
       - `PUT  /crypto/config`          → `crypto.updateConfig`
       - `POST /crypto/test`            → `crypto.test`
       - `POST /crypto/rotate`          → `crypto.rotateKey`
       - `POST /crypto/reencrypt`       → `crypto.reencrypt`

---

## REST Endpoints (selected)

> Names as referenced by templates/scripts; adapt to your Flask blueprint layout.

- **Clients**
  - `GET  clients.listClients`
  - `GET  clients.viewClient(client_id)`
  - `PUT  clients.editClient(client_id)`
  - `POST clients.addDevice(client_id)`
  - `DELETE clients.deleteDevice(client_id, device_id)`

- **Devices**
  - `GET  devices.listDevices` (returns device type options for UI)

- **Parsers**
  - `GET  parsers.listParsers`
  - `GET  parsers.viewParser(parser_id)`
  - `GET  parsers.newParser`
  - `POST parsers.createParser`
  - `PUT  parsers.updateParser(parser_id)`
  - `DELETE parsers.deleteParser(parser_id)`

- **Settings**
  - **User**
    - `PUT users.editUser(user_id)` (email, language, track)
    - `PUT users.changePassword(user_id)`
  - **Metrics**
    - `POST metrics.createMetric`
    - `DELETE metrics.deleteMetric(metric_id)`
  - **Crypto**
    - `GET/PUT /crypto/config`
    - `POST   /crypto/test`
    - `POST   /crypto/rotate`
    - `POST   /crypto/reencrypt`

---

## Development Notes

- **Frontend**: Jinja2 templates using **Bootstrap 5** and **Bootstrap Icons**, with unobtrusive JS (fetch API + CSRF header).
- **Validation**:
  - Parser **name**: `^[A-Za-z0-9 ]+$`
  - Parser **version**: `^[0-9]+(\.[0-9]+){2}$` (e.g., `1.2.3`)
  - Metric **key_name**: `^[A-Za-z0-9_]+$`
- **Crypto module**: `crypto_envelopes.py` implements all three reversible ciphers with versioned tokens.

---

## Troubleshooting

- **Data isn't sent to the clients**
  - `systemctl status mqtt_transfer` and `journalctl -u mqtt_transfer -f`
  - Verify `DATABASE_URL`, MQTT env vars, and that MySQL is reachable.
- **Encryption config errors**
  - Ensure `MQTT_RELAY_ENC_KEY_<KEY_ID>` is set if `key_source=env` and is **32 bytes** (base64 or hex).
  - After rotation, run **Re-encrypt** in Settings to migrate existing secrets.

---

## License

MIT. See `LICENSE` file.