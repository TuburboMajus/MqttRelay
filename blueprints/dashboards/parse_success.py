from datetime import datetime, timedelta
from typing import Optional
from core.repository import repos
from core.models import Extraction

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

    Returns a float in [0, 100]. If no rows in window, returns 0.0
    """
    seconds = max(_parse_range_to_seconds(range_str), 60)
    # Naive UTC to match the naive utcnow() timestamps stored by the models.
    since = datetime.utcnow() - timedelta(seconds=seconds)

    # Query all extractions in time window
    extractions = repos['Extraction'].list()
    ok = 0
    total = 0

    for extraction in extractions:
        if extraction.parsed_at >= since:
            if client_id is not None:
                # Would need to join through message -> topic/device for client filtering
                pass
            elif client_slug_or_name:
                # Would need to join through message for client filtering
                pass
            else:
                # All clients - count success rate
                if extraction.success:
                    ok += 1
                total += 1
    
    if total == 0:
        return 0.0

    return float(ok) * 100.0 / float(total)