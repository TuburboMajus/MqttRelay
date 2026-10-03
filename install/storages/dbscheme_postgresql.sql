-- PostgreSQL Schema for MqttRelay (SQLAlchemy-based)
-- Replaces the MySQL schema in install/storages/dbscheme.sql
-- To use this schema:
--   1. Create a PostgreSQL database and user
--   2. Connect with psql and run this file
--   3. Or use: psql -U mqtt -d mqtt < install/storages/dbscheme_postgresql.sql

-- ============ APP & SECURITY ============

CREATE TABLE IF NOT EXISTS mqtt_relay (
    version VARCHAR(20) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS language (
    code VARCHAR(10) PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
    name VARCHAR(50) PRIMARY KEY,
    state VARCHAR(20) NOT NULL DEFAULT 'IDLE',
    last_state_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_exit_code INTEGER
);

CREATE TABLE IF NOT EXISTS crypto_config (
    id SERIAL PRIMARY KEY,
    algorithm VARCHAR(50) NOT NULL DEFAULT 'aes-256-gcm',
    key_source VARCHAR(20) NOT NULL DEFAULT 'env',
    key_id VARCHAR(128) NOT NULL DEFAULT 'PRIMARY',
    iv_bytes INTEGER NOT NULL DEFAULT 12,
    tag_bytes INTEGER NOT NULL DEFAULT 16,
    encoding VARCHAR(20) NOT NULL DEFAULT 'base64',
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crypto_key (
    key_id VARCHAR(128) PRIMARY KEY,
    key_b64 VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP,
    UNIQUE(key_id, version)
);

CREATE TABLE IF NOT EXISTS privilege (
    id VARCHAR(36) PRIMARY KEY,
    label VARCHAR(256) NOT NULL UNIQUE,
    roles VARCHAR(256) NOT NULL,
    editable BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS "user" (
    id VARCHAR(36) PRIMARY KEY,
    privilege_id VARCHAR(36) NOT NULL REFERENCES privilege(id),
    email VARCHAR(320) NOT NULL UNIQUE,
    password BYTEA NOT NULL,
    is_authenticated BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
    language VARCHAR(256) NOT NULL DEFAULT 'en',
    track BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY(privilege_id) REFERENCES privilege(id)
);

CREATE INDEX idx_user_email ON "user"(email);

-- ============ MULTI-TENANT (CLIENT) ============

CREATE TABLE IF NOT EXISTS client (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255),
    phone VARCHAR(150),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS client_destination (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL,
    host VARCHAR(255),
    port INTEGER,
    database_name VARCHAR(255),
    username VARCHAR(255),
    password_enc BYTEA,
    encryption_version VARCHAR(130),
    uri VARCHAR(1024),
    options_json TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES client(id) ON DELETE CASCADE
);

-- ============ IOT (DEVICES) ============

CREATE TABLE IF NOT EXISTS device_type (
    id SERIAL PRIMARY KEY,
    vendor VARCHAR(128) NOT NULL,
    model VARCHAR(128) NOT NULL,
    kind VARCHAR(64) NOT NULL,
    capabilities TEXT,
    payload_schema TEXT,
    defaults_json TEXT,
    notes VARCHAR(512),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vendor, model)
);

CREATE TABLE IF NOT EXISTS device (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    device_type_id INTEGER NOT NULL REFERENCES device_type(id),
    topic VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    external_ref VARCHAR(128),
    description VARCHAR(512),
    location VARCHAR(512),
    metadata_json TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    emission_rate INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES client(id) ON DELETE CASCADE,
    FOREIGN KEY(device_type_id) REFERENCES device_type(id)
);

-- ============ MQTT ============

CREATE TABLE IF NOT EXISTS mqtt_topic (
    id SERIAL PRIMARY KEY,
    topic VARCHAR(255) NOT NULL UNIQUE,
    description VARCHAR(512),
    qos_default INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    client_id INTEGER REFERENCES client(id),
    device_id INTEGER REFERENCES device(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mqtt_message (
    id SERIAL PRIMARY KEY,
    client VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    payload TEXT,
    qos INTEGER NOT NULL DEFAULT 0,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processor VARCHAR(36),
    at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mqtt_msg_processed ON mqtt_message(processed);
CREATE INDEX idx_mqtt_msg_topic ON mqtt_message(topic);
CREATE INDEX idx_mqtt_msg_at ON mqtt_message(at);

CREATE TABLE IF NOT EXISTS mqtt_broker (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    uri VARCHAR(512) NOT NULL,
    client_id INTEGER REFERENCES client(id),
    auth_json TEXT,
    last_seen_at TIMESTAMP,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY(client_id) REFERENCES client(id)
);

-- ============ PARSERS ============

CREATE TABLE IF NOT EXISTS parser (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    description VARCHAR(512),
    language VARCHAR(50) NOT NULL DEFAULT 'python',
    config_schema TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);

CREATE TABLE IF NOT EXISTS metric_catalog (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    unit VARCHAR(50),
    type VARCHAR(50) NOT NULL,
    description VARCHAR(512),
    default_unit VARCHAR(50),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extraction (
    id VARCHAR(36) PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES mqtt_message(id),
    -- Audit of what ran: intentionally no FK so extractions survive parser deletion.
    parser_id INTEGER,
    parser_config TEXT,
    parsed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    extracted_count INTEGER,
    error_text TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(message_id) REFERENCES mqtt_message(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS parsed_point (
    id SERIAL PRIMARY KEY,
    extraction_id VARCHAR(36) NOT NULL REFERENCES extraction(id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL,
    metric_id INTEGER NOT NULL REFERENCES metric_catalog(id),
    ts TIMESTAMP NOT NULL,
    num_value FLOAT,
    str_value VARCHAR(1024),
    bool_value BOOLEAN,
    json_value TEXT,
    unit VARCHAR(50),
    quality VARCHAR(20) NOT NULL DEFAULT 'good',
    meta_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(extraction_id) REFERENCES extraction(id) ON DELETE CASCADE,
    FOREIGN KEY(metric_id) REFERENCES metric_catalog(id),
    FOREIGN KEY(device_id) REFERENCES device(id)
);

CREATE INDEX idx_parsed_point_ts ON parsed_point(ts);
CREATE INDEX idx_parsed_point_metric ON parsed_point(metric_id);

-- ============ ROUTING ============

CREATE TABLE IF NOT EXISTS routing_rule (
    id VARCHAR(36) PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES mqtt_topic(id),
    device_id INTEGER REFERENCES device(id),
    parser_id INTEGER NOT NULL REFERENCES parser(id),
    parser_config TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 100,
    conditions TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(client_id) REFERENCES client(id) ON DELETE CASCADE
);

CREATE INDEX idx_route_client ON routing_rule(client_id);
CREATE INDEX idx_route_active ON routing_rule(active);

CREATE TABLE IF NOT EXISTS route_deposit (
    id SERIAL PRIMARY KEY,
    rule_id VARCHAR(36) NOT NULL REFERENCES routing_rule(id) ON DELETE CASCADE,
    destination_id INTEGER NOT NULL REFERENCES client_destination(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(rule_id) REFERENCES routing_rule(id) ON DELETE CASCADE,
    FOREIGN KEY(destination_id) REFERENCES client_destination(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dispatch (
    id SERIAL PRIMARY KEY,
    extraction_id VARCHAR(36) NOT NULL REFERENCES extraction(id),
    deposit_id INTEGER NOT NULL REFERENCES route_deposit(id),
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 1,
    http_status INTEGER,
    response_snippet TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(extraction_id) REFERENCES extraction(id) ON DELETE CASCADE,
    FOREIGN KEY(deposit_id) REFERENCES route_deposit(id) ON DELETE CASCADE
);

CREATE INDEX idx_dispatch_status ON dispatch(status);

-- ============ INITIAL DATA ============

-- Insert default language
INSERT INTO language (code, name) VALUES 
    ('en', 'English'),
    ('fr', 'Français'),
    ('es', 'Español'),
    ('ar', 'العربية')
ON CONFLICT DO NOTHING;

-- Insert default privilege (admin)
INSERT INTO privilege (id, label, roles, editable) VALUES
    ('admin-privilege', 'admin', 'admin', TRUE)
ON CONFLICT DO NOTHING;

-- Insert default crypto config
INSERT INTO crypto_config (id, algorithm, key_source, key_id) VALUES
    (1, 'aes-256-gcm', 'env', 'PRIMARY')
ON CONFLICT DO NOTHING;
