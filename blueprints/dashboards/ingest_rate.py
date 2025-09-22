from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Dict

from temod.base.attribute import DateTimeAttribute
from temod.base.condition import Superior

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
	If client_id is provided, messages are filtered to that client by joining:
	  mqtt_messages.topic -> mqtt_topic.topic -> (client_id or device.client_id)
	If client_slug_or_name is provided, falls back to filtering on mqtt_messages.client (VARCHAR).

	Schema references:
	  - mqtt_messages(id, client, topic, at, ...)
	  - mqtt_topic(topic UNIQUE, client_id, device_id)
	  - device(id, client_id)

	:param conn: an open PyMySQL connection
	:param range_str: e.g. '5m', '2h', '24h', '7d'
	:param client_id: numeric client ID (preferred)
	:param client_slug_or_name: fallback filter using mqtt_messages.client (VARCHAR)
	:return: rate as float (messages per minute)
	"""
	seconds = _parse_range_to_seconds(range_str)
	# Guard against tiny/zero windows
	seconds = max(seconds, 60)
	since = datetime.now(timezone.utc) - timedelta(seconds=seconds)

	return MqttMessage.storage.count(Superior(DateTimeAttribute("at",value=since))) / (seconds / 60.0)

	if client_id is not None:
		# Use JOIN to resolve client via topic/device mapping
		sql = """
			SELECT COUNT(*) AS cnt
			FROM mqtt_messages m
			JOIN mqtt_topic t   ON t.topic = m.topic
			LEFT JOIN device d  ON d.id = t.device_id
			WHERE m.at >= %s
			  AND (t.client_id = %s OR d.client_id = %s)
		"""
		params = (since.replace(tzinfo=None), client_id, client_id)
	elif client_slug_or_name:
		# Fallback: messages table carries a 'client' VARCHAR (slug/name)
		sql = """
			SELECT COUNT(*) AS cnt
			FROM mqtt_messages m
			WHERE m.at >= %s
			  AND m.client = %s
		"""
		params = (since.replace(tzinfo=None), client_slug_or_name)
	else:
		# All clients
		sql = """
			SELECT COUNT(*) AS cnt
			FROM mqtt_messages m
			WHERE m.at >= %s
		"""
		params = (since.replace(tzinfo=None),)

	with conn.cursor() as cur:
		cur.execute(sql, params)
		row = cur.fetchone()
		count = (row[0] if isinstance(row, tuple) else row.get("cnt", 0)) or 0

	rate = float(count) / (seconds / 60.0)
	return rate
	
