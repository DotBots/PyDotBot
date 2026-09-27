"""Tests for the simulated DotBot: its receive path, its plant, and the
sandbox dotbot app it runs."""

import math
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import toml
from dotbot_utils.protocol import Frame, Header, Packet

from dotbot import DOTBOT_ADDRESS_DEFAULT, addr_to_hex
from dotbot.area import Area
from dotbot.dotbot_simulator import (
    ADVERTISEMENT_TICKS,
    MARI_SLOTFRAME_SIZE,
    SIMULATOR_STEP_DELTA_T,
    TIMEOUT_STOP_TICKS,
    DotBotSimulator,
    DotBotSimulatorCommunicationInterface,
    DriveMode,
    SimulatedDotBotSettings,
    grid_positions,
    packaged_init_state_path,
    place_dotbots,
    placement_area,
)
from dotbot.protocol import (
    AXLE_UNKNOWN,
    DIRECTION_NONE,
    ControlModeType,
    PayloadCommandMaxSpeed,
    PayloadCommandMoveRaw,
    PayloadCommandRgbLed,
    PayloadCommandWheelVelocity,
    PayloadControlMode,
    PayloadDotBotAdvertisement,
    PayloadGPSPosition,
    PayloadLH2Location,
    PayloadLH2Waypoints,
    PayloadWaypointHeading,
    WaypointsAbortReason,
    WaypointsFailReason,
    WaypointsStatus,
)
from dotbot.site import Site
from dotbot.steering import SteeringState

ADDRESS = "BADCAFE111111111"


def _bot(address: str = ADDRESS, **settings) -> DotBotSimulator:
    settings = {"pos_x": 100, "pos_y": 100, **settings}
    return DotBotSimulator(
        SimulatedDotBotSettings(address=address, **settings), queue.Queue()
    )


def _frame(bot_or_address, payload) -> Frame:
    address = getattr(bot_or_address, "address", bot_or_address)
    return Frame(
        header=Header(destination=int(address, 16), source=0),
        packet=Packet().from_payload(payload),
    )


def _move_raw(destination: int) -> Frame:
    return Frame(
        header=Header(destination=destination, source=0),
        packet=Packet().from_payload(
            PayloadCommandMoveRaw(left_x=0, left_y=80, right_x=0, right_y=80)
        ),
    )


def _deliver(bot: DotBotSimulator, frame: Frame) -> None:
    """Hand the robot a single frame, through the wire."""
    bot.queue.put(Frame.from_bytes(frame.to_bytes()))
    bot.receive()


def _run(bot: DotBotSimulator, seconds: float) -> None:
    for _ in range(round(seconds / SIMULATOR_STEP_DELTA_T)):
        bot.tick()


def _run_until_done(bot: DotBotSimulator, timeout_s: float) -> None:
    ticks = 0
    while bot.steering.active and ticks * SIMULATOR_STEP_DELTA_T < timeout_s:
        bot.tick()
        ticks += 1
    _run(bot, 0.5)  # the run-on


def _waypoints(bot, points, threshold=10, batch_id=0, headings=None, pass_mm=0):
    headings = headings or [None] * len(points)
    payload = PayloadLH2Waypoints(
        threshold=threshold,
        count=len(points),
        waypoints=[PayloadLH2Location(pos_x=x, pos_y=y) for x, y in points],
        batch_id=batch_id,
        pass_mm=pass_mm,
        headings=[
            (
                PayloadWaypointHeading()
                if h is None
                else PayloadWaypointHeading(heading_cdeg=round(h * 100))
            )
            for h in headings
        ],
    )
    return _frame(bot, payload)


def _wire_advert(bot: DotBotSimulator) -> PayloadDotBotAdvertisement:
    """The advertisement as the controller parses it."""
    payload = bot.advertisement()
    return PayloadDotBotAdvertisement().from_bytes(payload.to_bytes())


@pytest.mark.parametrize(
    "address",
    [
        "B0B0F00D33333333",  # letters: fails if the two sides disagree on case
        "00B0F00D33333333",  # leading zero: fails if the address is not padded
        "1234567890123456",  # digits only: matches under either convention
    ],
)
def test_a_command_addressed_to_this_bot_is_applied(address):
    bot = _bot(address)
    _deliver(bot, _move_raw(int(address, 16)))
    # The app scales the joystick's +-127 to +-100 duty
    assert (bot.pwm_left, bot.pwm_right) == (62, 62)
    assert bot.drive_mode == DriveMode.RAW


def test_a_command_for_another_bot_is_ignored():
    bot = _bot("B0B0F00D33333333")
    _deliver(bot, _move_raw(0xDEADBEEF22222222))
    assert bot.pwm_left == 0
    assert bot.pwm_right == 0


def test_a_broadcast_command_is_applied_like_the_apps_radio_callback():
    bot = _bot("B0B0F00D33333333")
    _deliver(bot, _move_raw(int(DOTBOT_ADDRESS_DEFAULT, 16)))
    assert (bot.pwm_left, bot.pwm_right) == (62, 62)
    assert bot.drive_mode == DriveMode.RAW


def _wheel_velocity(bot: DotBotSimulator, left: int, right: int) -> Frame:
    return _frame(bot, PayloadCommandWheelVelocity(left_mm_s=left, right_mm_s=right))


def test_a_wheel_velocity_command_drives_the_wheels_at_that_speed():
    bot = _bot(motor_left_error=0.3, direction=0)
    _deliver(bot, _wheel_velocity(bot, 300, 300))
    _run(bot, 0.4)
    assert bot.v_left == pytest.approx(300, abs=1)
    assert bot.v_right == pytest.approx(300, abs=1)
    # The wheel loop closes on the encoders: no motor error, no turn
    assert bot.pos_x == pytest.approx(100)
    assert bot.heading_deg == pytest.approx(0)
    # The wheel lag costs 0.05 s of travel
    assert bot.pos_y == pytest.approx(100 + 300 * (0.4 - 0.05), abs=2)
    assert bot.controller_mode == ControlModeType.MANUAL


def test_wheel_speeds_are_capped_at_700_mm_s():
    bot = _bot()
    _deliver(bot, _wheel_velocity(bot, 1500, -900))
    assert (bot.setpoint_left, bot.setpoint_right) == (700, -700)


def test_the_wheels_stop_when_wheel_velocity_commands_stop_arriving():
    bot = _bot()
    _deliver(bot, _wheel_velocity(bot, 300, -300))
    _run(bot, (TIMEOUT_STOP_TICKS + 20) * SIMULATOR_STEP_DELTA_T)
    assert bot.drive_mode == DriveMode.IDLE
    assert (bot.setpoint_left, bot.setpoint_right) == (0, 0)
    _run(bot, 0.5)
    assert (bot.v_left, bot.v_right) == (0, 0)


def test_a_move_raw_command_takes_over_from_wheel_velocity():
    bot = _bot()
    _deliver(bot, _wheel_velocity(bot, 300, 300))
    _deliver(bot, _move_raw(int(ADDRESS, 16)))
    assert bot.drive_mode == DriveMode.RAW
    assert (bot.setpoint_left, bot.setpoint_right) == (0, 0)
    assert bot.pwm_left == 62


def test_an_unhandled_payload_type_is_logged():
    bot = _bot()
    bot.logger = MagicMock()
    _deliver(bot, _frame(bot, PayloadGPSPosition(latitude=1, longitude=2)))
    bot.logger.warning.assert_called_once_with(
        "Unhandled payload type", payload_type="0x05"
    )


def test_an_rgb_led_command_is_accepted_quietly():
    bot = _bot()
    bot.logger = MagicMock()
    _deliver(bot, _frame(bot, PayloadCommandRgbLed(red=1, green=2, blue=3)))
    bot.logger.warning.assert_not_called()


def test_the_address_rendering_round_trips():
    """The rx path and the index map must render an address the same way."""
    for address in ("B0B0F00D33333333", "00B0F00D33333333", "1234567890123456"):
        assert addr_to_hex(int(address, 16)) == address


# --- Estimator and advertisement ---------------------------------------------


def test_a_robot_given_a_heading_advertises_it_with_its_axle():
    bot = _bot(pos_x=1000, pos_y=1000, direction=90)
    advert = _wire_advert(bot)
    assert advert.has_report
    assert advert.direction == 90
    assert (advert.axle_x, advert.axle_y) == (1000, 1000)
    # The LH2 position is the photodiode, a lever arm ahead of the axle
    assert (advert.pos_x, advert.pos_y) == (949, 1000)  # 51.5 mm, rounded half up
    assert advert.waypoints_status == WaypointsStatus.NONE
    assert advert.max_speed_10mm == 30


def test_a_fresh_robot_has_no_heading_until_its_photodiode_has_moved():
    bot = _bot(pos_x=1000, pos_y=1000)
    _run(bot, 1.0)
    advert = _wire_advert(bot)
    assert advert.direction == DIRECTION_NONE
    assert (advert.axle_x, advert.axle_y) == (AXLE_UNKNOWN, AXLE_UNKNOWN)
    # Standing still, the position is the last raw fix of the photodiode
    assert (advert.pos_x, advert.pos_y) == (1000, 1052)

    _deliver(bot, _wheel_velocity(bot, 100, 100))
    _run(bot, 0.3)
    assert bot.direction == DIRECTION_NONE  # 30 mm: not far enough yet
    _run(bot, 0.3)
    assert bot.direction == 0


def test_a_kidnapped_robot_loses_its_heading():
    bot = _bot(pos_x=1000, pos_y=1000, direction=45)
    bot.kidnap(1500, 1500, 0)
    assert bot.direction == DIRECTION_NONE


def test_without_fixes_a_tracking_robot_goes_lost_after_a_second():
    bot = _bot(direction=0)
    bot.lh2_visible = False
    _run(bot, 0.9)
    assert bot.direction == 0
    _run(bot, 0.3)
    assert bot.direction == DIRECTION_NONE


def test_the_advertisement_reports_the_encoder_counts_since_the_last_one():
    bot = _bot(direction=0)
    _deliver(bot, _wheel_velocity(bot, 200, 200))
    _run(bot, 0.5)
    first = bot.advertisement()
    second = bot.advertisement()
    assert first.encoder_left > 500
    assert (second.encoder_left, second.encoder_right) == (0, 0)


# --- Waypoints -----------------------------------------------------------------


@pytest.mark.parametrize("direction", [90, DIRECTION_NONE], ids=["heading", "none"])
def test_a_robot_reaches_a_target_it_must_turn_toward(direction):
    bot = _bot(pos_x=1000, pos_y=1000, direction=direction)
    _deliver(bot, _waypoints(bot, [(1000, 300)], batch_id=3))
    assert bot.controller_mode == ControlModeType.AUTO
    _run_until_done(bot, timeout_s=15)
    assert bot.steering.state == SteeringState.ARRIVED
    assert math.hypot(bot.pos_x - 1000, bot.pos_y - 300) < 10
    advert = _wire_advert(bot)
    assert advert.mode == ControlModeType.MANUAL
    assert advert.waypoints_status == WaypointsStatus.ARRIVED
    assert (advert.batch_id, advert.waypoint_idx) == (3, 1)
    assert advert.direction != DIRECTION_NONE


def test_a_robot_turns_in_place_before_it_drives():
    bot = _bot(pos_x=1000, pos_y=1000, direction=0)
    _deliver(bot, _waypoints(bot, [(1500, 1000)]))
    states = []
    for _ in range(300):
        bot.tick()
        if not states or states[-1][0] != bot.steering.state:
            states.append((bot.steering.state, bot.pos_x, bot.pos_y))
    assert [s for s, *_ in states[:3]] == [
        SteeringState.NO_HEADING,
        SteeringState.ALIGN,
        SteeringState.DRIVE,
    ]
    # ALIGN turned about the axle: still at the start when DRIVE began
    _, x, y = states[2]
    assert math.hypot(x - 1000, y - 1000) < 2


def test_a_pose_waypoint_ends_facing_its_heading():
    bot = _bot(pos_x=1000, pos_y=1000, direction=0)
    _deliver(bot, _waypoints(bot, [(1300, 1300)], headings=[-90.0]))
    _run_until_done(bot, timeout_s=15)
    assert bot.steering.state == SteeringState.ARRIVED
    assert abs(bot.heading_deg - -90) < 3


def test_a_batch_passes_its_intermediate_points_without_stopping():
    bot = _bot(pos_x=1000, pos_y=1000, direction=0)
    _deliver(bot, _waypoints(bot, [(1000, 1400), (1400, 1400)], pass_mm=40))
    seen = set()
    while bot.steering.active:
        bot.tick()
        if bot.steering.index == 1:
            seen.add(round(math.hypot(bot.v_left, bot.v_right)))
    assert bot.steering.state == SteeringState.ARRIVED
    assert min(seen) > 0  # never stood still at the corner


def test_a_repeat_of_the_current_batch_id_is_ignored():
    bot = _bot(pos_x=1000, pos_y=1000, direction=0)
    _deliver(bot, _waypoints(bot, [(1000, 1500)], batch_id=7))
    _run(bot, 0.5)
    _deliver(bot, _waypoints(bot, [(2000, 2000)], batch_id=7))
    assert (bot.steering.target.x_mm, bot.steering.target.y_mm) == (1000, 1500)
    _deliver(bot, _waypoints(bot, [(2000, 2000)], batch_id=8))
    assert (bot.steering.target.x_mm, bot.steering.target.y_mm) == (2000, 2000)


def test_a_new_batch_while_driving_carries_on_driving():
    bot = _bot(pos_x=1000, pos_y=1000, direction=0)
    _deliver(bot, _waypoints(bot, [(1000, 2000)], batch_id=1))
    _run(bot, 1.0)
    assert bot.steering.state == SteeringState.DRIVE
    _deliver(bot, _waypoints(bot, [(1000, 2500)], batch_id=2))
    assert bot.steering.state == SteeringState.DRIVE
    assert bot.setpoint_left > 100


def test_max_speed_is_clamped_and_advertised():
    bot = _bot(direction=0)
    for sent, advertised in [(150, 15), (5, 2), (5000, 70), (0, 30)]:
        _deliver(bot, _frame(bot, PayloadCommandMaxSpeed(max_speed_mm_s=sent)))
        assert _wire_advert(bot).max_speed_10mm == advertised


def test_max_speed_caps_the_cruise():
    bot = _bot(pos_x=1000, pos_y=1000, direction=0)
    _deliver(bot, _frame(bot, PayloadCommandMaxSpeed(max_speed_mm_s=120)))
    _deliver(bot, _waypoints(bot, [(1000, 2500)]))
    _run(bot, 3.0)
    assert max(bot.v_left, bot.v_right) == pytest.approx(120, abs=2)


@pytest.mark.parametrize(
    "command, reason",
    [
        (lambda bot: _move_raw(int(bot.address, 16)), WaypointsAbortReason.DIRECT),
        (lambda bot: _wheel_velocity(bot, 0, 0), WaypointsAbortReason.DIRECT),
        (lambda bot: _waypoints(bot, [], batch_id=9), WaypointsAbortReason.STOP),
        (
            lambda bot: _frame(bot, PayloadControlMode()),
            WaypointsAbortReason.CONTROL_MODE,
        ),
    ],
    ids=["raw", "velocity", "empty batch", "control mode"],
)
def test_a_command_that_stops_a_batch_reports_it_aborted(command, reason):
    bot = _bot(pos_x=1000, pos_y=1000, direction=0)
    _deliver(bot, _waypoints(bot, [(1000, 2000)], batch_id=1))
    _run(bot, 0.5)
    _deliver(bot, command(bot))
    advert = _wire_advert(bot)
    assert advert.waypoints_status == WaypointsStatus.ABORTED
    assert advert.waypoints_reason == reason
    assert advert.mode == ControlModeType.MANUAL


def test_a_batch_that_cannot_get_a_heading_reports_it_failed():
    bot = _bot(pos_x=1000, pos_y=1000)
    bot.lh2_visible = False
    _deliver(bot, _waypoints(bot, [(1000, 2000)], batch_id=1))
    _run(bot, 4.0)
    advert = _wire_advert(bot)
    assert advert.waypoints_status == WaypointsStatus.FAILED
    assert advert.waypoints_reason == WaypointsFailReason.NO_HEADING


# --- Placement of a world file's unpositioned robots -------------------------


HALL = Site(
    name="hall",
    extent_mm=(20000, 30000),
    areas={
        "charging": Area(1000, 1000, 1000, 500, "charging"),
        "arena": Area(14000, 22000, 2000, 2000, "arena"),
    },
)


def test_the_placement_area_is_the_arena_whatever_its_declaration_order():
    assert placement_area(HALL).name == "arena"


def test_a_site_with_areas_but_no_arena_places_in_the_first_declared_one():
    site = Site(
        name="hall",
        extent_mm=(20000, 30000),
        areas={
            "charging": Area(1000, 1000, 1000, 500, "charging"),
            "workshop": Area(5000, 5000, 3000, 3000, "workshop"),
        },
    )
    assert placement_area(site).name == "charging"


def test_a_site_with_an_extent_and_no_areas_places_over_the_whole_extent():
    area = placement_area(Site(name="hall", extent_mm=(20000, 30000)))
    assert (area.x, area.y, area.w, area.h) == (0, 0, 20000, 30000)


def test_a_site_measuring_neither_keeps_the_two_metre_square():
    """The package default site has no extent and no areas, so the fallback
    is the world the simulator has always run in, not an error."""
    for site in (None, Site()):
        area = placement_area(site)
        assert (area.x, area.y, area.w, area.h) == (0, 0, 2000, 2000)


def test_four_robots_take_the_cell_centres_of_a_two_by_two_grid():
    assert grid_positions(Area(0, 0, 2000, 2000), 4) == [
        (500, 500),
        (1500, 500),
        (500, 1500),
        (1500, 1500),
    ]


def test_the_grid_is_deterministic_and_stays_inside_its_area():
    area = Area(14000, 22000, 2000, 2000, "arena")
    first = grid_positions(area, 7)
    assert first == grid_positions(area, 7)
    assert len(set(first)) == 7
    assert all(area.x < x < area.x_max and area.y < y < area.y_max for x, y in first)


def test_no_robots_need_no_grid():
    assert grid_positions(Area(0, 0, 2000, 2000), 0) == []


def test_an_unpositioned_fleet_lands_inside_the_sites_arena():
    fleet = [SimulatedDotBotSettings(address=f"{i:016X}") for i in range(4)]
    placed = place_dotbots(fleet, HALL)
    assert [(bot.pos_x, bot.pos_y) for bot in placed] == [
        (14500, 22500),
        (15500, 22500),
        (14500, 23500),
        (15500, 23500),
    ]


def test_an_explicit_position_is_left_alone_and_takes_no_grid_cell():
    fleet = [
        SimulatedDotBotSettings(address="A" * 16, pos_x=7, pos_y=9),
        SimulatedDotBotSettings(address="B" * 16),
    ]
    placed = place_dotbots(fleet, HALL)
    assert (placed[0].pos_x, placed[0].pos_y) == (7, 9)
    # The one unplaced robot is alone on its grid, so it takes the centre.
    assert (placed[1].pos_x, placed[1].pos_y) == HALL.areas["arena"].centre


def test_a_fully_positioned_fleet_is_returned_unchanged():
    fleet = [SimulatedDotBotSettings(address="A" * 16, pos_x=7, pos_y=9)]
    assert place_dotbots(fleet, HALL) == fleet


def test_the_packaged_world_spreads_its_fleet_over_the_active_arena():
    """End to end from the shipped world file: every declared robot must start
    inside the site's arena, not in a corner of the floor."""
    interface = DotBotSimulatorCommunicationInterface(
        on_frame_received=lambda *_: None,
        simulator_init_state=str(packaged_init_state_path()),
        site=HALL,
    )
    arena = HALL.areas["arena"]
    assert len(interface.dotbots) == 5
    assert len({(bot.pos_x, bot.pos_y) for bot in interface.dotbots}) == 5
    assert all(
        arena.x < bot.pos_x < arena.x_max and arena.y < bot.pos_y < arena.y_max
        for bot in interface.dotbots
    )


def test_the_packaged_world_still_runs_with_no_site_at_all():
    interface = DotBotSimulatorCommunicationInterface(
        on_frame_received=lambda *_: None,
        simulator_init_state=str(packaged_init_state_path()),
    )
    assert len(interface.dotbots) == 5
    assert all(
        0 < bot.pos_x < 2000 and 0 < bot.pos_y < 2000 for bot in interface.dotbots
    )


def test_the_packaged_world_ships_a_robot_with_no_heading():
    """`dotbot run simulator` must be able to show the no-heading case."""
    interface = DotBotSimulatorCommunicationInterface(
        on_frame_received=lambda *_: None,
        simulator_init_state=str(packaged_init_state_path()),
        site=HALL,
    )
    assert [bot.direction for bot in interface.dotbots].count(DIRECTION_NONE) == 1


def _interface(tmp_path, dotbots, network=None):
    world = tmp_path / "world.toml"
    body = {"dotbots": dotbots, **({"network": network} if network else {})}
    world.write_text(toml.dumps(body))
    received = []
    interface = DotBotSimulatorCommunicationInterface(received.append, str(world))
    return interface, received


def test_the_live_fleet_runs_on_one_thread_at_the_wall_clock(tmp_path):
    interface, received = _interface(
        tmp_path, [{"address": f"{i:016X}", "pos_x": 100, "pos_y": 100} for i in (1, 2)]
    )
    threads = threading.active_count()
    interface.start()
    try:
        assert threading.active_count() == threads + 1
        began = time.monotonic()
        time.sleep(0.6)
        elapsed = time.monotonic() - began
    finally:
        interface.stop()
    assert not interface.main_thread.is_alive()
    assert interface.ticks == pytest.approx(elapsed / SIMULATOR_STEP_DELTA_T, rel=0.2)
    sources = {addr_to_hex(int(frame.header.source)) for frame in received}
    assert sources == {"0000000000000001", "0000000000000002"}


def test_a_mari_robot_is_heard_within_a_slotframe_of_the_stepped_clock(tmp_path):
    interface, received = _interface(
        tmp_path,
        [
            {
                "address": "0000000000000001",
                "pos_x": 100,
                "pos_y": 100,
                "network_mode": "mari",
            }
        ],
    )
    slotframe_ticks = math.ceil(
        MARI_SLOTFRAME_SIZE * 1.236 / 1000 / SIMULATOR_STEP_DELTA_T
    )
    for _ in range(ADVERTISEMENT_TICKS - 1):
        interface.step()
    assert not received
    for _ in range(slotframe_ticks + 1):
        interface.step()
    assert len(received) == 1


def test_a_mari_downlink_reaches_its_robot(tmp_path):
    interface, _ = _interface(
        tmp_path,
        [
            {
                "address": "0000000000000001",
                "pos_x": 100,
                "pos_y": 100,
                "network_mode": "mari",
            }
        ],
    )
    bot = interface.dotbots[0]
    interface.write(_move_raw(1).to_bytes())
    for _ in range(20):
        interface.step()
    assert bot.drive_mode == DriveMode.RAW


def test_write_parses_once_and_delivers_only_to_its_addressee(tmp_path):
    """A command addressed to one robot must not cost a parse per fleet
    member - the O(N) fan-out this guards against made a round of commands
    O(N^2) in fleet size."""
    interface, _ = _interface(
        tmp_path,
        [
            {"address": "0000000000000001", "pos_x": 100, "pos_y": 100},
            {"address": "0000000000000002", "pos_x": 100, "pos_y": 100},
        ],
    )
    bot_a, bot_b = interface.dotbots
    with patch.object(Frame, "from_bytes", side_effect=Frame.from_bytes) as from_bytes:
        interface.write(_move_raw(1).to_bytes())
        assert from_bytes.call_count == 1
    assert bot_a.queue.qsize() == 1
    assert bot_b.queue.qsize() == 0
    bot_a.receive()
    bot_b.receive()
    assert bot_a.drive_mode == DriveMode.RAW
    assert bot_b.drive_mode == DriveMode.IDLE


def test_write_to_broadcast_reaches_every_robot(tmp_path):
    interface, _ = _interface(
        tmp_path,
        [
            {"address": "0000000000000001", "pos_x": 100, "pos_y": 100},
            {"address": "0000000000000002", "pos_x": 100, "pos_y": 100},
        ],
    )
    interface.write(_move_raw(int(DOTBOT_ADDRESS_DEFAULT, 16)).to_bytes())
    for bot in interface.dotbots:
        bot.receive()
    assert all(bot.drive_mode == DriveMode.RAW for bot in interface.dotbots)


def test_write_to_an_unknown_address_reaches_nobody(tmp_path):
    interface, _ = _interface(
        tmp_path, [{"address": "0000000000000001", "pos_x": 100, "pos_y": 100}]
    )
    interface.write(_move_raw(0xDEADBEEF22222222).to_bytes())
    assert interface.dotbots[0].queue.empty()
