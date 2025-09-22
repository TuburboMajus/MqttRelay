from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

import pymysql


# ---------- helpers ----------

def _parse_range_to_seconds(s: str) -> int:
    if not s:
        return 2 * 60 * 60
    s = s.strip().lower()
    try:
        if s.endswith("m"): return int(s[:-1]) * 60
        if s.endswith("h"): return int(s[:-1]) * 3600
        if s.endswith("d"): return int(s[:-1]) * 86400
        return int(s) * 60  # bare minutes
    except Exception:
        return 2 * 60 * 60

def _auto_bucket(seconds: int) -> int:
    """Return bucket size in seconds based on the requested window."""
    if seconds <= 2 * 3600:      # <= 2h
        return 60                # 1 min
    if seconds <= 6 * 3600:      # <= 6h
        return 300               # 5 min
    if seconds <= 24 * 3600:     # <= 24h
        return 900               # 15 min
    if seconds <= 7 * 86400:     # <= 7d
        return 3600              # 60 min
    return 10800                 # 180 min

def _floor_to_bucket(ts: datetime, bucket_sec: int) -> datetime:
    epoch = int(ts.timestamp())
    floored = (epoch // bucket_sec) * bucket_sec
    return datetime.fromtimestamp(floored, tz=timezone.utc)

def _build_time_axis(since: datetime, until: datetime, bucket_sec: int) -> List[datetime]:
    out = []
    cur = since
    while cur <= until:
        out.append(cur)
        cur = cur + timedelta(seconds=bucket_sec)
    return out

# ---------- core computation ----------

def compute(
    range_str: str = "2h",
    client_id: Optional[int] = None,
    client_slug_or_name: Optional[str] = None,
    bucket: Optional[str] = None,  # e.g. "1m", "5m", "15m", "60m", "auto"
) -> Dict[str, Any]:
    """
    Returns Chart.js-ready payload for messages throughput:
      { "labels": [...], "datasets": [{"label": "msgs/min", "data": [...]}] }

    - Buckets the counts over time using UNIX bucketing in SQL.
    - Filters by client if client_id is provided (via mqtt_topic/device joins),
      or falls back to mqtt_messages.client (VARCHAR).

    Tables used:
      mqtt_messages(m.at, m.topic, m.client)
      mqtt_topic(topic UNIQUE, client_id, device_id)
      device(id, client_id)
    """
    window_sec = max(_parse_range_to_seconds(range_str), 60)
    bucket_sec = _auto_bucket(window_sec) if (not bucket or bucket == "auto") else _parse_range_to_seconds(bucket)
    # Avoid division by non-minute buckets in label
    per_label = "msgs/min" if bucket_sec == 60 else f"msgs/{int(bucket_sec/60)}m"

    now_utc = datetime.now(timezone.utc)
    until = _floor_to_bucket(now_utc, bucket_sec)
    since = _floor_to_bucket(now_utc - timedelta(seconds=window_sec), bucket_sec)

    # Build WHERE + JOINs
    where = [f"m.at >= '{since.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')}'", f"m.at < '{(until + timedelta(seconds=bucket_sec)).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')}'"]; 
    joins: List[str] = []

    if client_id is not None:
        joins.append("JOIN mqtt_topic t ON t.topic = m.topic")
        where.append(f"(t.client_id = {client_id} OR d.client_id = {client_id})")
    elif client_slug_or_name:
        where.append(f"m.client = {client_id}")

    # Group by bucket using UNIX_TIMESTAMP bucketing
    sql = f"""
        SELECT
          FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(m.at)/{bucket_sec})*{bucket_sec}) AS bucket_ts,
          COUNT(*) AS cnt
        FROM mqtt_message m
        {' '.join(joins)}
        WHERE {" AND ".join(where)}
        GROUP BY bucket_ts
        ORDER BY bucket_ts;
    """

    # Fetch
    series: Dict[datetime, int] = {}
    conn: pymysql.connections.Connection = pymysql.connections.Connection(**{k:v for k,v in MqttMessage.storage.credentials.items() if k != "auth_plugin"})
    with conn.cursor() as cur:
        cur.execute(sql, [])
        for row in cur.fetchall():
            # row can be tuple or dict
            bts = row[0] if isinstance(row, tuple) else row["bucket_ts"]
            cnt = row[1] if isinstance(row, tuple) else row["cnt"]
            # Ensure timezone-aware UTC
            if bts.tzinfo is None:
                bts = bts.replace(tzinfo=timezone.utc)
            series[bts] = int(cnt)

    # Fill 0s for missing buckets
    axis = _build_time_axis(since, until, bucket_sec)
    labels = [dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") for dt in axis]
    data = [series.get(dt, 0) for dt in axis]

    return {
        "labels": labels,
        "datasets": [{
            "label": per_label,
            "data": data,
            "fill": False,
            "tension": 0.15,
        }]
    }
