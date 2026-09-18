"""Tests for the camera robot detector.

The robot these tests draw is built from the estimator's own outline, so it
is model-consistent by construction: what they guard is the plumbing, the
unit and frame conventions and the two confidence thresholds. Accuracy
against a real photograph is not something a synthetic raster can show, and
is left to the bench.

Everything is drawn at 2.0 mm/px, which is the raster the controller warps a
camera into, and the polygons are filled at four times that and box-filtered
down so the edges carry the anti-aliasing a lens would give them.
"""

import subprocess
import sys

import cv2
import numpy as np
import pytest

from dotbot.camera.detection import Detection, Pose, RobotDetector, frame_pose
from dotbot.camera.detection import propose as proposer
from dotbot.camera.detection import wrap180
from dotbot.camera.detection.pose import (
    NOSE_AHEAD_MM,
    NOSE_BAND_MM,
    PHOTODIODE_AHEAD_MM,
    TAIL_HALF_MM,
    _nose_flare,
    axes,
    features,
    robot_mask,
)
from dotbot.camera.detection.robot import GREEN_FLARE_MIN, TMPL_MARGIN_MIN, classify
from dotbot.camera.sheets import MARKER_DICTIONARY
from dotbot.robots import robot_geometry
from dotbot.tests.camera_fixtures import DETECTION_AREA as AREA
from dotbot.tests.camera_fixtures import (
    MM_PER_PX,
    carpet,
    draw_robot,
)

# The middle of the default raster, in raster pixels.
CENTRE_PX = (125.0, 125.0)


def rect_px(raster, x0, y0, x1, y1, colour):
    """One axis-aligned rectangle of raster pixels, filled."""
    raster[int(y0) : int(y1), int(x0) : int(x1)] = colour
    return raster


def truth_mm(centre_px, area=AREA):
    """The frame millimetres a raster pixel centre stands at."""
    return (area.x + centre_px[0] * MM_PER_PX, area.y + centre_px[1] * MM_PER_PX)


# --- the pose it reports ----------------------------------------------------


@pytest.mark.parametrize("heading", [0.0, 90.0, -90.0, 180.0, 37.0, -123.0])
def test_finds_a_robot_and_reports_its_pose(heading):
    """One robot, any heading: found, and every derived point where it belongs."""
    raster = draw_robot(carpet(), CENTRE_PX, heading)
    detection = RobotDetector(MM_PER_PX).detect(raster)
    assert detection.status == "found"
    assert detection.candidates == 1

    pose = frame_pose(detection.pose, AREA, MM_PER_PX)
    expected = truth_mm(CENTRE_PX)
    assert np.allclose(pose["centre_mm"], expected, atol=3.0)
    assert abs(wrap180(pose["heading_atan2_deg"] - heading)) < 3.0

    right, forward = axes(pose["heading_atan2_deg"])
    centre = np.asarray(pose["centre_mm"])
    assert np.allclose(pose["photodiode_mm"], centre + forward * 29.0, atol=0.1)
    assert np.allclose(pose["nose_mm"], centre + forward * NOSE_AHEAD_MM, atol=0.1)

    # The outline is the board turned to the reported heading, so its reach
    # forward, backward and sideways is the board's own. A sign slip in the
    # rotation shows here as a reach on the wrong axis.
    outline = np.asarray(pose["outline_mm"])
    assert outline.shape == (14, 2)
    ahead = (outline - centre) @ forward
    across = (outline - centre) @ right
    assert ahead.max() == pytest.approx(NOSE_AHEAD_MM, abs=0.2)
    assert ahead.min() == pytest.approx(-NOSE_AHEAD_MM, abs=0.2)
    assert across.max() == pytest.approx(47.0, abs=0.2)
    assert across.min() == pytest.approx(-47.0, abs=0.2)


def test_direction_convention():
    """The heading the console draws is the detector's, turned by 90 degrees.

    `heading_deg` is the robot `direction` convention: 0 = +y, +90 = -x.
    `heading_atan2_deg` is the detector's: 0 = +x, +90 = +y.
    """
    for atan2_deg, direction_deg in ((0.0, -90.0), (90.0, 0.0), (180.0, 90.0)):
        raster = draw_robot(carpet(), CENTRE_PX, atan2_deg)
        detection = RobotDetector(MM_PER_PX).detect(raster)
        assert detection.status == "found"
        pose = frame_pose(detection.pose, AREA, MM_PER_PX)
        assert abs(wrap180(pose["heading_atan2_deg"] - atan2_deg)) < 3.0
        assert abs(wrap180(pose["heading_deg"] - direction_deg)) < 3.0


def test_wrap180_maps_into_the_half_open_turn():
    assert wrap180(-270) == 90
    assert wrap180(180) == 180
    assert wrap180(181) == -179
    assert wrap180(-180) == 180
    assert wrap180(0) == 0


def test_photodiode_offset_matches_the_robot_geometry():
    """The detector and the calibration point resolver share one photodiode.

    A drift between the two would put the camera 29 mm from the lighthouse
    on every comparison, rotating with the heading.
    """
    geometry = robot_geometry()
    ahead = geometry.board_length_mm / 2 - geometry.diode_to_front_mm
    assert PHOTODIODE_AHEAD_MM == ahead
    assert PHOTODIODE_AHEAD_MM == 29.0


# --- what it refuses --------------------------------------------------------


def test_empty_floor_is_none():
    detection = RobotDetector(MM_PER_PX).detect(carpet())
    assert detection.status == "none"
    assert detection.candidates == 0
    assert detection.pose is None


def test_a_grey_board_is_refused_for_carrying_no_colour():
    """A robot-sized grey object answers the matched filter and gets no further.

    Stage one is a filter on size, so it responds to anything the right
    size; a robot carries coloured parts and a floor does not, which is the
    only thing that separates the two. The colourless one is dropped at its
    peak, before anything is spent re-centring it.
    """
    grey = (110, 110, 110)
    raster = draw_robot(
        carpet(), CENTRE_PX, 37.0, board=grey, connector=(150, 150, 150)
    )

    # The filter does respond where the object is.
    scored, _, _, (sx, sy), _ = proposer.response(raster, None, MM_PER_PX)
    peak = np.unravel_index(scored.argmax(), scored.shape)
    assert scored[peak] > proposer.K_SIGMA
    assert abs(peak[1] * sx - CENTRE_PX[0]) < 20
    assert abs(peak[0] * sy - CENTRE_PX[1]) < 20

    # And it carries no colour, so it never becomes a candidate.
    half = int(0.6 * proposer.ROBOT_MM / MM_PER_PX)
    assert proposer._saturation(raster, CENTRE_PX, half) < proposer.PRE_SAT_MIN
    assert proposer.verify(raster, None, MM_PER_PX) == []

    detection = RobotDetector(MM_PER_PX).detect(raster)
    assert detection.status == "none"
    assert detection.pose is None


@pytest.mark.parametrize(
    "green_flare, tmpl_margin",
    [(GREEN_FLARE_MIN - 0.1, 1.0), (0.8, TMPL_MARGIN_MIN - 0.2)],
)
def test_low_confidence_is_refused_not_hidden(green_flare, tmpl_margin):
    """A pose that clears neither threshold is still reported, marked refused.

    The console draws it dashed rather than dropping it, so an operator
    sees the estimator hesitating instead of seeing nothing at all.
    """
    pose = Pose(
        centre_px=(10.0, 10.0),
        heading_atan2_deg=0.0,
        green_flare=green_flare,
        tmpl_margin=tmpl_margin,
        refined=True,
    )
    assert classify(pose) == "refused"


def test_a_confident_pose_is_found():
    pose = Pose(
        centre_px=(10.0, 10.0),
        heading_atan2_deg=0.0,
        green_flare=GREEN_FLARE_MIN,
        tmpl_margin=TMPL_MARGIN_MIN,
        refined=True,
    )
    assert classify(pose) == "found"


def test_jpeg_round_trip_does_not_fill_the_mask():
    """The robot mask stays a robot after a JPEG round trip.

    Chroma subsampling shrinks the floor's own measured spread, and a scale
    estimate with no floor under it turns the whole frame into evidence.
    """
    raster = draw_robot(carpet(), CENTRE_PX, 37.0)
    ok, buffer = cv2.imencode(".jpg", raster, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    assert ok
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    assert robot_mask(features(decoded)).mean() < 0.2


# --- the keep mask ----------------------------------------------------------


def test_the_pre_gate_window_covers_the_refinement_it_gates():
    """The peak's own error sets the pre-gate window, not the verdict's crop.

    `_refine` exists because a matched-filter peak locates an object without
    centring on it, and the pre-gate is what decides whether it runs at all.
    A window narrower than refinement's reach asks about a point the peak has
    not earned, and drops robots whose peak landed beside them.
    """
    assert proposer.PRE_CROP_FRAC >= proposer.SAT_CROP_FRAC + proposer.REFINE_FRAC


def test_the_pre_gate_asks_the_same_absolute_colour_as_the_verdict():
    """A threshold on a fraction only holds still if it falls with the area."""
    narrow = proposer.SAT_CROP_FRAC**2 * (proposer.SAT_MIN / 4)
    wide = proposer.PRE_CROP_FRAC**2 * proposer.PRE_SAT_MIN
    assert wide == pytest.approx(narrow)


def test_a_registration_sheet_is_dropped_without_being_masked():
    """A printed page under neutral light needs no hole cut in the floor.

    Cutting the pages out of the keep mask would blind a robot's width of
    floor around each of them, since a candidate needs its whole footprint
    on known floor. Under light the white balance matches, a page carries no
    saturated colour and the colour check is enough on its own. Off neutral
    it is not, which the test below covers.
    """
    raster = carpet(300, 250)
    raster = rect_px(raster, 20, 40, 125, 188, (245, 245, 245))  # A4 at 2 mm/px
    raster = rect_px(raster, 55, 85, 90, 140, (15, 15, 15))  # its marker
    raster = draw_robot(raster, (220.0, 125.0), 37.0)

    half = int(proposer.PRE_CROP_FRAC * proposer.ROBOT_MM / MM_PER_PX)
    assert proposer._saturation(raster, (72.0, 114.0), half) < proposer.PRE_SAT_MIN

    candidates = proposer.verify(raster, None, MM_PER_PX)
    assert [c["robot"] for c in candidates].count(True) == 1
    assert not any(c["robot"] and c["centre"][0] < 140 for c in candidates)

    detection = RobotDetector(MM_PER_PX).detect(raster)
    assert detection.status == "found"
    assert detection.candidates == 1
    pose = frame_pose(detection.pose, AREA, MM_PER_PX)
    assert np.allclose(pose["centre_mm"], truth_mm((220.0, 125.0)), atol=4.0)


def test_a_sheet_off_neutral_is_taken_out_by_the_marker_printed_on_it():
    """White paper is only colourless under light the white balance matches.

    Off neutral the page carries saturation of its own, the colour check
    stops separating it from a robot, and the sheet is proposed and fitted.
    It costs more than a phantom row: the sheet's candidate can win, and the
    detection is refused rather than reported. What takes the page back out
    is the marker that made it a sheet, decoded on the same frame.
    """
    raster = carpet(300, 250)
    raster = rect_px(raster, 20, 40, 140, 200, (245, 245, 245))  # the page
    marker = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, MARKER_DICTIONARY)),
        0,
        75,
    )
    raster[95:170, 45:120] = np.repeat(marker[:, :, None], 3, axis=2)
    raster = draw_robot(raster, (220.0, 125.0), 37.0)
    # The blue cast a warm white balance gives a lit floor.
    raster = np.clip(
        raster.astype(np.float32) * np.array([1.35, 1.0, 0.62]), 0, 255
    ).astype(np.uint8)

    half = int(0.6 * proposer.ROBOT_MM / MM_PER_PX)
    assert proposer._saturation(raster, (80.0, 120.0), half) > proposer.SAT_MIN

    loose = RobotDetector(MM_PER_PX, exclude_sheets=False).detect(raster)
    assert loose.candidates == 2
    assert loose.status == "refused"

    detector = RobotDetector(MM_PER_PX)
    assert len(detector.sheet_quads(raster)) == 1
    detection = detector.detect(raster)
    assert detection.status == "found"
    assert detection.candidates == 1


def test_a_lifted_sheet_gives_its_floor_straight_back():
    """Nothing is remembered from the registration, so nothing stays blind.

    The pages are found frame by frame, which is what lets a robot stand
    where a sheet used to be as soon as it is picked up.
    """
    raster = draw_robot(carpet(300, 250), (72.0, 114.0), 37.0)

    detector = RobotDetector(MM_PER_PX)
    assert detector.sheet_quads(raster) == []
    detection = detector.detect(raster)
    assert detection.status == "found"
    pose = frame_pose(detection.pose, AREA, MM_PER_PX)
    assert np.allclose(pose["centre_mm"], truth_mm((72.0, 114.0)), atol=4.0)


def test_keep_mask_excludes_the_border_the_warp_had_no_source_for():
    """A robot is still found beside a third of the raster with no source."""
    raster = carpet(300, 250)
    raster[:, 200:] = 0
    raster = draw_robot(raster, (100.0, 125.0), -123.0)

    masked = np.full(raster.shape[:2], 255, np.uint8)
    masked[:, 200:] = 0

    detection = RobotDetector(MM_PER_PX, masked).detect(raster)
    assert detection.status == "found"
    pose = frame_pose(detection.pose, AREA, MM_PER_PX)
    assert np.allclose(pose["centre_mm"], truth_mm((100.0, 125.0)), atol=4.0)


# --- the module's own constraints -------------------------------------------


def test_importing_the_detector_does_not_need_opencv():
    """`import dotbot.camera.detection` must cost nothing without the extra."""
    code = (
        "import sys;"
        "sys.modules['cv2'] = None;"
        "import dotbot.camera, dotbot.camera.detection, dotbot.camera.service;"
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_detector_does_not_drag_in_the_controller():
    """It is tuned by running it on saved photographs with no controller."""
    code = (
        "import sys;"
        "sys.modules['cv2'] = None;"
        "import dotbot.camera.detection;"
        "held = {'dotbot.controller', 'dotbot.camera.service', 'dotbot.server'};"
        "assert not held & set(sys.modules), sorted(held & set(sys.modules));"
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_a_detection_carries_its_own_cost():
    """What one frame cost, so a bench machine reports its own budget."""
    raster = draw_robot(carpet(), CENTRE_PX, 37.0)
    detection = RobotDetector(MM_PER_PX).detect(raster)
    assert isinstance(detection, Detection)
    assert detection.elapsed_ms > 0
    print(f"detection on a 250 x 250 raster: {detection.elapsed_ms} ms")


def test_the_template_margin_measures_the_nose_against_its_flip():
    """The margin is the one thing the template says, and which way round.

    Inverting the two scores would refuse every correct pose and accept
    every backwards one, and the drawn outline would be 180 degrees out with
    nothing else looking wrong.
    """
    from dotbot.camera.detection.pose import (
        Template,
        coarse_pose,
        features,
        robot_mask,
        template_search,
    )

    raster = draw_robot(carpet(), CENTRE_PX, 37.0)
    detection = RobotDetector(MM_PER_PX).detect(raster)
    assert detection.status == "found"
    assert detection.pose.tmpl_margin > 0

    features_map = features(raster)
    region = robot_mask(features_map) > 0
    coarse = coarse_pose(features_map, region, MM_PER_PX)
    ahead = coarse["heading"]
    _, scores = template_search(
        features_map,
        coarse["coarse_centre"],
        Template(MM_PER_PX),
        [ahead, ahead + 180.0],
    )
    assert scores[float(ahead)] > scores[float(ahead + 180.0)]
    assert detection.pose.tmpl_margin == pytest.approx(
        scores[float(ahead)] - scores[float(ahead + 180.0)], abs=0.05
    )


def test_a_lower_scoring_heading_understates_the_margin():
    """A coarse heading off the true best can only make the gate stricter.

    The margin is scored at the coarse heading, not at the best one, so it
    is bounded above by what a search would have found. The gate therefore
    fails closed when the coarse pose is a few degrees out.
    """
    from dotbot.camera.detection.pose import (
        Template,
        coarse_pose,
        features,
        robot_mask,
        template_search,
    )

    raster = draw_robot(carpet(), CENTRE_PX, 37.0)
    features_map = features(raster)
    region = robot_mask(features_map) > 0
    coarse = coarse_pose(features_map, region, MM_PER_PX)
    centre, ahead = coarse["coarse_centre"], coarse["heading"]
    template = Template(MM_PER_PX)

    _, scores = template_search(features_map, centre, template, [ahead, ahead + 180.0])
    reported = scores[float(ahead)] - scores[float(ahead + 180.0)]

    swept = np.arange(ahead - 10.0, ahead + 10.01, 2.0)
    best, _ = template_search(features_map, centre, template, swept)
    assert reported <= best[0] - scores[float(ahead + 180.0)] + 1e-9


def test_the_nose_band_only_counts_what_the_tail_cannot_reach():
    """The band has to sit outside the tail and inside the nose.

    Below the tail's half-width it counts mass both ends carry and stops
    separating them; above the nose's it counts nothing at all.
    """
    assert TAIL_HALF_MM == 28.5
    assert TAIL_HALF_MM < NOSE_BAND_MM < 47.0


def test_the_nose_signal_ignores_a_translated_green_mass():
    """Displacing the whole mass must not move the signal at all.

    It is measured about the mass's own centroid, so the shift moves the mass
    and the point it is measured about together.
    """
    points = np.array(
        [(x, y) for x in np.arange(-47, 47.5, 1.0) for y in np.arange(-47, 48.5, 1.0)]
    )
    keep = np.abs(points[:, 0]) <= np.where(points[:, 1] > 1.5, 47.0, 28.5)
    gx, gy = points[keep, 0], points[keep, 1]
    gw = np.ones(len(gx))
    forward = np.array([0.0, 1.0])
    centre = np.array([gx.mean(), gy.mean()])
    here = _nose_flare(gx, gy, gw, centre, forward, 1.0)
    moved = _nose_flare(
        gx + 13.0, gy - 8.0, gw, centre + np.array([13.0, -8.0]), forward, 1.0
    )
    assert here > 0.7
    assert moved == pytest.approx(here)
    assert _nose_flare(gx, gy, gw, centre, -forward, 1.0) == pytest.approx(-here)


def test_the_nose_signal_holds_when_the_board_is_displaced():
    """A board displaced in the FRAME, not the robot, must not sway the gate.

    The green mass and the axle are different colours in different places, so
    anything displacing one against the other adds a fixed frame vector to
    the distance between them. That reads as a cosine in the body heading and
    sinks a whole heading band below the floor; the flare is built not to see
    it.
    """
    flares = []
    for heading in range(0, 360, 30):
        raster = draw_robot(
            carpet(), CENTRE_PX, float(heading), board_offset_mm=(24.0, 0.0)
        )
        detection = RobotDetector(MM_PER_PX).detect(raster)
        assert detection.pose is not None
        flares.append(detection.pose.green_flare)
    # The lever this replaced swings 25 mm under the same displacement and
    # dips under its own 8 mm floor; the flare keeps several times its margin.
    assert min(flares) > 3 * GREEN_FLARE_MIN
