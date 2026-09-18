"""Tests for `collect`: finding the camera, reading the sheets, solving.

The fixture the whole file turns on is a synthetic 1920 x 1080 frame with
the four `dev-corner` sheets rendered into it through a known homography.
It is what lets the geometry be checked to a tenth of a millimetre with no
camera in the room, and what every later phase reads back, so the render
itself is checked first: a frame whose markers are a fraction of a pixel
out would quietly loosen every tolerance below it.

The probe and the choice run against a scripted capture whose `read()`
returns a planned sequence, handed in on the `open_source` seam. Those
exercise the choice rules, never a device.

Both the frame and the capture come from `camera_fixtures`, which the sheet
and detector tests share.
"""

import cv2
import numpy as np
import pytest

from dotbot.area import Area
from dotbot.calibration.lighthouse2 import read_calibration_file
from dotbot.calibration.points import CORNERS
from dotbot.camera import registration
from dotbot.camera.capture import (
    DARK_MEAN_MAX,
    FLAT_SPREAD_MAX,
    LIT_MEAN_MIN,
    Probe,
    average_corners,
    build_detector,
    capture_reads,
    choose,
    detect_markers,
    discover,
    parse_source,
    probe,
)
from dotbot.camera.registration import (
    CAMERA_KIND,
    CAMERA_SCHEMA_VERSION,
    LENS_DEFAULT,
    RESIDUAL_WARN_MM,
    build_calibration,
    load_camera_calibration,
    read_camera_calibration_file,
    render_camera_calibration,
    solve,
    write_camera_calibration,
)
from dotbot.camera.sheets import (
    MARKER_DICTIONARY,
    corner_of,
    layout_ids,
    marker_id_for,
    marker_layout,
    span_mm,
)
from dotbot.site import Site
from dotbot.tests.camera_fixtures import (
    DEV_CORNER,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    SITE,
    ScriptedCapture,
    draw_marker,
    ground_truth_mm_to_px,
    project,
    synthetic_frame,
)

# The plan's gates for the synthetic check: a residual under 0.3 mm and the
# area's own corners recovered within 0.5 mm of the truth.
RESIDUAL_MAX_MM = 0.3
AREA_CORNER_MAX_MM = 0.5


@pytest.fixture(scope="module")
def frame():
    return synthetic_frame()


@pytest.fixture(scope="module")
def frame_path(tmp_path_factory, frame):
    """The synthetic frame on disk, which `--camera <path>` opens directly."""
    path = tmp_path_factory.mktemp("camera") / "synthetic.png"
    cv2.imwrite(str(path), frame)
    return path


def test_the_synthetic_frame_carries_the_four_sheets(frame):
    """The fixture every tolerance below rests on, checked before it is used."""
    assert frame.shape == (FRAME_HEIGHT, FRAME_WIDTH)
    found = detect_markers(frame, build_detector())
    assert sorted(found) == list(layout_ids())

    mm_to_px = ground_truth_mm_to_px()
    for marker in marker_layout(DEV_CORNER):
        truth = project(mm_to_px, marker.corners_mm)
        assert found[marker.id] == pytest.approx(truth, abs=0.5)


# --- The solve --------------------------------------------------------------


def test_a_rendered_frame_solves_back_to_the_homography_it_was_drawn_with(frame):
    """The plan's own check: the geometry, end to end, with no camera."""
    layout = marker_layout(DEV_CORNER)
    found = detect_markers(frame, build_detector())
    solution = solve(layout, found)

    assert solution.residual_mm < RESIDUAL_MAX_MM

    truth = [
        (DEV_CORNER.x, DEV_CORNER.y),
        (DEV_CORNER.x_max, DEV_CORNER.y),
        (DEV_CORNER.x_max, DEV_CORNER.y_max),
        (DEV_CORNER.x, DEV_CORNER.y_max),
    ]
    corners_px = project(ground_truth_mm_to_px(), truth)
    recovered = project(np.array(solution.matrix), corners_px)
    assert recovered == pytest.approx(np.array(truth), abs=AREA_CORNER_MAX_MM)


def test_the_solve_reports_a_residual_per_marker(frame):
    """Sixteen corners over eight unknowns, so every sheet has its own error."""
    solution = solve(marker_layout(DEV_CORNER), detect_markers(frame, build_detector()))
    assert sorted(solution.per_marker_mm) == list(layout_ids())
    worst_id, worst_mm = solution.worst
    assert worst_mm == max(solution.per_marker_mm.values())
    assert worst_id in layout_ids()


def test_a_sheet_taped_outside_the_area_is_named_rather_than_averaged_away():
    """The failure that would otherwise be a confident wrong answer.

    A sheet 300 mm out still detects cleanly and still solves; what stops it
    passing for a registration is that the fit gets worse and says which
    sheet did it.
    """
    displaced = synthetic_frame(displace={3: (300.0, 120.0)})
    solution = solve(
        marker_layout(DEV_CORNER), detect_markers(displaced, build_detector())
    )

    assert solution.residual_mm > RESIDUAL_WARN_MM
    worst_id, worst_mm = solution.worst
    assert worst_id == 3
    assert worst_mm > RESIDUAL_WARN_MM
    assert corner_of(worst_id) == "bottom-right"


def test_the_solve_refuses_a_layout_it_has_no_pixels_for(frame):
    """Three sheets is not a fit with one missing: it is not a fit."""
    found = detect_markers(frame, build_detector())
    found.pop(2)
    with pytest.raises(ValueError, match="marker 2 \\(bottom-left\\) was never read"):
        solve(marker_layout(DEV_CORNER), found)


# --- The id-to-corner seam --------------------------------------------------


def test_the_seam_refuses_an_id_that_names_no_corner():
    with pytest.raises(ValueError, match="names no area corner"):
        corner_of(len(CORNERS))
    with pytest.raises(ValueError, match="unknown corner"):
        marker_id_for("middle")


# --- Scripted captures: the probe, the warm-up and the choice ---------------


def black():
    return np.zeros((FRAME_HEIGHT, FRAME_WIDTH), np.uint8)


def dark():
    return np.full((FRAME_HEIGHT, FRAME_WIDTH), int(DARK_MEAN_MAX) - 4, np.uint8)


def flat():
    """Lit but structureless: a blank wall, or a ceiling."""
    return np.full((FRAME_HEIGHT, FRAME_WIDTH), 140, np.uint8)


def scene():
    """Lit and structured, with no markers: the carpet before the sheets."""
    generator = np.random.default_rng(7)
    return generator.integers(40, 220, (FRAME_HEIGHT, FRAME_WIDTH), dtype=np.uint8)


def sources(mapping):
    """An `open_source` over a dict of source to frames, or None for closed."""

    def open_source(source):
        frames = mapping.get(source)
        if frames is None:
            return ScriptedCapture([], opens=False)
        return ScriptedCapture(frames)

    return open_source


def test_the_probe_discards_the_warm_up_frames(frame):
    """Black first, live second, which is what two of three cameras do."""
    found = probe(0, sources({0: [black(), black(), frame]}))

    assert found.opened
    assert found.discarded == 2
    assert found.marker_ids == layout_ids()
    assert found.width == FRAME_WIDTH and found.height == FRAME_HEIGHT
    assert found.fps == 30.0
    assert found.backend == "SCRIPTED"


def test_a_source_that_never_lights_keeps_its_last_frame(frame):
    """Black throughout still gets a row and a probe frame, not silence."""
    found = probe(0, sources({0: [black(), black()]}))

    assert found.opened
    assert found.frame is not None
    assert found.mean < LIT_MEAN_MIN
    assert found.dark
    assert found.marker_ids == ()


def test_a_source_that_opens_and_yields_nothing_is_reported_as_such():
    found = probe(3, sources({3: []}))

    assert found.opened and found.frame is None
    assert "no frames" in found.row


def test_a_source_that_does_not_open_is_reported_as_such():
    found = probe(9, sources({}))

    assert not found.opened
    assert "did not open" in found.row


def test_discovery_stops_after_two_indices_in_a_row_fail_to_open(frame):
    probes = discover(sources({0: [frame], 1: [scene()]}))

    assert [p.source for p in probes] == [0, 1, 2, 3]
    assert [p.opened for p in probes] == [True, True, False, False]


def test_the_source_that_sees_the_sheets_is_chosen(frame):
    """A dark one, a flat one and the synthetic frame: markers decide."""
    probes = discover(sources({0: [dark()], 1: [flat()], 2: [frame]}))
    choice = choose(probes, layout_ids())

    assert choice.chosen and choice.probe.source == 2
    assert "sees sheets 0 1 2 3: chosen" in choice.reason


def test_a_subset_of_the_sheets_is_named_and_accepted():
    """The reads are what settle whether it was the warm-up or the placement."""
    three = synthetic_frame(Area(1000, 0, 1000, 1000, "dev-corner"))
    three[:] = np.where(
        _mask_of_marker(three, 2), 235, three
    )  # paint out the bottom-left sheet
    probes = [probe(0, sources({0: [three]}))]
    choice = choose(probes, layout_ids())

    assert choice.chosen
    assert "missing 2" in choice.reason


def _mask_of_marker(image, marker_id):
    """A box over one marker, used to paint a sheet out of a rendered frame."""
    found = detect_markers(image, build_detector())
    quad = found[marker_id]
    mask = np.zeros(image.shape[:2], bool)
    x0, y0 = np.floor(quad.min(axis=0)).astype(int) - 40
    x1, y1 = np.ceil(quad.max(axis=0)).astype(int) + 40
    mask[max(y0, 0) : y1, max(x0, 0) : x1] = True
    return mask


def test_two_sources_seeing_markers_refuse_to_choose(frame):
    """Two cameras over one set of sheets: only the operator knows which."""
    probes = discover(sources({0: [frame], 1: [frame.copy()]}))
    choice = choose(probes, layout_ids())

    assert not choice.chosen
    assert "sources 0, 1 all see markers" in choice.reason


def test_one_lit_scene_is_chosen_when_nothing_sees_markers():
    """The case before any sheet exists: a carpet under the right camera."""
    probes = discover(sources({0: [dark()], 1: [scene()], 2: [flat()]}))
    choice = choose(probes, layout_ids())

    assert choice.chosen and choice.probe.source == 1
    assert "no markers; the one lit scene" in choice.reason


def test_two_lit_scenes_refuse_to_choose():
    probes = discover(sources({0: [scene()], 1: [scene()]}))
    choice = choose(probes, layout_ids())

    assert not choice.chosen
    assert "sources 0, 1 all show a lit scene" in choice.reason


def test_no_lit_scene_names_what_opened():
    probes = discover(sources({0: [dark()], 1: [flat()]}))
    choice = choose(probes, layout_ids())

    assert not choice.chosen
    assert "no source shows a lit scene (opened: 0, 1)" in choice.reason


def test_a_flat_frame_is_not_a_scene():
    """A blank wall is lit; the spread is what says nothing is in front of it."""
    found = probe(0, sources({0: [flat()]}))
    assert found.mean > DARK_MEAN_MAX
    assert found.spread < FLAT_SPREAD_MAX
    assert not found.scene


# --- The reads --------------------------------------------------------------


def test_a_black_read_is_counted_apart_from_a_read_with_no_markers(frame):
    """`23 of 25 reads (black 2)` rather than a count that hides the cause."""
    capture = ScriptedCapture([black(), black()] + [frame] * 25)
    kept, tally, last = capture_reads(capture, layout_ids(), 25, build_detector())

    assert tally.discarded == 2
    assert tally.complete == 25 and len(kept) == 25
    assert tally.black == 0
    assert tally.summary == "4 markers in 25 of 25 reads"
    assert last is not None


def test_a_black_frame_mid_run_is_counted_as_black(frame):
    capture = ScriptedCapture([frame] + [black()] * 2 + [frame] * 23)
    _, tally, _ = capture_reads(capture, layout_ids(), 25, build_detector())

    assert tally.black == 2
    assert tally.complete == 23
    assert tally.summary == "4 markers in 23 of 25 reads (black 2)"


def test_a_frame_with_only_three_markers_leaves_nothing_to_average():
    """Named by the missing id, rather than fitted over what was there."""
    three = synthetic_frame()
    three[_mask_of_marker(three, 1)] = 235
    capture = ScriptedCapture([three] * 5)
    kept, tally, _ = capture_reads(capture, layout_ids(), 5, build_detector())

    assert kept == []
    assert tally.complete == 0
    assert tally.short == 5
    assert tally.missing == (1,)
    with pytest.raises(ValueError, match="nothing to average"):
        average_corners(kept, layout_ids())


def test_a_read_with_a_duplicate_id_is_dropped_rather_than_arbitrated(frame):
    """Two candidates decoding to one id: nothing in the image says which."""
    doubled = _paste_second_copy(frame, marker_id=0)
    capture = ScriptedCapture([doubled] * 4)
    kept, tally, _ = capture_reads(capture, layout_ids(), 4, build_detector())

    assert kept == []
    assert tally.duplicated == 4
    assert "duplicate ids 4" in tally.summary


def _paste_second_copy(frame, marker_id):
    """A second print of one marker, somewhere else in the same frame."""
    found = detect_markers(frame, build_detector())
    quad = found[marker_id].astype(int)
    x0, y0 = quad.min(axis=0) - 30
    x1, y1 = quad.max(axis=0) + 30
    patch = frame[y0:y1, x0:x1]
    doubled = frame.copy()
    height, width = patch.shape
    doubled[FRAME_HEIGHT - height - 10 : FRAME_HEIGHT - 10, 10 : 10 + width] = patch
    return doubled


def test_a_marker_outside_this_layout_is_reported_and_left_out(frame):
    """A stray print, or another area's sheets under a widened seam."""
    stray = frame.copy()
    draw_marker(
        stray,
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, MARKER_DICTIONARY)),
        7,
        (1500.0, 500.0),
        ground_truth_mm_to_px(),
        (0.0, 0.0),
        supersample=1,
    )
    capture = ScriptedCapture([stray] * 3)
    kept, tally, _ = capture_reads(capture, layout_ids(), 3, build_detector())

    assert tally.extra == (7,)
    assert tally.complete == 3
    assert all(sorted(read) == list(layout_ids()) for read in kept)


def test_the_reads_average_the_corners_they_kept(frame):
    capture = ScriptedCapture([frame] * 4)
    kept, _, _ = capture_reads(capture, layout_ids(), 4, build_detector())
    averaged = average_corners(kept, layout_ids())

    assert sorted(averaged) == list(layout_ids())
    for marker_id, quad in averaged.items():
        assert quad.shape == (4, 2)
        assert quad == pytest.approx(kept[0][marker_id])


def test_a_source_that_stops_delivering_is_counted_not_hidden(frame):
    """One recorded frame against `--reads 5`: four reads had no frame."""
    capture = ScriptedCapture([frame])
    kept, tally, _ = capture_reads(capture, layout_ids(), 5, build_detector())

    assert tally.complete == 1
    assert tally.stopped == 4
    assert "no frame 4" in tally.summary
    assert len(kept) == 1


# --- The file ---------------------------------------------------------------


def a_calibration(frame, reads=25):
    layout = marker_layout(DEV_CORNER)
    found = detect_markers(frame, build_detector())
    return build_calibration(
        site=SITE,
        area=DEV_CORNER,
        layout=layout,
        corners_px=found,
        solution=solve(layout, found),
        probe_result=Probe(
            source=0,
            opened=True,
            backend="AVFOUNDATION",
            width=FRAME_WIDTH,
            height=FRAME_HEIGHT,
            fps=30.0,
        ),
        reads=reads,
        created="2026-09-15T13:42:00Z",
    )


def test_the_file_round_trips_through_the_writer_and_the_reader(frame, tmp_path):
    written = a_calibration(frame)
    path = write_camera_calibration(written, root=tmp_path)
    back = read_camera_calibration_file(path)

    assert path.name == f"camera-2026-09-15T13-42-00Z-{written.id8}.toml"
    assert path.parent.name == "c405-arena"
    assert back.id == written.id
    assert back.area == "dev-corner"
    assert back.source == 0
    assert (back.width, back.height, back.fps) == (FRAME_WIDTH, FRAME_HEIGHT, 30.0)
    assert back.lens == LENS_DEFAULT
    assert back.reads == 25
    assert back.site.name == SITE.name and back.site.anchor == SITE.anchor
    assert [m.id for m in back.markers] == list(layout_ids())
    assert back.span_mm == span_mm(marker_layout(DEV_CORNER))
    assert np.array(back.matrix) == pytest.approx(np.array(written.matrix))
    assert back.residual_mm == pytest.approx(written.residual_mm)


def test_the_file_records_a_path_source_as_a_string(frame, tmp_path):
    written = a_calibration(frame)
    written.source = "/dev/v4l/by-id/usb-camera"
    back = read_camera_calibration_file(
        write_camera_calibration(written, root=tmp_path)
    )
    assert back.source == "/dev/v4l/by-id/usb-camera"


def test_the_id_is_unchanged_by_a_rewrite(frame, tmp_path):
    """Provenance moves without moving the identity."""
    written = a_calibration(frame)
    before = written.id

    written.created = "2026-09-16T09:00:00Z"
    written.lens = "wide"
    written.source = 3
    written.reads = 40
    written.site.anchor = "a sentence nobody reads back"
    assert written.id == before

    rewritten = read_camera_calibration_file(
        write_camera_calibration(written, root=tmp_path)
    )
    assert rewritten.id == before


def test_the_file_records_the_cameras_colour_controls(frame, tmp_path):
    """Nothing else records the light the colour check was measured under."""
    written = a_calibration(frame)
    written.controls = {"auto_wb": 0.0, "wb_temperature": 4780.0}
    back = read_camera_calibration_file(
        write_camera_calibration(written, root=tmp_path)
    )
    assert back.controls == {"auto_wb": 0.0, "wb_temperature": 4780.0}


def test_a_registration_written_without_controls_still_reads(frame, tmp_path):
    """A file from before the controls were recorded stays readable."""
    written = a_calibration(frame)
    assert written.controls == {}
    path = write_camera_calibration(written, root=tmp_path)
    assert "[camera.controls]" not in path.read_text(encoding="utf-8")
    assert read_camera_calibration_file(path).controls == {}


def test_the_controls_do_not_change_the_id(frame):
    """The light a camera was registered under cannot move its homography."""
    written = a_calibration(frame)
    before = written.id
    written.controls = {"auto_wb": 0.0, "wb_temperature": 4780.0}
    assert written.id == before


def test_a_white_balance_that_walked_away_is_named():
    """A camera back on automatic drifts far from what was recorded."""
    from dotbot.camera.capture import control_drift

    recorded = {"auto_wb": 0.0, "wb_temperature": 4780.0}
    drift = control_drift({"auto_wb": 1.0, "wb_temperature": 6500.0}, recorded)

    assert drift["auto_wb"] == (1.0, 0.0)
    assert drift["wb_temperature"] == (6500.0, 4780.0)
    # A driver quantises a temperature to its own step, which is not drift.
    assert control_drift({"auto_wb": 0.0, "wb_temperature": 4800.0}, recorded) == {}


def test_exposure_is_compared_only_when_it_was_a_setting():
    """Under an automatic mode the exposure is an outcome, not a setting.

    Holding a camera to an exposure its own driver is choosing would warn on
    every change of light in the room.
    """
    from dotbot.camera.capture import comparable_controls, control_drift

    auto = {"auto_wb": 0.0, "auto_exposure": 3.0, "exposure": 83.0, "gain": 241.0}
    manual = dict(auto, auto_exposure=1.0)

    assert "exposure" not in comparable_controls(auto)
    assert "exposure" in comparable_controls(manual)
    assert control_drift(dict(auto, exposure=300.0), auto) == {}
    assert control_drift(dict(manual, exposure=300.0), manual)["exposure"] == (
        300.0,
        83.0,
    )


def test_a_source_reporting_no_controls_records_none(frame):
    """A device answers negative for a control it does not carry."""
    found = probe(0, sources({0: [frame]}))
    assert found.controls == {}


def test_the_id_changes_when_one_pixel_corner_does(frame):
    written = a_calibration(frame)
    before = written.id
    first = written.markers[0]
    moved = list(first.corners_px)
    moved[0] = (moved[0][0] + 0.5, moved[0][1])
    written.markers[0] = type(first)(
        id=first.id,
        centre_mm=first.centre_mm,
        corners_mm=first.corners_mm,
        corners_px=tuple(moved),
    )
    assert written.id != before


def test_the_id_changes_when_the_area_does(frame):
    written = a_calibration(frame)
    before = written.id
    written.area = "annex"
    assert written.id != before


def test_the_written_file_declares_its_kind_and_schema(frame):
    text = render_camera_calibration(a_calibration(frame))
    assert f"schema_version = {CAMERA_SCHEMA_VERSION}" in text
    assert f'kind = "{CAMERA_KIND}"' in text
    assert 'area = "dev-corner"' in text


def test_the_loader_takes_a_path_or_an_id_prefix(frame, tmp_path):
    written = a_calibration(frame)
    path = write_camera_calibration(written, root=tmp_path)

    assert load_camera_calibration(str(path)).id == written.id
    assert (
        load_camera_calibration(written.id8, root=tmp_path, site=SITE.name).id
        == written.id
    )


def test_an_id_prefix_that_matches_nothing_says_where_it_looked(tmp_path):
    with pytest.raises(ValueError, match="no camera calibration matches"):
        load_camera_calibration("deadbeef", root=tmp_path, site=SITE.name)


def test_the_two_loaders_refuse_each_other(frame, tmp_path, monkeypatch):
    """Two kinds in one directory, and neither can be read as the other."""
    camera_path = write_camera_calibration(a_calibration(frame), root=tmp_path)
    with pytest.raises(ValueError, match="unsupported calibration schema_version 1"):
        read_calibration_file(camera_path)

    lighthouse_path = camera_path.parent / "calibration-2026-09-15T13-42-00Z-abc.toml"
    lighthouse_path.write_text(
        'schema_version = 2\n\n[metadata]\nid = "abcdef0123456789"\n\n'
        '[site]\nname = "c405-arena"\nanchor = ""\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not a camera calibration"):
        read_camera_calibration_file(lighthouse_path)

    # An id prefix cannot cross between them: the globs are disjoint.
    with pytest.raises(ValueError, match="no camera calibration matches"):
        load_camera_calibration("abcdef", root=tmp_path, site=SITE.name)


# --- The source spec --------------------------------------------------------


def test_a_camera_spec_is_an_index_or_a_path():
    assert parse_source("0") == 0
    assert parse_source(" 2 ") == 2
    assert parse_source("/tmp/synthetic.png") == "/tmp/synthetic.png"
    assert parse_source("/dev/video0") == "/dev/video0"


def test_a_recorded_frame_opens_as_a_source(frame_path):
    """What makes every phase after this one rehearsable off the bench."""
    found = probe(str(frame_path))
    assert found.opened
    assert found.marker_ids == layout_ids()
    assert (found.width, found.height) == (FRAME_WIDTH, FRAME_HEIGHT)


# --- The command ------------------------------------------------------------


def run_collect(tmp_path, monkeypatch, args, areas=None):
    """`collect` driven the way the operator drives it, off a recorded frame."""
    from click.testing import CliRunner

    from dotbot.cli import camera_calibrate

    site = Site(
        name=SITE.name,
        anchor=SITE.anchor,
        areas=areas if areas is not None else {"dev-corner": DEV_CORNER},
    )
    monkeypatch.setattr(
        camera_calibrate, "site_from_context", lambda ctx, flag=None: (site, "the test")
    )
    monkeypatch.setattr(registration, "site_dir", lambda name: tmp_path / name)
    return CliRunner().invoke(camera_calibrate.collect, args, input="\n")


def test_collect_registers_a_camera_from_a_recorded_frame(
    tmp_path, monkeypatch, frame_path
):
    """The whole command, with the synthetic frame standing in for the camera."""
    result = run_collect(
        tmp_path,
        monkeypatch,
        ["--camera", str(frame_path), "--area", "dev-corner", "--reads", "1"],
    )

    assert result.exit_code == 0, result.output
    assert "sheet 0 inside the top-left corner of dev-corner" in result.output
    assert "4 markers in 1 of 1 reads" in result.output
    assert "sees sheets 0 1 2 3: chosen" in result.output

    written = sorted((tmp_path / SITE.name).glob("camera-*.toml"))
    assert len(written) == 1
    assert written[0].with_suffix(".jpg").is_file()

    calibration = read_camera_calibration_file(written[0])
    assert calibration.area == "dev-corner"
    assert calibration.source == str(frame_path)
    assert calibration.reads == 1
    assert calibration.residual_mm < RESIDUAL_MAX_MM
    assert calibration.id8 in written[0].name


def test_collect_writes_nothing_when_a_sheet_is_missing(tmp_path, monkeypatch):
    """Named by the id that was never seen, and no file to mistake for one."""
    three = synthetic_frame()
    three[_mask_of_marker(three, 1)] = 235
    path = tmp_path / "three.png"
    cv2.imwrite(str(path), three)

    result = run_collect(
        tmp_path,
        monkeypatch,
        ["--camera", str(path), "--area", "dev-corner", "--reads", "1"],
    )

    assert result.exit_code == 1
    assert "never saw 1" in result.output
    assert not list((tmp_path / SITE.name).glob("camera-*.toml"))


def test_collect_names_the_sheet_that_does_not_fit(tmp_path, monkeypatch):
    """A registration that would otherwise be a confident wrong answer."""
    path = tmp_path / "displaced.png"
    cv2.imwrite(str(path), synthetic_frame(displace={3: (300.0, 120.0)}))

    result = run_collect(
        tmp_path,
        monkeypatch,
        ["--camera", str(path), "--area", "dev-corner", "--reads", "1"],
    )

    assert result.exit_code == 0
    assert "this registration is suspect" in result.output
    assert "Marker 3 sits" in result.output
    assert "bottom-right corner puts it" in result.output


def test_collect_refuses_an_area_the_site_does_not_define(tmp_path, monkeypatch):
    result = run_collect(
        tmp_path, monkeypatch, ["--area", "nowhere"], areas={"arena": DEV_CORNER}
    )

    assert result.exit_code != 0
    assert "unknown area 'nowhere'" in result.output
    assert "defines: arena" in result.output


def test_collect_needs_an_area_to_derive_the_sheets_from(tmp_path, monkeypatch):
    """The bare group invokes collect with no flags, so the ask has to be said."""
    result = run_collect(tmp_path, monkeypatch, [])
    assert result.exit_code != 0
    assert "--area" in result.output
