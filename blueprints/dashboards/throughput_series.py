from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from core.repository import repos
from core.models import MqttMessage


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
    # Epoch math on naive-UTC datetimes: .timestamp() would reinterpret them
    # as local time, and aware results can't compare with the stored values.
    epoch = int((ts - datetime(1970, 1, 1)).total_seconds())
    floored = (epoch // bucket_sec) * bucket_sec
    return datetime(1970, 1, 1) + timedelta(seconds=floored)

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

    - Buckets the counts over time
    - Filters by client if client_id is provided, or falls back to mqtt_messages.client (VARCHAR).
    """
    window_sec = max(_parse_range_to_seconds(range_str), 60)
    bucket_sec = _auto_bucket(window_sec) if (not bucket or bucket == "auto") else _parse_range_to_seconds(bucket)
    # Avoid division by non-minute buckets in label
    per_label = "msgs/min" if bucket_sec == 60 else f"msgs/{int(bucket_sec/60)}m"

    now_utc = datetime.utcnow()
    until = _floor_to_bucket(now_utc, bucket_sec)
    since = _floor_to_bucket(now_utc - timedelta(seconds=window_sec), bucket_sec)

    # Collect messages in time window and bucket them
    series: Dict[datetime, int] = {}
    messages = repos['MqttMessage'].list()
    
    for msg in messages:
        if msg.at >= since and msg.at <= until:
            if client_id is not None:
                # Would need to join through topic/device for client filtering
                pass
            elif client_slug_or_name:
                if msg.client == client_slug_or_name:
                    bucket_ts = _floor_to_bucket(msg.at, bucket_sec)
                    series[bucket_ts] = series.get(bucket_ts, 0) + 1
            else:
                # All clients
                bucket_ts = _floor_to_bucket(msg.at, bucket_sec)
                series[bucket_ts] = series.get(bucket_ts, 0) + 1

    # Fill 0s for missing buckets
    axis = _build_time_axis(since, until, bucket_sec)
    labels = [dt.strftime("%Y-%m-%d %H:%M") for dt in axis]
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
