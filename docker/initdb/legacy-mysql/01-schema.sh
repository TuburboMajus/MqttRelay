#!/bin/bash
# ---------------------------------------------------------------------------
# MySQL init script — sourced by the official mysql:8.0 entrypoint on FIRST
# start (only when the data volume is empty).
#
# Applies the MqttRelay schema (install/storages/dbscheme.sql) and seeds the
# baseline rows the application needs. The first dashboard user is created from
# the /signup page (it is granted the `admin` role).
# ---------------------------------------------------------------------------
set -e

DB="${MYSQL_DATABASE}"

echo "[initdb] Applying MqttRelay schema to database '${DB}'..."
sed 's|\$database|'"${DB}"'|g' /schema/dbscheme.sql | docker_process_sql

echo "[initdb] Seeding baseline data..."
docker_process_sql <<EOSQL
INSERT IGNORE INTO language (code, name) VALUES
  ('fr', 'français'),
  ('en', 'English');

INSERT IGNORE INTO privilege (id, label, roles) VALUES
  ('00000000-0000-0000-0000-000000000001', 'admin', '*');

INSERT IGNORE INTO job (name, state, last_state_update, last_exit_code) VALUES
  ('MqttTransfer', 'IDLE', NOW(), 0);

INSERT IGNORE INTO crypto_config (id) VALUES (1);

INSERT IGNORE INTO mqtt_relay (version) VALUES ('1.0.1');
EOSQL

echo "[initdb] Database initialized."
