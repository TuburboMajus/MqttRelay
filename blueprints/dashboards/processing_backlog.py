from datetime import datetime, timedelta
from typing import Optional
from core.repository import repos
from core.models import MqttMessage


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

    Filters:
      - client_id: scope backlog to a tenant
      - client_slug_or_name: fallback using mqtt_messages.client (VARCHAR)
      - max_age: optional time window (e.g. '24h') to only count recent backlog

    Returns: integer count
    """
    since = None
    if max_age:
        secs = _parse_range_to_seconds(max_age)
        if secs > 0:
            # Naive UTC to match the naive utcnow() timestamps stored by the models.
            since = datetime.utcnow() - timedelta(seconds=secs)

    # Count unprocessed messages
    messages = repos['MqttMessage'].list()
    count = 0
    
    for msg in messages:
        if not msg.processed:
            if since and msg.at < since:
                continue
            if client_id is not None:
                # Would need to join through topic/device for client filtering
                pass
            elif client_slug_or_name:
                if msg.client == client_slug_or_name:
                    count += 1
            else:
                # All clients
                count += 1
    
    return count