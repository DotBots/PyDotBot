"""Tests for the simulated fleet: its placement, its radio and the firmware
control it runs."""

import math
import threading
import time
from unittest.mock import patch

import pytest
import toml
from dotbot_utils.protocol import Frame, Header, Packet

from dotbot import DOTBOT_ADDRESS_DEFAULT, addr_to_hex
from dotbot.area import Area
from dotbot.dotbot_simulator import (
    ADVERTISEMENT_TICKS,
    FLEET_PITCH_MM,
    MARI_SLOTFRAME_SIZE,
    SIMULATOR_STEP_DELTA_T,
    DotBotSimulatorCommunicationInterface,
    FleetDoesNotFit,
    InitStateToml,
    SimulatedDotBotSettings,
    fleet_capacity,
    fleet_init_state,
    grid_positions,
    init_state_toml,
    packaged_init_state_path,
    place_dotbots,
    placement_area,
)
from dotbot.protocol import (
    AXLE_UNKNOWN,
    DIRECTION_NONE,
    ControlModeType,
    PayloadCommandMoveRaw,
    PayloadCommandWheelVelocity,
    PayloadDotBotAdvertisement,
    PayloadLH2Location,
    PayloadLH2Waypoints,
    PayloadWaypointHeading,
    WaypointsStatus,
)
from dotbot.sim import core as control
from dotbot.site import Site

# The firmware advertises every twice its node's minimum TX interval, the
# slotframe, once joined: 2 x 126 ms
MARI_ADVERTISEMENT_TICKS = 25


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


def _wheel_velocity(bot, left: int, right: int) -> Frame:
    return _frame(bot, PayloadCommandWheelVelocity(left_mm_s=left, right_mm_s=right))


def test_the_address_rendering_round_trips():
    """The rx path and the index map must render an address the same way."""
    for address in ("B0B0F00D33333333", "00B0F00D33333333", "1234567890123456"):
        assert addr_to_hex(int(address, 16)) == address


# --- Placement of a world file's unpositioned robots -------------------------


HALL = Site(
    name="hall",
    extent_mm=(20000, 30000),
    areas={
        "charging": Area(1000, 1000, 1000, 500, "charging", "staging"),
        "field": Area(14000, 22000, 2000, 2000, "field", "field"),
    },
)


def test_the_placement_area_is_the_field_whatever_its_declaration_order():
    assert placement_area(HALL).name == "field"


def test_a_site_without_a_field_places_in_its_first_area_that_is_not_staging():
    site = Site(
        name="hall",
        extent_mm=(20000, 30000),
        areas={
            "charging": Area(1000, 1000, 1000, 500, "charging", "staging"),
            "bench": Area(1000, 2000, 1000, 1000, "bench", "corner"),
            "workshop": Area(5000, 5000, 3000, 3000, "workshop"),
        },
    )
    assert placement_area(site).name == "workshop"


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


def test_an_unpositioned_fleet_lands_inside_the_sites_field():
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
    assert (placed[1].pos_x, placed[1].pos_y) == HALL.areas["field"].centre


def test_a_fully_positioned_fleet_is_returned_unchanged():
    fleet = [SimulatedDotBotSettings(address="A" * 16, pos_x=7, pos_y=9)]
    assert place_dotbots(fleet, HALL) == fleet


# --- A fleet generated by `--robots N` ---------------------------------------


FIELD_SITE = Site(
    name="hall",
    extent_mm=(20000, 30000),
    areas={
        "staging": Area(0, 0, 20000, 2000, "staging", "staging"),
        "field": Area(2000, 10000, 16000, 16000, "field", "field"),
    },
)


@pytest.mark.parametrize("count", [1, 7, 500, 1000])
def test_a_generated_fleet_has_its_count_inside_the_field(count):
    field = FIELD_SITE.areas["field"]
    bots = fleet_init_state(count, FIELD_SITE).dotbots
    assert len(bots) == count
    assert len({bot.address for bot in bots}) == count
    assert all(
        field.x < bot.pos_x < field.x_max and field.y < bot.pos_y < field.y_max
        for bot in bots
    )


def test_a_generated_fleet_is_centred_and_a_pitch_apart():
    field = FIELD_SITE.areas["field"]
    bots = fleet_init_state(500, FIELD_SITE).dotbots
    xs, ys = [bot.pos_x for bot in bots], [bot.pos_y for bot in bots]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(field.x + field.w / 2, abs=100)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(field.y + field.h / 2, abs=100)
    nearest = min(
        math.dist((a.pos_x, a.pos_y), (b.pos_x, b.pos_y))
        for i, a in enumerate(bots)
        for b in bots[i + 1 :]
    )
    assert nearest == FLEET_PITCH_MM


def test_a_generated_fleet_all_faces_up():
    bots = fleet_init_state(4, FIELD_SITE).dotbots
    assert [bot.direction for bot in bots] == [180, 180, 180, 180]


def test_a_generated_fleets_photodiodes_are_evenly_spaced():
    """Robots facing opposite ways put their photodiodes a lever arm closer or
    further apart than their axles; the reported grid must stay one pitch."""
    fleet = fleet_init_state(100, FIELD_SITE)
    sim = DotBotSimulatorCommunicationInterface(lambda frame: None, fleet)
    px, py = sim.plant.photodiode()
    rows = sorted({round(y) for y in py})
    assert {b - a for a, b in zip(rows, rows[1:])} == {FLEET_PITCH_MM}
    columns = sorted({round(x) for x in px})
    assert {b - a for a, b in zip(columns, columns[1:])} == {FLEET_PITCH_MM}


def test_without_a_field_the_fleet_goes_to_the_first_area_then_the_extent():
    area = Area(1000, 1000, 1000, 1000, "pen")
    bots = fleet_init_state(4, Site(areas={"pen": area})).dotbots
    assert all(area.x < bot.pos_x < area.x_max for bot in bots)
    bots = fleet_init_state(1000, Site(extent_mm=(20000, 30000))).dotbots
    assert len(bots) == 1000


@pytest.mark.parametrize(
    "site",
    [None, Site(areas={"field": Area(1500, 1500, 2000, 2000, "field", "field")})],
)
def test_a_fleet_that_does_not_fit_is_refused_with_how_many_do(site):
    assert fleet_capacity(Area(0, 0, 2000, 2000)) == 100
    fleet_init_state(100, site)
    with pytest.raises(FleetDoesNotFit, match="101 robots.*at most 100 do"):
        fleet_init_state(101, site)


def test_the_capacity_of_a_narrow_area_is_one_full_row():
    assert fleet_capacity(Area(0, 0, 2000, 200)) == 10
    bots = fleet_init_state(
        10, Site(areas={"strip": Area(0, 0, 2000, 200, "strip")})
    ).dotbots
    assert {bot.pos_y for bot in bots} == {100}


RECTANGLE = Site(
    name="arena",
    extent_mm=(2000, 4000),
    areas={
        "field": Area(0, 0, 2000, 2000, "field", "field"),
        "staging": Area(0, 2000, 2000, 2000, "staging", "staging"),
    },
)


def test_the_capacity_of_a_rectangle_is_its_pitch_squares():
    area = RECTANGLE.registry().resolve("field+staging")
    assert fleet_capacity(area) == 200
    assert fleet_capacity(Area(0, 0, 2050, 4199)) == 10 * 20


@pytest.mark.parametrize("count", [150, 200])
def test_a_generated_fleet_fills_a_tall_rectangle(count):
    area = RECTANGLE.registry().resolve("field+staging")
    bots = fleet_init_state(count, RECTANGLE, area=area).dotbots
    assert len(bots) == count
    assert all(
        area.x < b.pos_x < area.x_max and area.y < b.pos_y < area.y_max for b in bots
    )
    assert len({(b.pos_x, b.pos_y) for b in bots}) == count
    assert len({b.pos_y for b in bots}) > len({b.pos_x for b in bots})
    with pytest.raises(FleetDoesNotFit, match="201 robots.*at most 200 do"):
        fleet_init_state(201, RECTANGLE, area=area)


def test_a_generated_grid_takes_the_shape_of_its_area():
    tall = fleet_init_state(50, area=Area(0, 0, 2000, 8000)).dotbots
    xs, ys = {b.pos_x for b in tall}, {b.pos_y for b in tall}
    assert len(ys) > len(xs)
    wide = fleet_init_state(50, area=Area(0, 0, 8000, 2000)).dotbots
    assert len({b.pos_x for b in wide}) > len({b.pos_y for b in wide})


def test_the_simulator_example_puts_a_thousand_robots_in_its_field():
    from pathlib import Path

    import dotbot
    from dotbot.config import load_files
    from dotbot.site_packs import resolve_site_entry

    path = Path(dotbot.__file__).parent / "examples" / "simulator_fleet" / "dotbot.toml"
    config = load_files([("project", path)])
    site = resolve_site_entry(config, config.site).site()
    assert site.staging.name == "staging"
    assert [a.name for a in site.areas.values() if a.role == "staging"] == ["staging"]
    field = site.field
    assert field.name == "field"
    bots = fleet_init_state(1000, site).dotbots
    assert all(field.x < b.pos_x < field.x_max for b in bots)
    assert all(field.y < b.pos_y < field.y_max for b in bots)


def test_a_written_fleet_reads_back_as_the_same_robots(tmp_path):
    fleet = fleet_init_state(50, FIELD_SITE)
    path = tmp_path / "fleet.toml"
    path.write_text(init_state_toml(fleet))
    sim = DotBotSimulatorCommunicationInterface(lambda frame: None, str(path))
    assert [
        (bot.address, bot.pos_x, bot.pos_y, bot.heading_deg % 360)
        for bot in sim.dotbots
    ] == [(bot.address, bot.pos_x, bot.pos_y, bot.direction) for bot in fleet.dotbots]


def test_the_simulator_runs_a_generated_fleet_without_a_file():
    fleet = fleet_init_state(9, FIELD_SITE)
    sim = DotBotSimulatorCommunicationInterface(lambda frame: None, fleet)
    assert [bot.address for bot in sim.dotbots] == [
        bot.address for bot in fleet.dotbots
    ]


def test_the_packaged_world_spreads_its_fleet_over_the_active_field():
    """End to end from the shipped world file: every declared robot must start
    inside the site's field, not in a corner of the floor."""
    interface = DotBotSimulatorCommunicationInterface(
        on_frame_received=lambda *_: None,
        simulator_init_state=str(packaged_init_state_path()),
        site=HALL,
    )
    field = HALL.areas["field"]
    assert len(interface.dotbots) == 5
    assert len({(bot.pos_x, bot.pos_y) for bot in interface.dotbots}) == 5
    assert all(
        field.x < bot.pos_x < field.x_max and field.y < bot.pos_y < field.y_max
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
    for _ in range(MARI_ADVERTISEMENT_TICKS - 1):
        interface.step()
    assert not received
    for _ in range(slotframe_ticks + 1):
        interface.step()
    assert len(received) == 1


@pytest.mark.parametrize(
    "network_mode,ticks", [("default", ADVERTISEMENT_TICKS), ("mari", None)]
)
def test_a_robot_advertises_at_its_firmware_rate(tmp_path, network_mode, ticks):
    """A joined Mari robot advertises at the rate its firmware derives from
    the slotframe, an unjoined one at the firmware's default."""
    ticks = ticks or MARI_ADVERTISEMENT_TICKS
    interface, received = _interface(
        tmp_path,
        [
            {
                "address": "0000000000000001",
                "pos_x": 100,
                "pos_y": 100,
                "network_mode": network_mode,
            }
        ],
    )
    for _ in range(1000):
        interface.step()
    assert abs(len(received) - 1000 / ticks) <= 1


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
    assert bot.drive_mode == control.DriveMode.RAW


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
    with patch.object(
        Header, "from_bytes", autospec=True, side_effect=Header.from_bytes
    ) as from_bytes:
        interface.write(_move_raw(1).to_bytes())
        assert from_bytes.call_count == 1
    interface.step()
    assert bot_a.drive_mode == control.DriveMode.RAW
    assert bot_b.drive_mode == control.DriveMode.IDLE


def test_write_to_broadcast_reaches_every_robot(tmp_path):
    interface, _ = _interface(
        tmp_path,
        [
            {"address": "0000000000000001", "pos_x": 100, "pos_y": 100},
            {"address": "0000000000000002", "pos_x": 100, "pos_y": 100},
        ],
    )
    interface.write(_move_raw(int(DOTBOT_ADDRESS_DEFAULT, 16)).to_bytes())
    interface.step()
    assert all(bot.drive_mode == control.DriveMode.RAW for bot in interface.dotbots)


def test_write_to_an_unknown_address_reaches_nobody(tmp_path):
    interface, _ = _interface(
        tmp_path, [{"address": "0000000000000001", "pos_x": 100, "pos_y": 100}]
    )
    interface.write(_move_raw(0xDEADBEEF22222222).to_bytes())
    interface.step()
    assert interface.dotbots[0].drive_mode == control.DriveMode.IDLE


# --- The fleet on the firmware's control core ---------------------------------


def _step(interface, seconds: float):
    for _ in range(round(seconds / SIMULATOR_STEP_DELTA_T)):
        interface.step()


def _adverts(received) -> list:
    return [
        PayloadDotBotAdvertisement().from_bytes(frame.packet.payload.to_bytes())
        for frame in received
    ]


def test_a_robot_given_a_heading_starts_tracking_it_where_it_was_put(tmp_path):
    interface, received = _interface(
        tmp_path,
        [
            {
                "address": "0000000000000001",
                "pos_x": 1000,
                "pos_y": 1000,
                "direction": 90,
            }
        ],
    )
    bot = interface.dotbots[0]
    assert bot.estimator_status == control.PoseStatus.TRACKING
    assert math.hypot(bot.pos_x - 1000, bot.pos_y - 1000) < 3
    assert bot.heading_deg == pytest.approx(90, abs=1)
    _step(interface, 0.5)
    (advert,) = _adverts(received)
    assert advert.direction == pytest.approx(90, abs=1)
    assert math.hypot(advert.axle_x - 1000, advert.axle_y - 1000) < 3
    # The LH2 position is the photodiode, a lever arm ahead of the axle
    assert math.hypot(advert.pos_x - 949, advert.pos_y - 1000) < 3
    assert (advert.encoder_left, advert.encoder_right) == (0, 0)


@pytest.mark.parametrize(
    "calibrated, expected",
    [(None, [0xFFFF, 0x05]), (0b11, [0b11, 0x05]), (0x0104, [0x0104, 0x05])],
)
def test_a_robot_holds_the_controllers_stations_unless_its_file_says(
    calibrated, expected
):
    fleet = InitStateToml(
        dotbots=[
            SimulatedDotBotSettings(address="0000000000000001", pos_x=1, pos_y=1),
            SimulatedDotBotSettings(
                address="0000000000000002", pos_x=1, pos_y=1, calibrated=0x05
            ),
        ]
    )
    received = []
    interface = DotBotSimulatorCommunicationInterface(
        received.append, fleet, calibrated=calibrated
    )
    _step(interface, 0.5)
    by_source = {
        frame.header.source: advert
        for frame, advert in zip(received, _adverts(received))
    }
    assert [by_source[1].calibrated, by_source[2].calibrated] == expected


def test_a_robot_without_a_heading_starts_with_none_and_no_position(tmp_path):
    interface, received = _interface(
        tmp_path, [{"address": "0000000000000001", "pos_x": 1000, "pos_y": 1000}]
    )
    assert interface.dotbots[0].estimator_status == control.PoseStatus.SEEDING
    interface.dotbots[0].lh2_visible = False
    _step(interface, 0.5)
    (advert,) = _adverts(received)
    assert advert.direction == DIRECTION_NONE
    assert (advert.axle_x, advert.axle_y) == (AXLE_UNKNOWN, AXLE_UNKNOWN)
    assert (advert.pos_x, advert.pos_y) == (0, 0)


def test_advertisements_carry_the_battery_and_the_calibration(tmp_path):
    interface, received = _interface(
        tmp_path,
        [
            {
                "address": "0000000000000001",
                "pos_x": 100,
                "pos_y": 100,
                "calibrated": 0x03,
            }
        ],
    )
    _step(interface, 1.0)
    adverts = _adverts(received)
    assert len(adverts) == 2
    assert all(a.has_report and a.calibrated == 0x03 for a in adverts)
    assert adverts[-1].battery == pytest.approx(3000, abs=2)
    assert adverts[-1].max_speed_10mm == 30


def test_robots_advertise_out_of_phase(tmp_path):
    interface, received = _interface(
        tmp_path,
        [{"address": f"{i + 1:016X}", "pos_x": 100, "pos_y": 100} for i in range(50)],
    )
    per_tick = []
    for _ in range(ADVERTISEMENT_TICKS):
        before = len(received)
        interface.step()
        per_tick.append(len(received) - before)
    assert sum(per_tick) == 50
    assert max(per_tick) == 1


def test_wheel_speeds_hold_through_a_motor_error(tmp_path):
    """The firmware's wheel loop closes on the encoders, so a weak motor
    neither slows its wheel nor turns the robot."""
    interface, _ = _interface(
        tmp_path,
        [
            {
                "address": "0000000000000001",
                "pos_x": 1000,
                "pos_y": 1000,
                "direction": 0,
                "motor_left_error": 0.3,
            }
        ],
    )
    bot = interface.dotbots[0]
    for _ in range(5):
        interface.write(_wheel_velocity(bot, 200, 200).to_bytes())
        _step(interface, 0.2)
    assert bot.drive_mode == control.DriveMode.VELOCITY
    assert bot.v_left == pytest.approx(200, abs=25)
    assert bot.v_right == pytest.approx(200, abs=25)
    assert abs(bot.heading_deg) < 5


def test_the_wheels_stop_when_commands_stop_arriving(tmp_path):
    interface, _ = _interface(
        tmp_path, [{"address": "0000000000000001", "pos_x": 1000, "pos_y": 1000}]
    )
    bot = interface.dotbots[0]
    interface.write(_wheel_velocity(bot, 300, -300).to_bytes())
    _step(interface, 0.3)
    assert abs(bot.v_left) > 100
    _step(interface, 1.0)
    assert bot.drive_mode == control.DriveMode.IDLE
    assert (bot.v_left, bot.v_right) == (0, 0)


def test_a_waypoint_batch_is_driven_by_the_firmware(tmp_path):
    interface, received = _interface(
        tmp_path,
        [{"address": "0000000000000001", "pos_x": 1000, "pos_y": 1000, "direction": 0}],
    )
    bot = interface.dotbots[0]
    interface.write(
        _waypoints(bot, [(1000, 1500)], threshold=20, batch_id=4).to_bytes()
    )
    for _ in range(1000):
        interface.step()
        if bot.steering_state == control.SteeringState.ARRIVED:
            break
    assert bot.steering_state == control.SteeringState.ARRIVED
    _step(interface, 0.6)
    assert math.hypot(bot.pos_x - 1000, bot.pos_y - 1500) <= 20
    advert = _adverts(received)[-1]
    assert advert.waypoints_status == WaypointsStatus.ARRIVED
    assert (advert.batch_id, advert.waypoint_idx) == (4, 1)
    assert advert.mode == ControlModeType.MANUAL


def test_a_visible_robot_gets_a_fix_only_when_its_firmware_reads_one(tmp_path):
    interface, _ = _interface(
        tmp_path,
        [{"address": "0000000000000001", "pos_x": 100, "pos_y": 100}],
    )
    before = int(interface.plant.fix_sequence[0])
    for _ in range(100):
        interface.step()
    assert int(interface.plant.fix_sequence[0]) - before == 10
    assert int(interface.reports()[0]["fix_sequence"]) == int(
        interface.plant.fix_sequence[0]
    )
