from temod_flask.blueprint import Blueprint

from datetime import datetime, date

import traceback
import json
import os


mqtt_blueprint = Blueprint('mqtt',__name__, default_config={})


def setup_mqtt(mqtt):

    # MQTT hooks
    @mqtt.on_connect()
    def handle_connect(client, userdata, flags, rc):
        mqtt.app.logger.info(f"Connected to MQTT broker with result code {rc}")
        mqtt.subscribe("+/+/+", qos=0)

    @mqtt.on_disconnect()
    def handle_disconnect(client, userdata, rc):
        mqtt.app.logger.warning(f"Disconnected from MQTT broker (rc={rc})")

    @mqtt.on_message()
    def handle_mqtt_message(client, userdata, message):
        try:
            MqttMessage.storage.create(MqttMessage(
                id=-1, client=message.topic.split("/")[0], topic=message.topic, payload=message.payload.decode("utf-8", errors="replace") if message.payload else None,
                qos=message.qos, at=datetime.now()
            ))
        except Exception as e:
            mqtt.app.logger.exception(f"Failed to store message from topic {message.topic}: {e}")

    return mqtt_blueprint

mqtt_blueprint.setup_mqtt = setup_mqtt