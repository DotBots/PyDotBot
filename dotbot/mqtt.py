"""Module for MQTT communication."""

import json
import os
from typing import Any, Optional

from fastapi_mqtt import FastMQTT, MQTTConfig
from pydantic import Field, ValidationError
from pydantic.tools import parse_obj_as
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotbot.crypto import decrypt
from dotbot.logger import LOGGER
from dotbot.models import (
    ApplicationType,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotRequestModel,
    DotBotRgbLedCommandModel,
    DotBotWaypoints,
)
from dotbot.protocol import (
    PROTOCOL_VERSION,
    CommandMoveRaw,
    CommandRgbLed,
    GPSPosition,
    GPSWaypoints,
    LH2Location,
    LH2Waypoints,
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


async def mqtt_command_move_raw(
    address: str,
    swarm_id: str,
    application: ApplicationType,
    command: Any,
):
    """MQTT callback for move_raw command."""
    try:
        command = DotBotMoveRawCommandModel(**command)
    except ValidationError as exc:
        LOGGER.warning(f"Invalid move raw command: {exc.errors()}")
        return
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


async def mqtt_command_rgb_led(
    address: str,
    swarm_id: str,
    application: ApplicationType,
    command: Any,
):
    """MQTT callback for rgb_led command."""
    try:
        command = DotBotRgbLedCommandModel(**command)
    except ValidationError as exc:
        LOGGER.warning(f"Invalid rgb led command: {exc.errors()}")
        return
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


async def mqtt_command_waypoints(
    address: str,
    swarm_id: str,
    application: ApplicationType,
    command: Any,
):
    command = parse_obj_as(DotBotWaypoints, command)
    logger = LOGGER.bind(
        context=__name__,
        address=address,
        application=application.name,
        command="waypoints",
        threshold=command.threshold,
        length=len(command.waypoints),
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
    waypoints_list = command.waypoints
    if ApplicationType(application) == ApplicationType.SailBot:
        if mqtt.controller.dotbots[address].gps_position is not None:
            waypoints_list = [
                mqtt.controller.dotbots[address].gps_position
            ] + command.waypoints
        payload = ProtocolPayload(
            header,
            PayloadType.GPS_WAYPOINTS,
            GPSWaypoints(
                threshold=command.threshold,
                waypoints=[
                    GPSPosition(
                        latitude=int(waypoint.latitude * 1e6),
                        longitude=int(waypoint.longitude * 1e6),
                    )
                    for waypoint in command.waypoints
                ],
            ),
        )
    else:  # DotBot application
        if mqtt.controller.dotbots[address].lh2_position is not None:
            waypoints_list = [
                mqtt.controller.dotbots[address].lh2_position
            ] + command.waypoints
        payload = ProtocolPayload(
            header,
            PayloadType.LH2_WAYPOINTS,
            LH2Waypoints(
                threshold=command.threshold,
                waypoints=[
                    LH2Location(
                        pos_x=int(waypoint.x * 1e6),
                        pos_y=int(waypoint.y * 1e6),
                        pos_z=int(waypoint.z * 1e6),
                    )
                    for waypoint in command.waypoints
                ],
            ),
        )
    mqtt.controller.send_payload(payload)
    mqtt.controller.dotbots[address].waypoints = waypoints_list
    mqtt.controller.dotbots[address].waypoints_threshold = command.threshold
    await mqtt.controller.notify_clients(
        DotBotNotificationModel(cmd=DotBotNotificationCommand.RELOAD)
    )


async def mqtt_command_clear_history(
    address: str,
    _: str,
    application: ApplicationType,
    command: str,
):
    logger = LOGGER.bind(
        context=__name__,
        address=address,
        application=application.name,
        command=command,
    )
    if address not in mqtt.controller.dotbots:
        logger.warning("DotBot not found")
        return
    logger.info("Sending command")
    mqtt.controller.dotbots[address].position_history = []


MQTT_TOPICS = {
    "move_raw": mqtt_command_move_raw,
    "rgb_led": mqtt_command_rgb_led,
    "waypoints": mqtt_command_waypoints,
    "clear_history": mqtt_command_clear_history,
}
MQTT_ROOT = os.getenv("DOTBOT_MQTT_ROOT", "/dotbots")


async def handle_request(_, request):
    logger = LOGGER.bind(context=__name__, **request)
    logger.info("Request received")
    try:
        request = DotBotRequestModel(**request)
    except ValidationError as exc:
        logger.warning(f"Invalid request: {exc.errors()}")
        return

    if request.cmd == DotBotNotificationCommand.RELOAD:
        mqtt.controller.publish_dotbots(f"{mqtt_root_topic()}/reply/{request.reply}")
    else:
        logger.warning("Invalid request command")


def mqtt_root_topic(old=False):
    return (
        f"{MQTT_ROOT}/{mqtt.controller.mqtt_topic}"
        if old is False
        else f"{MQTT_ROOT}/{mqtt.controller.old_mqtt_topic}"
    )


def subscribe_to_mqtt_topics(client):
    """Subscribe to all topics for a DotBot swarm."""
    for topic in MQTT_TOPICS.keys():
        client.subscribe(
            f"{mqtt_root_topic()}/{mqtt.controller.settings.swarm_id}/+/+/{topic}"
        )
    client.subscribe(f"{mqtt_root_topic()}/request")


@mqtt.on_connect()
def connect(client, flags, rc, properties):
    """MQTT callback called on broker connection."""
    logger = LOGGER.bind(context=__name__, rc=rc, flags=flags, **properties)
    logger.info("Connected")
    subscribe_to_mqtt_topics(client)


@mqtt.on_message()
async def message(client, topic, payload, qos, properties):
    """MQTT callback called on message received."""
    logger = LOGGER.bind(context=__name__, topic=topic, qos=qos, **properties)
    topic_split = topic.split("/")[2:]
    secret_topic = topic_split[0]
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

    if len(topic_split) == 2:  # Request
        await handle_request(client, payload)
    elif len(topic_split) == 5:  # Command
        swarm_id, address, application, cmd = topic_split[1:]
        await MQTT_TOPICS[cmd](
            address,
            swarm_id,
            ApplicationType(int(application)),
            payload,
        )
    else:
        logger.warning(f"Invalid topic '{topic}'")


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
