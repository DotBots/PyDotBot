"""Module for MQTT communication."""

import json
import os
from typing import Any, Optional

from fastapi_mqtt import FastMQTT, MQTTConfig
from pydantic import Field, ValidationError
from pydantic.tools import parse_obj_as
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotbot.crypto import decrypt, encrypt
from dotbot.logger import LOGGER
from dotbot.models import (
    ApplicationType,
    DotBotCalibrationIndexModel,
    DotBotMoveRawCommandModel,
    DotBotNotificationCommand,
    DotBotNotificationModel,
    DotBotQueryModel,
    DotBotReplyModel,
    DotBotRequestModel,
    DotBotRequestType,
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


def publish_dotbots(topic, key):
    if mqtt.client.is_connected is False:
        return
    logger = LOGGER.bind(context=__name__, topic=topic)
    logger.info("Publish dotbots")
    data = [
        dotbot.model_dump(exclude_none=True)
        for dotbot in mqtt.controller.get_dotbots(DotBotQueryModel())
    ]
    message = DotBotReplyModel(
        request=DotBotRequestType.DOTBOTS,
        data=data,
    ).model_dump(exclude_none=True)
    message = encrypt(json.dumps(message), key)
    mqtt.publish(topic, message)


def publish_lh2_state(topic, key):
    if mqtt.client.is_connected is False:
        return
    logger = LOGGER.bind(context=__name__, topic=topic)
    logger.info("Publish LH2 state")
    message = DotBotReplyModel(
        request=DotBotRequestType.LH2_CALIBRATION_STATE,
        data=mqtt.controller.lh2_manager.state_model.model_dump(),
    ).model_dump(exclude_none=True)
    message = encrypt(json.dumps(message), key)
    mqtt.publish(topic, message)


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


async def mqtt_lh2_add_calibration(payload):
    try:
        payload = DotBotCalibrationIndexModel(**payload)
    except ValidationError as exc:
        LOGGER.warning(f"Invalid calibration index payload: {exc.errors()}")
        return
    logger = LOGGER.bind(
        context=__name__,
        **payload.model_dump(),
    )
    logger.info("Add calibration point")
    mqtt.controller.lh2_manager.add_calibration_point(payload.index)


async def mqtt_lh2_start_calibration():
    logger = LOGGER.bind(context=__name__)
    logger.info("Start calibration")
    mqtt.controller.lh2_manager.compute_calibration()


MQTT_COMMAND_TOPICS = {
    "move_raw": mqtt_command_move_raw,
    "rgb_led": mqtt_command_rgb_led,
    "waypoints": mqtt_command_waypoints,
    "clear_history": mqtt_command_clear_history,
}
MQTT_LH2_CALIBRATION_TOPICS = {
    "add": mqtt_lh2_add_calibration,
    "start": mqtt_lh2_start_calibration,
}
MQTT_ROOT = os.getenv("DOTBOT_MQTT_ROOT", "/dotbots")


async def handle_request(topic, secret_key, request):
    logger = LOGGER.bind(context=__name__, topic=topic, **request)
    logger.info("Request received")
    try:
        request = DotBotRequestModel(**request)
    except ValidationError as exc:
        logger.warning(f"Invalid request: {exc.errors()}")
        return

    if (
        mqtt.controller.old_mqtt_topic is not None
        and topic == mqtt.controller.old_mqtt_topic
    ):
        reply_topic = f"{mqtt_root_topic(old=True)}/reply/{request.reply}"
    else:
        reply_topic = f"{mqtt_root_topic()}/reply/{request.reply}"
    if request.request == DotBotRequestType.DOTBOTS:
        publish_dotbots(reply_topic, secret_key)
    elif request.request == DotBotRequestType.LH2_CALIBRATION_STATE:
        publish_lh2_state(reply_topic, secret_key)
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
    for topic in MQTT_COMMAND_TOPICS.keys():
        client.subscribe(
            f"{mqtt_root_topic()}/{mqtt.controller.settings.swarm_id}/+/+/{topic}"
        )
    for topic in MQTT_LH2_CALIBRATION_TOPICS.keys():
        client.subscribe(f"{mqtt_root_topic()}/lh2/calibration/{topic}")
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
        await handle_request(secret_topic, secret_key, payload)
    elif len(topic_split) == 4:  # LH2 calibration
        cmd = topic_split[-1]
        await MQTT_LH2_CALIBRATION_TOPICS[cmd](
            payload
        ) if payload else await MQTT_LH2_CALIBRATION_TOPICS[cmd]()
    elif len(topic_split) == 5:  # Command
        swarm_id, address, application, cmd = topic_split[1:]
        await MQTT_COMMAND_TOPICS[cmd](
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
