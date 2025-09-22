/******************************\
 *  INITIALIZE
\******************************/ 

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET sql_require_primary_key = 0;

drop database IF EXISTS $database;
create database $database;
use $database;

-- =========================
-- 1) APP
-- =========================

create table mqtt_relay(
    version varchar(20) primary key not null
);

create table if not exists language(
    code varchar(2) primary key not null,
    name varchar(50) not null
);

create table if not exists job(
    name varchar(50) primary key not null,
    state varchar(20) not null default "IDLE",
    last_state_update datetime not null,
    last_exit_code int
);

-- =========================
-- 2) USERS
-- =========================
create table privilege(
    id varchar(36) primary key not null,
    label varchar(256) not null unique,
    roles varchar(256) not null,
    editable bool not null default 1
);

create table user(
    id varchar(36) primary key not null,
    privilege varchar(36) not null,
    email varchar(320) not null,
    password binary(60) not null,
    is_authenticated bool not null default 0,
    is_active bool not null default 0,
    is_disabled bool not null default 0,
    language varchar(256) not null default "en",
    track bool not null default 0,
    foreign key (privilege) references privilege(id)
);

-- =========================
-- 3) Tenants / Clients
-- =========================
CREATE TABLE client (
  id            BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  slug          VARCHAR(64)  NOT NULL UNIQUE,
  name          VARCHAR(255) NOT NULL,
  contact_email VARCHAR(255),
  status        ENUM('active','paused','disabled') NOT NULL DEFAULT 'active',
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Optional: multiple target sinks per client (DBs, HTTP, files, etc.)
CREATE TABLE client_destination (
  id             BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  client_id      BIGINT UNSIGNED NOT NULL,
  type           ENUM('mysql','postgres','http','kafka','file','other') NOT NULL,
  host           VARCHAR(255),
  port           INT,
  database_name  VARCHAR(255),
  username       VARCHAR(255),
  -- Store encrypted/externally-managed secret; avoid plaintext.
  password_enc   VARBINARY(1024),
  encryption_version   VARCHAR(130),
  uri            VARCHAR(1024),          -- e.g. HTTP endpoint or DSN
  options_json   JSON,                    -- e.g. SSL params, schema, table, headers
  active         TINYINT(1) NOT NULL DEFAULT 1,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_dest_client
    FOREIGN KEY (client_id) REFERENCES client(id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

-- =========================
-- 4) Devices & Topics
-- =========================
CREATE TABLE device_type (
  id             BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  vendor         VARCHAR(128)  NOT NULL,          -- e.g., Dragino, Bosch
  model          VARCHAR(128)  NOT NULL,          -- e.g., LSE01, BME280
  kind           VARCHAR(64)   NOT NULL,          -- sensor, gateway, meter, etc.
  capabilities   JSON NULL,                        -- e.g., ["temperature","humidity","soil_moisture"]
  payload_schema JSON NULL,                        -- JSON schema or hints for parsing
  defaults_json  JSON NULL,                        -- default units, scaling, meta
  notes          VARCHAR(512),
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_vendor_model_rev (vendor, model)
) ENGINE=InnoDB;

-- Update devices to reference device_types
CREATE TABLE device (
  id             BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  client_id      BIGINT UNSIGNED,
  device_type_id BIGINT UNSIGNED NOT NULL,        -- <— FK to device_types
  external_ref   VARCHAR(128),                    -- vendor serial / custom id
  name           VARCHAR(255),
  metadata_json  JSON,                            -- per-device overrides/meta
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_dev_client
    FOREIGN KEY (client_id) REFERENCES client(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_dev_type
    FOREIGN KEY (device_type_id) REFERENCES device_type(id)
    ON DELETE RESTRICT,
  KEY idx_dev_client (client_id),
  KEY idx_dev_type (device_type_id)
) ENGINE=InnoDB;

-- =========================
-- 5) Mqtt
-- =========================

CREATE TABLE mqtt_topic (
  id            BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  topic         VARCHAR(255) NOT NULL UNIQUE,
  description   VARCHAR(512),
  qos_default   TINYINT UNSIGNED DEFAULT 0,
  active        TINYINT(1) NOT NULL DEFAULT 1,
  client_id     BIGINT UNSIGNED,
  device_id     BIGINT UNSIGNED,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_topic_client
    FOREIGN KEY (client_id) REFERENCES client(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_topic_device
    FOREIGN KEY (device_id) REFERENCES device(id)
    ON DELETE SET NULL
) ENGINE=InnoDB;

-- Optional: support multiple brokers/subscriptions
CREATE TABLE mqtt_broker (
  id           BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  name         VARCHAR(128) NOT NULL,
  uri          VARCHAR(512) NOT NULL,     -- mqtt[s]://host:port
  client_id    BIGINT UNSIGNED,
  auth_json    JSON,                       -- username/cert paths/etc. (no plaintext secrets)
  last_seen_at TIMESTAMP NULL,
  active       TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT fk_broker_client
    FOREIGN KEY (client_id) REFERENCES client(id)
    ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mqtt_message (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    client VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    payload TEXT NULL,
    qos TINYINT UNSIGNED NOT NULL DEFAULT 0,
    at DATETIME NOT NULL,
    processed bool NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    INDEX idx_topic_received (topic, at),
    INDEX idx_received (at)
);

-- =========================
-- 6) Parsing / Extraction
-- =========================
CREATE TABLE parser (
  id            BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  name          VARCHAR(128) NOT NULL,
  version       VARCHAR(32)  NOT NULL,
  description   VARCHAR(512),
  language      VARCHAR(32),             -- e.g. python, js, sql
  config_schema JSON,                    -- schema for parser config
  active        TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_parser (name, version)
) ENGINE=InnoDB;

CREATE TABLE extraction (
  id             VARCHAR(36) PRIMARY KEY,
  message_id     BIGINT UNSIGNED NOT NULL,
  parser_id      BIGINT UNSIGNED NOT NULL,
  parser_config  JSON,                   -- instance config actually used
  parsed_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  success        TINYINT(1) NOT NULL,
  error_text     TEXT,
  extracted_count INT UNSIGNED NOT NULL DEFAULT 0,
  CONSTRAINT fk_ext_msg
    FOREIGN KEY (message_id) REFERENCES mqtt_message(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_ext_parser
    FOREIGN KEY (parser_id) REFERENCES parser(id)
    ON DELETE RESTRICT,
  KEY idx_ext_msg (message_id),
  KEY idx_ext_parser (parser_id),
  KEY idx_ext_parsed_at (parsed_at)
) ENGINE=InnoDB;

-- Dictionary of metrics/fields your pipeline recognizes
CREATE TABLE metric_catalog (
  id            BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  key_name      VARCHAR(128) NOT NULL UNIQUE,  -- e.g. 'soil_moisture', 'battery'
  default_unit  VARCHAR(32),
  description   VARCHAR(512),
  digiupagri_ref varchar(3)
) ENGINE=InnoDB;

-- Normalized time-series points coming out of parsing
CREATE TABLE parsed_point (
  id            BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  extraction_id VARCHAR(36) NOT NULL,
  device_id     BIGINT UNSIGNED,
  metric_id     BIGINT UNSIGNED,
  ts            DATETIME(6) NOT NULL,       -- UTC
  num_value     DECIMAL(20,8) NULL,
  str_value     VARCHAR(1024) NULL,
  bool_value    TINYINT(1) NULL,
  json_value    JSON NULL,                  -- complex sub-objects/arrays
  unit          VARCHAR(32),
  quality       ENUM('good','suspect','bad') NOT NULL DEFAULT 'good',
  meta_json     JSON,
  CONSTRAINT fk_pp_ext
    FOREIGN KEY (extraction_id) REFERENCES extraction(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_pp_dev
    FOREIGN KEY (device_id) REFERENCES device(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_pp_metric
    FOREIGN KEY (metric_id) REFERENCES metric_catalog(id)
    ON DELETE SET NULL,
  KEY idx_pp_device_ts (device_id, ts),
  KEY idx_pp_key_ts (metric_id, ts),
  KEY idx_pp_ts (ts)
) ENGINE=InnoDB;

-- Optional materialized “latest” cache (maintained by app/jobs)
CREATE TABLE latest_value (
  device_id   BIGINT UNSIGNED NOT NULL,
  key_name    VARCHAR(128) NOT NULL,
  ts          DATETIME(6) NOT NULL,
  num_value   DECIMAL(20,8),
  str_value   VARCHAR(1024),
  bool_value  TINYINT(1),
  json_value  JSON,
  unit        VARCHAR(32),
  quality     ENUM('good','suspect','bad') NOT NULL DEFAULT 'good',
  meta_json   JSON,
  PRIMARY KEY (device_id, key_name),
  KEY idx_lv_ts (ts),
  CONSTRAINT fk_lv_device
    FOREIGN KEY (device_id) REFERENCES device(id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

-- =========================
-- 7) Routing Helpers
-- =========================
-- Explicit mapping of topics/devices to clients (overrides mqtt_topics.client_id)
CREATE TABLE routing_rule (
  id           VARCHAR(36) PRIMARY KEY NOT NULL,
  client_id    BIGINT UNSIGNED NOT NULL,
  topic_id     BIGINT UNSIGNED NULL,
  device_id    BIGINT UNSIGNED NULL,
  parser_id    BIGINT UNSIGNED NULL,
  parser_config   JSON,
  active       TINYINT(1) NOT NULL DEFAULT 1,
  priority     INT NOT NULL DEFAULT 100,   -- lower = higher priority
  conditions   JSON,                       -- e.g. payload predicates, key filters
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_rr_client
    FOREIGN KEY (client_id) REFERENCES client(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_rr_topic
    FOREIGN KEY (topic_id) REFERENCES mqtt_topic(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_rr_device
    FOREIGN KEY (device_id) REFERENCES device(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_rr_parser
    FOREIGN KEY (parser_id) REFERENCES parser(id)
    ON DELETE SET NULL,
  KEY idx_rr_active_prio (active, priority)
) ENGINE=InnoDB;

CREATE TABLE route_deposit (
  rule_id    VARCHAR(36) NOT NULL,
  destination_id     BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (rule_id, destination_id),
  CONSTRAINT fk_rd_rule
    FOREIGN KEY (rule_id) REFERENCES routing_rule(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_rd_destination
    FOREIGN KEY (destination_id) REFERENCES client_destination(id)
    ON DELETE SET NULL,
) ENGINE=InnoDB;

CREATE TABLE dispatch (
  id               VARCHAR(36) PRIMARY KEY,
  extraction_id    VARCHAR(36) NOT NULL,
  destination_id   BIGINT UNSIGNED NOT NULL,
  rule_id          VARCHAR(36) NOT NULL,
  status           ENUM('queued','sent','failed','retrying','dead') NOT NULL DEFAULT 'queued',
  http_status      INT NULL,
  response_snippet TEXT,
  attempts         INT UNSIGNED NOT NULL DEFAULT 0,
  next_retry_at    DATETIME(6) NULL,
  sent_at          DATETIME(6) NULL,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_disp_ext
    FOREIGN KEY (extraction_id) REFERENCES extraction(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_disp_dest
    FOREIGN KEY (destination_id) REFERENCES client_destination(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_disp_rule
    FOREIGN KEY (rule_id) REFERENCES routing_rule(id)
    ON DELETE CASCADE,
  KEY idx_disp_status_next (status, next_retry_at),
  KEY idx_disp_created (created_at)
) ENGINE=InnoDB;

-- =========================
-- 8) Encryption
-- =========================
-- Reversible encryption settings (single-row table)
CREATE TABLE crypto_config (
  id            TINYINT UNSIGNED NOT NULL PRIMARY KEY,
  algorithm     ENUM('aes-256-gcm','chacha20-poly1305','aes-256-cbc-hmac') NOT NULL DEFAULT 'aes-256-gcm',
  key_source    ENUM('env','kms','db') NOT NULL DEFAULT 'env',
  key_id        VARCHAR(128) NOT NULL DEFAULT 'PRIMARY',
  iv_bytes      TINYINT UNSIGNED NOT NULL DEFAULT 12,
  tag_bytes     TINYINT UNSIGNED NOT NULL DEFAULT 16,
  encoding      ENUM('base64','hex') NOT NULL DEFAULT 'base64',
  version       INT UNSIGNED NOT NULL DEFAULT 1,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  -- sanity checks
  CONSTRAINT chk_crypto_cfg_single_row CHECK (id = 1),
  CONSTRAINT chk_crypto_cfg_iv_bytes    CHECK (iv_bytes BETWEEN 8 AND 32),
  CONSTRAINT chk_crypto_cfg_tag_bytes   CHECK (tag_bytes BETWEEN 12 AND 16),

  KEY idx_crypto_cfg_key_id (key_id)
) ENGINE=InnoDB;


CREATE TABLE crypto_key (
  key_id     VARCHAR(128) NOT NULL,
  version    INT UNSIGNED NOT NULL,
  key_b64    VARCHAR(64)  NOT NULL,  -- base64 of 32-byte key (typically 44 chars)
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (key_id, version)
) ENGINE=InnoDB;