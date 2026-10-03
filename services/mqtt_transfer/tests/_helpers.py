"""Shared helpers for the ``services/mqtt_transfer`` smoke tests.

The worker module (``services/mqtt_transfer/mqtt_transfer.py``) only defines some of
its globals (``entities``, ``eval_mongo_dsl``, ``DISPATCHERS``, ``PARSERS_DB``,
``LOGGER``) inside ``if __name__ == "__main__":``. When imported as a module those
names do not exist, so this module injects them onto it — mirroring the real boot
sequence. All MySQL access is replaced with in-memory :class:`FakeStorage` objects.
"""
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make the repo root importable so `core.entity`, `tools.*` and the service
# itself can be imported.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core.entity as entities
import services.mqtt_transfer.mqtt_transfer as mtt
from services.mqtt_transfer.dispatchers import DISPATCHERS
from tools.json_conditions import eval_mongo_dsl

# Inject the globals that the real entrypoint would set before running.
mtt.entities = entities
mtt.eval_mongo_dsl = eval_mongo_dsl
mtt.DISPATCHERS = DISPATCHERS
mtt.LOGGER = logging.getLogger("mqttt-tests")
mtt.LOGGER.setLevel(logging.INFO)
mtt.LOGGER.propagate = True
mtt.PARSERS_DB = None


# --------------------------------------------------------------------------- #
# Row / storage fakes
# --------------------------------------------------------------------------- #
class Record(dict):
    """Lightweight stand-in for a Temod entity row.

    Supports the attribute surface the worker touches: ``row['field']``,
    ``row.to_dict()``, ``row.takeSnapshot()`` and ``row.setAttribute(s)``.
    """

    def to_dict(self):
        return dict(self)

    def takeSnapshot(self):
        return self

    def setAttribute(self, key, value):
        self[key] = value
        return self

    def setAttributes(self, **kwargs):
        self.update(kwargs)
        return self


class FakeStorage:
    """In-memory stand-in for ``MysqlEntityStorage``.

    Implements the subset of the API used by ``MqttTransfer``: ``get``, ``list``,
    ``count``, ``create``, ``updateOnSnapshot``, ``delete`` and ``generate_value``.
    ``get``/``list`` accept Temod conditions (``Or``/``And``/``Not``/``Equals``) in
    addition to keyword equality filters.
    """

    def __init__(self, name=None, rows=None):
        self.name = name
        self.rows = list(rows or [])
        self.created = []
        self.get_calls = 0
        self._seq = 0

    # -- condition evaluation ------------------------------------------------ #
    @staticmethod
    def _field(row, key):
        """Read a field from a dict-like or a real Temod entity row."""
        if hasattr(row, "get"):
            return row.get(key)
        try:
            return row[key]
        except Exception:
            return None

    def _match_one(self, row, cond):
        from temod.base.condition import And, Equals, Not, Or

        if isinstance(cond, Or):
            return any(self._match_one(row, c) for c in cond.conditions)
        if isinstance(cond, And):
            return all(self._match_one(row, c) for c in cond.conditions)
        if isinstance(cond, Not):
            return not self._match_one(row, cond.condition)
        if isinstance(cond, Equals):
            field1 = cond.field1
            name1 = getattr(field1, "name", None)
            if cond.field2 is None:
                # Equals(attribute) with no value => IS NULL
                if getattr(field1, "value", None) is None:
                    return self._field(row, name1) is None
                return self._field(row, name1) == field1.value
            name2 = getattr(cond.field2, "name", cond.field2)
            return self._field(row, name1) == self._field(row, name2)
        raise NotImplementedError(
            f"FakeStorage cannot evaluate condition {type(cond).__name__}"
        )

    def _match(self, row, conditions, kwargs):
        for key, value in kwargs.items():
            if self._field(row, key) != value:
                return False
        return all(self._match_one(row, c) for c in conditions)

    # -- storage API --------------------------------------------------------- #
    def get(self, *conditions, **kwargs):
        self.get_calls += 1
        for row in self.rows:
            if self._match(row, conditions, kwargs):
                return row
        return None

    def list(self, *conditions, **kwargs):
        return [row for row in self.rows if self._match(row, conditions, kwargs)]

    def count(self, *conditions, **kwargs):
        return len(self.list(*conditions, **kwargs))

    def create(self, entity):
        self.created.append(entity)
        self.rows.append(entity)
        return len(self.rows)

    def updateOnSnapshot(self, entity):
        return entity

    def delete(self, *args, **kwargs):
        return None

    def generate_value(self, attribute):
        self._seq += 1
        return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Instance builder
# --------------------------------------------------------------------------- #
def build_instance(**creds):
    """Construct a ``MqttTransfer`` whose storages are all fakes."""
    with patch.object(mtt, "MysqlEntityStorage", return_value=MagicMock()):
        inst = mtt.MqttTransfer(**creds)
    inst.storages = {}
    inst.metrics_cache = {}
    inst.device_types_cache = {}
    return inst


def seed(inst, key, rows=None):
    """Attach a seeded :class:`FakeStorage` under ``inst.storages[key]``."""
    storage = FakeStorage(key, rows)
    inst.storages[key] = storage
    return storage


# --------------------------------------------------------------------------- #
# Row builders (lightweight Records, except where the service builds real entities)
# --------------------------------------------------------------------------- #
def rec(**kwargs):
    return Record(kwargs)


def client_row(id_=1, name="Acme"):
    return rec(id=id_, name=name, slug=f"slug-{id_}", status="active")


def device_row(id_=1, client_id=1, device_type_id=10, topic="devices/1"):
    return rec(id=id_, client_id=client_id, device_type_id=device_type_id,
               topic=topic, name=f"device-{id_}", working=True, installed=True)


def device_type_row(id_=10, model="LSE01"):
    return rec(id=id_, model=model, vendor="Vendor", kind="sensor",
               capabilities="{}", payload_schema="{}", defaults_json="{}")


def topic_row(topic, id_=1, client_id=1, device_id=1, active=1):
    return rec(id=id_, topic=topic, client_id=client_id, device_id=device_id,
               active=active, qos_default=0, created_at=datetime(2026, 1, 1))


def metric_row(id_=1, key_name="soil_moisture", default_unit="%"):
    return rec(id=id_, key_name=key_name, default_unit=default_unit, description=None)


def route_row(id_="r1", client_id=1, topic_id=10, device_id=None, parser_id=1,
              parser_config="{}", conditions=None, priority=100, active=1,
              created_at=None):
    return rec(id=id_, client_id=client_id, topic_id=topic_id, device_id=device_id,
               parser_id=parser_id, parser_config=parser_config, conditions=conditions,
               priority=priority, active=active,
               created_at=created_at or datetime(2026, 1, 1, 0, 0, 0))


def parser_row(id_=1, name="LSE01 Soil", version="1.0.0", language="python"):
    return rec(id=id_, name=name, version=version, language=language,
               description=None, active=1)


def message_row(id_=1, topic="devices/1", payload='{"Temp_SOIL": 28.1}', at=None,
                client="slug-1"):
    return rec(id=id_, topic=topic, payload=payload,
               at=at or datetime(2026, 1, 1, 12, 0, 0),
               client=client, qos=0, processed=False)


def destination_row(id_=3, client_id=1, type_="mysql", **overrides):
    """Build a real ``ClientDestination`` (its ``type`` enum exposes ``.name``)."""
    values = dict(id=id_, client_id=client_id, type=type_, host="127.0.0.1",
                  port=3306, database_name="clientdb", username="user",
                  password_enc=None, encryption_version=None,
                  uri=None, options_json="{}", active=1, created_at=datetime(2026, 1, 1))
    values.update(overrides)
    return entities.ClientDestination(**values)


def dispatch_entity(**overrides):
    """Build a real ``Dispatch`` entity (its ``status`` enum exposes ``.name``)."""
    values = dict(id=str(uuid.uuid4()), extraction_id=str(uuid.uuid4()),
                  destination_id=1, rule_id=str(uuid.uuid4()), status="queued",
                  created_at=datetime.now(), attempts=1)
    values.update(overrides)
    return entities.Dispatch(**values)


# --------------------------------------------------------------------------- #
# Fake dispatchers (replace ``mtt.DISPATCHERS`` in tests)
# --------------------------------------------------------------------------- #
class FakeDispatcher:
    """Synchronous dispatcher stand-in that always reports 'sent'."""
    instances = []
    asynchronous = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.parsed_points = None
        FakeDispatcher.instances.append(self)

    def dispatch(self, parsed_points=None):
        self.parsed_points = parsed_points
        return {"status": "sent", "http_status": 200, "response_snippet": "ok"}


class FakeFailingDispatcher:
    """Synchronous dispatcher stand-in that always reports 'failed'."""
    asynchronous = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def dispatch(self, parsed_points=None):
        return {"status": "failed", "http_status": None, "response_snippet": "nope"}


class FakeAsyncDispatcher:
    """Asynchronous dispatcher stand-in (callback style)."""
    instances = []
    asynchronous = True

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.callback = None
        self.parsed_points = None
        FakeAsyncDispatcher.instances.append(self)

    def setCallback(self, callback):
        self.callback = callback

    def dispatch(self, parsed_points=None):
        self.parsed_points = parsed_points
        return {"status": "queued", "http_status": None, "response_snippet": "async"}
