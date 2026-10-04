# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A site's objects: read from site.toml, served, patched by the editor,
charged at in the simulator, and used by the charging-station example."""

import tomllib

import numpy as np
import pytest
import tomlkit

from dotbot.config import SiteSection
from dotbot.dotbot_simulator import (
    DotBotSimulatorCommunicationInterface,
    InitStateToml,
    SimulatedDotBotSettings,
)
from dotbot.examples.charging_station.charging_station import layout_from_site
from dotbot.models import DotBotSiteModel
from dotbot.sim.plant import INITIAL_BATTERY_VOLTAGE
from dotbot.site import SiteObject, site_from_table
from dotbot.site_toml import patched_text, site_model

SITE_TOML = """\
anchor = "the door corner"
extent_mm = [2000, 4000]

[areas.field]
x = 0
y = 0
w = 2000
h = 2000

[areas.staging]
x = 0
y = 2000
w = 2000
h = 2000

[objects.charger-1]   # the pad by the door
kind = "charger"
x = 800
y = 3800
heading_deg = 180.0
"""


def _site():
    table = SiteSection.model_validate(tomllib.loads(SITE_TOML))
    return site_from_table("lab", table)


def test_objects_are_read_and_served():
    site = _site()
    assert site.objects == {
        "charger-1": SiteObject("charger-1", "charger", 800, 3800, 180.0)
    }
    assert site.objects_of("charger") == [site.objects["charger-1"]]
    model = DotBotSiteModel.from_site(site)
    assert model.objects[0].kind == "charger"
    assert model.to_site().objects == site.objects


def test_an_unknown_kind_is_refused():
    with pytest.raises(ValueError, match="charger"):
        SiteSection.model_validate(
            tomllib.loads('[objects.x]\nkind = "teleporter"\nx = 0\ny = 0\n')
        )


def _loaded(text):
    model = site_model(tomlkit.parse(text))
    for key in ("areas", "objects"):
        for entry in model[key]:
            entry["was"] = entry["name"]
    for key in ("walls", "obstacles"):
        for index, entry in enumerate(model[key]):
            entry["was"] = index
    return model


def test_the_editor_round_trips_and_moves_an_object():
    model = _loaded(SITE_TOML)
    assert patched_text(SITE_TOML, model) == SITE_TOML
    assert model["objects"][0]["comment"] == "the pad by the door"
    model["objects"][0]["x"] = 600
    model["objects"][0]["name"] = "pad"
    result = patched_text(SITE_TOML, model)
    assert "[objects.pad]   # the pad by the door\n" in result
    assert "x = 600\n" in result and "heading_deg = 180.0" in result


def test_the_editor_adds_an_object_and_drops_a_zero_heading():
    model = _loaded(SITE_TOML)
    model["objects"].append(
        {"name": "dock", "kind": "dock", "x": 100, "y": 100, "heading_deg": 0}
    )
    result = patched_text(SITE_TOML, model)
    assert '[objects.dock]\nkind = "dock"\nx = 100\ny = 100\n' in result


def test_the_charging_station_takes_its_charger_from_the_site():
    layout = layout_from_site(_site())
    assert (layout.charger_x, layout.charger_y) == (800, 3800)
    assert (layout.queue_head_x, layout.queue_head_y) == (800, 2000)


def test_a_simulated_robot_on_a_charger_charges_and_one_off_it_drains():
    state = InitStateToml(
        dotbots=[
            SimulatedDotBotSettings(address="0000000000000001", pos_x=800, pos_y=3800),
            SimulatedDotBotSettings(address="0000000000000002", pos_x=800, pos_y=1000),
        ]
    )
    sim = DotBotSimulatorCommunicationInterface(lambda frame: None, state, site=_site())
    sim.battery[:] = INITIAL_BATTERY_VOLTAGE / 2
    for _ in range(1000):
        sim.step()
    on, off = sim.battery
    assert list(sim.on_charger()) == [True, False]
    # Ten seconds: a twelfth of a full charge on, a sliver of drain off
    assert on == pytest.approx(INITIAL_BATTERY_VOLTAGE * (0.5 + 10 / 120), abs=1)
    assert off < INITIAL_BATTERY_VOLTAGE / 2


def test_a_robot_with_a_learned_battery_model_charges_on_a_charger_too(monkeypatch):
    import contextlib
    import sys
    import types

    # Stands in for torch: the model below draws 10 mV/s whatever it is fed
    torch = types.SimpleNamespace(
        tensor=lambda data, dtype=None: data,
        float32=None,
        no_grad=contextlib.nullcontext,
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    state = InitStateToml(
        dotbots=[
            SimulatedDotBotSettings(address="0000000000000001", pos_x=800, pos_y=3800),
            SimulatedDotBotSettings(address="0000000000000002", pos_x=800, pos_y=1000),
        ]
    )
    sim = DotBotSimulatorCommunicationInterface(lambda frame: None, state, site=_site())
    sim._battery_models = {0: lambda features: np.array([[-10.0]])}
    sim._battery_modelled[:] = [True, False]
    sim.battery[:] = INITIAL_BATTERY_VOLTAGE / 2
    for _ in range(100):
        sim.step()
    assert sim.battery[0] > INITIAL_BATTERY_VOLTAGE / 2

