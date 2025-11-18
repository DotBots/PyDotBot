import asyncio
from unittest.mock import patch

import pytest
from dotbot_utils.hdlc import hdlc_encode
from dotbot_utils.protocol import Frame, Header, Packet

from dotbot.adapter import MarilibCloudAdapter, MarilibEdgeAdapter, SerialAdapter
from dotbot.protocol import PayloadAdvertisement


@pytest.mark.asyncio
@patch("dotbot.adapter.SerialInterface")
async def test_serial_adapter(_):
    adapter = SerialAdapter(port="test", baudrate=9600)
    frames = []

    def on_frame_received(f):
        frames.append(f)

    payload = PayloadAdvertisement()
    frame = Frame(header=Header(), packet=Packet().from_payload(payload))

    async def feed_bytes(queue):
        for b in hdlc_encode(frame.to_bytes()):
            await queue.put(b.to_bytes(1, "little"))
            await asyncio.sleep(0.05)

    mock_queue = asyncio.Queue()
    with patch("asyncio.Queue", return_value=mock_queue):

        async def start_task():
            await adapter.start(on_frame_received)

        asyncio.create_task(name="test_serial_adapter_start", coro=start_task())
        await feed_bytes(mock_queue)

        await asyncio.sleep(0.1)
        assert frames == [frame]

        adapter.send_payload(frame.header.destination, payload)
        adapter.serial.write.assert_called_once_with(hdlc_encode(frame.to_bytes()))
        adapter.serial.flush.assert_called_once()
        adapter.close()
        adapter.serial.stop.assert_called_once()


@pytest.mark.asyncio
@patch("dotbot.adapter.MarilibEdge")
async def test_marilib_edge_adapter(_):
    adapter = MarilibEdgeAdapter(port="p", baudrate=1)
    frames = []

    def on_frame_received(f):
        frames.append(f)

    payload = PayloadAdvertisement()
    frame = Frame(header=Header(), packet=Packet().from_payload(payload))

    mock_queue = asyncio.Queue()
    with patch("asyncio.Queue", return_value=mock_queue):

        async def start_task():
            await adapter.start(on_frame_received)

        asyncio.create_task(start_task())
        await asyncio.sleep(3.1)

        event_loop = asyncio.get_event_loop()
        event_loop.call_soon(adapter.on_frame_received, frame)

        await asyncio.sleep(0.01)
        assert frames == [frame]

        adapter.send_payload(frame.header.destination, payload)
        adapter.mari.send_frame.assert_called_once_with(
            dst=frame.header.destination, payload=frame.packet.to_bytes()
        )
        adapter.close()
        adapter.mari.close.assert_called_once()


@pytest.mark.asyncio
@patch("dotbot.adapter.MarilibCloud")
async def test_marilib_cloud_adapter(_):
    adapter = MarilibCloudAdapter(host="h", port=1, use_tls=False, network_id=2)
    frames = []

    def on_frame_received(f):
        frames.append(f)

    payload = PayloadAdvertisement()
    frame = Frame(header=Header(), packet=Packet().from_payload(payload))

    mock_queue = asyncio.Queue()
    with patch("asyncio.Queue", return_value=mock_queue):

        async def start_task():
            await adapter.start(on_frame_received)

        asyncio.create_task(start_task())
        await asyncio.sleep(3.1)

        event_loop = asyncio.get_event_loop()
        event_loop.call_soon(adapter.on_frame_received, frame)

        await asyncio.sleep(0.01)
        assert frames == [frame]

        adapter.send_payload(frame.header.destination, payload)
        adapter.mari.send_frame.assert_called_once_with(
            dst=frame.header.destination, payload=frame.packet.to_bytes()
        )
        adapter.close()
