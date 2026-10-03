#!/usr/bin/env python3
"""
One-off data migration: copy MqttRelay data from the old MySQL database into
the new PostgreSQL database (used when moving docker-compose.dev.yml from
MySQL to PostgreSQL persistence).

Usage (from repo root, with both databases reachable):

    python3 docker/migrate_mysql_to_postgres.py \\
        --mysql-host 127.0.0.1 --mysql-port 3307 \\
        --mysql-user root --mysql-password root --mysql-db mqttrelay \\
        --pg-host 127.0.0.1 --pg-port 5432 \\
        --pg-user mqttrelay --pg-password mqttrelay --pg-db mqttrelay

All arguments have sensible defaults matching docker-compose.dev.yml's
published ports. Safe to re-run: every table is upserted by primary key
(ON CONFLICT DO UPDATE), so running it twice just refreshes the rows.

Known, deliberately-skipped data (documented, not a bug):
- `device.installed` / `device.working`: no destination column, folded into
  the new `status`/`active` columns on a best-effort basis instead.
- `latest_value`: not modeled at all in the new schema (materialized/derived
  table, was empty in production anyway).
"""
import argparse
import sys

import pymysql
import psycopg2
import psycopg2.extras


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mysql-host", default="127.0.0.1")
    p.add_argument("--mysql-port", type=int, default=3307)
    p.add_argument("--mysql-user", default="root")
    p.add_argument("--mysql-password", default="root")
    p.add_argument("--mysql-db", default="mqttrelay")
    p.add_argument("--pg-host", default="127.0.0.1")
    p.add_argument("--pg-port", type=int, default=5432)
    p.add_argument("--pg-user", default="mqttrelay")
    p.add_argument("--pg-password", default="mqttrelay")
    p.add_argument("--pg-db", default="mqttrelay")
    p.add_argument("--dry-run", action="store_true", help="Print what would be migrated without writing to PostgreSQL.")
    return p.parse_args()


def fetch_all(mysql_conn, table):
    with mysql_conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute(f"SELECT * FROM `{table}`")
        return cur.fetchall()


def upsert(pg_conn, table, columns, rows, pk, conflict_col=None):
    if not rows:
        return 0
    conflict_col = conflict_col or pk
    cols_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_cols = [c for c in columns if c != conflict_col]
    conflict_action = (
        "DO NOTHING" if not update_cols
        else "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    )
    sql = (
        f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders}) '
        f"ON CONFLICT ({conflict_col}) {conflict_action}"
    )
    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(sql, [row.get(c) for c in columns])
    pg_conn.commit()
    return len(rows)


def bump_serial_sequence(pg_conn, table, pk):
    """After inserting explicit integer PKs, advance the SERIAL sequence past the max id."""
    with pg_conn.cursor() as cur:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), "
            f'COALESCE((SELECT MAX({pk}) FROM "{table}"), 1))'
        )
    pg_conn.commit()


def migrate_simple(mysql_conn, pg_conn, table, columns, pk, dry_run, rename=None, bump_serial=False, bool_columns=None, conflict_col=None):
    """Copy a table 1:1 (optionally renaming a source column) with no other transformation."""
    rename = rename or {}
    bool_columns = bool_columns or set()
    src_rows = fetch_all(mysql_conn, table)
    mapped = []
    for row in src_rows:
        mapped_row = {dst: row.get(rename.get(dst, dst)) for dst in columns}
        for col in bool_columns:
            if mapped_row.get(col) is not None:
                mapped_row[col] = bool(mapped_row[col])
        mapped.append(mapped_row)
    print(f"[migrate] {table}: {len(src_rows)} row(s) read from MySQL")
    if dry_run:
        return
    n = upsert(pg_conn, table, columns, mapped, pk, conflict_col=conflict_col)
    if bump_serial:
        bump_serial_sequence(pg_conn, table, pk)
    print(f"[migrate] {table}: {n} row(s) upserted into PostgreSQL")


def migrate_device(mysql_conn, pg_conn, dry_run):
    """`device` fields diverged between the old and new schema — map explicitly."""
    src_rows = fetch_all(mysql_conn, "device")
    columns = [
        "id", "client_id", "device_type_id", "topic", "name", "external_ref",
        "description", "location", "metadata_json", "active", "status", "emission_rate", "created_at",
    ]
    mapped = []
    for row in src_rows:
        working = bool(row.get("working"))
        installed = bool(row.get("installed"))
        mapped.append({
            "id": row["id"],
            "client_id": row["client_id"],
            "device_type_id": row["device_type_id"],
            "topic": row["topic"],
            "name": row["name"],
            "external_ref": row.get("external_ref") or None,
            "description": None,
            "location": None,
            "metadata_json": row.get("metadata_json") or None,
            "active": working,
            "status": "online" if working else ("installed" if installed else "unknown"),
            "emission_rate": row.get("emission_rate"),
            "created_at": row["created_at"],
        })
    print(f"[migrate] device: {len(src_rows)} row(s) read from MySQL")
    if dry_run:
        return
    n = upsert(pg_conn, "device", columns, mapped, "id")
    bump_serial_sequence(pg_conn, "device", "id")
    print(f"[migrate] device: {n} row(s) upserted into PostgreSQL")


def migrate_parser(mysql_conn, pg_conn, dry_run):
    """`parser` never had `created_at` in MySQL — default it to now."""
    import datetime
    src_rows = fetch_all(mysql_conn, "parser")
    columns = ["id", "name", "version", "description", "language", "config_schema", "active", "created_at"]
    mapped = []
    for row in src_rows:
        mapped.append({
            "id": row["id"],
            "name": row["name"],
            "version": row["version"],
            "description": row.get("description") or None,
            "language": row["language"],
            "config_schema": row.get("config_schema") or None,
            "active": bool(row["active"]),
            "created_at": datetime.datetime.utcnow(),
        })
    print(f"[migrate] parser: {len(src_rows)} row(s) read from MySQL (created_at defaulted to now)")
    if dry_run:
        return
    n = upsert(pg_conn, "parser", columns, mapped, "id")
    bump_serial_sequence(pg_conn, "parser", "id")
    print(f"[migrate] parser: {n} row(s) upserted into PostgreSQL")


def main():
    args = parse_args()

    mysql_conn = pymysql.connect(
        host=args.mysql_host, port=args.mysql_port,
        user=args.mysql_user, password=args.mysql_password, database=args.mysql_db,
        charset="utf8mb4",
    )
    pg_conn = None
    if not args.dry_run:
        pg_conn = psycopg2.connect(
            host=args.pg_host, port=args.pg_port,
            user=args.pg_user, password=args.pg_password, dbname=args.pg_db,
        )

    try:
        # Order matters: parents before children (FK dependencies).
        migrate_simple(mysql_conn, pg_conn, "language", ["code", "name"], "code", args.dry_run)
        migrate_simple(mysql_conn, pg_conn, "privilege", ["id", "label", "roles", "editable"], "id", args.dry_run, bool_columns={"editable"}, conflict_col="label")
        migrate_simple(
            mysql_conn, pg_conn, "user",
            ["id", "privilege_id", "email", "password", "is_authenticated", "is_active", "is_disabled", "language", "track"],
            "id", args.dry_run, rename={"privilege_id": "privilege"}, bool_columns={"is_authenticated", "is_active", "is_disabled", "track"},
        )
        migrate_simple(mysql_conn, pg_conn, "client", ["id", "slug", "name", "contact_email", "phone", "status", "created_at"], "id", args.dry_run, bump_serial=True)
        migrate_simple(mysql_conn, pg_conn, "device_type", ["id", "vendor", "model", "kind", "capabilities", "payload_schema", "defaults_json", "notes", "created_at"], "id", args.dry_run, bump_serial=True)
        migrate_device(mysql_conn, pg_conn, args.dry_run)
        migrate_simple(mysql_conn, pg_conn, "client_destination", ["id", "client_id", "type", "host", "port", "database_name", "username", "password_enc", "encryption_version", "uri", "options_json", "active"], "id", args.dry_run, bump_serial=True, bool_columns={"active"})
        migrate_simple(mysql_conn, pg_conn, "mqtt_topic", ["id", "topic", "description", "qos_default", "active", "client_id", "device_id", "created_at"], "id", args.dry_run, bump_serial=True, bool_columns={"active"})
        migrate_simple(mysql_conn, pg_conn, "mqtt_broker", ["id", "name", "uri", "client_id", "auth_json", "last_seen_at", "active"], "id", args.dry_run, bump_serial=True, bool_columns={"active"})
        migrate_simple(mysql_conn, pg_conn, "mqtt_message", ["id", "client", "topic", "payload", "qos", "processed", "processor", "at"], "id", args.dry_run, bump_serial=True, bool_columns={"processed"})
        migrate_parser(mysql_conn, pg_conn, args.dry_run)
        migrate_simple(mysql_conn, pg_conn, "metric_catalog", ["id", "name", "unit", "type", "description", "default_unit", "active", "created_at"], "id", args.dry_run, bump_serial=True, bool_columns={"active"})
        migrate_simple(mysql_conn, pg_conn, "crypto_config", ["id", "algorithm", "key_source", "key_id", "iv_bytes", "tag_bytes", "encoding", "version", "updated_at"], "id", args.dry_run, bump_serial=True)
        migrate_simple(mysql_conn, pg_conn, "crypto_key", ["key_id", "key_b64", "version", "updated_at"], "key_id", args.dry_run)
        migrate_simple(mysql_conn, pg_conn, "routing_rule", ["id", "client_id", "topic_id", "device_id", "parser_id", "parser_config", "active", "priority", "conditions", "created_at"], "id", args.dry_run, bool_columns={"active"})
        migrate_simple(mysql_conn, pg_conn, "route_deposit", ["id", "rule_id", "destination_id", "created_at"], "id", args.dry_run, bump_serial=True)
        migrate_simple(mysql_conn, pg_conn, "extraction", ["id", "message_id", "parser_id", "parsed_at", "success", "error_text", "extracted_count"], "id", args.dry_run, bool_columns={"success"})
        migrate_simple(mysql_conn, pg_conn, "parsed_point", ["id", "extraction_id", "device_id", "metric_id", "ts", "num_value", "str_value", "bool_value", "json_value", "unit", "quality", "meta_json", "created_at"], "id", args.dry_run, bump_serial=True, bool_columns={"bool_value"})
        migrate_simple(mysql_conn, pg_conn, "dispatch", ["id", "extraction_id", "deposit_id", "status", "attempts", "http_status", "response_snippet", "updated_at"], "id", args.dry_run, bump_serial=True)
        migrate_simple(mysql_conn, pg_conn, "job", ["name", "state", "last_state_update", "last_exit_code"], "name", args.dry_run)
        migrate_simple(mysql_conn, pg_conn, "mqtt_relay", ["version"], "version", args.dry_run)
    finally:
        mysql_conn.close()
        if pg_conn is not None:
            pg_conn.close()

    print("[migrate] done.")


if __name__ == "__main__":
    main()
