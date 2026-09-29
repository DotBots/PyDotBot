# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the site resolution ladder.

A site names a physical place, so the package must not ship one: the neutral
default is what a fresh install gets, and a real name comes from the config.
"""

import pytest

from dotbot.area import Area
from dotbot.cli._site import resolve_site_name
from dotbot.config import load_config_text, select_deployment
from dotbot.site import (
    FIELD_FALLBACK_MM,
    SITE_DEFAULT,
    Site,
    field_or_fallback,
    site_from_config,
)


def test_no_config_falls_back_to_a_neutral_package_site():
    assert SITE_DEFAULT == "default"
    assert resolve_site_name(environ={}) == ("default", "the default")


def test_the_config_names_the_site():
    config = load_config_text('site = "inria-aio-c"')
    assert resolve_site_name(config=config, environ={}) == (
        "inria-aio-c",
        "the config file",
    )


def test_the_flag_wins_over_the_config():
    config = load_config_text('site = "inria-aio-c"')
    assert resolve_site_name(config=config, flag="taped-square", environ={}) == (
        "taped-square",
        "the command line",
    )


def test_the_environment_wins_over_the_config_and_loses_to_the_flag():
    config = load_config_text('site = "inria-aio-c"')
    environ = {"DOTBOT_SITE": "bench"}
    assert resolve_site_name(config=config, environ=environ) == (
        "bench",
        "DOTBOT_SITE",
    )
    assert resolve_site_name(config=config, flag="taped", environ=environ)[0] == "taped"


def test_a_deployment_carries_its_own_site():
    config = load_config_text(
        'site = "inria-aio-c"\n'
        'default_deployment = "limerick"\n'
        '[deployment.limerick]\nsite = "limerick-hall"\n'
    )
    deployment, _ = select_deployment(config)
    assert resolve_site_name(config=config, deployment=deployment, environ={}) == (
        "limerick-hall",
        "the config file",
    )


def test_a_site_table_becomes_its_anchor_extent_and_areas():
    config = load_config_text(
        'site = "c405-arena"\n'
        "[sites.c405-arena]\n"
        'anchor = "the arena top-left corner, C405"\n'
        "extent_mm = [2000, 4000]\n"
        "[sites.c405-arena.areas.field]\n"
        "x = 0\ny = 0\nw = 2000\nh = 2000\n"
    )
    site = site_from_config(config, "c405-arena")
    assert site.anchor == "the arena top-left corner, C405"
    assert site.extent_mm == (2000, 4000)
    assert site.valid_mm == (0, 0, 2000, 4000)
    assert site.registry().resolve("field").as_dict() == {
        "x": 0,
        "y": 0,
        "w": 2000,
        "h": 2000,
        "name": "field",
        "role": "field",
    }


def test_a_named_site_with_no_table_is_empty_rather_than_an_error():
    """The default site is exactly this: a name, and nothing measured yet."""
    site = site_from_config(load_config_text('site = "bench"'), "bench")
    assert (site.name, site.anchor, site.extent_mm, site.areas) == (
        "bench",
        "",
        None,
        {},
    )


def _site(areas: str, extent: str = "") -> Site:
    config = load_config_text(f"[sites.hall]\n{extent}[sites.hall.areas]\n{areas}")
    return site_from_config(config, "hall")


def test_an_area_named_after_a_role_has_it_unless_it_declares_another():
    site = _site(
        "staging = { x = 0, y = 0, w = 10, h = 10 }\n"
        'field = { x = 0, y = 0, w = 10, h = 10, role = "corner" }\n'
        "pen = { x = 0, y = 0, w = 10, h = 10 }\n"
    )
    assert {name: a.role for name, a in site.areas.items()} == {
        "staging": "staging",
        "field": "corner",
        "pen": None,
    }


@pytest.mark.parametrize(
    "areas, field",
    [
        # the field, wherever it is declared
        (
            "staging = { x = 0, y = 0, w = 10, h = 10 }\n"
            'main = { x = 5, y = 5, w = 10, h = 10, role = "field" }\n',
            "main",
        ),
        # no field: the first area that is neither staging nor a corner
        (
            "staging = { x = 0, y = 0, w = 10, h = 10 }\n"
            'bench = { x = 0, y = 0, w = 5, h = 5, role = "corner" }\n'
            "pen = { x = 0, y = 0, w = 10, h = 10 }\n",
            "pen",
        ),
        # only staging and corners: the first area
        (
            'bench = { x = 0, y = 0, w = 5, h = 5, role = "corner" }\n'
            "staging = { x = 0, y = 0, w = 10, h = 10 }\n",
            "bench",
        ),
    ],
)
def test_the_field_falls_back_in_order(areas, field):
    assert _site(areas).field.name == field


def test_a_site_with_no_areas_takes_its_extent_as_the_field():
    field = _site("", "extent_mm = [5000, 4000]\n").field
    assert (field.x, field.y, field.w, field.h) == (0, 0, 5000, 4000)
    assert field.name == "0,0,5000,4000"


def test_a_site_that_declares_nothing_has_no_field():
    assert Site().field is None


def test_staging_is_the_first_staging_area():
    site = Site(
        areas={
            "field": Area(0, 0, 10, 10, "field", "field"),
            "dock": Area(0, 10, 10, 5, "dock", "staging"),
            "staging": Area(0, 15, 10, 5, "staging", "staging"),
        }
    )
    assert site.staging.name == "dock"
    assert Site(areas={"field": Area(0, 0, 1, 1, "field", "field")}).staging is None


def test_field_or_fallback():
    assert (
        field_or_fallback(_site("field = { x = 1, y = 1, w = 10, h = 10 }\n")).name
        == "field"
    )
    fallback = Area(0, 0, FIELD_FALLBACK_MM, FIELD_FALLBACK_MM)
    assert field_or_fallback(Site()) == fallback
    assert field_or_fallback(None) == fallback
