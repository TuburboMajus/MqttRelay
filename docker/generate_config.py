#!/usr/bin/env python3
"""
Generate /app/config.toml from environment variables.

Used by docker/entrypoint.sh when /app/config.toml does not yet exist.
See .env.example for the full list of supported variables.
"""
import os

import toml

CONFIG_FILE = "/app/config.toml"


def _env(name, default=""):
    return os.environ.get(name, default).strip()


def _env_bool(name, default=False):
    value = _env(name)
    if value == "":
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    value = _env(name)
    return int(value) if value else default


def build_config():
    return {
        "app": {
            "prod": _env_bool("APP_PROD", True),
            "host": _env("APP_HOST", "0.0.0.0"),
            "port": _env_int("APP_PORT", 23909),
            "threaded": _env_bool("APP_THREADED", True),
            "debug": _env_bool("APP_DEBUG", False),
            "log_level": _env("APP_LOG_LEVEL", "INFO"),
            "ssl": _env_bool("APP_SSL", False),
            "ssl_key": _env("APP_SSL_KEY", "resources/key.pem"),
            "ssl_cert": _env("APP_SSL_CERT", "resources/cert.pem"),
            "ssl_encapsulated": _env_bool("APP_SSL_ENCAPSULATED", False),
            "templates_folder": _env("APP_TEMPLATES_FOLDER", "front/templates"),
            "static_folder": _env("APP_STATIC_FOLDER", "front/static"),
            "secret_key": _env("APP_SECRET_KEY"),
            "default_language": _env("DEFAULT_LANGUAGE", "fr"),
        },
        "mqtt": {
            "broker_url": _env("MQTT_BROKER_URL", "localhost"),
            "broker_port": _env_int("MQTT_BROKER_PORT", 1883),
            "username": _env("MQTT_USERNAME"),
            "password": _env("MQTT_PASSWORD"),
            "keepalive": _env_int("MQTT_KEEPALIVE", 60),
            "tls_enabled": _env_bool("MQTT_TLS_ENABLED", False),
        },
        "temod": {
            "bound_database": _env("TEMOD_BOUND_DATABASE", "postgresql"),
            "core_directory": _env("TEMOD_CORE_DIRECTORY", "core"),
        },
        "storage": {
            "credentials": {
                "host": _env("DB_HOST", "127.0.0.1"),
                "port": _env_int("DB_PORT", 5432),
                "database": _env("DB_NAME", "mqttrelay"),
                "user": _env("DB_USER", "mqttrelay"),
                "password": _env("DB_PASSWORD"),
            }
        },
    }


def main():
    config = build_config()
    with open(CONFIG_FILE, "w") as f:
        toml.dump(config, f)
    print(f"[entrypoint] Generated {CONFIG_FILE}")


if __name__ == "__main__":
    main()
