from typing import Any, Dict, List
from datetime import datetime

import psycopg2
import json


class PostgresDispatcher(object):
    """Insert parsed_points into a client PostgreSQL database.

    Expected client_destination keys (row from client_destinations):
      - type: "postgres" (or "postgresql")
      - host, port, database_name, username
      - password (plaintext; the worker decrypts password_enc before calling)
      - options_json (dict or JSON string) with optional keys:
          table: str = target table name (default "parsed_points")
          column_map: dict[str,str] = {source_key -> dest_column}
              default maps the canonical parsed_points fields 1:1:
                {
                  "device_id":"device_id", "key_name":"key_name", "ts":"ts",
                  "value":"value", "unit":"unit",
                  "quality":"quality", "meta_json":"meta_json"
                }
          conflict_keys: list[str] = source keys that form the target UNIQUE key
                default ["device_id","key_name","ts"]
          on_conflict: "ignore" | "update" | "error"  (default "update";
                "ignore"/"update" require a unique constraint on conflict_keys)
          batch_size: int (default 1000)
    """

    def __init__(self, host="127.0.0.1", port=5432, database_name=None, username=None,
                 password=None, password_enc=None, **kwargs):
        super(PostgresDispatcher, self).__init__()
        self.host = host
        self.port = port
        self.database_name = database_name
        self.username = username
        self.password = password
        self.password_enc = password_enc
        self.opts = kwargs

    def _iso_to_dt(x: Any) -> Any:
        """Convert ISO-8601 strings to datetime; pass through others."""
        if isinstance(x, str):
            try:
                return datetime.fromisoformat(x.replace("Z", "+00:00"))
            except Exception:
                return x
        return x

    def dispatch(self, parsed_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Insert points; returns dict(status, http_status, response_snippet)."""
        table = self.opts.get("table", "parsed_points")
        column_map: Dict[str, str] = self.opts.get("column_map") or {
            "device_id": "device_id",
            "key_name": "key_name",
            "ts": "ts",
            "value": "value",
            "unit": "unit",
            "quality": "quality",
            "meta_json": "meta_json",
        }
        conflict_keys_src = self.opts.get("conflict_keys", ["device_id", "key_name", "ts"])
        on_conflict = self.opts.get("on_conflict", "update")  # ignore|update|error
        batch_size = int(self.opts.get("batch_size", 1000))

        src_keys = list(column_map.keys())
        dest_cols = [column_map[k] for k in src_keys]
        conflict_cols = [column_map[k] for k in conflict_keys_src if k in column_map]

        password = self.password
        if password is None and self.password_enc is not None:
            # password_enc holds a crypto-envelope token (v1.<alg>....) that
            # only the worker can decrypt (it has the master key); it must pass
            # the plaintext as `password`.
            return {
                "status": "failed",
                "http_status": None,
                "response_snippet": "Encrypted password provided without decryption; caller must decrypt password_enc.",
            }

        if not (self.username and self.database_name):
            return {
                "status": "failed",
                "http_status": None,
                "response_snippet": "Missing username or database_name for PostgreSQL destination.",
            }

        if not parsed_points:
            return {"status": "sent", "http_status": None, "response_snippet": "No points to send."}

        cols_sql = ", ".join(f'"{c}"' for c in dest_cols)
        placeholders = ", ".join(["%s"] * len(dest_cols))
        insert_sql = f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders})'

        if on_conflict == "ignore":
            insert_sql += " ON CONFLICT DO NOTHING"
        elif on_conflict == "update":
            if not conflict_cols:
                return {
                    "status": "failed",
                    "http_status": None,
                    "response_snippet": "on_conflict='update' requires conflict_keys present in column_map.",
                }
            conflict_sql = ", ".join(f'"{c}"' for c in conflict_cols)
            update_cols = [c for c in dest_cols if c not in conflict_cols]
            if update_cols:
                set_sql = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in update_cols)
                insert_sql += f" ON CONFLICT ({conflict_sql}) DO UPDATE SET {set_sql}"
            else:
                insert_sql += f" ON CONFLICT ({conflict_sql}) DO NOTHING"
        elif on_conflict != "error":
            return {
                "status": "failed",
                "http_status": None,
                "response_snippet": f"Unsupported on_conflict='{on_conflict}'.",
            }

        def _row_from_point(p: Dict[str, Any]) -> List[Any]:
            row: List[Any] = []
            meta = json.loads(p.get("meta_json") or "{}")
            for key in src_keys:
                val = p.get(key, None)
                if key == "ts":
                    val = PostgresDispatcher._iso_to_dt(val)
                elif key == "value":
                    non_null_value = [v for k, v in p.items() if k.endswith('_value') and v is not None]
                    if len(non_null_value) == 0:
                        raise Exception(f"Some parsed point has no values at all {p}")
                    elif len(non_null_value) > 1:
                        raise Exception(f"Some parsed point has multiple values {p}")
                    val = non_null_value[0]
                elif key == "device_id":
                    val = meta.get('devices', {}).get(str(val), val)
                elif key == "metric_id":
                    val = meta.get('metrics', {}).get(str(val), val)
                elif key in ("json_value", "meta_json") and val is not None and not isinstance(val, (str, bytes)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(val)
            return row

        try:
            conn = psycopg2.connect(
                host=self.host or "localhost",
                port=int(self.port or 5432),
                user=self.username,
                password=password or "",
                dbname=self.database_name,
            )
        except Exception as e:
            return {"status": "failed", "http_status": None, "response_snippet": f"Connect error: {e}"}

        total_rows = 0
        try:
            with conn.cursor() as cur:
                for i in range(0, len(parsed_points), batch_size):
                    batch = parsed_points[i:i + batch_size]
                    values = [_row_from_point(p) for p in batch]
                    cur.executemany(insert_sql, values)
                    conn.commit()
                    total_rows += len(batch)

            return {
                "status": "sent",
                "http_status": None,
                "response_snippet": f"table={table}; rows={total_rows}; mode={on_conflict}",
            }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()
