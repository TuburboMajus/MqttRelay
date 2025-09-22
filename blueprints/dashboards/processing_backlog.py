from datetime import datetime, timedelta, timezone
from typing import Optional



# Optional helper if you want a time-bounded backlog (not required for the KPI)
def _parse_range_to_seconds(range_str: str) -> int:
    if not range_str:
        return 0
    s = range_str.strip().lower()
    try:
        if s.endswith('m'):
            return int(s[:-1]) * 60
        if s.endswith('h'):
            return int(s[:-1]) * 3600
        if s.endswith('d'):
            return int(s[:-1]) * 86400
        return int(s) * 60
    except Exception:
        return 0


def compute(
    client_id: Optional[int] = None,
    client_slug_or_name: Optional[str] = None,
    max_age: Optional[str] = None,  # e.g. '24h' if you want to bound the backlog window (optional)
) -> int:
    """
    Count unprocessed MQTT messages.

    Schema:
      mqtt_messages(id, client, topic, at, processed, ...)
      mqtt_topic(topic UNIQUE, client_id, device_id, ...)
      device(id, client_id, ...)

    Filters:
      - client_id: join through mqtt_topic/device to scope backlog to a tenant
      - client_slug_or_name: fallback using mqtt_messages.client (VARCHAR)
      - max_age: optional time window (e.g. '24h') to only count recent backlog

    Returns: integer count

    Performance tip: add an index like
      CREATE INDEX idx_processed_at ON mqtt_messages (processed, at);
    """
    '''where = ["m.processed = 0"]
    params = []
    joins = []

    # Optional: limit to recent messages (if you pass max_age)

    if client_id is not None:
        joins.append("JOIN mqtt_topic t ON t.topic = m.topic")
        joins.append("LEFT JOIN device d ON d.id = t.device_id")
        where.append("(t.client_id = %s OR d.client_id = %s)")
        params.extend([client_id, client_id])
    elif client_slug_or_name:
        where.append("m.client = %s")
        params.append(client_slug_or_name)

    sql = f"""
        SELECT COUNT(*) AS cnt
        FROM mqtt_messages m
        {' '.join(joins)}
        WHERE {" AND ".join(where)}
    """'''
    since = None
    if max_age:
        secs = _parse_range_to_seconds(max_age)
        if secs > 0:
            since = datetime.now(timezone.utc) - timedelta(seconds=secs)

    return MqttMessage.storage.count(*([Superior(DateTimeAttribute("at",value=since))] if since else []),processed=False)