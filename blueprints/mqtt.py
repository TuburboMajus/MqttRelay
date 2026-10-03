from flask import Blueprint
from core.repository import repos
from core.models import MqttMessage

from datetime import datetime, date
import logging


mqtt_bp = Blueprint('mqtt', __name__)

def setup(config=None):
    """Setup MQTT blueprint with configuration."""
    return mqtt_bp


def setup_mqtt(mqtt):
    """Setup MQTT message handlers."""

    # MQTT hooks
    @mqtt.on_connect()
    def handle_connect(client, userdata, flags, rc):
        mqtt.app.logger.info(f"Connected to MQTT broker with result code {rc}")
        mqtt.subscribe("+/+/+", qos=0)

    @mqtt.on_disconnect()
    def handle_disconnect(*args, **kwargs):
        # flask-mqtt 1.2.1 calls the disconnect handler with NO arguments
        # (_handle_disconnect -> self._disconnect_handler()), unlike on_connect
        # which forwards (client, userdata, flags, rc). Accept *args/**kwargs so
        # this survives both the current behaviour and a future flask-mqtt fix,
        # and never crashes the paho network thread.
        rc = args[2] if len(args) > 2 else kwargs.get('rc', 'unknown')
        mqtt.app.logger.warning(f"Disconnected from MQTT broker (rc={rc})")

    @mqtt.on_message()
    def handle_mqtt_message(client, userdata, message):
        try:
            payload_str = message.payload.decode("utf-8", errors="replace") if message.payload else None
            mqtt_message = MqttMessage(
                client=message.topic.split("/")[0],
                topic=message.topic,
                payload=payload_str,
                qos=message.qos,
                at=datetime.utcnow()
            )
            repos['MqttMessage'].create(mqtt_message)
            mqtt.app.logger.debug(f"Stored MQTT message from topic {message.topic} (qos={message.qos})")
        except Exception as e:
            mqtt.app.logger.exception(f"Failed to store message from topic {message.topic}: {e}")

    return mqtt_bp


mqtt_bp.setup_mqtt = setup_mqtt