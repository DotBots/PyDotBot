"""Tests for the LH2 calibration from circle tracks.

The synthetic station is a measured one: the camera-to-floor homography of a
real corner calibration, inverted to turn floor points into camera points.
Its intrinsics are not the identity, which the solve must not assume.
"""

from dataclasses import replace

import numpy as np
import pytest

from dotbot.calibration import conics
from dotbot.calibration.conics import Track, apply
from dotbot.calibration.lighthouse2 import (
    TrackSample,
    counts_for_camera_point,
    read_calibration_file,
    render_calibration,
)
from dotbot.robots import robot_geometry
from dotbot.site import Site

RADIUS = robot_geometry().spin_radius_mm
REACH = robot_geometry().axle_reach_mm

STATION = np.array(
    [
        [189.809398943489, 2711.3856245939314, 1001.2158981500457],
        [-2180.185035995121, 288.17989657057416, 2247.631285943657],
        [0.08275982451927269, 0.08570280253867424, 1.0],
    ]
)
FLOOR_TO_CAM = np.linalg.inv(STATION)

CENTRES = [
    (300, 300),
    (1700, 400),
    (1000, 1000),
    (400, 1700),
    (1600, 1800),
    (1000, 2600),
]


def grid(x0=100, y0=100, x1=1900, y1=2900, n=15):
    xs, ys = np.meshgrid(np.linspace(x0, x1, n), np.linspace(y0, y1, n))
    return np.c_[xs.ravel(), ys.ravel()]


def circle(centre, radius=RADIUS, n=120, turn=1, arc=2 * np.pi, noise=0.0, rng=None):
    # A counter-clockwise loop as drawn in a y-down frame decreases the angle.
    th = -turn * np.linspace(0, arc, n, endpoint=False)
    pts = np.c_[centre[0] + radius * np.cos(th), centre[1] + radius * np.sin(th)]
    if noise:
        pts = pts + rng.normal(0, noise, pts.shape)
    return pts


def tracks_at(centres, radius=RADIUS, noise=0.0, seed=0, **kwargs):
    rng = np.random.default_rng(seed)
    return [
        Track(
            points=apply(
                FLOOR_TO_CAM, circle(c, radius, noise=noise, rng=rng, **kwargs)
            ),
            radius_mm=radius,
            turn=kwargs.get("turn", 1),
            name=f"c{i}",
        )
        for i, c in enumerate(centres)
    ]


def similarity_error(H, reference=STATION):
    """RMS mm between H and the reference over the field, after the best similarity."""
    P = grid()
    cam = apply(FLOOR_TO_CAM, P)
    ours = apply(H, cam)
    S = conics.similarity(ours, P)
    return float(np.sqrt(np.mean(np.sum((apply(S, ours) - P) ** 2, axis=1)))), S


def test_fit_conic_recovers_an_ellipse():
    th = np.linspace(0, 2 * np.pi, 50, endpoint=False)
    a, b, phi = 3.0, 1.2, 0.4
    x = a * np.cos(th) * np.cos(phi) - b * np.sin(th) * np.sin(phi) + 5
    y = a * np.cos(th) * np.sin(phi) + b * np.sin(th) * np.cos(phi) - 2
    centre, major, minor = conics.ellipse_axes(conics.fit_conic(np.c_[x, y]))
    assert np.allclose(centre, [5, -2])
    assert major == pytest.approx(a)
    assert minor == pytest.approx(b)


def test_eccentricity_of_a_circle_is_zero():
    C = conics.fit_conic(circle((1, 2), 3))
    assert conics.eccentricity(C) == pytest.approx(0, abs=1e-6)


def test_two_imaged_circles_meet_at_the_imaged_circular_points():
    C1 = conics.fit_conic(apply(FLOOR_TO_CAM, circle((300, 300))))
    C2 = conics.fit_conic(apply(FLOOR_TO_CAM, circle((1500, 2000))))
    expected = FLOOR_TO_CAM @ np.array([1, 1j, 0])
    expected = expected / expected[2]
    found = conics.circular_point_candidates(C1, C2)
    assert any(
        np.allclose(p, expected, atol=1e-6)
        or np.allclose(p, np.conj(expected), atol=1e-6)
        for p in found
    )


def test_closed_form_rectifies_up_to_a_similarity():
    Hr, e = conics.closed_form(tracks_at(CENTRES[:3]))
    assert e < 1e-4
    rms, _ = similarity_error(Hr)
    assert rms < 0.1


def test_refine_holds_on_noisy_tracks():
    tracks = tracks_at(CENTRES, noise=1.0, seed=3)
    Hr0, _ = conics.closed_form(tracks)
    Hr = conics.refine(tracks, Hr0)
    assert similarity_error(Hr)[0] < similarity_error(Hr0)[0]
    assert similarity_error(Hr)[0] < 5.0


def test_free_mode_keeps_distances_and_handedness():
    sol = conics.solve(tracks_at(CENTRES, noise=0.5, seed=1))
    rms, S = similarity_error(sol.homography)
    assert rms < 3.0
    # scale from the spin radius: the best similarity back to the floor is a rotation
    assert np.sqrt(abs(np.linalg.det(S[:2, :2]))) == pytest.approx(1.0, abs=0.01)
    # no mirror: the similarity is proper
    assert np.linalg.det(S[:2, :2]) > 0
    assert not sol.dropped
    assert all(abs(t.radius_mm - RADIUS) < 1 for t in sol.tracks)


def test_free_mode_field_is_the_rectangle_around_the_spins():
    sol = conics.solve(tracks_at(CENTRES), margin_mm=200)
    xs = [t.centre_mm[0] for t in sol.tracks]
    ys = [t.centre_mm[1] for t in sol.tracks]
    assert min(xs) == pytest.approx(200, abs=0.5) and min(ys) == pytest.approx(
        200, abs=0.5
    )
    assert sol.field_mm[0] == pytest.approx(max(xs) + 200, abs=1.5)
    assert sol.field_mm[1] == pytest.approx(max(ys) + 200, abs=1.5)


def test_free_mode_axes_follow_rows_of_robots():
    # a 3 x 4 grid turned by 20 degrees on the floor comes out axis-aligned
    turn = np.radians(20)
    rot = np.array([[np.cos(turn), -np.sin(turn)], [np.sin(turn), np.cos(turn)]])
    grid_pts = [
        np.array([700, 900]) + rot @ np.array([i * 400, j * 500])
        for i in range(3)
        for j in range(4)
    ]
    sol = conics.solve(tracks_at(grid_pts))
    xs = np.round([t.centre_mm[0] for t in sol.tracks])
    ys = np.round([t.centre_mm[1] for t in sol.tracks])
    assert len(set(np.round(xs / 10))) <= 4 and len(set(np.round(ys / 10))) <= 5
    assert sorted(sol.field_mm) == pytest.approx(
        sorted([800 + 2 * REACH, 1500 + 2 * REACH]), abs=3
    )


def test_free_mode_mirrors_when_the_tracks_turn_the_other_way():
    sol = conics.solve(tracks_at(CENTRES, turn=-1))
    _, S = similarity_error(sol.homography)
    assert np.linalg.det(S[:2, :2]) > 0


def test_free_mode_takes_partial_arcs():
    sol = conics.solve(tracks_at(CENTRES, arc=np.pi, noise=0.3, seed=2))
    assert similarity_error(sol.homography)[0] < 5.0


def test_two_circles_are_not_enough():
    with pytest.raises(ValueError, match="at least 3 circles"):
        conics.solve(tracks_at(CENTRES[:2]))


def test_a_track_that_is_not_a_circle_is_left_out():
    tracks = tracks_at(CENTRES)
    squashed = circle((1500, 1200)) * [1, 0.7] + [0, 360]
    tracks.append(
        Track(
            points=apply(FLOOR_TO_CAM, squashed), radius_mm=RADIUS, turn=1, name="slip"
        )
    )
    sol = conics.solve(tracks)
    assert sol.rejected == ["slip"]
    assert sol.dropped[0].why.startswith("axis ratio")
    assert similarity_error(sol.homography)[0] < 0.5


def track_samples(centres, station=0):
    samples = []
    for i, centre in enumerate(centres):
        counts = [
            counts_for_camera_point(x, y, station)
            for x, y in apply(FLOOR_TO_CAM, circle(centre))
        ]
        samples.append(
            TrackSample(
                station=station,
                name=f"robot{i}",
                radius_mm=RADIUS,
                turn=1,
                count1=[round(c.count1) for c in counts],
                count2=[round(c.count2) for c in counts],
            )
        )
    return samples


def test_free_mode_calibration_file_round_trips(tmp_path):
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="lab")
    )
    assert calibration.stations[0].solved_from == "conics-free"
    assert calibration.site.anchor == conics.FREE_FRAME_ANCHOR
    assert calibration.valid_mm[:2] == (0, 0)
    path = tmp_path / "cal.toml"
    path.write_text(render_calibration(calibration))
    back = read_calibration_file(path)
    assert back.id == calibration.id == back.stored_id
    assert len(back.tracks) == len(CENTRES)
    assert similarity_error(back.stations[0].matrix)[0] < 1.0


def test_the_tracks_are_part_of_the_identity():
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="lab")
    )
    edited = replace(calibration, tracks=calibration.tracks[:-1])
    assert edited.id != calibration.id


def test_a_self_defined_site_centres_the_field():
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="lab")
    )
    field_w, field_h = calibration.valid_mm[2:]
    site, placed = conics.self_defined_site(calibration, "spun", size_mm=(3000, 4000))
    assert site.extent_mm == (3000, 4000)
    field = site.areas["field"]
    assert (field.w, field.h) == (field_w, field_h)
    assert (field.x, field.y) == ((3000 - field_w) // 2, (4000 - field_h) // 2)
    assert placed.valid_mm == (0, 0, 3000, 4000)
    assert (
        placed.site.anchor
        == site.anchor
        == f"self-defined from spin calibration {calibration.id8}"
    )
    cam = apply(FLOOR_TO_CAM, np.array([[500.0, 500.0]]))
    moved = apply(placed.stations[0].matrix, cam) - apply(
        calibration.stations[0].matrix, cam
    )
    assert moved[0] == pytest.approx([field.x, field.y])


def test_a_self_defined_site_must_hold_the_field():
    calibration, _, _ = conics.solve_calibration(
        track_samples(CENTRES), Site(name="lab")
    )
    with pytest.raises(ValueError, match="does not fit"):
        conics.self_defined_site(calibration, "spun", size_mm=(100, 100))


def test_a_circle_smaller_than_its_peers_is_left_out():
    tracks = tracks_at(CENTRES)
    small = circle((1300, 2000), radius=0.8 * RADIUS)
    tracks.append(
        Track(
            points=apply(FLOOR_TO_CAM, small), radius_mm=RADIUS, turn=1, name="caster"
        )
    )
    sol = conics.solve(tracks)
    assert sol.rejected == ["caster"]
    assert "off its peers" in sol.dropped[0].why
    assert similarity_error(sol.homography)[0] < 0.5


def test_too_few_reads_leave_a_track_out():
    tracks = tracks_at(CENTRES)
    tracks.append(
        Track(points=tracks[0].points[:5], radius_mm=RADIUS, turn=1, name="short")
    )
    sol = conics.solve(tracks)
    assert sol.rejected == ["short"] and "5 reads" in sol.dropped[0].why


def test_the_radius_sets_the_scale():
    sol = conics.solve(tracks_at(CENTRES))
    tracks = tracks_at(CENTRES)
    for t in tracks:
        t.radius_mm = 53.5
    long = conics.solve(tracks)
    _, S = similarity_error(sol.homography)
    _, S_long = similarity_error(long.homography)
    ratio = np.sqrt(abs(np.linalg.det(S[:2, :2])) / abs(np.linalg.det(S_long[:2, :2])))
    assert ratio == pytest.approx(53.5 / RADIUS, rel=1e-3)


# A second station, looking at the floor from the other side
STATION_B = np.array(
    [
        [-150.0, -2600.0, 3100.0],
        [2100.0, -250.0, 1500.0],
        [-0.07, -0.08, 1.0],
    ]
)


def circle_samples(station_matrix, centres, station, start=0):
    samples = []
    for i, centre in enumerate(centres, start=start):
        cam = apply(np.linalg.inv(station_matrix), circle(centre))
        counts = [counts_for_camera_point(x, y, station) for x, y in cam]
        samples.append(
            TrackSample(
                station=station,
                name=f"robot{i}",
                radius_mm=RADIUS,
                turn=1,
                count1=[round(c.count1) for c in counts],
                count2=[round(c.count2) for c in counts],
            )
        )
    return samples


def test_a_second_station_lands_in_the_first_ones_frame():
    samples = circle_samples(STATION, CENTRES, 0) + circle_samples(
        STATION_B, CENTRES[1:], 1, start=1
    )
    calibration, solutions, unsolved = conics.solve_calibration(
        samples, Site(name="lab")
    )
    assert not unsolved and sorted(solutions) == [0, 1]
    P = grid(300, 300, 1700, 2600, n=8)
    a = apply(calibration.station(0).matrix, apply(FLOOR_TO_CAM, P))
    b = apply(calibration.station(1).matrix, apply(np.linalg.inv(STATION_B), P))
    assert np.max(np.linalg.norm(a - b, axis=1)) < 1.0


def test_a_station_with_too_few_circles_is_reported_not_fatal():
    samples = circle_samples(STATION, CENTRES, 0) + circle_samples(
        STATION_B, CENTRES[:2], 1
    )
    calibration, solutions, unsolved = conics.solve_calibration(
        samples, Site(name="lab")
    )
    assert sorted(solutions) == [0] and "at least 3 circles" in unsolved[1]
    assert [s.index for s in calibration.stations] == [0]
