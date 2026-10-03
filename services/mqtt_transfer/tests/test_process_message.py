"""Smoke tests for ``MqttTransfer.process_message`` (parse -> points -> extraction)."""
from datetime import datetime
from unittest.mock import patch

import pytest

import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import (
    client_row, device_row, device_type_row, message_row, metric_row,
    parser_row, route_row, seed, topic_row,
)


def _full_setup(instance, payload='{"Temp_SOIL": 28.1, "Water_SOIL": 12}'):
    seed(instance, "topics", [topic_row("devices/5", id_=10, client_id=1, device_id=5)])
    seed(instance, "devices", [device_row(id_=5, client_id=1, device_type_id=10)])
    seed(instance, "clients", [client_row(id_=1, name="Acme")])
    seed(instance, "device_types", [device_type_row(id_=10)])
    seed(instance, "routes", [route_row("r1", client_id=1, topic_id=10, device_id=5,
                                        parser_id=1, parser_config='{"gain": 2}')])
    seed(instance, "parsers", [parser_row(id_=1, name="LSE01 Soil", version="1.0.0")])
    seed(instance, "metrics", [metric_row(id_=1, key_name="Temp_SOIL", default_unit="°C"),
                               metric_row(id_=2, key_name="Water_SOIL", default_unit="%")])
    seed(instance, "extractions", [])
    return message_row(id_=100, topic="devices/5", payload=payload)


def test_process_message_parses_numeric_points(instance):
    message = _full_setup(instance)
    fake_parse = lambda data, **cfg: {1: data["Temp_SOIL"], 2: data["Water_SOIL"], "note": "x"}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        points, extraction, route = instance.process_message(message)

    assert extraction["success"] == 1
    assert extraction["extracted_count"] == 3  # len(results) counts all keys
    assert extraction["message_id"] == 100
    assert extraction["parser_id"] == 1
    assert extraction["parser_config"] == '{"gain": 2}'

    assert len(points) == 2
    p1, p2 = points[0], points[1]
    assert p1["device_id"] == 5 and p1["metric_id"] == 1
    assert p1["unit"] == "°C" and p1["quality"].name == "good"
    assert float(p1["num_value"]) == 28.1
    assert float(p2["num_value"]) == 12.0
    assert '"note": "x"' in p1["meta_json"]
    assert route["id"] == "r1"


def test_process_message_uses_parser_at_for_timestamp(instance):
    message = _full_setup(instance)
    at = datetime(2025, 6, 1, 8, 0, 0)
    fake_parse = lambda data, **cfg: {1: 5, "at": at}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        points, extraction, _ = instance.process_message(message)
    assert points[0]["ts"] == at


def test_process_message_default_timestamp_is_message_at(instance):
    message = _full_setup(instance)
    fake_parse = lambda data, **cfg: {1: 5}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        points, extraction, _ = instance.process_message(message)
    assert points[0]["ts"] == message["at"]


def test_process_message_no_results_marks_failure(instance):
    message = _full_setup(instance)
    fake_parse = lambda data, **cfg: {}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        points, extraction, _ = instance.process_message(message)
    assert extraction["success"] == 0
    assert extraction["error_text"] is not None
    assert extraction["extracted_count"] == 0
    assert points == []


def test_process_message_only_meta_keys_produce_no_points(instance):
    message = _full_setup(instance)
    fake_parse = lambda data, **cfg: {"only": "meta"}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        points, extraction, _ = instance.process_message(message)
    assert extraction["success"] == 1
    assert extraction["extracted_count"] == 1
    assert points == []


def test_process_message_unknown_metric_raises(instance):
    message = _full_setup(instance)
    fake_parse = lambda data, **cfg: {99: 1.0}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        with pytest.raises(mtt.MetricNotFound):
            instance.process_message(message)


def test_process_message_str_and_bool_values(instance):
    message = _full_setup(instance)
    fake_parse = lambda data, **cfg: {1: "warm", 2: True}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        points, extraction, _ = instance.process_message(message)
    by_metric = {p["metric_id"]: p for p in points}
    assert by_metric[1]["str_value"] == "warm"
    assert by_metric[2]["bool_value"] == 1


def test_process_message_json_value(instance):
    message = _full_setup(instance)
    fake_parse = lambda data, **cfg: {1: {"a": [1, 2]}}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        points, extraction, _ = instance.process_message(message)
    assert '"a"' in points[0]["json_value"]


def test_process_message_payload_dict_used_directly(instance):
    message = _full_setup(instance, payload={"Temp_SOIL": 9.9, "Water_SOIL": 3})
    seen = {}

    def fake_parse(data, **cfg):
        seen["data"] = data
        return {1: data["Temp_SOIL"]}

    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse):
        instance.process_message(message)
    assert seen["data"] == {"Temp_SOIL": 9.9, "Water_SOIL": 3}
