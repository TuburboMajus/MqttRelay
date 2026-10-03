"""Smoke tests for ``MqttTransfer.process`` — the outer ingest->parse->dispatch
loop over unprocessed ``mqtt_message`` rows."""
import uuid
from unittest.mock import patch

import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import (
    FakeDispatcher, FakeFailingDispatcher, client_row, destination_row,
    device_row, device_type_row, message_row, metric_row, parser_row, rec,
    route_row, seed, topic_row,
)

RULE_ID = str(uuid.uuid4())


def _pipeline_setup(instance, messages=None):
    seed(instance, "topics", [topic_row("devices/5", id_=10, client_id=1, device_id=5)])
    seed(instance, "devices", [device_row(id_=5, client_id=1, device_type_id=10)])
    seed(instance, "clients", [client_row(id_=1, name="Acme")])
    seed(instance, "device_types", [device_type_row(id_=10)])
    seed(instance, "routes", [route_row(RULE_ID, client_id=1, topic_id=10, device_id=5,
                                        parser_id=1, parser_config="{}")])
    seed(instance, "parsers", [parser_row(id_=1)])
    seed(instance, "metrics", [metric_row(id_=1)])
    seed(instance, "extractions", [])
    seed(instance, "destinations", [destination_row(id_=3)])
    seed(instance, "deposits", [rec(rule_id=RULE_ID, destination_id=3)])
    seed(instance, "dispatches", [])
    seed(instance, "parsed_points", [])
    return seed(instance, "mqtt_messages", messages or [
        message_row(id_=100, topic="devices/5", payload='{"Temp_SOIL": 28.1}')
    ])


def test_process_marks_message_processed_on_success(instance):
    messages = _pipeline_setup(instance)
    fake_parse = lambda data, **cfg: {1: data["Temp_SOIL"]}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse), \
         patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        result = instance.process()

    assert result is True
    message = messages.rows[0]
    assert message["processed"] is True
    assert message["processor"] is not None
    assert len(instance.storages["extractions"].rows) == 1
    assert len(instance.storages["parsed_points"].rows) == 1
    # the extraction id is recorded as the message processor
    extraction_id = instance.storages["extractions"].rows[0]["id"]
    assert message["processor"] == extraction_id


def test_process_failed_dispatch_leaves_message_unprocessed(instance):
    messages = _pipeline_setup(instance)
    fake_parse = lambda data, **cfg: {1: 5}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse), \
         patch.object(mtt, "DISPATCHERS", {"mysql": FakeFailingDispatcher}):
        result = instance.process()

    assert result is False
    message = messages.rows[0]
    assert message["processed"] is False
    assert message["processor"] is not None  # processor is recorded regardless


def test_process_parser_without_results_marks_failure(instance):
    messages = _pipeline_setup(instance)
    fake_parse = lambda data, **cfg: {}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse), \
         patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        result = instance.process()

    assert result is False
    assert messages.rows[0]["processed"] is False
    # a failed extraction was persisted with an error
    assert len(instance.storages["extractions"].rows) == 1
    assert instance.storages["extractions"].rows[0]["success"] == 0


def test_process_message_error_does_not_crash_loop(instance):
    messages = seed(instance, "mqtt_messages",
                    [message_row(id_=1, topic="nope/topic")])
    seed(instance, "topics", [topic_row("devices/5", id_=10, client_id=1, device_id=5)])
    seed(instance, "devices", [device_row(id_=5)])
    seed(instance, "clients", [client_row(id_=1)])
    seed(instance, "device_types", [device_type_row(id_=10)])
    seed(instance, "routes", [])
    seed(instance, "parsers", [])
    seed(instance, "metrics", [])
    seed(instance, "extractions", [])
    seed(instance, "deposits", [])
    seed(instance, "destinations", [])
    seed(instance, "dispatches", [])
    seed(instance, "parsed_points", [])

    result = instance.process()
    assert result is False
    assert messages.rows[0]["processed"] is False


def test_process_returns_true_when_no_messages(instance):
    seed(instance, "mqtt_messages", [])
    assert instance.process() is True  # all([]) is True


def test_process_handles_multiple_messages(instance):
    messages = _pipeline_setup(instance, messages=[
        message_row(id_=100, topic="devices/5", payload='{"Temp_SOIL": 28.1}'),
        message_row(id_=101, topic="devices/5", payload='{"Temp_SOIL": 29.0}'),
    ])
    fake_parse = lambda data, **cfg: {1: data["Temp_SOIL"]}  # noqa: E731
    with patch.object(mtt.MqttTransfer, "load_parse_function", return_value=fake_parse), \
         patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        result = instance.process()

    assert result is True
    assert all(m["processed"] is True for m in messages.rows)
    assert len(instance.storages["extractions"].rows) == 2
    assert len(instance.storages["parsed_points"].rows) == 2
