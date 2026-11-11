# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Anchoring the frame on tape-measured spots: the rigid fit from any
number of spots, the route the editor calls, and the spots kept in
site.toml."""

import math

import pytest
import tomlkit

from dotbot.calibration.site_frame import fit_spots
from dotbot.calibration.site_turn import floor_move
from dotbot.site_editor import EditorState, create_app
from dotbot.site_toml import patched_text, site_model, validate
from dotbot.tests.test_site_editor import local_client

CORNERS = [(0.0, 0.0), (3000.0, 0.0), (3000.0, 2000.0), (0.0, 2000.0)]


def _reads(spots, theta_deg, shift):
    """Where robots on `spots` read themselves when the frame they report
    in is the anchored one turned by `theta_deg` and shifted by `shift`."""
    c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
    return [(c * x - s * y + shift[0], s * x + c * y + shift[1]) for x, y in spots]


def _lands(fit, reads):
    """The reads in the anchored frame, by the move the server applies."""
    return floor_move(fit.theta_deg, fit.pivot, fit.shift).apply(reads)


def test_four_exact_corners_give_back_the_move():
    reads = _reads(CORNERS, 3.0, (120.0, 340.0))
    fit = fit_spots(CORNERS, reads)
    assert fit.theta_deg == pytest.approx(3.0, abs=0.01)
    assert max(fit.residuals_mm) <= 0.3
    for got, want in zip(_lands(fit, reads), CORNERS):
        assert got == pytest.approx(want, abs=0.5)


def test_noisy_spots_fit_by_least_squares():
    reads = _reads(CORNERS, -1.5, (80.0, 60.0))
    noise = [(2.0, -1.0), (-1.5, 2.0), (1.0, 1.5), (-2.0, -1.5)]
    noisy = [(x + dx, y + dy) for (x, y), (dx, dy) in zip(reads, noise)]
    fit = fit_spots(CORNERS, noisy)
    assert fit.theta_deg == pytest.approx(-1.5, abs=0.1)
    assert 0.5 < max(fit.residuals_mm) < 4.0
    for got, want in zip(_lands(fit, noisy), CORNERS):
        assert got == pytest.approx(want, abs=4.0)


def test_two_spots_turn_and_shift():
    spots = [(500.0, 500.0), (2500.0, 500.0)]
    reads = _reads(spots, 10.0, (-50.0, 200.0))
    fit = fit_spots(spots, reads)
    assert fit.theta_deg == pytest.approx(10.0, abs=0.01)
    assert max(fit.residuals_mm) <= 0.5


def test_one_spot_shifts_only():
    fit = fit_spots([(100.0, 100.0)], [(130.0, 90.0)])
    assert fit.theta_deg == 0.0
    assert fit.residuals_mm == [0.0]
    assert _lands(fit, [(130.0, 90.0)])[0] == pytest.approx((100.0, 100.0))


def test_a_spot_without_a_read_is_refused():
    with pytest.raises(ValueError):
        fit_spots([(0.0, 0.0), (1.0, 1.0)], [(0.0, 0.0)])


ARENA = """\
anchor = "the tape cross by the door"
extent_mm = [3000, 2000]
"""


def test_the_route_fits_and_writes_nothing(tmp_path):
    pack = tmp_path / "arena"
    pack.mkdir()
    (pack / "site.toml").write_text(ARENA)
    client = local_client(create_app(EditorState("arena", pack, []), None))
    reads = _reads(CORNERS, 2.0, (40.0, 30.0))
    r = client.post(
        "/api/anchor",
        json={"spots": [{"at_mm": s, "read_mm": r} for s, r in zip(CORNERS, reads)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["move"]["theta_deg"] == pytest.approx(2.0, abs=0.01)
    assert len(body["residuals_mm"]) == 4
    assert body["worst_mm"] == max(body["residuals_mm"])
    assert (pack / "site.toml").read_text() == ARENA
    assert client.post("/api/anchor", json={"spots": []}).status_code == 422


def test_anchor_spots_are_kept_in_site_toml_beside_the_note():
    model = site_model(tomlkit.parse(ARENA))
    assert model["anchor_spots"] == []
    model["anchor_spots"] = [
        {"at_mm": [0, 0], "error_mm": 1.24},
        {"at_mm": [3000, 2000.5], "error_mm": 0.6},
    ]
    text = patched_text(ARENA, model)
    assert text.startswith(ARENA)
    assert "[[anchor_spots]]\nat_mm = [0, 0]\nerror_mm = 1.2\n" in text
    assert validate(text).anchor_spots[1].at_mm == (3000.0, 2000.5)
    again = site_model(tomlkit.parse(text))
    assert again["anchor_spots"][0] == {"at_mm": [0.0, 0.0], "error_mm": 1.2}
    assert patched_text(text, again) == text
    again["anchor_spots"] = []
    assert patched_text(text, again).rstrip() == ARENA.rstrip()
