from typing import Any, Dict, List, Optional
from pymysql.cursors import Cursor
from datetime import datetime

import pymysql
import base64
import json



class MysqlDispatcher(object):
    """Insert parsed_points into a client MySQL database.

    Expected client_destination keys (row from client_destinations):
      - type: must be "mysql"
      - host, port, database_name, username
      - password or password_enc
      - options_json (dict or JSON string) with optional keys:
          table: str = target table name (default "parsed_points")
          column_map: dict[str,str] = {source_key -> dest_column}
              default maps the canonical parsed_points fields 1:1:
                {
                  "device_id":"device_id", "key_name":"key_name", "ts":"ts",
                  "num_value":"num_value", "str_value":"str_value",
                  "bool_value":"bool_value", "json_value":"json_value",
                  "unit":"unit", "quality":"quality", "meta_json":"meta_json"
                }
          conflict_keys: list[str] = source keys that form the target UNIQUE key
                default ["device_id","key_name","ts"]
          on_conflict: "ignore" | "update" | "error"  (default "ignore")
          batch_size: int (default 1000)
    """
    def __init__(self, host="127.0.0.1",port=3306, database_name=None, username=None, password=None, password_enc=None, **kwargs):
        super(MysqlDispatcher, self).__init__()
        self.host = host
        self.port = port
        self.database_name = database_name
        self.username = username
        self.password = password
        self.password_enc = password_enc
        self.opts = kwargs

    def _decode_secret(x: Any) -> Optional[str]:
        """
        Replace this with your KMS/valut decrypt. Here we accept either a plain string
        or bytes (as stored in password_enc) and decode utf-8.
        """
        if x is None:
            return None
        if isinstance(x, (bytes, bytearray)):
            try:
                return base64.b64decode(x).decode("utf-8")
            except Exception:
                return None
        if isinstance(x, str):
            return base64.b64decode(x.encode('utf-8')).decode("utf-8")
        return None

    def _iso_to_mysql_dt(x: Any) -> Any:
        """Convert ISO-8601 strings to datetime; pass through others."""
        if isinstance(x, str):
            try:
                # handle trailing Z
                x = x.replace("Z", "+00:00")
                return datetime.fromisoformat(x)
            except Exception:
                return x
        return x

    def dispatch(self, parsed_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        parsed_points item example (canonical):
          {
            "device_id": 123, "key_name": "soil_moisture", "ts": "2025-09-16T19:20:25Z",
            "num_value": 12.34, "str_value": None, "bool_value": None, "json_value": None,
            "unit":"%", "quality":"good", "meta_json": {"raw": "..."}
          }

        Returns:
          dict(status, http_status, response_snippet)
          - status: "sent" | "failed"
          - http_status: None (non-HTTP transport)
          - response_snippet: short human string (inserted/updated/ignored counts)
        """

        # Load options
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

        # Derive ordered destination columns from the mapping (stable order)
        src_keys = list(column_map.keys())
        dest_cols = [column_map[k] for k in src_keys]

        # Map conflict keys (source) to destination column names
        conflict_cols = [column_map[k] for k in conflict_keys_src if k in column_map]

        # Connection parameters
        host = self.host or "localhost"
        port = int(self.port or 3306)
        user = self.username
        dbname = self.database_name
        password = (self.password or MysqlDispatcher._decode_secret(self.password_enc))

        if not (user and dbname):
            return {
                "status": "failed",
                "http_status": None,
                "response_snippet": "Missing username or database_name for MySQL destination.",
            }

        if not parsed_points:
            return {
                "status": "sent",
                "http_status": None,
                "response_snippet": "No points to send.",
            }

        # Build base INSERT
        cols_sql = ", ".join(f"`{c}`" for c in dest_cols)
        placeholders = ", ".join(["%s"] * len(dest_cols))

        if on_conflict == "ignore":
            insert_sql = f"INSERT IGNORE INTO `{table}` ({cols_sql}) VALUES ({placeholders})"
            update_clause = ""
        elif on_conflict == "update":
            # Update all non-conflict columns to VALUES()
            update_cols = [c for c in dest_cols if c not in conflict_cols]
            if update_cols:
                set_sql = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in update_cols)
            else:
                # If conflict keys cover all columns, do nothing special
                set_sql = f"`{dest_cols[-1]}`=`{dest_cols[-1]}`"
            insert_sql = f"INSERT INTO `{table}` ({cols_sql}) VALUES ({placeholders})"
            update_clause = f" ON DUPLICATE KEY UPDATE {set_sql}"
        elif on_conflict == "error":
            insert_sql = f"INSERT INTO `{table}` ({cols_sql}) VALUES ({placeholders})"
            update_clause = ""
        else:
            return {
                "status": "failed",
                "http_status": None,
                "response_snippet": f"Unsupported on_conflict='{on_conflict}'.",
            }

        total_rows = 0
        inserted = 0
        updated = 0
        ignored = 0

        def _row_from_point(p: Dict[str, Any]) -> List[Any]:
            row: List[Any] = []
            meta = json.loads(p.get("meta_json","{}"))
            for key in src_keys:
                val = p.get(key, None)
                if key == "ts":
                    val = MysqlDispatcher._iso_to_mysql_dt(val)
                elif key == "value":
                    non_null_value = [v for k,v in p.items() if k.endswith('_value') and v is not None]
                    if len(non_null_value) == 0:
                        raise Exception(f"Some parsed point has no values at all {p}")
                    elif len(non_null_value) > 1:
                        raise Exception(f"Some parsed point has multiple values {p}")
                    val = non_null_value[0]
                elif key == "device_id":
                    val = meta.get('devices',{}).get(str(val), val)
                elif key == "metric_id":
                    val = meta.get('metrics',{}).get(str(val), val)
                elif key in ("json_value", "meta_json") and val is not None and not isinstance(val, (str, bytes)):
                    # Ensure JSON/text columns get serialized JSON
                    val = json.dumps(val, ensure_ascii=False)
                row.append(val)
            return row

        # Chunked batch insert
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password or "",
                database=dbname,
                charset="utf8mb4",
                autocommit=False,
            )
        except Exception as e:
            return {"status": "failed", "http_status": None, "response_snippet": f"Connect error: {e}"}

        try:
            with conn:
                with conn.cursor() as cur:  # type: Cursor
                    sql = insert_sql + update_clause
                    # Prepare batches
                    for i in range(0, len(parsed_points), batch_size):
                        batch = parsed_points[i : i + batch_size]
                        values = [_row_from_point(p) for p in batch]
                        print(values)
                        cur.executemany(sql, values)
                        conn.commit()

                        # Heuristic accounting:
                        # - INSERT IGNORE: rowcount ≈ inserted (ignores are 0)
                        # - ON DUPLICATE KEY UPDATE: affected rows counts inserts as 1, updates as 2 (or 0 if no-op)
                        rc = cur.rowcount if cur.rowcount is not None else 0
                        total_rows += len(batch)

                        if on_conflict == "ignore":
                            inserted += rc
                            ignored += len(batch) - rc
                        elif on_conflict == "update":
                            # Best effort split: assume up to rc//2 were updates and the rest inserts.
                            # (MySQL returns 2 per update row, 1 per insert, 0 per no-op)
                            # We estimate by preferring updates, then inserts.
                            upd_est = min(len(batch), rc // 2)
                            rem = rc - 2 * upd_est
                            ins_est = max(0, rem)
                            updated += upd_est
                            inserted += ins_est
                            # no-op updates counted as 0 -> treat as ignored
                            ignored += len(batch) - (upd_est + ins_est)
                        else:
                            inserted += rc  # "error" mode -> duplicates would have raised already

            return {
                "status": "sent",
                "http_status": None,
                "response_snippet": (
                    f"table={table}; rows={total_rows}; "
                    f"inserted≈{inserted}; updated≈{updated}; ignored≈{ignored}; mode={on_conflict}"
                ),
            }
        except Exception as e:
            conn.rollback()
            raise
