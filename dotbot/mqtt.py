"""Module for MQTT communication."""

import json
import os
from typing import Optional

from fastapi_mqtt import FastMQTT, MQTTConfig
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotbot.crypto import decrypt
from dotbot.logger import LOGGER
from dotbot.models import (
    ApplicationType,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
)
from dotbot.protocol import (
    PROTOCOL_VERSION,
    CommandMoveRaw,
    CommandRgbLed,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
)


class MqttSettings(BaseSettings):
    """Mqtt broker connection settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    mqtt_host: str = Field(default="localhost")
    mqtt_port: int = Field(default=1883)
    mqtt_use_ssl: bool = Field(default=False)
    mqtt_username: Optional[str] = Field(default=None)
    mqtt_password: Optional[str] = Field(default=None)


settings = MqttSettings()
mqtt_config = MQTTConfig(
    host=settings.mqtt_host,
    port=settings.mqtt_port,
    username=settings.mqtt_username,
    password=settings.mqtt_password,
    ssl=settings.mqtt_use_ssl,
)

mqtt = FastMQTT(
    config=mqtt_config,
)


def mqtt_command_move_raw(
    address: str,
    swarm_id: str,
    application: ApplicationType,
    command: DotBotMoveRawCommandModel,
):
    """MQTT callback for move_raw command."""
    logger = LOGGER.bind(
        context=__name__,
        address=address,
        application=application.name,
        command="move_raw",
        **command.model_dump(),
    )
    if address not in mqtt.controller.dotbots:
        logger.warning("DotBot not found")
        return
    logger.info("Sending command")
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(mqtt.controller.settings.gw_address, 16),
        swarm_id=int(swarm_id, 16),
        application=ApplicationType(application),
        version=PROTOCOL_VERSION,
    )
    payload = ProtocolPayload(
        header,
        PayloadType.CMD_MOVE_RAW,
        CommandMoveRaw(
            left_x=command.left_x,
            left_y=command.left_y,
            right_x=command.right_x,
            right_y=command.right_y,
        ),
    )
    mqtt.controller.send_payload(payload)
    mqtt.controller.dotbots[address].move_raw = command


def mqtt_command_rgb_led(
    address: str,
    swarm_id: str,
    application: ApplicationType,
    command: DotBotRgbLedCommandModel,
):
    """MQTT callback for rgb_led command."""
    logger = LOGGER.bind(
        context=__name__,
        address=address,
        application=application.name,
        command="rgb_led",
        **command.model_dump(),
    )
    if address not in mqtt.controller.dotbots:
        logger.warning("DotBot not found")
        return
    logger.info("Sending command")
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(mqtt.controller.settings.gw_address, 16),
        swarm_id=int(swarm_id, 16),
        application=ApplicationType(application),
        version=PROTOCOL_VERSION,
    )
    payload = ProtocolPayload(
        header,
        PayloadType.CMD_RGB_LED,
        CommandRgbLed(command.red, command.green, command.blue),
    )
    mqtt.controller.send_payload(payload)
    mqtt.controller.dotbots[address].rgb_led = command


MQTT_TOPICS = {
    "move_raw": {
        "callback": mqtt_command_move_raw,
        "model": DotBotMoveRawCommandModel,
    },
    "rgb_led": {
        "callback": mqtt_command_rgb_led,
        "model": DotBotRgbLedCommandModel,
    },
}
MQTT_ROOT = os.getenv("DOTBOT_MQTT_ROOT", "/dotbots")


def mqtt_root_topic(old=False):
    if mqtt.controller.settings.use_mqtt_crypto is True:
        return (
            f"{MQTT_ROOT}/{mqtt.controller.mqtt_topic}"
            if old is False
            else f"{MQTT_ROOT}/{mqtt.controller.old_mqtt_topic}"
        )
    return f"{MQTT_ROOT}"


def subscribe_to_mqtt_topics(client):
    """Subscribe to all topics for a DotBot swarm."""
    for topic in MQTT_TOPICS.keys():
        client.subscribe(
            f"{mqtt_root_topic()}/{mqtt.controller.settings.swarm_id}/+/+/{topic}"
        )


@mqtt.on_connect()
def connect(client, flags, rc, properties):
    """MQTT callback called on broker connection."""
    logger = LOGGER.bind(context=__name__, rc=rc, flags=flags, **properties)
    logger.info("Connected")
    subscribe_to_mqtt_topics(client)


@mqtt.on_message()
async def message(_, topic, payload, qos, properties):
    """MQTT callback called on message received."""
    logger = LOGGER.bind(context=__name__, topic=topic, qos=qos, **properties)
    if mqtt.controller.settings.use_mqtt_crypto is True:
        topic = topic.split("/")[3:]
    else:
        topic = topic.split("/")[2:]
    if len(topic) < 4:
        logger.warning(f"Invalid topic '{topic}'")
        return
    swarm_id, address, application, cmd = topic
    if mqtt.controller.settings.use_mqtt_crypto is True:
        secret_topic = topic[2]
        if secret_topic == mqtt.controller.old_mqtt_topic:
            secret_key = mqtt.controller.old_mqtt_aes_key
            if secret_key is None:
                logger.warning("Topic was disabled", topic=secret_topic)
                return
        else:
            secret_key = mqtt.controller.mqtt_aes_key
        payload = decrypt(payload, secret_key)
        if not payload:
            logger.warning("Invalid payload")
            return
    try:
        payload = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON payload")
        return
    logger.info("Message received")
    try:
        MQTT_TOPICS[cmd]["callback"](
            address,
            swarm_id,
            ApplicationType(int(application)),
            MQTT_TOPICS[cmd]["model"](**payload),
        )
    except ValidationError as exc:
        logger.warning(f"Invalid payload: {exc.errors()}")


@mqtt.on_disconnect()
def disconnect(_, packet, exc=None):
    """MQTT callback called on broker disconnect."""
    logger = LOGGER.bind(context=__name__, packet=packet, exc=exc)
    logger.info("Disconnected")


@mqtt.on_subscribe()
def subscribe(client, mid, qos, properties):
    """MQTT callback called on topic subscription."""
    logger = LOGGER.bind(context=__name__, qos=qos, **properties)
    topic = (
        client.get_subscriptions_by_mid(mid)[0].topic
        if client.get_subscriptions_by_mid(mid)
        else None
    )
    logger.info(f"Subscribed to {topic}")
