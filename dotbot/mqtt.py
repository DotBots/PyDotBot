"""Module for MQTT communication."""

import json

from fastapi_mqtt import FastMQTT, MQTTConfig
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str


settings = MqttSettings()
mqtt_config = MQTTConfig(
    host=settings.mqtt_host,
    port=settings.mqtt_port,
    username=settings.mqtt_username,
    password=settings.mqtt_password,
    ssl=True,
)

mqtt = FastMQTT(
    config=mqtt_config,
)


def mqtt_command_move_raw(
    address: str, application: ApplicationType, command: DotBotMoveRawCommandModel
):
    """MQTT callback for move_raw command."""
    logger = LOGGER.bind(
        context=__name__,
        address=address,
        application=application.name,
        command="move_raw",
        **command.dict(),
    )
    logger.info("Sending command")
    if address not in mqtt.controller.dotbots:
        logger.warning(f"DotBot {address} not found in controller")
        return
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(mqtt.controller.settings.gw_address, 16),
        swarm_id=int(mqtt.controller.settings.swarm_id, 16),
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
    address: str, application: ApplicationType, command: DotBotRgbLedCommandModel
):
    """MQTT callback for rgb_led command."""
    logger = LOGGER.bind(
        context=__name__,
        address=address,
        application=application.name,
        command="rgb_led",
        **command.dict(),
    )
    logger.info("Sending command")
    if address not in mqtt.controller.dotbots:
        logger.warning(f"DotBot {address} not found in controller")
        return
    header = ProtocolHeader(
        destination=int(address, 16),
        source=int(mqtt.controller.settings.gw_address, 16),
        swarm_id=int(mqtt.controller.settings.swarm_id, 16),
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


@mqtt.on_connect()
def connect(client, flags, rc, properties):
    """MQTT callback called on broker connection."""
    logger = LOGGER.bind(context=__name__, rc=rc, flags=flags, **properties)
    logger.info("Connected")
    for topic in MQTT_TOPICS.keys():
        client.subscribe(f"/dotbots/+/+/{topic}")


@mqtt.on_message()
async def message(_, topic, payload, qos, properties):
    """MQTT callback called on message received."""
    logger = LOGGER.bind(context=__name__, topic=topic, qos=qos, **properties)
    topic = topic.split("/")[2:]
    if len(topic) < 3:
        logger.warning(f"Invalid topic '{topic}'")
        return
    address, application, cmd = topic
    try:
        payload = json.loads(payload.decode())
    except json.JSONDecodeError:
        logger.warning("Invalid JSON payload")
        return
    logger.info("Command received")
    MQTT_TOPICS[cmd]["callback"](
        address, ApplicationType(int(application)), MQTT_TOPICS[cmd]["model"](**payload)
    )


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
    logger.info(f"Subscribed to topic {topic}")
