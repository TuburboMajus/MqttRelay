"""Smoke tests for ``MqttTransfer.select_route`` (priority + conditions DSL)."""
from datetime import datetime

import pytest

import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import (
    client_row, device_row, device_type_row, message_row, route_row, seed,
    topic_row,
)


def _context(instance, *, routes=None, device_type_id=10):
    seed(instance, "routes", routes or [])
    seed(instance, "device_types", [device_type_row(id_=device_type_id)])
    client = client_row(id_=1)
    device = device_row(id_=5, client_id=1, device_type_id=device_type_id,
                        topic="devices/5")
    topic = topic_row("devices/5", id_=10, client_id=1, device_id=5)
    message = message_row(id_=100, topic="devices/5", payload='{"Temp_SOIL": 30}')
    return client, device, topic, message


def test_select_route_lowest_priority_wins(instance):
    client, device, topic, message = _context(instance, routes=[
        route_row("r1", priority=100),
        route_row("r2", priority=5),
        route_row("r3", priority=50),
    ])
    selected = instance.select_route(client, device, topic, message)
    assert selected["id"] == "r2"


def test_select_route_matches_device_scoped_or_wildcard(instance):
    # both are candidates: one scoped to the device, one to "any device"
    client, device, topic, message = _context(instance, routes=[
        route_row("r-device", device_id=5, priority=10, created_at=datetime(2026, 1, 1)),
        route_row("r-wild", device_id=None, priority=10, created_at=datetime(2026, 1, 2)),
    ])
    selected = instance.select_route(client, device, topic, message)
    # equal priority + equal "evaluated" -> newest created_at wins
    assert selected["id"] == "r-wild"


def test_select_route_matching_conditions_beat_conditionless(instance):
    client, device, topic, message = _context(instance, routes=[
        route_row("r-match", priority=10, conditions='{"message.qos": {"$gte": 0}}'),
        route_row("r-plain", priority=10, conditions=None),
    ])
    selected = instance.select_route(client, device, topic, message)
    assert selected["id"] == "r-match"


def test_select_route_skips_routes_with_failing_conditions(instance):
    client, device, topic, message = _context(instance, routes=[
        route_row("r-fail", priority=10, conditions='{"message.qos": {"$gt": 10}}'),
        route_row("r-ok", priority=20, conditions=None),
    ])
    selected = instance.select_route(client, device, topic, message)
    assert selected["id"] == "r-ok"


def test_select_route_only_failing_conditions_raises_no_route(instance):
    client, device, topic, message = _context(instance, routes=[
        route_row("r-fail", priority=10,
                  conditions='{"message.qos": {"$gt": 10}}'),
    ])
    with pytest.raises(mtt.NoRouteFound):
        instance.select_route(client, device, topic, message)


def test_select_route_invalid_conditions_are_penalized(instance, caplog):
    client, device, topic, message = _context(instance, routes=[
        route_row("r-bad", priority=10, conditions="{not valid json"),
        route_row("r-plain", priority=10, conditions=None),
    ])
    with caplog.at_level("WARNING"):
        selected = instance.select_route(client, device, topic, message)
    assert selected["id"] == "r-plain"
    assert "failed to be evaulated" in caplog.text


def test_select_route_no_candidates_raises(instance):
    client, device, topic, message = _context(instance, routes=[])
    with pytest.raises(mtt.NoRouteFound):
        instance.select_route(client, device, topic, message)


def test_select_route_invalid_parser_config_raises(instance):
    client, device, topic, message = _context(instance, routes=[
        route_row("r-bad", priority=10, parser_config="{not json"),
    ])
    with pytest.raises(ValueError):
        instance.select_route(client, device, topic, message)


def test_select_route_tie_warns_and_uses_newest(instance, caplog):
    client, device, topic, message = _context(instance, routes=[
        route_row("r-old", priority=10, created_at=datetime(2026, 1, 1)),
        route_row("r-new", priority=10, created_at=datetime(2026, 1, 3)),
    ])
    with caplog.at_level("WARNING"):
        selected = instance.select_route(client, device, topic, message)
    assert selected["id"] == "r-new"
    assert "Multiple routes are possible" in caplog.text


def test_select_route_ignores_inactive_routes(instance):
    client, device, topic, message = _context(instance, routes=[
        route_row("r-inactive", priority=1, active=0),
        route_row("r-active", priority=50, active=1),
    ])
    selected = instance.select_route(client, device, topic, message)
    assert selected["id"] == "r-active"
