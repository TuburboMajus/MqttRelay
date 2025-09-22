from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

import pymysql
from flask import Blueprint, request, jsonify

bp = Blueprint("dashboard_dispatch_status", __name__)

# ---------- helpers ----------

def _parse_range_to_seconds(s: str) -> int:
    if not s:
        return 24 * 60 * 60
    s = s.strip().lower()
    try:
        if s.endswith("m"): return int(s[:-1]) * 60
        if s.endswith("h"): return int(s[:-1]) * 3600
        if s.endswith("d"): return int(s[:-1]) * 86400
        return int(s) * 60  # bare minutes
    except Exception:
        return 24 * 60 * 60

def _auto_bucket(seconds: int) -> int:
    if seconds <= 2 * 3600:   return 60      # 1m
    if seconds <= 6 * 3600:   return 300     # 5m
    if seconds <= 24 * 3600:  return 900     # 15m
    if seconds <= 7 * 86400:  return 3600    # 60m
    return 10800                              # 180m

def _floor_to_bucket(ts: datetime, bucket_sec: int) -> datetime:
    epoch = int(ts.timestamp())
    floored = (epoch // bucket_sec) * bucket_sec
    return datetime.fromtimestamp(floored, tz=timezone.utc)

def _time_axis(since: datetime, until: datetime, bucket_sec: int) -> List[datetime]:
    out = []
    cur = since
    while cur <= until:
        out.append(cur)
        cur += timedelta(seconds=bucket_sec)
    return out

# ---------- core ----------

def compute(
    range_str: str = "24h",
    client_id: Optional[int] = None,
    client_slug: Optional[str] = None,
    bucket: Optional[str] = "auto",
) -> Dict[str, Any]:
    """
    Build a stacked time series (Chart.js payload) of dispatch counts per status.
    Uses dispatch.created_at as the timeline.

    Joins to scope per-client:
      dispatch.destination_id -> client_destination(client_id) -> client
      dispatch.rule_id        -> routing_rule(client_id)       -> client

    Returns:
      { "labels": [...],
        "datasets": [
          {"label":"queued","data":[...]}, {"label":"retrying","data":[...]},
          {"label":"failed","data":[...]}, {"label":"dead","data":[...]},
          {"label":"sent","data":[...]}
        ]
      }
    """
    window_sec = max(_parse_range_to_seconds(range_str), 60)
    bucket_sec = _auto_bucket(window_sec) if (not bucket or bucket == "auto") else _parse_range_to_seconds(bucket)

    now_utc = datetime.now(timezone.utc)
    until = _floor_to_bucket(now_utc, bucket_sec)
    since = _floor_to_bucket(now_utc - timedelta(seconds=window_sec), bucket_sec)

    statuses = ["queued", "retrying", "failed", "dead", "sent"]  # consistent order

    joins = [
        "LEFT JOIN client_destination cd ON cd.id = d.destination_id",
        "LEFT JOIN client c1 ON c1.id = cd.client_id",
        "LEFT JOIN routing_rule rr ON rr.id = d.rule_id",
        "LEFT JOIN client c2 ON c2.id = rr.client_id",
    ]
    where = [f"d.created_at >= '{since.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')}'", f"d.created_at < '{(until + timedelta(seconds=bucket_sec)).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')}'"]

    if client_id is not None:
        where.append(f"(c1.id = {client_id} OR c2.id = {client_id})")
    elif client_slug:
        # filter by client slug if provided as non-integer
        where.append(f"(c1.slug = {client_slug} OR c2.slug = {client_slug})")

    sql = f"""
        SELECT
          FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(d.created_at)/{bucket_sec})*{bucket_sec}) AS bucket_ts,
          d.status,
          COUNT(*) AS cnt
        FROM dispatch d
        {' '.join(joins)}
        WHERE {" AND ".join(where)}
        GROUP BY bucket_ts, d.status
        ORDER BY bucket_ts
    """

    # Collect counts
    grid: Dict[datetime, Dict[str, int]] = {}
    conn: pymysql.connections.Connection = pymysql.connections.Connection(**{k:v for k,v in Dispatch.storage.credentials.items() if k != "auth_plugin"})
    with conn.cursor() as cur:
        cur.execute(sql, [])
        for row in cur.fetchall():
            bts = row[0] if isinstance(row, tuple) else row["bucket_ts"]
            status = row[1] if isinstance(row, tuple) else row["status"]
            cnt = int(row[2] if isinstance(row, tuple) else row["cnt"])
            if bts.tzinfo is None:
                bts = bts.replace(tzinfo=timezone.utc)
            bucket_map = grid.setdefault(bts, {})
            bucket_map[status] = cnt

    # Build full axis and datasets
    axis = _time_axis(since, until, bucket_sec)
    labels = [dt.strftime("%Y-%m-%d %H:%M") for dt in axis]
    datasets = []
    for s in statuses:
        datasets.append({
            "label": s,
            "data": [grid.get(dt, {}).get(s, 0) for dt in axis]
        })

    return {"labels": labels, "datasets": datasets}