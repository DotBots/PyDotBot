# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The site editor's round trip: a model patched back into `site.toml` keeps
every comment, blank line and key it did not change."""

import pytest
import tomlkit

from dotbot import site_toml
from dotbot.cli.config_cmd import default_site_toml
from dotbot.site_toml import SiteTomlError, patched_text, site_model

ARENA = """\
# Site arena: zero is the anchor, x right, y down, millimetres.

anchor = "the corner where the top wall meets the door wall"
extent_mm = [2000, 4000]   # encloses every area below

[areas.field]     # the 2 x 2 m square at the top
x = 0
y = 0
w = 2000
h = 2000

[areas.staging]   # the 2 x 2 m square directly below it
x = 0
y = 2000
w = 2000
h = 2000

[areas."field+staging"]   # the 2 x 4 m rectangle along the door wall
x = 0
y = 0
w = 2000
h = 4000

[areas.dev-corner]      # a 1 x 1 m development patch
role = "corner"
x = 1000
y = 0
w = 1000
h = 1000
"""

HALL = """\
# Site hall. Every number below is a placeholder.

anchor = "the north-west corner of the hall's floor marking"   # to be measured
extent_mm = [20000, 30000]   # to be measured

[connection]
conn = "mqtts://broker.example:8883"
swarm_id = "A001"

[areas.field]    # a 2 x 2 m square inside the hall
x = 5000   # to be measured
y = 5000   # to be measured
w = 2000
h = 2000
"""

INLINE = """\
[areas]
field   = { x = 0, y = 0, w = 1000, h = 1000 }  # the field
staging = { x = 0, y = 1000, w = 1000, h = 500 }
"""


WALLED = (
    ARENA
    + """
[[walls]]   # the door wall
name = "door"
points = [[0, 0], [0, 4000]]

[[walls]]
points = [[2000, 0], [2000, 4000]]   # the far wall

[[obstacles]]
name = "pillar"
points = [[1500, 2500], [1700, 2500], [1700, 2700]]
"""
)


def _loaded(text):
    model = site_model(tomlkit.parse(text))
    for area in model["areas"]:
        area["was"] = area["name"]
    for key in site_toml.BARRIERS:
        for index, item in enumerate(model[key]):
            item["was"] = index
    return model


@pytest.mark.parametrize(
    "text", [ARENA, HALL, INLINE, WALLED, default_site_toml((2000, 2000))]
)
def test_an_unchanged_model_writes_the_file_back_byte_for_byte(text):
    assert patched_text(text, _loaded(text)) == text


def test_the_model_carries_the_declared_role_and_the_comment():
    model = site_model(tomlkit.parse(ARENA))
    assert model["extent_mm"] == [2000, 4000]
    assert [a["name"] for a in model["areas"]] == [
        "field",
        "staging",
        "field+staging",
        "dev-corner",
    ]
    corner = model["areas"][3]
    assert (corner["role"], corner["comment"]) == (
        "corner",
        "a 1 x 1 m development patch",
    )
    assert model["areas"][0]["role"] is None


def test_moving_an_area_changes_its_numbers_and_nothing_else():
    model = _loaded(ARENA)
    model["areas"][3]["x"] = 1050
    out = patched_text(ARENA, model)
    changed = [(a, b) for a, b in zip(ARENA.splitlines(), out.splitlines()) if a != b]
    assert changed == [("x = 1000", "x = 1050")]


def test_a_value_keeps_its_own_comment():
    model = _loaded(HALL)
    model["areas"][0]["x"] = 5100
    model["anchor"] = "the door"
    model["extent_mm"] = [21000, 30000]
    out = patched_text(HALL, model)
    assert "x = 5100   # to be measured" in out
    assert 'anchor = "the door"   # to be measured' in out
    assert "extent_mm = [21000, 30000]   # to be measured" in out


def test_the_connection_is_left_as_it_is():
    model = _loaded(HALL)
    model["connection"] = {"conn": "mqtt://elsewhere:1883"}
    model["areas"][0]["w"] = 2500
    assert '[connection]\nconn = "mqtts://broker.example:8883"' in patched_text(
        HALL, model
    )


def test_a_new_area_follows_the_file_style():
    model = _loaded(ARENA)
    model["areas"].append(
        {
            "name": "dock",
            "x": 0,
            "y": 3500,
            "w": 500,
            "h": 500,
            "role": None,
            "comment": "chargers",
        }
    )
    out = patched_text(ARENA, model)
    assert out.startswith(ARENA)
    assert out.endswith("[areas.dock]  # chargers\nx = 0\ny = 3500\nw = 500\nh = 500\n")

    model = _loaded(INLINE)
    model["areas"].append({"name": "dock", "x": 0, "y": 0, "w": 1, "h": 1})
    assert "\ndock = {" in patched_text(INLINE, model)


def test_a_deleted_area_goes_with_its_comment():
    model = _loaded(ARENA)
    del model["areas"][2]
    out = patched_text(ARENA, model)
    assert "field+staging" not in out and "along the door wall" not in out
    assert "[areas.dev-corner]      # a 1 x 1 m development patch" in out


def test_a_renamed_area_keeps_its_place_and_comment():
    model = _loaded(ARENA)
    model["areas"][2]["name"] = "arena"
    out = patched_text(ARENA, model)
    assert out == ARENA.replace('[areas."field+staging"]', "[areas.arena]")

    model = _loaded(INLINE)
    model["areas"][0]["name"] = "square"
    model["areas"][0]["role"] = "field"
    line = patched_text(INLINE, model).splitlines()[1]
    assert line.startswith("square = {") and line.endswith("# the field")


def test_the_first_area_of_an_empty_pack():
    out = patched_text(
        'anchor = "a"\n',
        {
            "anchor": "a",
            "extent_mm": [3000, 3000],
            "areas": [{"name": "field", "x": 0, "y": 0, "w": 1000, "h": 1000}],
        },
    )
    assert site_toml.validate(out).areas["field"].w == 1000
    assert out.startswith('anchor = "a"\nextent_mm = [3000, 3000]\n')


def test_the_comment_is_edited_and_removed():
    model = _loaded(ARENA)
    model["areas"][0]["comment"] = "moved"
    model["areas"][1]["comment"] = None
    out = patched_text(ARENA, model)
    assert "[areas.field]     # moved\n" in out
    assert "[areas.staging]\n" in out


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda m: m["areas"][1].update(role="field"), "at most one field"),
        (lambda m: m["areas"][1].update(name="field"), "two areas are named"),
        (lambda m: m["areas"][1].update(name="a,b"), "comma"),
        (lambda m: m["areas"][1].update(name=""), "needs a name"),
    ],
)
def test_a_model_the_schema_refuses_is_an_error(change, message):
    model = _loaded(ARENA)
    change(model)
    with pytest.raises(SiteTomlError, match=message):
        patched_text(ARENA, model)


def test_the_revision_is_the_hash_of_the_bytes():
    assert site_toml.revision(b"a") != site_toml.revision(b"b")
    assert len(site_toml.revision(b"")) == 64


def test_walls_and_obstacles_are_modelled_with_their_comments():
    model = _loaded(WALLED)
    assert [(w["name"], w["points"], w["comment"]) for w in model["walls"]] == [
        ("door", [[0, 0], [0, 4000]], "the door wall"),
        (None, [[2000, 0], [2000, 4000]], None),
    ]
    assert model["obstacles"][0]["points"][2] == [1700, 2700]


def test_moving_a_wall_point_changes_that_point_only():
    model = _loaded(WALLED)
    model["walls"][1]["points"][1] = [2000, 3500]
    result = patched_text(WALLED, model)
    assert result == WALLED.replace(
        "points = [[2000, 0], [2000, 4000]]   # the far wall",
        "points = [[2000, 0], [2000, 3500]]   # the far wall",
    )


def test_a_barrier_is_added_and_one_deleted_keeping_the_others():
    model = _loaded(WALLED)
    del model["walls"][0]
    model["obstacles"].append(
        {"name": "box", "points": [[100, 100], [300, 100], [300, 300]], "was": None}
    )
    result = patched_text(WALLED, model)
    assert "# the door wall" not in result and "# the far wall" in result
    back = site_model(tomlkit.parse(result))
    assert [o["name"] for o in back["obstacles"]] == ["pillar", "box"]
    assert len(back["walls"]) == 1


def test_the_first_wall_of_a_pack_and_the_last_removed():
    model = _loaded(ARENA)
    model["walls"] = [{"points": [[0, 0], [100, 0]], "was": None}]
    walled = patched_text(ARENA, model)
    assert walled.startswith(ARENA) and "[[walls]]" in walled
    model = _loaded(walled)
    model["walls"] = []
    assert patched_text(walled, model).rstrip() == ARENA.rstrip()


def test_a_barrier_with_too_few_points_is_refused():
    model = _loaded(WALLED)
    model["obstacles"][0]["points"] = [[0, 0], [1, 1]]
    with pytest.raises(SiteTomlError, match="at least 3"):
        patched_text(WALLED, model)


def test_a_new_array_of_tables_starts_after_a_blank_line():
    model = _loaded(INLINE)
    model["walls"] = [{"points": [[0, 0], [100, 0]], "was": None}]
    model["obstacles"] = [{"points": [[0, 0], [100, 0], [0, 100]], "was": None}]
    result = patched_text(INLINE, model)
    assert "500 }\n\n[[walls]]" in result
    assert "\n\n[[obstacles]]" in result
