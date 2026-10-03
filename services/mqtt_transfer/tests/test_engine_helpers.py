"""Smoke tests for ``MqttTransfer.__init__`` and its small helper methods."""
from unittest.mock import MagicMock, patch

import pytest

import core.entity as entities
import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import build_instance, device_type_row, metric_row, seed

EXPECTED_STORAGE_KEYS = {
    "mqtt_messages", "parsers", "metrics", "parsed_points", "extractions",
    "clients", "device_types", "topics", "devices", "routes", "deposits",
    "dispatches", "destinations",
}


def test_init_builds_all_storages_and_caches():
    created = {}

    def factory(entity, **creds):
        created[entity.ENTITY_NAME] = entity
        return MagicMock()

    with patch.object(mtt, "MysqlEntityStorage", side_effect=factory):
        inst = mtt.MqttTransfer(host="127.0.0.1", port=3306)

    assert set(inst.storages.keys()) == EXPECTED_STORAGE_KEYS

    # entity classes are bound to the correct storages (regression: `clients`
    # used to point at Parser, and `device_types` was missing entirely)
    assert created["client"] is entities.Client
    assert created["device_type"] is entities.DeviceType
    assert created["mqtt_message"] is entities.MqttMessage
    assert created["parser"] is entities.Parser
    assert created["routing_rule"] is entities.RoutingRule
    assert created["route_deposit"] is entities.RouteDeposit
    assert created["client_destination"] is entities.ClientDestination
    assert created["parsed_point"] is entities.ParsedPoint

    assert inst.metrics_cache == {}
    assert inst.device_types_cache == {}
    assert inst.mysql_credentials == {"host": "127.0.0.1", "port": 3306}


def test_judge_data_quality_is_a_good_stub():
    inst = build_instance()
    assert inst.judge_data_quality("metric", 12.5, device="x") == "good"
    assert inst.judge_data_quality() == "good"


def test_load_metric_caches_lookup():
    inst = build_instance()
    metrics = seed(inst, "metrics", [metric_row(id_=1)])
    metric = inst._load_metric(1)
    assert metric["id"] == 1
    assert metric["default_unit"] == "%"
    assert metrics.get_calls == 1
    # second call hits the cache, not the storage
    assert inst._load_metric(1) is metric
    assert metrics.get_calls == 1


def test_load_metric_missing_raises():
    inst = build_instance()
    seed(inst, "metrics", [metric_row(id_=1)])
    with pytest.raises(mtt.MetricNotFound):
        inst._load_metric(99)


def test_load_device_type_caches_lookup():
    inst = build_instance()
    types = seed(inst, "device_types", [device_type_row(id_=10)])
    device_type = inst._load_device_type(10)
    assert device_type["model"] == "LSE01"
    assert types.get_calls == 1
    assert inst._load_device_type(10) is device_type
    assert types.get_calls == 1


def test_load_device_type_missing_raises():
    inst = build_instance()
    seed(inst, "device_types", [device_type_row(id_=10)])
    with pytest.raises(mtt.DeviceTypeNotFound):
        inst._load_device_type(999)
