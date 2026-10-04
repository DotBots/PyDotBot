"""Tests for several LH2 stations put in one frame from shared spins.

The stations are the measured c405 one moved over the floor (see
`lh2_multi_fixture`), so every number here is in floor millimetres.
"""

import tomllib
from pathlib import Path

import numpy as np
import pytest

from dotbot.calibration import conics
from dotbot.calibration import multi_station as ms
from dotbot.calibration.conics import apply, similarity
from dotbot.calibration.lighthouse2 import (
    TrackSample,
    read_calibration_file,
    render_calibration,
    station_mask,
)
from dotbot.site import Site
from dotbot.tests import lh2_multi_fixture as F

HERE = Path(__file__).parent


def two_stations():
    a = F.station(0)
    b = F.station(1, F.rigid(2200, 0, 0), aspect=0.9)
    return a, b


def floor_grid(stations, step=450, y=(300, 2800)):
    centres = [
        (x, yy) for x in np.arange(-200, 3500, step) for yy in np.arange(*y, 500)
    ]
    return [c for c in centres if any(s.sees(c) for s in stations)]


def overlap_disagreement(joint, a, b):
    P = np.array(
        [
            (x, y)
            for x in np.arange(1300, 2000, 100)
            for y in np.arange(800, 2200, 100)
            if a.sees((x, y)) and b.sees((x, y))
        ]
    )
    pa = apply(joint.homographies[a.index], apply(a.floor_to_cam, P))
    pb = apply(joint.homographies[b.index], apply(b.floor_to_cam, P))
    return np.linalg.norm(pa - pb, axis=1)


def test_two_stations_map_the_overlap_to_the_same_points():
    a, b = two_stations()
    tracks = F.spins([a, b], floor_grid([a, b]), noise=1.0, seed=2)
    joint = ms.solve_joint(tracks)
    assert sorted(joint.homographies) == [0, 1]
    assert overlap_disagreement(joint, a, b).max() < 1.0
    errors = F.placed_error(joint.homographies, [a, b])
    assert max(rms for rms, _ in errors.values()) < 2.5
    (link,) = joint.graph.links
    assert (link.a, link.b) == (0, 1)
    assert link.shared >= ms.LINK_SHARED_ADVISED and ms.link_advised(link)
    assert all(abs(r - 1) < 0.005 for r in joint.scale_ratio.values())


def test_two_stations_noise_free_are_exact():
    a, b = two_stations()
    joint = ms.solve_joint(F.spins([a, b], floor_grid([a, b])))
    assert overlap_disagreement(joint, a, b).max() < 0.05
    errors = F.placed_error(joint.homographies, [a, b])
    assert max(worst for _, worst in errors.values()) < 0.05


def test_each_station_gets_its_own_rectangle_and_the_fence_is_their_union():
    a, b = two_stations()
    joint = ms.solve_joint(F.spins([a, b], floor_grid([a, b])))
    ra, rb = joint.rectangles[0], joint.rectangles[1]
    for s, rect in joint.rectangles.items():
        centres = np.array(
            [t.centre_mm for t in joint.solutions[s].tracks], dtype=float
        )
        assert rect[0] == max(0, int(np.floor(centres[:, 0].min() - 300)))
        assert rect[2] == int(np.ceil(centres[:, 0].max() + 300))
        assert rect[1] == max(0, int(np.floor(centres[:, 1].min() - 300)))
    assert joint.valid_mm == (
        min(ra[0], rb[0]),
        min(ra[1], rb[1]),
        max(ra[2], rb[2]),
        max(ra[3], rb[3]),
    )
    # station 1 sits to the right of station 0, so its rectangle starts later
    assert rb[0] > ra[0] + 1000


def ring(n=5, radius=1700):
    stations = []
    for k in range(n):
        a = 2 * np.pi * k / n
        vertex = np.array([radius * np.cos(a), radius * np.sin(a)]) + 3000
        theta = np.degrees(a) + 90
        patch = apply(F.rigid(0, 0, theta), F.C405_PATCH[None, :])[0]
        stations.append(
            F.station(
                k, F.rigid(*(vertex - patch), theta), aspect=0.9 if k % 2 else 1.0
            )
        )
    return stations


def ring_centres(stations, closed):
    """Twelve spins per station of its own, and two 400 mm apart per overlap;
    a chain leaves the last overlap out."""
    n, middle = len(stations), np.mean([s.patch for s in stations], axis=0)
    centres = []
    for k, st in enumerate(stations):
        out = (st.patch - middle) / np.linalg.norm(st.patch - middle)
        side = np.array([-out[1], out[0]])
        centres += [
            st.patch + out * e + side * d
            for d in (-450, -150, 150, 450)
            for e in (0, 400, 800)
        ]
        if k == n - 1 and not closed:
            continue
        nxt = stations[(k + 1) % n].patch
        mid = (st.patch + nxt) / 2
        t = (nxt - st.patch) / np.linalg.norm(nxt - st.patch)
        normal = np.array([-t[1], t[0]])
        centres += [mid + normal * d for d in (-200, 200)]
    if not closed:
        centres = [
            c for c in centres if not (stations[0].sees(c) and stations[-1].sees(c))
        ]
    return centres


def drift(homographies, stations, a, b):
    """rms mm of station b once station a alone is put on the truth."""
    pa = F.grid_in(stations[a])
    S = similarity(
        apply(homographies[a], apply(stations[a].floor_to_cam, pa)), pa, scale=False
    )
    pb = F.grid_in(stations[b], inset=600)
    got = apply(S @ homographies[b], apply(stations[b].floor_to_cam, pb))
    return float(np.sqrt(np.mean(np.sum((got - pb) ** 2, axis=1))))


def chained(tracks, order):
    """Pairwise rigid fits composed down `order`: the seed alone."""
    solutions = {s: conics.solve(tracks[s]) for s in order}
    own = {
        s: {t.key: np.array(t.centre_mm) for t in solutions[s].tracks} for s in order
    }
    H, world = {order[0]: solutions[order[0]].homography}, {order[0]: own[order[0]]}
    for p, s in zip(order, order[1:]):
        keys = sorted(set(own[s]) & set(own[p]), key=lambda k: k.name)
        S = similarity(
            np.array([own[s][k] for k in keys]),
            np.array([world[p][k] for k in keys]),
            scale=False,
        )
        H[s] = S @ solutions[s].homography
        world[s] = {k: apply(S, v[None, :])[0] for k, v in own[s].items()}
    return H


@pytest.mark.parametrize("seed", [0, 2])
def test_a_ring_holds_better_than_a_chain_and_beats_chaining(seed):
    stations = ring()
    ring_tracks = F.spins(stations, ring_centres(stations, True), noise=2.0, seed=seed)
    chain_tracks = F.spins(
        stations, ring_centres(stations, False), noise=2.0, seed=seed
    )
    closed = ms.solve_joint(ring_tracks)
    chain = ms.solve_joint(chain_tracks)
    assert len(closed.loops) == 1 and not chain.loops
    assert drift(closed.homographies, stations, 0, 4) < drift(
        chain.homographies, stations, 0, 4
    )
    # the joint solve closes the loop that chaining down the ring cannot
    assert drift(closed.homographies, stations, 0, 4) < drift(
        chained(ring_tracks, [0, 1, 2, 3, 4]), stations, 0, 4
    )
    assert closed.error_map.worst_mm < chain.error_map.worst_mm


def test_an_island_is_refused_by_name_and_dropping_it_solves_the_rest():
    a, b = two_stations()
    far = F.station(8, F.rigid(0, 3200, 0))
    centres = floor_grid([a, b]) + [far.patch + d for d in ((0, 0), (500, 0), (0, 500))]
    # one robot where station 8 and station 0 both see it: a one-circle link
    shared = ((a.patch + far.patch) / 2).tolist()
    a.reach_mm = far.reach_mm = 1800
    assert a.sees(shared) and far.sees(shared) and not b.sees(shared)
    tracks = F.spins([a, b, far], centres + [shared])
    assert {t.key for t in tracks[0]} & {t.key for t in tracks[8]}
    with pytest.raises(ms.MultiStationError) as caught:
        ms.solve_joint(tracks)
    assert caught.value.islands == [8]
    assert "station 8 (channel 9)" in str(caught.value)
    assert "--drop-station 8" in str(caught.value)
    assert [(k.a, k.b, k.shared) for k in caught.value.weak] == [(0, 8, 1)]
    joint = ms.solve_joint(tracks, drop=[8])
    assert sorted(joint.homographies) == [0, 1]


@pytest.mark.parametrize("apart_mm", [200, 10])
def test_shared_centres_closer_than_300_mm_are_not_a_link(apart_mm):
    a = F.station(0)
    b = F.station(1, F.rigid(2200, 0, 0))
    own_a = [(500, 1000), (500, 2000), (900, 1500), (300, 1500)]
    own_b = [(3200, 1000), (3200, 2000), (3600, 1500), (2900, 1500)]
    tie = [(1800, 1500), (1800 + apart_mm, 1500)]
    assert all(a.sees(c) and b.sees(c) for c in tie)
    tracks = F.spins([a, b], own_a + own_b + tie)
    graph = ms.station_graph(tracks)
    (link,) = graph.links
    assert link.shared == 2 and link.spread_mm == pytest.approx(apart_mm, abs=0.5)
    assert not ms.link_holds(link) and graph.components == [[0], [1]]
    with pytest.raises(ms.MultiStationError, match="station 1 \\(channel 2\\)"):
        ms.solve_joint(tracks)


def test_the_error_map_predicts_the_spread_of_solves():
    """Predicted sigma against 20 noisy solves of the same floor."""
    a, b = two_stations()
    centres = floor_grid([a, b])
    reference = None
    errors = {0: [], 1: []}
    for seed in range(20):
        joint = ms.solve_joint(
            F.spins([a, b], centres, noise=1.0, seed=seed, points=60)
        )
        if reference is None:
            reference = joint
            em = joint.error_map
            rows, cols = em.sigma_mm.shape
            cells = np.array(
                [em.centre(r, c) for r in range(rows) for c in range(cols)]
            )
            cover = {
                s: (cells[:, 0] >= r[0])
                & (cells[:, 0] <= r[2])
                & (cells[:, 1] >= r[1])
                & (cells[:, 1] <= r[3])
                for s, r in joint.rectangles.items()
            }
            floor = {
                s: apply(
                    st.cam_to_floor,
                    apply(np.linalg.inv(joint.homographies[s]), cells[cover[s]]),
                )
                for s, st in ((0, a), (1, b))
            }
        ours = {
            s: apply(joint.homographies[s], apply(st.floor_to_cam, floor[s]))
            for s, st in ((0, a), (1, b))
        }
        S = similarity(
            np.vstack([ours[0], ours[1]]), np.vstack([floor[0], floor[1]]), scale=False
        )
        for s in (0, 1):
            errors[s].append(apply(S, ours[s]) - floor[s])
    info = np.zeros(len(cells))
    for s in (0, 1):
        e = np.array(errors[s])
        e -= e.mean(axis=0)
        info[cover[s]] += 1 / np.mean(np.sum(e**2, axis=2), axis=0)
    predicted = reference.error_map.sigma_mm.ravel()
    seen = ~np.isnan(predicted) & (info > 0)
    ratio = np.median(predicted[seen] / (1 / np.sqrt(info[seen])))
    assert 1 / 1.5 < ratio < 1.5
    assert reference.error_map.cells_over_10mm == 0
    assert reference.error_map.worst_mm == pytest.approx(np.nanmax(predicted))


def test_the_error_map_grows_away_from_the_spins():
    a, b = two_stations()
    joint = ms.solve_joint(F.spins([a, b], floor_grid([a, b]), noise=1.0, seed=4))
    em = joint.error_map
    centres = np.array([v for v in joint.centres.values()])
    rows, cols = em.sigma_mm.shape
    near, far = [], []
    for r in range(rows):
        for c in range(cols):
            if np.isnan(em.sigma_mm[r, c]):
                continue
            d = np.min(np.linalg.norm(centres - np.array(em.centre(r, c)), axis=1))
            (near if d < 150 else far if d > 400 else []).append(em.sigma_mm[r, c])
    assert np.median(far) > np.median(near)


def one_bad_circle(a, b):
    """Tracks of two stations where station 1 saw one shared circle 25 mm off."""
    centres = floor_grid([a, b], step=300)
    tracks = F.spins([a, b], centres, noise=0.5, seed=1)
    shared = sorted(
        {t.key for t in tracks[0]} & {t.key for t in tracks[1]}, key=lambda k: k.name
    )
    assert len(shared) >= 6
    bad = shared[len(shared) // 2]
    for t in tracks[1]:
        if t.key == bad:
            floor = apply(b.cam_to_floor, t.points) + [25.0, 0.0]
            t.points = apply(b.floor_to_cam, floor)
    return tracks, bad


def test_a_circle_the_stations_disagree_on_is_untied():
    a, b = two_stations()
    tracks, bad = one_bad_circle(a, b)
    joint = ms.solve_joint(tracks)
    assert list(joint.dropped) == [bad]
    assert "mm apart" in joint.dropped[bad]
    assert overlap_disagreement(joint, a, b).max() < 1.0


def test_a_circle_untied_in_the_last_round_is_out_of_the_solve(monkeypatch):
    monkeypatch.setattr(ms, "TIE_ROUNDS_MAX", 1)
    a, b = two_stations()
    tracks, bad = one_bad_circle(a, b)
    joint = ms.solve_joint(tracks)
    assert list(joint.dropped) == [bad]
    assert overlap_disagreement(joint, a, b).max() < 1.0


def test_the_normal_equations_match_the_whole_jacobian():
    a, b = two_stations()
    tracks = F.spins([a, b], floor_grid([a, b]), noise=1.0, seed=6, points=40)
    joint = ms.solve_joint(tracks)
    kept = {
        s: [t for t in tracks[s] if t.key in {f.key for f in sol.tracks}]
        for s, sol in joint.solutions.items()
    }
    world = {
        s: {t.key: np.array(t.centre_mm) for t in sol.tracks}
        for s, sol in joint.solutions.items()
    }
    tied = {}
    for s, centres in world.items():
        for k in centres:
            tied.setdefault(k, set()).add(s)
    problem, x = ms._build_problem(kept, world, tied, joint.homographies, 0)
    w = np.random.default_rng(0).uniform(0.5, 1.5, len(problem.residuals(x)))
    step = 1e-6 * np.maximum(np.abs(x), 1e-3)
    J = np.column_stack(
        [
            (problem.residuals(x + dx) - problem.residuals(x - dx)) / (2 * dx[i])
            for i, dx in enumerate(np.diag(step))
        ]
    )
    A, g = problem.normal(x, w)
    Jw = J * w[:, None]
    assert np.allclose(A, Jw.T @ Jw, rtol=1e-4, atol=1e-6 * np.abs(A).max())
    assert np.allclose(
        g, Jw.T @ (w * problem.residuals(x)), rtol=1e-4, atol=1e-6 * np.abs(g).max()
    )


def test_a_two_circle_link_claims_no_better_yaw_than_its_baseline_allows():
    a = F.station(0)
    b = F.station(1, F.rigid(2200, 0, 0))
    own_a = [(500, 1000), (500, 2000), (900, 1500), (300, 1500)]
    own_b = [(3200, 1000), (3200, 2000), (3600, 1500), (2900, 1500)]
    tie = [(1700, 1500), (2100, 1500)]
    joint = ms.solve_joint(F.spins([a, b], own_a + own_b + tie))
    (link,) = joint.graph.links
    assert link.shared == 2 and link.disagreement_mm < 0.1
    # sqrt(2) sigma / L with sigma at its floor: noise-free fits measure none
    floor = 1000 * np.sqrt(2) * ms.TIE_SIGMA_FLOOR_MM / link.spread_mm
    assert link.yaw_sigma_mrad == pytest.approx(floor, rel=0.01)


def test_a_single_station_is_solved_as_free_mode_solves_it():
    a = F.station(0)
    tracks = F.spins([a], floor_grid([a]), noise=0.5, seed=3)
    joint = ms.solve_joint(tracks)
    own = conics.solve(tracks[0])
    assert np.array_equal(joint.homographies[0], own.homography / own.homography[2, 2])
    assert joint.field_mm == own.field_mm
    assert not joint.graph.links and joint.error_map.covered > 0


def real_spin_samples():
    data = tomllib.loads((HERE / "lh2_spin_c405.toml").read_text())
    samples = [
        TrackSample(
            station=t["station"],
            name=t["name"],
            radius_mm=t["radius_mm"],
            turn=t["turn"],
            count1=t["count1"],
            count2=t["count2"],
        )
        for t in data["track"]
    ]
    return data, samples


def test_a_real_single_station_calibration_solves_as_before():
    data, samples = real_spin_samples()
    calibration, joint, unsolved = conics.solve_calibration(samples, Site(name="lab"))
    assert not unsolved
    (station,) = calibration.stations
    assert station.solved_from == "conics-free"
    expected = np.array(data["expected_homography"])
    cams = np.vstack([s.camera_points() for s in samples])
    moved = np.linalg.norm(apply(expected, cams) - apply(station.matrix, cams), axis=1)
    assert moved.max() < 0.1
    assert list(joint.field_mm) == data["expected_field_mm"]
    assert calibration.valid_mm == station.valid_mm
    assert joint.error_map.worst_mm < 10


def test_stations_2_and_8_are_written_as_schema_4(tmp_path):
    two = F.station(2)
    eight = F.station(8, F.rigid(2200, 0, 0), aspect=0.9)
    samples = F.samples(F.spins([two, eight], floor_grid([two, eight])))
    calibration, joint, _ = conics.solve_calibration(samples, Site(name="arena"))
    assert [s.index for s in calibration.stations] == [2, 8]
    assert {s.solved_from for s in calibration.stations} == {"conics-joint"}
    assert station_mask(calibration) == 0x0104
    assert [(k.a, k.b) for k in calibration.links] == [(2, 8)]
    path = tmp_path / "cal.toml"
    path.write_text(render_calibration(calibration), encoding="utf-8")
    back = read_calibration_file(path)
    assert back.id == calibration.id == back.stored_id
    assert back.links == calibration.links
    assert [s.valid_mm for s in back.stations] == [
        joint.rectangles[2],
        joint.rectangles[8],
    ]
    assert back.valid_mm == joint.valid_mm


def test_circles_are_keyed_by_robot_and_round():
    a, b = two_stations()
    first = F.spins([a, b], floor_grid([a, b])[::2], names=None)
    # the same robots, moved, in a second round
    second = F.spins([a, b], floor_grid([a, b])[1::2], round_=1)
    tracks = {s: first.get(s, []) + second.get(s, []) for s in (0, 1)}
    names = {t.name for t in tracks[0]}
    assert any(n in {t.name for t in second[0]} for n in names)
    joint = ms.solve_joint(tracks)
    keys = set(joint.centres)
    assert {k.round for k in keys} == {0, 1}
    same_name = [k for k in keys if k.round == 1 and ms.CircleKey(k.name, 0) in keys]
    assert same_name
    for k in same_name:
        assert (
            np.linalg.norm(joint.centres[k] - joint.centres[ms.CircleKey(k.name, 0)])
            > 100
        )
    samples = F.samples(tracks)
    calibration, _, _ = conics.solve_calibration(samples, Site(name="arena"))
    assert sorted({t.round for t in calibration.tracks}) == [0, 1]


def test_a_schema_3_file_is_refused(tmp_path):
    path = tmp_path / "cal.toml"
    path.write_text("schema_version = 3\n", encoding="utf-8")
    with pytest.raises(
        ValueError, match="schema_version 3.*collect the calibration again"
    ):
        read_calibration_file(path)


def test_the_report_names_stations_links_and_the_error_map(tmp_path):
    a, b = two_stations()
    samples = F.samples(F.spins([a, b], floor_grid([a, b]), noise=0.5, seed=5))
    calibration, joint, _ = conics.solve_calibration(samples, Site(name="arena"))
    live = ms.multi_station_report(calibration, joint)
    text = "\n".join(live)
    assert "station 0 (channel 1)" in text and "station 1 (channel 2)" in text
    assert "station 0 (channel 1) - station 1 (channel 2):" in text
    assert "predicted error (100 mm cells): worst" in text
    path = tmp_path / "cal.toml"
    path.write_text(render_calibration(calibration), encoding="utf-8")
    offline = ms.multi_station_report(read_calibration_file(path))
    assert any(line.startswith("predicted error") for line in offline)
    assert any(" - station 1 (channel 2):" in line for line in offline)


def test_the_file_rules_are_enforced(tmp_path):
    a, b = two_stations()
    samples = F.samples(F.spins([a, b], floor_grid([a, b])))
    calibration, _, _ = conics.solve_calibration(samples, Site(name="arena"))
    text = render_calibration(calibration)
    path = tmp_path / "cal.toml"
    cases = {
        "not the union": text.replace(
            f"valid_mm = [{', '.join(map(str, calibration.valid_mm))}]",
            "valid_mm = [0, 0, 10, 10]",
            1,
        ),
        "no \\[\\[link\\]\\]": text[: text.index("[[link]]")],
        "has no valid_mm": text.replace(
            "valid_mm = ["
            + ", ".join(map(str, calibration.stations[1].valid_mm))
            + "]\n",
            "",
        ),
    }
    for match, broken in cases.items():
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(ValueError, match=match):
            read_calibration_file(path)
