"""Tests for the LH2 calibration solve, the schema 2 file and the identity.

Synthetic captures are built by inverting one chosen station matrix, so the
correspondences are exactly consistent and the solver's own error is the only
thing under test. A raw count is an integer, and one count unit is worth
about 0.1 mm on the floor, so the declared coordinates are derived from the
integer counts rather than the other way round.
"""

import tomllib
from dataclasses import replace

import numpy as np
import pytest

from dotbot.area import Area, AreaRegistry
from dotbot.calibration import lighthouse2
from dotbot.calibration.lighthouse2 import (
    LH2Counts,
    LighthouseManager,
    Placement,
    Sample,
    apply_homography,
    calculate_camera_point,
    counts_for_camera_point,
    read_calibration_file,
    render_calibration,
    resolve_calibration_path,
)
from dotbot.calibration.points import collect_header, point_prompt, resolve_points
from dotbot.site import Site

# A plausible wall-mounted station: the magnitude of perspective row real
# calibration files carry.
H_TRUE = np.array(
    [
        [1523.4, -38.2, 1012.7],
        [41.9, 1531.8, 988.3],
        [0.2134, -0.0871, 1.0],
    ],
    dtype=np.float64,
)

ARENA = Area(0, 0, 2000, 2000, "arena")
# The C405 layout, which the package no longer ships: a site is measured.
C405 = Site(
    name="c405-arena",
    anchor="the arena's top-left corner, against the door wall of C405",
    extent_mm=(2000, 4000),
    areas={
        "arena": ARENA,
        "annex": Area(0, 2000, 2000, 2000, "annex"),
        "arena+annex": Area(0, 0, 2000, 4000, "arena+annex"),
        "wing": Area(2000, 2610, 1330, 1390, "wing"),
    },
)


def _floor_from_camera(homography, cam_x, cam_y):
    return apply_homography(homography, np.array([[cam_x, cam_y]]))[0]


def _integer_counts(cam_x, cam_y, lh_index=0) -> tuple[int, int]:
    counts = counts_for_camera_point(cam_x, cam_y, lh_index)
    return (round(counts.count1), round(counts.count2))


def _sample(station, point, count1, count2, reads=1) -> Sample:
    return Sample(
        station=station,
        point=point,
        count1=[count1] * reads,
        count2=[count2] * reads,
    )


def _grid_camera_points(n_side):
    """Camera points spread over the part of the view the arena occupies."""
    return [
        (-0.30 + 0.60 * i / (n_side - 1), -0.30 + 0.60 * j / (n_side - 1))
        for i in range(n_side)
        for j in range(n_side)
    ]


def _consistent_placement(camera_points, station=0, reads=1, jitter_mm=0.0, seed=0):
    """A placement whose declared points are `H_TRUE`'s image of the counts.

    With `jitter_mm` the declared coordinates are displaced by a Gaussian per
    axis, which is what a hand-placed photodiode does.
    """
    rng = np.random.default_rng(seed)
    points, samples = [], []
    for index, (cam_x, cam_y) in enumerate(camera_points):
        count1, count2 = _integer_counts(cam_x, cam_y, station)
        back = calculate_camera_point(LH2Counts(station, count1, count2))
        floor = _floor_from_camera(H_TRUE, back[0], back[1])
        if jitter_mm:
            floor = floor + rng.normal(0.0, jitter_mm, 2)
        points.append((float(floor[0]), float(floor[1])))
        samples.append(_sample(station, index, count1, count2, reads))
    return Placement(index=0, at="synthetic", points_mm=points, samples=samples)


# --- the camera model -------------------------------------------------------


def test_camera_points():
    counts = LH2Counts(lh_index=1, count1=49341, count2=85887)
    x, y = calculate_camera_point(counts)
    assert x == pytest.approx(-0.43435315273542)
    assert y == pytest.approx(0.1512338330873567)


# --- the solver -------------------------------------------------------------


def test_four_points_solve_exactly_and_place_an_off_centre_point():
    """Four noiseless points fix the map, and it holds 900 mm off centre."""
    corners = [(-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)]
    placement = _consistent_placement(corners)
    manager = LighthouseManager(placements=[placement])
    station = manager.solve()[0]

    assert station.points == 4
    # A four-point fit reprojects its own points exactly; the residual is the
    # solver's own arithmetic, tens of nanometres on a matrix of this scale.
    assert station.residual_mm < 1e-3

    centre = np.mean(np.array(placement.points_mm), axis=0)
    # A camera point whose true floor position is about 900 mm off the figure
    # centre, so the check is extrapolation rather than interpolation.
    off_x, off_y = 0.55, 0.55
    count1, count2 = _integer_counts(off_x, off_y)
    back = calculate_camera_point(LH2Counts(0, count1, count2))
    truth = _floor_from_camera(H_TRUE, back[0], back[1])
    solved = _floor_from_camera(station.matrix, back[0], back[1])

    assert np.linalg.norm(truth - centre) == pytest.approx(900, abs=250)
    assert np.linalg.norm(solved - truth) < 0.01


def test_sixteen_noisy_points_solve_by_least_squares_with_a_residual():
    """Over-determined and noisy: a residual, and no exception."""
    placement = _consistent_placement(
        _grid_camera_points(4), reads=25, jitter_mm=3.0, seed=7
    )
    manager = LighthouseManager(placements=[placement])
    station = manager.solve()[0]

    assert station.points == 16
    # Four points fix eight unknowns, so sixteen points leave the residual at
    # roughly the per-point placement sigma. It is never zero with noise.
    assert 0.5 < station.residual_mm < 5.0


def test_a_solve_needs_four_points():
    placement = _consistent_placement([(-0.2, -0.2), (0.2, -0.2), (-0.2, 0.2)])
    manager = LighthouseManager(placements=[placement])
    with pytest.raises(ValueError, match="4 points a homography needs"):
        manager.solve()


def test_two_stations_are_solved_from_the_same_placement():
    """A placement seen by two stations ties both into the same frame."""
    corners = [(-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)]
    placement = _consistent_placement(corners)
    for index, (cam_x, cam_y) in enumerate(corners):
        count1, count2 = _integer_counts(cam_x, cam_y, 1)
        placement.samples.append(_sample(1, index, count1, count2))

    stations = LighthouseManager(placements=[placement]).solve()
    assert [s.index for s in stations] == [0, 1]
    assert all(s.points == 4 for s in stations)


def test_reads_are_averaged_before_the_solve():
    sample = _sample(0, 0, 100, 200, reads=1)
    sample.count1 = [100, 102, 104]
    sample.count2 = [200, 200, 200]
    assert sample.reads == 3
    assert sample.mean_counts().count1 == pytest.approx(102.0)


def test_reads_with_swapped_sweeps_are_ordered_before_averaging():
    sample = _sample(0, 0, 40661, 80988, reads=1)
    sample.count1 = [40661, 80992]
    sample.count2 = [80988, 40664]
    counts = sample.mean_counts()
    assert counts.count1 == pytest.approx(40662.5)
    assert counts.count2 == pytest.approx(80990.0)
    assert sample.spread_mm() == (pytest.approx(1.5), pytest.approx(2.0))


# --- the file ---------------------------------------------------------------


def _saved(monkeypatch, tmp_path, **kwargs):
    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    corners = [(-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)]
    placement = _consistent_placement(corners, reads=3)
    manager = LighthouseManager(placements=[placement], **kwargs)
    manager.solve()
    return manager, manager.save_calibration(tag=kwargs.pop("tag", None))


def test_save_writes_schema_2_into_the_site_directory(monkeypatch, tmp_path):
    _, path = _saved(monkeypatch, tmp_path)

    assert path.parent == tmp_path / "calibrations" / "default"
    parsed = tomllib.loads(path.read_text())
    assert parsed["schema_version"] == 2
    assert parsed["site"]["name"] == "default"
    assert parsed["site"]["anchor"] == ""
    assert "frame" not in parsed
    assert "false_origin_mm" not in parsed["site"]
    assert parsed["validity"]["valid_mm"] == [0, 0, 4000, 4500]
    assert parsed["metadata"]["robot"] == "dotbot-v3"
    assert len(parsed["metadata"]["id"]) == 16
    assert path.name.endswith(f"-{parsed['metadata']['id'][:8]}.toml")
    assert len(parsed["placement"]) == 1
    assert len(parsed["placement"][0]["samples"]) == 4
    assert parsed["placement"][0]["samples"][0]["count1"] == pytest.approx(
        parsed["placement"][0]["samples"][0]["count1"]
    )
    assert len(parsed["station"]) == 1
    assert parsed["station"][0]["solved_from"] == "direct"
    assert "calibration_distance_mm" not in parsed["metadata"]
    assert "num_lh_stations" not in parsed["metadata"]
    assert "calibration" not in parsed


def test_save_writes_no_legacy_out_sidecar(monkeypatch, tmp_path):
    _saved(monkeypatch, tmp_path)
    assert not (tmp_path / "calibration.out").exists()
    assert list(tmp_path.rglob("*.out")) == []


def test_schema_2_round_trips_and_re_solves_to_the_same_matrices_and_id(
    monkeypatch, tmp_path
):
    manager, path = _saved(monkeypatch, tmp_path)
    loaded = read_calibration_file(path)

    assert loaded.stored_id == loaded.id
    assert loaded.placements[0].points_mm == manager.placements[0].points_mm

    re_solved = LighthouseManager(
        placements=loaded.placements, site=loaded.site, valid_mm=loaded.valid_mm
    )
    re_solved.solve()
    assert re_solved.stations[0].homography == loaded.stations[0].homography
    assert re_solved.stations[0].residual_mm == loaded.stations[0].residual_mm

    written_again = render_calibration(loaded)
    assert f'id = "{loaded.id}"' in written_again


def test_schema_1_file_is_rejected(tmp_path):
    path = tmp_path / "calibration-2026-01-01T00-00-00Z-deadbeef.toml"
    path.write_text(
        'schema_version = 1\n[calibration]\ndata_hex = "00"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="schema_version 1"):
        read_calibration_file(path)


def test_a_file_carrying_a_frame_table_is_rejected(tmp_path):
    path = tmp_path / "calibration-2026-01-01T00-00-00Z-deadbeef.toml"
    path.write_text(
        'schema_version = 2\n[frame]\nname = "inria-aio-c"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"\[frame\] is not a table"):
        read_calibration_file(path)


def test_calibration_id_ignores_the_descriptive_fields(monkeypatch, tmp_path):
    _, path = _saved(monkeypatch, tmp_path)
    original = read_calibration_file(path)
    before = original.id

    original.site.anchor = "somewhere else entirely, 2027"
    original.created_at = "2030-12-31T23:59:59Z"
    original.tag = "another-session"
    original.robot = "dotbot-v9"
    original.placements[0].at = "typed by hand"
    assert original.id == before


def test_calibration_id_moves_when_the_site_is_renamed(monkeypatch, tmp_path):
    _, path = _saved(monkeypatch, tmp_path)
    calibration = read_calibration_file(path)
    before = calibration.id

    calibration.site.name = "somewhere-else"
    assert calibration.id != before


def test_calibration_id_moves_when_a_reframe_shifts_the_points(monkeypatch, tmp_path):
    """Zero is the anchor, so a reframe shows up in `points_mm` alone."""
    _, path = _saved(monkeypatch, tmp_path)
    calibration = read_calibration_file(path)
    before = calibration.id

    calibration.placements[0].points_mm = [
        (x + 100.0, y) for x, y in calibration.placements[0].points_mm
    ]
    assert calibration.id != before


def test_calibration_id_moves_when_a_point_or_a_matrix_moves(monkeypatch, tmp_path):
    _, path = _saved(monkeypatch, tmp_path)

    calibration = read_calibration_file(path)
    before = calibration.id
    x, y = calibration.placements[0].points_mm[0]
    calibration.placements[0].points_mm[0] = (x + 1.0, y)
    assert calibration.id != before

    calibration = read_calibration_file(path)
    calibration.stations[0].homography[2][2] = 1.001
    assert calibration.id != before

    calibration = read_calibration_file(path)
    calibration.valid_mm = (0, 0, 5000, 5000)
    assert calibration.id != before


def test_resolve_by_id_prefix_under_the_site_directory(monkeypatch, tmp_path):
    _, path = _saved(monkeypatch, tmp_path)
    calibration = read_calibration_file(path)

    resolved = resolve_calibration_path(calibration.id8, root=tmp_path / "calibrations")
    assert resolved == path

    with pytest.raises(ValueError, match="no calibration matches"):
        resolve_calibration_path("ffffffff", root=tmp_path / "calibrations")


def test_an_id_prefix_resolves_only_under_the_named_site(monkeypatch, tmp_path):
    _, path = _saved(monkeypatch, tmp_path, site=Site(name="site-a"))
    root = tmp_path / "calibrations"
    prefix = path.name.split("-")[-1][:8]

    assert resolve_calibration_path(prefix, root, site="site-a") == path
    with pytest.raises(ValueError, match="no calibration matches"):
        resolve_calibration_path(prefix, root, site="site-b")


def test_resolve_prefers_an_actual_path(monkeypatch, tmp_path):
    _, path = _saved(monkeypatch, tmp_path)
    assert resolve_calibration_path(str(path)) == path


# --- points and areas ------------------------------------------------------


def _mm(spec, registry):
    return [point.mm for point in resolve_points(spec, registry)]


def test_arena_corner_marks_come_from_the_robot_geometry():
    """Every corner insets by the photodiode's distance to the PCB edges."""
    assert _mm("arena:corners", C405.registry()) == [
        (47.0, 18.5),
        (1953.0, 18.5),
        (47.0, 1981.5),
        (1953.0, 1981.5),
    ]


def test_a_taller_area_insets_both_ends_by_the_front_clearance():
    """Noses point outward, so the front edge rests on each y line."""
    assert _mm("arena+annex:corners", C405.registry()) == [
        (47.0, 18.5),
        (1953.0, 18.5),
        (47.0, 3981.5),
        (1953.0, 3981.5),
    ]


def test_corner_marks_follow_an_offset_rectangle():
    registry = AreaRegistry(named={"open": Area(500, 700, 1000, 1000, "open")})
    assert _mm("open:corners", registry) == [
        (547.0, 718.5),
        (1453.0, 718.5),
        (547.0, 1681.5),
        (1453.0, 1681.5),
    ]


def test_a_literal_rectangle_carries_the_corner_rule():
    """A taped square needs no config entry: x,y,w,h stands in for a name."""
    registry = C405.registry()
    assert _mm("750,750,500,500:corners", registry) == [
        (797.0, 768.5),
        (1203.0, 768.5),
        (797.0, 1231.5),
        (1203.0, 1231.5),
    ]
    assert _mm("750,750,500,500:bottom-right", registry) == [(1203.0, 1231.5)]
    assert _mm("750,750,500,500", registry) == [(1000.0, 1000.0)]


def test_points_forms():
    registry = C405.registry()
    assert _mm("1500,2500", registry) == [(1500.0, 2500.0)]
    assert _mm("arena", registry) == [(1000.0, 1000.0)]
    assert _mm("arena:top-right", registry) == [(1953.0, 18.5)]
    with pytest.raises(ValueError, match="unknown area"):
        resolve_points("nowhere", registry)
    with pytest.raises(ValueError, match="four are a rectangle"):
        resolve_points("1,2,3", registry)


def test_an_area_name_in_a_site_with_no_areas_says_so():
    """A fresh install ships no site, so the message has to name the fix."""
    with pytest.raises(ValueError, match=r"defines no areas"):
        resolve_points("arena:corners", Site().registry())
    assert resolve_points("1500,2500", Site().registry())[0].mm == (1500.0, 2500.0)


def test_area_resolution_forms():
    registry = C405.registry()
    assert registry.resolve("annex").as_dict() == {
        "x": 0,
        "y": 2000,
        "w": 2000,
        "h": 2000,
        "name": "annex",
    }
    assert registry.resolve("0,0,500,600").as_dict() == {
        "x": 0,
        "y": 0,
        "w": 500,
        "h": 600,
        "name": "0,0,500,600",
    }
    composite = registry.resolve("arena+wing")
    assert composite.as_dict() == {
        "x": 0,
        "y": 0,
        "w": 3330,
        "h": 4000,
        "name": "arena+wing",
    }


# --- what the operator reads ------------------------------------------------


def test_every_corner_describes_the_pose_before_the_coordinate():
    prompts = [
        point_prompt(i, 4, point)
        for i, point in enumerate(resolve_points("arena:corners", C405.registry()))
    ]
    assert prompts[0] == (
        "point 0 of 4, top-left corner of arena: robot inside the rectangle, "
        "left edge on the left line, front edge on the top line, nose toward "
        "the top. Photodiode lands at (47, 18.5) mm. Press Enter when it is "
        "still."
    )
    assert prompts[1] == (
        "point 1 of 4, top-right corner of arena: robot inside the rectangle, "
        "right edge on the right line, front edge on the top line, nose "
        "toward the top. Photodiode lands at (1953, 18.5) mm. Press Enter "
        "when it is still."
    )
    assert prompts[2] == (
        "point 2 of 4, bottom-left corner of arena: robot inside the "
        "rectangle, left edge on the left line, front edge on the bottom "
        "line, nose toward the bottom. Photodiode lands at (47, 1981.5) mm. "
        "Press Enter when it is still."
    )
    assert prompts[3] == (
        "point 3 of 4, bottom-right corner of arena: robot inside the "
        "rectangle, right edge on the right line, front edge on the bottom "
        "line, nose toward the bottom. Photodiode lands at (1953, 1981.5) "
        "mm. Press Enter when it is still."
    )


def test_a_typed_point_instructs_nothing_beyond_the_coordinate():
    point = resolve_points("1500,2500", C405.registry())[0]
    assert point.corner is None
    assert point.where == "" and point.how == ""
    assert point_prompt(2, 5, point) == (
        "point 2 of 5: photodiode on (1500, 2500) mm. Press Enter when it is " "still."
    )


def test_the_header_states_the_site_the_orientation_and_the_rule():
    header = collect_header(C405, "the config file", 4, 10)
    assert "site c405-arena (from the config file)" in header
    assert "x grows right, y grows down" in header
    assert f"zero is {C405.anchor}" in header
    assert "nose toward the nearest top or bottom edge" in header


def test_the_header_names_the_missing_anchor_key():
    header = collect_header(Site(), "the default", 4, 10)
    assert "add `anchor` to [sites.default]" in header


def test_the_package_default_site_names_no_lab():
    """A real site is measured: the package ships a name and nothing else."""
    site = Site()
    assert site.name == "default"
    assert site.anchor == ""
    assert site.extent_mm is None
    assert site.areas == {}
    assert site.valid_mm is None


def test_a_site_extent_is_the_plausibility_fence():
    assert C405.valid_mm == (0, 0, 2000, 4000)
    assert C405.extent.as_dict() == {
        "x": 0,
        "y": 0,
        "w": 2000,
        "h": 4000,
        "name": "c405-arena",
    }


def test_slug_tag_rules():
    assert lighthouse2._slug_tag("office-2x2m") == "office-2x2m"
    assert lighthouse2._slug_tag("  a  b  ") == "a-b"
    assert lighthouse2._slug_tag("a/b\\c:d") == "a-b-c-d"
    assert lighthouse2._slug_tag("--keep_me.v2--") == "keep_me.v2"
    assert lighthouse2._slug_tag("..") == ""
    assert lighthouse2._slug_tag("***") == ""


# The same schema 2 fixture swarmit's test_helpers.py carries, so the two
# packers cannot drift.
FIXTURE_TOML = """\
schema_version = 2

[metadata]
created_at = "2026-09-10T09:12:00Z"
id = "3f9a1c07e2b845d6"
robot = "dotbot-v3"

[site]
name = "inria-aio-c"
anchor = "the arena's top-left corner, against the door wall of C405"

[validity]
valid_mm = [0, 0, 4000, 4500]

[[placement]]
index = 0
at = "arena:corners"
points_mm = [[50.0, 20.0], [2000.0, 20.0], [50.0, 2000.0], [2000.0, 2000.0]]
captured_at = "2026-09-10T09:10:41Z"
samples = [
  { station = 0, point = 0, count1 = [41290], count2 = [51728] },
]

[[station]]
index = 0
solved_from = "direct"
points = 4
residual_mm = 0.0
homography = [[1523.4, -38.2, 1012.7], [41.9, 1531.8, 988.3], [0.2134, -0.0871, 1.0]]
"""


def _wire_fixture(tmp_path):
    from dotbot.tests.lh2_wire_fixture import FIXTURE_TOML as WIRE_TOML

    path = tmp_path / "calibration.toml"
    path.write_text(WIRE_TOML, encoding="utf-8")
    return read_calibration_file(path)


def test_the_calibration_messages_are_pinned(tmp_path):
    """The 84-byte messages, byte for byte; swarmit's packer pins the same."""
    from dotbot.calibration.lighthouse2 import calibration_messages
    from dotbot.tests.lh2_wire_fixture import FIXTURE_ID, MESSAGE_HEX

    calibration = _wire_fixture(tmp_path)
    assert calibration.id == FIXTURE_ID

    messages = calibration_messages(calibration)
    assert [m.hex() for m in messages] == MESSAGE_HEX
    assert all(len(m) == 84 for m in messages)


def test_a_message_carries_the_matrix_as_float32_and_the_site_fields(tmp_path):
    import struct

    from dotbot.calibration.lighthouse2 import calibration_messages

    calibration = _wire_fixture(tmp_path)
    message = calibration_messages(calibration)[1]
    count, index = struct.unpack_from("<II", message, 0)
    assert (count, index) == (2, 1)
    assert np.allclose(
        np.array(struct.unpack_from("<9f", message, 8)).reshape(3, 3),
        calibration.station(1).homography,
        rtol=1e-7,
    )
    assert struct.unpack_from("<4I", message, 44) == (0, 0, 3330, 4000)
    assert message[60:76] == b"c405-arena" + bytes(6)
    assert message[76:84] == bytes.fromhex("ac893d2d85e3068c")


def test_a_gap_in_the_station_numbering_is_refused(tmp_path):
    """The receiver trusts slots 0 to count - 1, so station 2 alone leaves slot 0 empty."""
    from dotbot.calibration.lighthouse2 import calibration_messages

    calibration = _wire_fixture(tmp_path)
    calibration.stations = [replace(calibration.stations[1], index=2)]
    calibration.stored_id = ""

    with pytest.raises(ValueError, match="numbered from zero without gaps"):
        calibration_messages(calibration)


def test_a_hand_edited_file_is_not_pushed_under_its_old_id(tmp_path):
    from dotbot.calibration.lighthouse2 import calibration_messages

    calibration = _wire_fixture(tmp_path)
    calibration.stations[0].homography[0][0] = 1600.0

    with pytest.raises(ValueError, match="does not match its content"):
        calibration_messages(calibration)


@pytest.mark.parametrize(
    "name",
    ["", "a-site-name-longer-than-16", "caf\u00e9"],
    ids=["empty", "long", "ascii"],
)
def test_a_site_name_a_robot_cannot_store_is_refused(name):
    from dotbot.calibration.lighthouse2 import site_name_as_bytes

    with pytest.raises(ValueError):
        site_name_as_bytes(name)


def test_a_sixteen_character_site_name_fills_the_field_without_a_nul():
    from dotbot.calibration.lighthouse2 import site_name_as_bytes

    assert site_name_as_bytes("demo-dcoss-2026x") == b"demo-dcoss-2026x"


def test_reframe_shifts_the_points_resolves_and_keeps_the_residual(tmp_path):
    """A shift moves no point relative to another, so the fit is as good as before."""
    from dotbot.calibration.lighthouse2 import (
        LighthouseManager,
        Placement,
        Sample,
        apply_homography,
        reframe_calibration,
    )

    pytest.importorskip("cv2")
    placement = _five_point_placement()
    manager = LighthouseManager(placements=[placement], site=Site(name="c405-arena"))
    manager.solve()
    source = manager.calibration()
    floor = Site(name="inria-aio-c", anchor="floor top-left", extent_mm=(12000, 20000))

    reframed = reframe_calibration(source, floor, (5000.0, 7000.0))

    assert reframed.site.name == "inria-aio-c"
    assert reframed.valid_mm == (0, 0, 12000, 20000)
    assert reframed.id != source.id
    for (x0, y0), (x1, y1) in zip(
        source.placements[0].points_mm, reframed.placements[0].points_mm
    ):
        assert (x1, y1) == pytest.approx((x0 + 5000.0, y0 + 7000.0))
    old, new = source.stations[0], reframed.stations[0]
    assert new.residual_mm == pytest.approx(old.residual_mm, abs=1e-6)
    # A camera point lands where it did, plus the shift, to the solver's
    # own numerical noise.
    camera = np.array([[0.1, -0.2]])
    assert apply_homography(new.matrix, camera)[0] == pytest.approx(
        apply_homography(old.matrix, camera)[0] + [5000.0, 7000.0], abs=1e-3
    )
    assert isinstance(reframed.placements[0], Placement)
    assert isinstance(reframed.placements[0].samples[0], Sample)
    # The source is left as it was.
    assert source.placements[0].points_mm[0] == placement.points_mm[0]


def test_reframe_with_a_rotation_turns_about_the_first_point(tmp_path):
    from dotbot.calibration.lighthouse2 import LighthouseManager, reframe_calibration

    pytest.importorskip("cv2")
    manager = LighthouseManager(
        placements=[_five_point_placement()], site=Site(name="c405-arena")
    )
    manager.solve()
    source = manager.calibration()

    reframed = reframe_calibration(
        source, Site(name="tilted", extent_mm=(9000, 9000)), (100.0, 200.0), 90.0
    )

    (px, py), (qx, qy) = source.placements[0].points_mm[:2]
    (rx, ry), (sx, sy) = reframed.placements[0].points_mm[:2]
    assert (rx, ry) == pytest.approx((px + 100.0, py + 200.0))
    # +90 degrees turns +x into +y.
    assert (sx - rx, sy - ry) == pytest.approx((-(qy - py), qx - px), abs=1e-9)
    assert reframed.stations[0].residual_mm == pytest.approx(
        source.stations[0].residual_mm, abs=1e-6
    )


def _five_point_placement():
    """Five points of one station, so the residual is not trivially zero."""
    from dotbot.calibration.lighthouse2 import (
        Placement,
        Sample,
        counts_for_camera_point,
    )

    matrix = np.array(
        [[1523.4, -38.2, 1012.7], [41.9, 1531.8, 988.3], [0.2134, -0.0871, 1.0]]
    )
    points = [
        (47.0, 18.5),
        (1953.0, 18.5),
        (47.0, 1981.5),
        (1953.0, 1981.5),
        (1000, 1000),
    ]
    samples = []
    for index, (x, y) in enumerate(points):
        camera = np.linalg.inv(matrix) @ np.array([x, y, 1.0])
        camera /= camera[2]
        counts = counts_for_camera_point(camera[0] + 0.002 * index, camera[1], 0)
        samples.append(Sample(0, index, [round(counts.count1)], [round(counts.count2)]))
    return Placement(index=0, points_mm=points, samples=samples)
