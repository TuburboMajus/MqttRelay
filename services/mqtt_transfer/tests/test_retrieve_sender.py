"""Smoke tests for ``MqttTransfer.retrieve_sender`` (topic -> device -> client)."""
import pytest

import services.mqtt_transfer.mqtt_transfer as mtt
from _helpers import client_row, device_row, message_row, seed, topic_row


def _seed_happy(instance, *, topic="devices/1", topic_active=1, device_id=1, client_id=1):
    seed(instance, "topics",
         [topic_row(topic, id_=1, device_id=device_id, client_id=client_id,
                    active=topic_active)] if topic else [])
    seed(instance, "devices", [device_row(id_=device_id, client_id=client_id)]
         if device_id is not None else [])
    seed(instance, "clients", [client_row(id_=client_id)] if client_id is not None else [])


def test_retrieve_sender_happy_path(instance):
    _seed_happy(instance, topic="devices/1")
    topic, device, client = instance.retrieve_sender(message_row(id_=1, topic="devices/1"))
    assert topic["id"] == 1
    assert device["id"] == 1
    assert client["name"] == "Acme"


def test_retrieve_sender_unknown_topic(instance):
    _seed_happy(instance, topic=None)
    with pytest.raises(mtt.TopicNotFound):
        instance.retrieve_sender(message_row(topic="unknown/topic"))


def test_retrieve_sender_disabled_topic(instance):
    _seed_happy(instance, topic="devices/1", topic_active=0)
    with pytest.raises(mtt.DisabledTopic):
        instance.retrieve_sender(message_row(topic="devices/1"))


def test_retrieve_sender_topic_without_device(instance):
    _seed_happy(instance, topic="devices/1", device_id=None)
    with pytest.raises(mtt.DeviceNotFound):
        instance.retrieve_sender(message_row(topic="devices/1"))


def test_retrieve_sender_topic_without_client(instance):
    _seed_happy(instance, topic="devices/1", client_id=None)
    with pytest.raises(mtt.ClientNotFound):
        instance.retrieve_sender(message_row(topic="devices/1"))


def test_retrieve_sender_device_not_linked(instance):
    # topic references device 2, but no device row exists
    seed(instance, "topics", [topic_row("devices/1", id_=1, device_id=2, client_id=1)])
    seed(instance, "devices", [])
    seed(instance, "clients", [client_row(id_=1)])
    with pytest.raises(mtt.DeviceNotFound):
        instance.retrieve_sender(message_row(topic="devices/1"))
