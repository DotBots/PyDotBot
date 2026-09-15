# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the site resolution ladder.

A site names a physical place, so the package must not ship one: the neutral
default is what a fresh install gets, and a real name comes from the config.
"""

from dotbot.cli._site import resolve_site_name
from dotbot.config import load_config_text, select_deployment
from dotbot.site import SITE_DEFAULT, site_from_config


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
        "[sites.c405-arena.areas.arena]\n"
        "x = 0\ny = 0\nw = 2000\nh = 2000\n"
    )
    site = site_from_config(config, "c405-arena")
    assert site.anchor == "the arena top-left corner, C405"
    assert site.extent_mm == (2000, 4000)
    assert site.valid_mm == (0, 0, 2000, 4000)
    assert site.registry().resolve("arena").as_dict() == {
        "x": 0,
        "y": 0,
        "w": 2000,
        "h": 2000,
        "name": "arena",
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
