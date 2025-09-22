from datetime import datetime, timedelta, timezone
from typing import Optional

from temod.base.attribute import DateTimeAttribute
from temod.base.condition import Superior

# ---- shared helper (same as in ingest_rate) --------------------------------
def _parse_range_to_seconds(range_str: str) -> int:
    """
    Accepts '5m', '1h', '2h', '24h', '7d', '30d' (or bare minutes like '15').
    Returns seconds (int). Defaults to 2h on invalid input.
    """
    if not range_str:
        return 2 * 60 * 60
    s = range_str.strip().lower()
    try:
        if s.endswith('m'):
            return int(s[:-1]) * 60
        if s.endswith('h'):
            return int(s[:-1]) * 3600
        if s.endswith('d'):
            return int(s[:-1]) * 86400
        return int(s) * 60  # bare minutes
    except Exception:
        return 2 * 60 * 60


def compute(
    range_str: str = "2h",
    client_id: Optional[int] = None,
    client_slug_or_name: Optional[str] = None,
) -> float:
    """
    Compute parse success percentage over the time window.
    - Numerator: #extraction.success = 1
    - Denominator: total #extraction rows
    Optional client scoping via mqtt_topic.client_id / device.client_id,
    or via mqtt_messages.client (VARCHAR fallback).

    Tables (per your schema):
      extraction(id, message_id, parser_id, parsed_at, success, ...)
      mqtt_messages(id, client, topic, at, ...)
      mqtt_topic(topic UNIQUE, client_id, device_id, ...)
      device(id, client_id, ...)

    Returns a float in [0, 100]. If no rows in window, returns 0.0
    """
    seconds = max(_parse_range_to_seconds(range_str), 60)
    since = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    since_naive = since.replace(tzinfo=None)

    '''
    where = ["e.last_update >= %s"]
    params = [since_naive]
    joins = []

    #Filter by client if provided
    if client_id is not None:
        joins.append("JOIN mqtt_messages m ON m.id = e.message_id")
        joins.append("LEFT JOIN mqtt_topic t ON t.topic = m.topic")
        joins.append("LEFT JOIN device d ON d.id = t.device_id")
        where.append("(t.client_id = %s OR d.client_id = %s)")
        params.extend([client_id, client_id])
    elif client_slug_or_name:
        joins.append("JOIN mqtt_messages m ON m.id = e.message_id")
        where.append("m.client = %s")
        params.append(client_slug_or_name)"""

    sql = f"""
        SELECT
          SUM(CASE WHEN e.success = 1 THEN 1 ELSE 0 END) AS ok,
          COUNT(*) AS total
        FROM extraction e
        {' '.join(joins)}
        WHERE {" AND ".join(where)}
    """'''

    dispatches = Dispatch.storage.list(Superior(DateTimeAttribute("updated_at",value=since)))
    ok = 0; total = 0

    for dispatch in dispatches:
        ok += int(dispatch['status'].name == "sent")
        total += 1

    if total == 0:
        return 0.0

    return float(ok) * 100.0 / float(total)