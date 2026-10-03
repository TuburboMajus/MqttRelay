"""Smoke tests for dispatch: ``on_data_sent``, ``dispatch_to_deposit`` and
``send_parsed_data``."""
import uuid
from unittest.mock import patch

import pytest

import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import (
    FakeAsyncDispatcher, FakeDispatcher, FakeFailingDispatcher,
    destination_row, dispatch_entity, rec, route_row, seed,
)

RULE_ID = str(uuid.uuid4())


def _deposit(destination_id):
    return rec(rule_id=RULE_ID, destination_id=destination_id)


# --------------------------------------------------------------------------- #
# on_data_sent
# --------------------------------------------------------------------------- #
def test_on_data_sent_marks_sent(instance):
    dispatch = dispatch_entity()
    seed(instance, "dispatches", [])
    ok = instance.on_data_sent(dispatch, status="sent", http_status=200,
                               response_snippet="ok")
    assert ok is True
    assert dispatch["status"].name == "sent"
    assert dispatch["http_status"] == 200


def test_on_data_sent_marks_failed(instance):
    dispatch = dispatch_entity()
    seed(instance, "dispatches", [])
    ok = instance.on_data_sent(dispatch, status="failed", http_status=None,
                               response_snippet="boom")
    assert ok is False
    assert dispatch["status"].name == "failed"


# --------------------------------------------------------------------------- #
# dispatch_to_deposit
# --------------------------------------------------------------------------- #
def test_dispatch_to_deposit_sync_success(instance):
    extraction = dispatch_entity()
    data_points = [rec(device_id=5, metric_id=1)]
    deposit = _deposit(3)
    seed(instance, "destinations",
         [destination_row(id_=3, options_json='{"table": "client_points"}')])
    dispatches = seed(instance, "dispatches", [])

    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        result = instance.dispatch_to_deposit(deposit, extraction, data_points)

    assert result is True
    assert len(dispatches.created) == 1
    assert dispatches.created[0]["rule_id"] == RULE_ID
    assert dispatches.created[0]["destination_id"] == 3

    instance_dispatcher = FakeDispatcher.instances[-1]
    assert instance_dispatcher.parsed_points == [{"device_id": 5, "metric_id": 1}]
    assert instance_dispatcher.kwargs.get("table") == "client_points"
    assert instance_dispatcher.kwargs.get("host") == "127.0.0.1"


def test_dispatch_to_deposit_creates_queued_dispatch(instance):
    extraction = dispatch_entity()
    deposit = _deposit(3)
    seed(instance, "destinations", [destination_row(id_=3)])
    seed(instance, "dispatches", [])

    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        with patch.object(instance, "on_data_sent", return_value=True) as ods:
            result = instance.dispatch_to_deposit(deposit, extraction, [])

    assert result is True
    ods.assert_called_once()
    created = ods.call_args.args[0]
    assert created["rule_id"] == RULE_ID
    assert created["destination_id"] == 3
    assert created["extraction_id"] == extraction["id"]
    assert created["status"].name == "queued"
    assert ods.call_args.kwargs["status"] == "sent"


def test_dispatch_to_deposit_missing_destination(instance):
    extraction = dispatch_entity()
    deposit = _deposit(99)
    seed(instance, "destinations", [])
    seed(instance, "dispatches", [])
    with pytest.raises(mtt.DestinationNotFound):
        instance.dispatch_to_deposit(deposit, extraction, [])


def test_dispatch_to_deposit_unimplemented_dispatcher(instance):
    extraction = dispatch_entity()
    deposit = _deposit(3)
    seed(instance, "destinations", [destination_row(id_=3, type_="postgres")])
    seed(instance, "dispatches", [])
    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        with pytest.raises(mtt.DispatcherNotFound):
            instance.dispatch_to_deposit(deposit, extraction, [])


def test_dispatch_to_deposit_dispatcher_failure(instance):
    extraction = dispatch_entity()
    deposit = _deposit(3)
    seed(instance, "destinations", [destination_row(id_=3)])
    seed(instance, "dispatches", [])
    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeFailingDispatcher}):
        result = instance.dispatch_to_deposit(deposit, extraction, [])
    assert result is False


def test_dispatch_to_deposit_dispatcher_raises_is_handled(instance, caplog):
    class ExplodingDispatcher:
        asynchronous = False

        def __init__(self, **kwargs):
            pass

        def dispatch(self, parsed_points=None):
            raise RuntimeError("boom")

    extraction = dispatch_entity()
    deposit = _deposit(3)
    seed(instance, "destinations", [destination_row(id_=3)])
    seed(instance, "dispatches", [])
    with patch.object(mtt, "DISPATCHERS", {"mysql": ExplodingDispatcher}):
        with caplog.at_level("WARNING"):
            result = instance.dispatch_to_deposit(deposit, extraction, [])
    assert result is False
    assert "Dispatch has failed" in caplog.text


def test_dispatch_to_deposit_async_registers_callback(instance):
    extraction = dispatch_entity()
    deposit = _deposit(3)
    seed(instance, "destinations", [destination_row(id_=3)])
    seed(instance, "dispatches", [])
    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeAsyncDispatcher}):
        result = instance.dispatch_to_deposit(deposit, extraction, [])
    # async path returns immediately without waiting for the sink
    assert result is True
    dispatcher = FakeAsyncDispatcher.instances[-1]
    assert dispatcher.callback is not None
    # invoking the completion callback must not raise
    dispatcher.callback(status="sent", http_status=200, response_snippet="done")


# --------------------------------------------------------------------------- #
# send_parsed_data
# --------------------------------------------------------------------------- #
def test_send_parsed_data_dispatches_to_all_deposits(instance):
    extraction = dispatch_entity()
    route = route_row(RULE_ID)
    seed(instance, "deposits", [_deposit(3), _deposit(4)])
    seed(instance, "destinations", [destination_row(id_=3), destination_row(id_=4)])
    seed(instance, "dispatches", [])
    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        result = instance.send_parsed_data(route, extraction, [])
    assert result is True
    assert len(FakeDispatcher.instances) == 2


def test_send_parsed_data_no_deposits_raises(instance):
    extraction = dispatch_entity()
    route = route_row(RULE_ID)
    seed(instance, "deposits", [])
    with pytest.raises(mtt.DepositNotFound):
        instance.send_parsed_data(route, extraction, [])


def test_send_parsed_data_false_if_any_dispatch_fails(instance):
    extraction = dispatch_entity()
    route = route_row(RULE_ID)
    seed(instance, "deposits", [_deposit(3), _deposit(4)])
    seed(instance, "destinations", [destination_row(id_=3), destination_row(id_=4)])
    seed(instance, "dispatches", [])
    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeFailingDispatcher}):
        result = instance.send_parsed_data(route, extraction, [])
    assert result is False


def test_send_parsed_data_recovers_from_dispatch_errors(instance, caplog):
    extraction = dispatch_entity()
    route = route_row(RULE_ID)
    # destination 99 does not exist -> dispatch_to_deposit raises, must be contained
    seed(instance, "deposits", [_deposit(3), _deposit(99)])
    seed(instance, "destinations", [destination_row(id_=3)])
    seed(instance, "dispatches", [])
    with patch.object(mtt, "DISPATCHERS", {"mysql": FakeDispatcher}):
        with caplog.at_level("ERROR"):
            result = instance.send_parsed_data(route, extraction, [])
    assert result is False
    assert "Error while dispatching data" in caplog.text
