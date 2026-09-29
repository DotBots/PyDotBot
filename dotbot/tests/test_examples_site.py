# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The examples place their shapes and bounds from the controller's site."""

import click
import pytest

from dotbot.area import Area
from dotbot.examples.minimum_naming_game.walk_avoid import walk_avoid
from dotbot.examples.motions.motions import motion_area, square_waypoints
from dotbot.site import Site

SITE = Site(
    name="hall",
    extent_mm=(5000, 5000),
    areas={
        "field": Area(1500, 1500, 2000, 2000, "field", "field"),
        "staging": Area(1500, 3500, 2000, 600, "staging", "staging"),
    },
)


def test_motions_centre_on_the_field():
    area = motion_area(SITE)
    corners = square_waypoints(400, area, 0)
    xs = [p["x"] for p in corners]
    ys = [p["y"] for p in corners]
    assert (min(xs) + max(xs)) / 2 == 2500
    assert (min(ys) + max(ys)) / 2 == 2500


def test_motions_area_resolves_in_the_site():
    assert motion_area(SITE, "staging").name == "staging"
    assert motion_area(SITE, "0,0,1000,1000").centre == (500, 500)
    with pytest.raises(click.BadParameter, match="field, staging"):
        motion_area(SITE, "nowhere")


def test_walk_avoid_turns_back_at_the_edges_of_an_offset_area():
    field = SITE.areas["field"]
    # Just inside the field's left edge, which starts 1500 mm from zero.
    vx, vy = walk_avoid(1550, 2500, 0, [], 100, field)
    assert vx > 0 and vy == 0
    # Mid-field, it walks on as it would with no edge in sight.
    free = walk_avoid(2500, 2500, 0, [], 100, Area(0, 0, 5000, 5000))
    assert walk_avoid(2500, 2500, 0, [], 100, field) == free
