# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A site's walls and obstacles: read from site.toml, served to the console,
and met by the simulated robots."""

import tomllib

import numpy as np
import pytest

from dotbot.config import SiteSection
from dotbot.models import DotBotSiteModel
from dotbot.sim.barriers import Barriers
from dotbot.sim.plant import FleetPlant
from dotbot.site import Obstacle, Site, Wall, site_from_table

SITE_TOML = """\
anchor = "the door corner"
extent_mm = [2000, 2000]

[[walls]]   # the long wall
name = "north"
points = [[0, 1000], [1000, 1000]]

[[obstacles]]
name = "pillar"
points = [[1500, 1500], [1700, 1500], [1700, 1700], [1500, 1700]]
"""


def _site() -> Site:
    return site_from_table("lab", SiteSection.model_validate(tomllib.loads(SITE_TOML)))


def test_walls_and_obstacles_are_read_from_site_toml():
    site = _site()
    assert site.walls == [Wall(((0, 1000), (1000, 1000)), "north")]
    assert site.obstacles == [
        Obstacle(((1500, 1500), (1700, 1500), (1700, 1700), (1500, 1700)), "pillar")
    ]


@pytest.mark.parametrize(
    "table, message",
    [
        ("[[walls]]\npoints = [[0, 0]]\n", "at least 2"),
        ("[[obstacles]]\npoints = [[0, 0], [1, 1]]\n", "at least 3"),
        ("[[walls]]\npoints = [[0, 0], [1, 1]]\nthickness = 3\n", "thickness"),
    ],
)
def test_a_barrier_the_schema_refuses(table, message):
    with pytest.raises(ValueError, match=message):
        SiteSection.model_validate(tomllib.loads(table))


def test_the_site_route_serves_walls_and_obstacles():
    model = DotBotSiteModel.from_site(_site())
    assert model.walls[0].points == [[0, 1000], [1000, 1000]]
    assert model.obstacles[0].name == "pillar"
    assert model.to_site().walls == _site().walls


def test_a_body_crossing_a_wall_or_inside_an_obstacle_is_blocked():
    barriers = Barriers.from_site(_site())
    # Facing +y (heading 0), the body's centre is 24.5 mm ahead of the axle
    # and its disc 47.5 mm round it
    assert list(barriers.blocked([500, 500], [920, 930], [0, 0])) == [False, True]
    assert barriers.blocked(1600, 1600, 90)[0]
    assert not barriers.blocked(1600, 1300, 0)[0]
    assert Barriers.from_site(Site(name="open")) is None


def test_a_robot_driven_at_a_wall_stops_at_it():
    plant = FleetPlant(
        x=[500.0, 1300.0],
        y=[500.0, 500.0],
        heading_deg=[0.0, 0.0],
        barriers=Barriers.from_site(_site()),
    )
    plant.pwm[:] = 60.0
    for _ in range(500):
        plant.step(np.zeros(2, dtype=bool))
    # The first meets the wall; the second, past its end, drives on
    assert 900 < plant.y[0] < 1000 - 47.5 - 24.5 + 1
    assert plant.y[1] > 1500


def test_a_robot_in_contact_may_back_off():
    plant = FleetPlant(
        x=[500.0], y=[928.0], heading_deg=[0.0], barriers=Barriers.from_site(_site())
    )
    plant.pwm[:] = -60.0
    for _ in range(100):
        plant.step(np.zeros(1, dtype=bool))
    assert plant.y[0] < 900


def _drive(plant, pwm, ticks):
    plant.pwm[:] = pwm
    for _ in range(ticks):
        plant.step(np.zeros(len(plant.x), dtype=bool))


def test_a_robot_placed_against_a_wall_cannot_drive_through_it():
    # Its disc already overlaps the wall at y = 1000, from the near side
    plant = FleetPlant(
        x=[500.0], y=[940.0], heading_deg=[0.0], barriers=Barriers.from_site(_site())
    )
    _drive(plant, 80.0, 400)
    assert plant.y[0] <= 940.0 + 1e-6


def test_a_robot_placed_across_a_wall_cannot_drive_back_over_it():
    plant = FleetPlant(
        x=[500.0], y=[1050.0], heading_deg=[180.0], barriers=Barriers.from_site(_site())
    )
    _drive(plant, 80.0, 400)
    assert plant.y[0] >= 1050.0 - 1e-6


def test_a_robot_placed_inside_an_obstacle_may_drive_out():
    plant = FleetPlant(
        x=[1600.0], y=[1600.0], heading_deg=[0.0], barriers=Barriers.from_site(_site())
    )
    _drive(plant, 60.0, 400)
    assert plant.y[0] > 1700 + 47.5


def test_a_robot_at_a_wall_may_turn_away_but_not_into_it():
    barriers = Barriers.from_site(_site())
    plant = FleetPlant(x=[500.0], y=[920.0], heading_deg=[0.0], barriers=barriers)
    _drive(plant, 60.0, 200)
    stopped = plant.heading_deg[0]
    plant.pwm[:, 0] = [60.0, -60.0]
    for _ in range(100):
        plant.step(np.zeros(1, dtype=bool))
    assert plant.heading_deg[0] != stopped
    assert not barriers.blocked(plant.x, plant.y, plant.heading_deg)[0]


def test_robots_standing_still_are_not_checked(monkeypatch):
    barriers = Barriers.from_site(_site())
    calls = []
    monkeypatch.setattr(barriers, "refused", lambda *a: calls.append(a))
    plant = FleetPlant(x=[500.0], y=[500.0], heading_deg=[0.0], barriers=barriers)
    plant.step(np.zeros(1, dtype=bool))
    assert calls == []


@pytest.mark.scenario
@pytest.mark.asyncio
async def test_a_waypoint_behind_a_wall_is_not_reached(tmp_path):
    from dotbot.tests.scenario_harness import Scenario

    address = "BADCAFE111111111"
    s = Scenario(
        tmp_path,
        [{"address": address, "pos_x": 500, "pos_y": 500, "direction": 0}],
        site=_site(),
    )
    try:
        await s.run(1.0)
        await s.waypoints(address, [(500, 1500)], threshold=20)
        await s.run(15.0)
        assert s.robots[address].pos_y < 1000 - 47.5 - 24.5 + 1
        site = (await s.client.get("/controller/site")).json()
        assert site["walls"][0]["points"] == [[0, 1000], [1000, 1000]]
    finally:
        await s.close()
