import asyncio
import threading
import time

import pytest
from dotbot_utils.protocol import Frame, Header, Packet

from dotbot.inbox import FrameInbox
from dotbot.protocol import PayloadControlMode, PayloadDotBotAdvertisement

ROBOTS = 200


def _advert(source: int, seq: int) -> Frame:
    payload = PayloadDotBotAdvertisement(pos_x=seq, report=True)
    return Frame(header=Header(source=source), packet=Packet.from_payload(payload))


def _event(source: int, seq: int) -> Frame:
    return Frame(
        header=Header(source=source),
        packet=Packet.from_payload(PayloadControlMode(mode=seq % 2)),
    )


async def _drain(task, inbox, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while len(inbox) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    task.cancel()


@pytest.mark.asyncio
async def test_a_flood_stays_bounded_keeps_the_latest_state_and_every_event():
    """A gateway thread far faster than the loop: what waits is bounded by
    the fleet, each robot's last advertisement wins, and no event is lost."""
    inbox = FrameInbox(asyncio.get_running_loop())
    rounds = 50
    adverts = [[_advert(0x1000 + r, n) for r in range(ROBOTS)] for n in range(rounds)]
    events = [_event(0x1000 + n % ROBOTS, n) for n in range(rounds)]
    handled = []
    longest = []

    def handler(frame):
        longest.append(len(inbox))
        handled.append(frame)
        time.sleep(0.0005)  # far slower than the feeder below

    def feed():
        for n in range(rounds):
            for frame in adverts[n]:
                inbox.put(frame)
            inbox.put(events[n])

    task = asyncio.create_task(inbox.run(handler))
    await asyncio.to_thread(feed)
    await _drain(task, inbox)

    assert inbox.coalesced > 0
    assert max(longest) <= ROBOTS + rounds
    assert len(handled) < rounds * ROBOTS
    last = {}
    for frame in handled:
        if isinstance(frame.packet.payload, PayloadDotBotAdvertisement):
            last[frame.header.source] = frame.packet.payload.pos_x
    assert last == {0x1000 + r: rounds - 1 for r in range(ROBOTS)}
    got_events = [
        f for f in handled if isinstance(f.packet.payload, PayloadControlMode)
    ]
    assert got_events == events
    assert inbox.dropped == 0


@pytest.mark.asyncio
async def test_frames_keep_their_order_and_a_replaced_state_keeps_its_place():
    inbox = FrameInbox(asyncio.get_running_loop())
    handled = []
    first, event, second, newer = (
        _advert(1, 0),
        _event(1, 0),
        _advert(2, 0),
        _advert(1, 1),
    )
    for frame in (first, event, second, newer):
        inbox.put(frame)
    task = asyncio.create_task(inbox.run(handled.append))
    await _drain(task, inbox)
    assert handled == [newer, event, second]
    assert inbox.coalesced == 1


@pytest.mark.asyncio
async def test_events_beyond_the_bound_are_dropped_and_counted():
    inbox = FrameInbox(asyncio.get_running_loop(), max_events=10)
    for n in range(25):
        inbox.put(_event(1, n))
    assert len(inbox) == 10
    assert inbox.dropped == 15
    handled = []
    task = asyncio.create_task(inbox.run(handled.append))
    await _drain(task, inbox)
    assert len(handled) == 10


@pytest.mark.asyncio
async def test_put_from_many_threads_loses_no_wakeup():
    inbox = FrameInbox(asyncio.get_running_loop(), max_events=100_000)
    handled = []
    task = asyncio.create_task(inbox.run(handled.append))

    def feed(source):
        for n in range(2000):
            inbox.put(_event(source, n))

    threads = [threading.Thread(target=feed, args=(s,)) for s in range(4)]
    for thread in threads:
        thread.start()
    await asyncio.to_thread(lambda: [t.join() for t in threads])
    await _drain(task, inbox)
    assert len(handled) == 8000


@pytest.mark.asyncio
async def test_a_frame_the_handler_raises_on_does_not_stop_the_rest():
    inbox = FrameInbox(asyncio.get_running_loop())
    handled = []

    def handler(frame):
        if frame.packet.payload.mode == 1:
            raise OverflowError("can't convert negative int to unsigned")
        handled.append(frame)

    task = asyncio.create_task(inbox.run(handler))
    for n in range(4):
        inbox.put(_event(1, n))
    await asyncio.sleep(0.05)
    assert not task.done()
    task.cancel()
    assert [f.packet.payload.mode for f in handled] == [0, 0]
