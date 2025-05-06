# SPDX-FileCopyrightText: 2025-present Inria
# SPDX-FileCopyrightText: 2025-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Interface of the Dotbot Edge Gateway."""

import asyncio
import base64
import time
import uuid
from binascii import hexlify
from dataclasses import dataclass
from typing import Dict

import serial
from gmqtt import Client as MQTTClient
from qrkey import qrkey_settings

from dotbot import DOTBOT_ADDRESS_DEFAULT, GATEWAY_ADDRESS_DEFAULT
from dotbot.hdlc import HDLCHandler, HDLCState, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.models import DotBotModel
from dotbot.protocol import Frame, Header, PacketType, ProtocolPayloadParserException
from dotbot.serial_interface import SerialInterface, SerialInterfaceException

LOST_DELAY = 5  # seconds


@dataclass
class EdgeGatewaySettings:
    """Data class that holds controller settings."""

    port: str
    baudrate: int
    dotbot_address: str
    gw_address: str
    verbose: bool = False


class EdgeGateway:
    """Edge gateway class."""

    def __init__(self, settings: EdgeGatewaySettings):
        self.dotbots: Dict[str, DotBotModel] = {}
        self.logger = LOGGER.bind(context=__name__)
        self.header = Header(
            destination=int(DOTBOT_ADDRESS_DEFAULT, 16),
            source=int(settings.gw_address, 16),
        )
        self.settings = settings
        self.hdlc_handler = HDLCHandler()
        self.serial = None
        self.mqtt_client = None

    def on_connect(self, _, flags, rc, properties):
        logger = self.logger.bind(
            context=__name__,
            rc=rc,
            flags=flags,
            **properties,
        )
        logger.info("Edge Gateway connected to broker")
        self.mqtt_client.subscribe("/pydotbot/controller_to_edge")

    def on_message(self, _, topic, payload, qos, properties):
        """Called when a message is received from the controller."""
        logger = self.logger.bind(topic=topic)
        logger.info("MQTT message received", message=payload.decode())
        self.serial.write(hdlc_encode(base64.b64decode(payload)))

    def on_disconnect(self, _, packet, exc=None):
        logger = self.logger.bind(packet=packet, exc=exc)
        logger.info("Disconnected")

    def on_subscribe(self, client, mid, qos, properties):
        logger = self.logger.bind(qos=qos, **properties)
        topic = (
            client.get_subscriptions_by_mid(mid)[0].topic
            if client.get_subscriptions_by_mid(mid)
            else None
        )
        logger.info(f"Subscribed to {topic}")

    async def _start_serial(self):
        """Starts the serial listener thread in a coroutine."""
        self.logger.info("Starting serial interface")
        queue = asyncio.Queue()
        event_loop = asyncio.get_event_loop()

        def on_byte_received(byte):
            """Callback called on byte received."""
            event_loop.call_soon_threadsafe(queue.put_nowait, byte)

        self.serial = SerialInterface(
            self.settings.port, self.settings.baudrate, on_byte_received
        )
        await asyncio.sleep(1)
        self.serial.write(hdlc_encode(b"\x01\xff"))
        while 1:
            byte = await queue.get()
            self.handle_byte(byte)

    def handle_byte(self, byte):
        """Called on each byte received over UART."""
        self.hdlc_handler.handle_byte(byte)
        if self.hdlc_handler.state == HDLCState.READY:
            payload = self.hdlc_handler.payload
            if payload:
                try:
                    header = Header().from_bytes(payload)
                except ProtocolPayloadParserException:
                    self.logger.warning("Cannot parse header")
                    if self.settings.verbose is True:
                        print(header)
                    return
                source = hexlify(int(header.source).to_bytes(8, "big")).decode()
                logger = self.logger.bind(source=source)
                if header.type_ != PacketType.DATA:
                    logger.info("Skipping non data packet")
                    return
                if self.mqtt_client and self.mqtt_client.is_connected is False:
                    logger.warning("MQTT client not connected")
                    return
                if source == GATEWAY_ADDRESS_DEFAULT:
                    logger.warning("Invalid source in header")
                    return
                dotbot = DotBotModel(
                    address=source,
                    last_seen=time.time(),
                )
                self.dotbots.update({source: dotbot})
                logger.info(
                    "Forwarding serial payload to MQTT",
                    payload_type=hex(payload[header.size]),
                )
                self.mqtt_client.publish(
                    "/pydotbot/edge_to_controller",
                    base64.b64encode(payload).decode(),
                )

    def send_frame(self, frame: Frame):
        """Sends a command in an HDLC frame over serial."""
        destination = hexlify(int(frame.header.destination).to_bytes(8, "big")).decode()
        if destination not in self.dotbots:
            return
        if self.serial is not None:
            self.serial.write(hdlc_encode(frame.to_bytes()))
            self.logger.debug(
                "Payload sent",
                application=self.dotbots[destination].application.name,
                destination=destination,
                payload_type=frame.payload_type.name,
            )

    async def _connect_to_mqtt_broker(self):
        """Connect to the MQTT broker."""
        self.logger.info("Connecting to MQTT broker")
        self.mqtt_client: MQTTClient = MQTTClient(f"qrkey-{uuid.uuid4().hex}")
        self.mqtt_client.set_config(qrkey_settings.model_dump(exclude_none=True))
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        self.mqtt_client.on_subscribe = self.on_subscribe
        await self.mqtt_client.connect(
            host=qrkey_settings.mqtt_host,
            port=qrkey_settings.mqtt_port,
            ssl=qrkey_settings.mqtt_use_ssl,
            keepalive=qrkey_settings.mqtt_keepalive,
            version=qrkey_settings.mqtt_version,
        )

    async def _dotbots_refresh(self):
        """Coroutine that periodically checks available dotbots."""
        while 1:
            dotbots_to_remove = []
            for address, dotbot in self.dotbots.items():
                if dotbot.last_seen + LOST_DELAY < time.time():
                    dotbots_to_remove.append(address)
            for address in dotbots_to_remove:
                self.logger.info("Removing lost dotbot", address=address)
                self.dotbots.pop(address)
            await asyncio.sleep(1)

    async def run(self):
        """Launch the controller."""
        tasks = []
        self.logger.info("Starting edge gateway")
        try:
            tasks = [
                asyncio.create_task(
                    name="MQTT broker client", coro=self._connect_to_mqtt_broker()
                ),
                # TODO better manage status of dotbots between the gateway board and the edge gateway
                # asyncio.create_task(
                #     name="Available dotbots check", coro=self._dotbots_refresh()
                # ),
                asyncio.create_task(name="Serial interface", coro=self._start_serial()),
            ]
            await asyncio.gather(*tasks)
        except (
            SerialInterfaceException,
            serial.serialutil.SerialException,
        ) as exc:
            self.logger.error(f"Error: {exc}")
        except SystemExit:
            pass
        finally:
            self.logger.info("Stopping edge gateway")
            self.serial.write(hdlc_encode(b"\x01\xfe"))
            for task in tasks:
                self.logger.info(f"Cancelling task '{task.get_name()}'")
                task.cancel()
            self.logger.info("Edge gateway stopped")
