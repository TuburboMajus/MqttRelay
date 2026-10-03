from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from core.repository import repos
from core.models import Dispatch


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
    # Epoch math on naive-UTC datetimes: .timestamp() would reinterpret them
    # as local time, and aware results can't compare with the stored values.
    epoch = int((ts - datetime(1970, 1, 1)).total_seconds())
    floored = (epoch // bucket_sec) * bucket_sec
    return datetime(1970, 1, 1) + timedelta(seconds=floored)

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

    now_utc = datetime.utcnow()
    until = _floor_to_bucket(now_utc, bucket_sec)
    since = _floor_to_bucket(now_utc - timedelta(seconds=window_sec), bucket_sec)

    statuses = ["queued", "retrying", "failed", "dead", "sent"]  # consistent order

    # Collect dispatch counts bucketed by time and status
    grid: Dict[datetime, Dict[str, int]] = {}
    dispatches = repos['Dispatch'].list()
    
    for dispatch in dispatches:
        if dispatch.created_at >= since and dispatch.created_at <= until:
            # Optional client filtering
            if client_id is not None:
                # Would need to check dispatch.destination.client_id or dispatch.rule.client_id
                pass
            elif client_slug:
                # Would need to check dispatch.destination.client.slug or dispatch.rule.client.slug
                pass
            else:
                # All dispatches - bucket by time and status
                bucket_ts = _floor_to_bucket(dispatch.created_at, bucket_sec)
                bucket_map = grid.setdefault(bucket_ts, {})
                status_str = dispatch.status if isinstance(dispatch.status, str) else dispatch.status.value
                bucket_map[status_str] = bucket_map.get(status_str, 0) + 1

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