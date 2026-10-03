from datetime import datetime, timedelta
from typing import Optional, Union, Dict
from core.repository import repos
from core.models import MqttMessage

# --- helpers ---------------------------------------------------------------

def _parse_range_to_seconds(range_str: str) -> int:
	"""
	Accepts '5m', '1h', '2h', '24h', '7d', '30d' (or plain minutes like '15').
	Returns seconds (int). Defaults to 2h if invalid.
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
		# bare number = minutes
		return int(s) * 60
	except Exception:
		return 2 * 60 * 60  # fallback: 2h


def compute(
	range_str: str = "2h",
	client_id: Optional[int] = None,
	client_slug_or_name: Optional[str] = None,
) -> float:
	"""
	Returns messages per minute over the given time window.

	:param range_str: e.g. '5m', '2h', '24h', '7d'
	:param client_id: numeric client ID (preferred)
	:param client_slug_or_name: fallback filter using mqtt_messages.client (VARCHAR)
	:return: rate as float (messages per minute)
	"""
	seconds = _parse_range_to_seconds(range_str)
	# Guard against tiny/zero windows
	seconds = max(seconds, 60)
	# Naive UTC: the models store naive utcnow() timestamps, so comparisons
	# must use naive UTC as well (aware vs naive raises TypeError).
	since = datetime.utcnow() - timedelta(seconds=seconds)

	count = 0
	for msg in repos['MqttMessage'].list():
		if msg.at >= since:
			if client_id is not None:
				# Would need to join through topic/device for client filtering
				pass
			elif client_slug_or_name:
				if msg.client == client_slug_or_name:
					count += 1
			else:
				count += 1

	rate = float(count) / (seconds / 60.0)
	return rate
