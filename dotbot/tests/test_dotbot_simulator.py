"""Tests for the simulated DotBot's receive path."""

import queue

import pytest
from dotbot_utils.protocol import Frame, Header, Packet

from dotbot import addr_to_hex
from dotbot.area import Area
from dotbot.dotbot_simulator import (
    DotBotSimulator,
    DotBotSimulatorCommunicationInterface,
    SimulatedDotBotSettings,
    grid_positions,
    packaged_init_state_path,
    place_dotbots,
    placement_area,
)
from dotbot.protocol import PayloadCommandMoveRaw
from dotbot.site import Site


def _bot(address: str) -> DotBotSimulator:
    return DotBotSimulator(
        SimulatedDotBotSettings(address=address, pos_x=100, pos_y=100),
        queue.Queue(),
    )


def _move_raw(destination: int) -> Frame:
    return Frame(
        header=Header(destination=destination, source=0),
        packet=Packet().from_payload(
            PayloadCommandMoveRaw(left_x=0, left_y=80, right_x=0, right_y=80)
        ),
    )


def _deliver(bot: DotBotSimulator, frame: Frame) -> None:
    """Run one pass of the rx loop over a single frame."""
    bot.queue.put(frame)
    bot.queue.put(None)  # breaks the loop once the frame is handled
    bot.rx_frame()


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
    assert bot.pwm_left == 80
    assert bot.pwm_right == 80


def test_a_command_for_another_bot_is_ignored():
    bot = _bot("B0B0F00D33333333")
    _deliver(bot, _move_raw(0xDEADBEEF22222222))
    assert bot.pwm_left == 0
    assert bot.pwm_right == 0


def test_the_address_rendering_round_trips():
    """The rx path and the index map must render an address the same way."""
    for address in ("B0B0F00D33333333", "00B0F00D33333333", "1234567890123456"):
        assert addr_to_hex(int(address, 16)) == address


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
    """End to end from the shipped world file: the default four robots must
    start inside the site's arena, not in a corner of the floor."""
    interface = DotBotSimulatorCommunicationInterface(
        on_frame_received=lambda *_: None,
        simulator_init_state=str(packaged_init_state_path()),
        site=HALL,
    )
    arena = HALL.areas["arena"]
    assert len(interface.dotbots) == 4
    assert len({(bot.pos_x, bot.pos_y) for bot in interface.dotbots}) == 4
    assert all(
        arena.x < bot.pos_x < arena.x_max and arena.y < bot.pos_y < arena.y_max
        for bot in interface.dotbots
    )


def test_the_packaged_world_still_runs_with_no_site_at_all():
    interface = DotBotSimulatorCommunicationInterface(
        on_frame_received=lambda *_: None,
        simulator_init_state=str(packaged_init_state_path()),
    )
    assert len(interface.dotbots) == 4
    assert all(
        0 < bot.pos_x < 2000 and 0 < bot.pos_y < 2000 for bot in interface.dotbots
    )
