"""What the camera tests draw, and the captures they read it back through.

Three test modules share this: the sheet renderer's, the registration's and
the detector's. Everything here is synthetic, so no test opens a device -
index 0 on the bench machine is a real camera.

Two frames are drawn. `synthetic_frame` is the four ArUco sheets of an area
seen through a plausible overhead homography, in grayscale, which is what a
registration is solved on. `synthetic_colour_frame` adds robots drawn from
the estimator's own outline, which is what the detector is run on. Both are
drawn at a multiple and box-filtered down, so edges carry the anti-aliasing
a lens would give them.
"""

import cv2
import numpy as np
import pytest

from dotbot.area import Area
from dotbot.camera.detection.pose import (
    CONN_MM,
    OUTLINE_MM,
    WHEELS_MM,
    axes,
)
from dotbot.camera.sheets import MARKER_DICTIONARY, MARKER_SIDE_MM
from dotbot.site import Site

# The camera plan's worked example: 1 x 1 m, its top-left corner one metre
# along the site's x axis.
DEV_CORNER = Area(1000, 0, 1000, 1000, "dev-corner")

# A smaller area for the detector's own raster, so a frame millimetre is
# never the same number as a raster pixel and a missing origin shows up.
DETECTION_AREA = Area(1000, 0, 500, 500, "detection")

SITE = Site(name="c405-arena", anchor="the arena's top-left corner")

FRAME_WIDTH, FRAME_HEIGHT = 1920, 1080

# The raster the controller warps a camera into.
MM_PER_PX = 2.0

# Drawn at this multiple and box-filtered down. The sheets need 3x: drawn at
# 1x the same fit lands an order of magnitude worse.
SHEET_SUPERSAMPLE = 3
ROBOT_SUPERSAMPLE = 4
COLOUR_SUPERSAMPLE = 2

CARPET_BGR = (150, 150, 150)
BOARD_BGR = (60, 140, 40)
CONNECTOR_BGR = (40, 40, 200)
TYRE_BGR = (30, 30, 30)


# --- The sheets, through a plausible overhead view ---------------------------


def ground_truth_mm_to_px() -> np.ndarray:
    """About one pixel per millimetre, plus a projective term.

    The area lands near the middle of the frame and the projective term is
    what makes the fit recover a homography rather than an affine.
    """
    return np.array(
        [
            [1.0, 0.0, -1000.0 + 460.0],
            [0.0, 1.0, 40.0],
            [2.0e-5, 1.2e-5, 1.0],
        ]
    )


def ground_truth_px_to_mm() -> np.ndarray:
    """The same view inverted, normalised so the bottom-right term is one."""
    matrix = np.linalg.inv(ground_truth_mm_to_px())
    return matrix / matrix[2, 2]


def project(matrix: np.ndarray, points) -> np.ndarray:
    """`points` through a homography, as plain (x, y) pairs."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homogeneous = np.hstack([points, np.ones((len(points), 1))])
    out = (np.asarray(matrix) @ homogeneous.T).T
    return out[:, :2] / out[:, 2:3]


def synthetic_frame(area: Area = DEV_CORNER, displace=None) -> np.ndarray:
    """The four sheets of `area` seen through the ground-truth homography.

    `displace` shifts one marker by a millimetre offset before it is drawn,
    which is how a sheet taped somewhere other than the corner it names is
    put in front of the solver.
    """
    from dotbot.camera.sheets import marker_layout

    mm_to_px = ground_truth_mm_to_px()
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, MARKER_DICTIONARY)
    )
    canvas = np.full(
        (FRAME_HEIGHT * SHEET_SUPERSAMPLE, FRAME_WIDTH * SHEET_SUPERSAMPLE),
        235,
        np.uint8,
    )
    for marker in marker_layout(area):
        draw_marker(
            canvas,
            dictionary,
            marker.id,
            marker.centre_mm,
            mm_to_px,
            (displace or {}).get(marker.id, (0.0, 0.0)),
        )
    return cv2.resize(canvas, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)


def draw_marker(
    canvas,
    dictionary,
    marker_id,
    centre_mm,
    mm_to_px,
    offset,
    supersample=SHEET_SUPERSAMPLE,
):
    """One marker warped onto the supersampled canvas, with its quiet zone.

    Both coordinate conventions matter to a tenth of a millimetre: a source
    pixel covers [i - 0.5, i + 0.5], and `INTER_AREA` maps a supersampled
    coordinate P to (P + 0.5) / n - 0.5. Getting either wrong biases every
    corner the same way, which reads as a scale error in the fit rather than
    as noise.
    """
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 600)
    marker = cv2.copyMakeBorder(
        marker, 100, 100, 100, 100, cv2.BORDER_CONSTANT, value=255
    )
    side = marker.shape[0]
    half_mm = (MARKER_SIDE_MM / 2) * (side / 600.0)
    x = centre_mm[0] + offset[0]
    y = centre_mm[1] + offset[1]
    quad_mm = [
        (x - half_mm, y - half_mm),
        (x + half_mm, y - half_mm),
        (x + half_mm, y + half_mm),
        (x - half_mm, y + half_mm),
    ]
    quad_px = project(mm_to_px, quad_mm) * supersample + (supersample - 1) / 2.0
    transform = cv2.getPerspectiveTransform(
        np.array(
            [
                [-0.5, -0.5],
                [side - 0.5, -0.5],
                [side - 0.5, side - 0.5],
                [-0.5, side - 0.5],
            ],
            np.float32,
        ),
        quad_px.astype(np.float32),
    )
    cv2.warpPerspective(
        marker,
        transform,
        (canvas.shape[1], canvas.shape[0]),
        canvas,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_TRANSPARENT,
    )


# --- The robot, drawn from the estimator's own outline -----------------------


def carpet(width_px=250, height_px=250, seed=7):
    """Grey floor with the speckle a proposer has to average away."""
    rng = np.random.default_rng(seed)
    base = np.full((height_px, width_px, 3), CARPET_BGR, np.float32)
    return np.clip(base + rng.normal(0.0, 6.0, base.shape), 0, 255).astype(np.uint8)


def draw_robot(
    raster,
    centre_px,
    heading_atan2_deg,
    board=BOARD_BGR,
    connector=CONNECTOR_BGR,
    tyre=TYRE_BGR,
    board_offset_mm=(0.0, 0.0),
):
    """One robot at `centre_px`, facing `heading_atan2_deg`.

    The heading is the detector's own convention: 0 = +x, +90 = +y.
    `board_offset_mm` displaces the green board alone, in frame millimetres
    rather than the robot's own frame, which is how anything that moves the
    board against the parts it is measured from shows up.
    """
    height, width = raster.shape[:2]
    big = cv2.resize(
        raster,
        (width * ROBOT_SUPERSAMPLE, height * ROBOT_SUPERSAMPLE),
        interpolation=cv2.INTER_NEAREST,
    )
    right, forward = axes(heading_atan2_deg)

    def fill(polygon_mm, colour, offset_mm=(0.0, 0.0)):
        points = np.array(
            [
                [
                    (
                        centre_px[i]
                        + (p[0] * right[i] + p[1] * forward[i] + offset_mm[i])
                        / MM_PER_PX
                        + 0.5
                    )
                    * ROBOT_SUPERSAMPLE
                    for i in (0, 1)
                ]
                for p in polygon_mm
            ],
            np.float32,
        )
        cv2.fillPoly(big, [np.round(points).astype(np.int32)], colour)

    fill(OUTLINE_MM, board, board_offset_mm)
    for polygon in WHEELS_MM:
        fill(polygon, tyre)
    for polygon in CONN_MM:
        fill(polygon, connector)
    return cv2.resize(big, (width, height), interpolation=cv2.INTER_AREA)


def synthetic_colour_frame(area=DEV_CORNER, robots=(), seed=11):
    """The area's sheets and `robots` through the fixture's own homography.

    Each robot is `(centre_mm, heading_atan2_deg)` in frame millimetres and
    the detector's heading convention: 0 = +x, +90 = +y.
    """
    from dotbot.camera.sheets import marker_layout

    scale = COLOUR_SUPERSAMPLE
    mm_to_px = ground_truth_mm_to_px()
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, MARKER_DICTIONARY)
    )
    big = np.full((FRAME_HEIGHT * scale, FRAME_WIDTH * scale, 3), CARPET_BGR, np.uint8)

    # Each sheet is drawn on its own grey plane and then painted in where it
    # landed, so the marker's white border reaches the colour canvas as the
    # page rather than as a transparent nothing.
    for marker in marker_layout(area):
        plane = np.zeros(big.shape[:2], np.uint8)
        draw_marker(
            plane, dictionary, marker.id, marker.centre_mm, mm_to_px, (0.0, 0.0), scale
        )
        painted = plane > 0
        big[painted] = np.repeat(plane[painted][:, None], 3, axis=1)

    for centre_mm, heading in robots:
        right, forward = axes(heading)

        def fill(polygon_mm, colour, centre=centre_mm, r=right, f=forward):
            points_mm = [
                (
                    centre[0] + p[0] * r[0] + p[1] * f[0],
                    centre[1] + p[0] * r[1] + p[1] * f[1],
                )
                for p in polygon_mm
            ]
            q = project(mm_to_px, points_mm) * scale + (scale - 1) / 2.0
            cv2.fillPoly(big, [np.round(q).astype(np.int32)], colour)

        fill(OUTLINE_MM, BOARD_BGR)
        for tyre in WHEELS_MM:
            fill(tyre, TYRE_BGR)
        for connector in CONN_MM:
            fill(connector, CONNECTOR_BGR)

    frame = cv2.resize(big, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
    rng = np.random.default_rng(seed)
    noisy = frame.astype(np.float32) + rng.normal(0.0, 4.0, frame.shape)
    return np.clip(noisy, 0, 255).astype(np.uint8)


# --- Captures, so no test opens a device -------------------------------------


class ScriptedCapture:
    """A `cv2.VideoCapture` stand-in whose `read()` returns a planned list."""

    def __init__(self, frames, backend="SCRIPTED", fps=30.0, opens=True):
        self.frames = list(frames)
        self.backend = backend
        self.fps = fps
        self.opens = opens
        self.released = False
        self.controls_set = {}

    def isOpened(self):  # noqa: N802 - the cv2 spelling
        return self.opens

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def get(self, prop):
        # A real device answers negative for a control it does not carry,
        # which is what keeps a scripted source out of a registration.
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        return self.controls_set.get(prop, -1.0)

    def set(self, prop, value):
        self.controls_set[prop] = value
        return True

    def getBackendName(self):  # noqa: N802 - the cv2 spelling
        return self.backend

    def release(self):
        self.released = True


class LoopingCapture(ScriptedCapture):
    """A capture delivering one frame for as long as it is read.

    A scripted list runs out in microseconds, which is one warp; a camera
    that keeps delivering is what a test about rates needs.
    """

    def __init__(self, frame, fps=0.0, interval=0.01):
        super().__init__([], fps=fps)
        self._frame = frame
        self._interval = interval

    def read(self):
        import time

        time.sleep(self._interval)
        return True, self._frame


def delivering(*frames, **mode):
    """An `open_source` handing back one scripted capture of `frames`."""
    return lambda source: ScriptedCapture(list(frames), **mode)


def looping(frame, **mode):
    """An `open_source` handing back a capture that never runs out."""
    return lambda source: LoopingCapture(frame, **mode)


def wait_for_detection(service, timeout=10.0):
    """The service's first detection record, or None if it never produced one."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = service.held_detection()
        if record is not None:
            return record
        time.sleep(0.02)
    return None


# --- Registrations -----------------------------------------------------------


def registration_for(frame, area=DEV_CORNER, source="synthetic-colour"):
    """A registration solved on `frame`, the way the fixture solves one."""
    from dotbot.camera.capture import build_detector, detect_markers
    from dotbot.camera.registration import CameraCalibration, MarkerObservation, solve
    from dotbot.camera.sheets import marker_layout, span_mm

    layout = marker_layout(area)
    corners = detect_markers(frame, build_detector())
    solution = solve(layout, corners)
    height, width = frame.shape[:2]
    return CameraCalibration(
        site=SITE,
        area=area.name,
        source=source,
        width=width,
        height=height,
        fps=0.0,
        markers=[
            MarkerObservation(
                id=marker.id,
                centre_mm=marker.centre_mm,
                corners_mm=marker.corners_mm,
                corners_px=tuple(tuple(p) for p in corners[marker.id]),
            )
            for marker in layout
            if marker.id in corners
        ],
        matrix=solution.matrix,
        residual_mm=solution.residual_mm,
        span_mm=span_mm(layout),
        created="2026-09-15T13:42:00Z",
    )


@pytest.fixture(scope="module")
def synthetic_camera(tmp_path_factory):
    """The synthetic sheet frame, registered, with its PNG as the source.

    Rendering and solving happen once per module: the frame is written to
    disk and every camera test reads it back through `--camera <path>`.
    """
    from dotbot.camera.capture import build_detector, detect_markers, probe
    from dotbot.camera.registration import build_calibration, solve
    from dotbot.camera.sheets import marker_layout

    frame = synthetic_frame(DEV_CORNER)
    path = tmp_path_factory.mktemp("camera") / "synthetic.png"
    cv2.imwrite(str(path), frame)

    layout = marker_layout(DEV_CORNER)
    corners = detect_markers(frame, build_detector())
    return build_calibration(
        site=SITE,
        area=DEV_CORNER,
        layout=layout,
        corners_px=corners,
        solution=solve(layout, corners),
        probe_result=probe(str(path)),
        reads=1,
        created="2026-09-15T13:42:00Z",
    )
