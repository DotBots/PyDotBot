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

from dotbot.area import Area
from dotbot.detection import Detection, Pose, RobotDetector, frame_pose
from dotbot.detection import propose as proposer
from dotbot.detection import wrap180
from dotbot.detection.pose import (
    AXLE_BEHIND_CENTRE_MM,
    CONN_MM,
    NOSE_AHEAD_MM,
    OUTLINE_MM,
    PHOTODIODE_AHEAD_MM,
    axes,
    features,
    robot_mask,
)
from dotbot.detection.robot import GREEN_LEVER_MIN_MM, TMPL_MARGIN_MIN, classify
from dotbot.robots import robot_geometry

MM_PER_PX = 2.0
SUPERSAMPLE = 4

# One area of floor to place the raster in, so a frame millimetre is never
# the same number as a raster pixel and a missing origin shows up.
AREA = Area(1000, 0, 500, 500, "detection")

CARPET = (150, 150, 150)
BOARD = (60, 140, 40)
CONNECTOR = (40, 40, 200)
TYRE = (30, 30, 30)

# The tyres the estimator's own template carries.
TRACK_MM, TYRE_W_MM, TYRE_D_MM = 85.0, 18.0, 40.0

# The middle of the default raster, in raster pixels.
CENTRE_PX = (125.0, 125.0)


def tyre_polygons_mm():
    """The two tyres in the robot frame, as the template places them."""
    out = []
    axle = -AXLE_BEHIND_CENTRE_MM
    for side in (-1, 1):
        x0 = side * TRACK_MM / 2 - TYRE_W_MM / 2
        x1 = side * TRACK_MM / 2 + TYRE_W_MM / 2
        out.append(
            np.array(
                [
                    (x0, axle - TYRE_D_MM / 2),
                    (x1, axle - TYRE_D_MM / 2),
                    (x1, axle + TYRE_D_MM / 2),
                    (x0, axle + TYRE_D_MM / 2),
                ],
                float,
            )
        )
    return out


def carpet(width_px=250, height_px=250, seed=7):
    """Grey floor with the speckle a proposer has to average away."""
    rng = np.random.default_rng(seed)
    base = np.full((height_px, width_px, 3), CARPET, np.float32)
    return np.clip(base + rng.normal(0.0, 6.0, base.shape), 0, 255).astype(np.uint8)


def draw_robot(
    raster, centre_px, heading_atan2_deg, board=BOARD, connector=CONNECTOR, tyre=TYRE
):
    """One robot at `centre_px`, facing `heading_atan2_deg`.

    The heading is the detector's own convention: 0 along +x, +90 along +y.
    """
    height, width = raster.shape[:2]
    big = cv2.resize(
        raster,
        (width * SUPERSAMPLE, height * SUPERSAMPLE),
        interpolation=cv2.INTER_NEAREST,
    )
    right, forward = axes(heading_atan2_deg)

    def fill(polygon_mm, colour):
        points = np.array(
            [
                [
                    (
                        centre_px[i]
                        + (p[0] * right[i] + p[1] * forward[i]) / MM_PER_PX
                        + 0.5
                    )
                    * SUPERSAMPLE
                    for i in (0, 1)
                ]
                for p in polygon_mm
            ],
            np.float32,
        )
        cv2.fillPoly(big, [np.round(points).astype(np.int32)], colour)

    fill(OUTLINE_MM, board)
    for polygon in tyre_polygons_mm():
        fill(polygon, tyre)
    for polygon in CONN_MM:
        fill(polygon, connector)
    return cv2.resize(big, (width, height), interpolation=cv2.INTER_AREA)


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

    `heading_deg` is the robot `direction` convention: 0 along +y, growing
    clockwise. `heading_atan2_deg` is the detector's: 0 along +x.
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


def test_a_grey_board_is_refused_by_the_verifier():
    """A robot-sized grey object is proposed and then thrown out.

    Stage one is a matched filter on size, so it answers for anything the
    right size; a robot carries coloured parts and a floor does not, which
    is the only thing that separates the two.
    """
    grey = (110, 110, 110)
    raster = draw_robot(
        carpet(), CENTRE_PX, 37.0, board=grey, connector=(150, 150, 150)
    )
    candidates = proposer.detect(raster, None, MM_PER_PX)
    assert candidates, "stage one should still propose a robot-sized object"
    assert not any(c["robot"] for c in candidates)

    detection = RobotDetector(MM_PER_PX).detect(raster)
    assert detection.status == "none"
    assert detection.pose is None


@pytest.mark.parametrize(
    "green_lever_mm, tmpl_margin",
    [(GREEN_LEVER_MIN_MM - 3.0, 1.0), (30.0, TMPL_MARGIN_MIN - 0.2)],
)
def test_low_confidence_is_refused_not_hidden(green_lever_mm, tmpl_margin):
    """A pose that clears neither threshold is still reported, marked refused.

    The console draws it dashed rather than dropping it, so an operator
    sees the estimator hesitating instead of seeing nothing at all.
    """
    pose = Pose(
        centre_px=(10.0, 10.0),
        heading_atan2_deg=0.0,
        green_lever_mm=green_lever_mm,
        tmpl_margin=tmpl_margin,
        refined=True,
    )
    assert classify(pose) == "refused"


def test_a_confident_pose_is_found():
    pose = Pose(
        centre_px=(10.0, 10.0),
        heading_atan2_deg=0.0,
        green_lever_mm=GREEN_LEVER_MIN_MM,
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


def test_keep_mask_excludes_a_sheet_the_camera_can_see():
    """An ArUco sheet is a robot-sized high-contrast object; the mask hides it."""
    raster = carpet(300, 250)
    raster = rect_px(raster, 20, 40, 125, 188, (245, 245, 245))  # A4 at 2 mm/px
    raster = rect_px(raster, 55, 85, 90, 140, (15, 15, 15))  # its marker
    raster = draw_robot(raster, (220.0, 125.0), 37.0)

    masked = np.full(raster.shape[:2], 255, np.uint8)
    masked[40:188, 20:125] = 0

    unmasked = proposer.detect(raster, None, MM_PER_PX)
    assert len(unmasked) >= 2, "the sheet should be a candidate when nothing hides it"

    detection = RobotDetector(MM_PER_PX, masked).detect(raster)
    assert detection.status == "found"
    assert detection.candidates == 1
    pose = frame_pose(detection.pose, AREA, MM_PER_PX)
    assert np.allclose(pose["centre_mm"], truth_mm((220.0, 125.0)), atol=4.0)


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
    """`import dotbot.detection` must cost nothing without the extra."""
    code = (
        "import sys;"
        "sys.modules['cv2'] = None;"
        "import dotbot.detection, dotbot.camera;"
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
