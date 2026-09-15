"""Tests for the camera sheets: the derived layout and the printed page.

The layout numbers are checked against `dev-corner`, the 1 x 1 m area the
camera plan works through, so a change to the page geometry or the corner
order shows up as a coordinate a human can compare with the plan. A sheet
is checked by decoding it back with the detector that will read it off the
floor, which is what catches a wrong id or a marker drawn at the wrong
scale.
"""

import cv2
import numpy as np
import pytest

from dotbot.area import Area
from dotbot.calibration.camera import (
    MARKER_DICTIONARY,
    MARKER_SIDE_MM,
    MARKER_SIDE_PX,
    PAGE_HEIGHT_PX,
    PAGE_WIDTH_PX,
    marker_layout,
    render_sheet,
    sheet_marker,
    span_mm,
)
from dotbot.calibration.points import CORNERS

# The camera plan's worked example: 1 x 1 m, its top-left corner one metre
# along the site's x axis.
DEV_CORNER = Area(1000, 0, 1000, 1000, "dev-corner")


def test_layout_places_one_sheet_in_each_corner():
    layout = marker_layout(DEV_CORNER)
    assert [marker.id for marker in layout] == [0, 1, 2, 3]
    assert [marker.corner for marker in layout] == list(CORNERS)
    assert [marker.centre_mm for marker in layout] == [
        (1105.0, 148.5),
        (1895.0, 148.5),
        (1105.0, 851.5),
        (1895.0, 851.5),
    ]


def test_layout_marker_corners_are_in_aruco_order():
    """Top-left, top-right, bottom-right, bottom-left around the centre."""
    top_left = marker_layout(DEV_CORNER)[0]
    assert top_left.corners_mm == (
        (1030.0, 73.5),
        (1180.0, 73.5),
        (1180.0, 223.5),
        (1030.0, 223.5),
    )


def test_layout_span_is_the_outer_marker_corners():
    span = span_mm(marker_layout(DEV_CORNER))
    assert span == [
        (1030.0, 73.5),
        (1970.0, 73.5),
        (1970.0, 926.5),
        (1030.0, 926.5),
    ]


def test_layout_follows_the_area_it_is_given():
    """Every sheet stays inside its own corner of a different rectangle."""
    layout = marker_layout(Area(0, 0, 3000, 2000, "arena"))
    assert [marker.centre_mm for marker in layout] == [
        (105.0, 148.5),
        (2895.0, 148.5),
        (105.0, 1851.5),
        (2895.0, 1851.5),
    ]


def test_layout_rejects_a_corner_that_is_not_one():
    with pytest.raises(ValueError, match="unknown corner"):
        sheet_marker(DEV_CORNER, "middle")


def test_layout_span_needs_all_four_sheets():
    with pytest.raises(ValueError, match="no sheet for"):
        span_mm(marker_layout(DEV_CORNER)[:3])


def test_sheet_rejects_an_id_that_names_no_corner():
    with pytest.raises(ValueError, match="unknown sheet id"):
        render_sheet(len(CORNERS))


def test_sheet_is_a4_at_300_dpi():
    page = render_sheet(0)
    assert page.shape == (PAGE_HEIGHT_PX, PAGE_WIDTH_PX) == (3508, 2480)
    assert MARKER_SIDE_PX == 1772  # 150 mm at 300 dpi


@pytest.mark.parametrize("marker_id", range(len(CORNERS)))
def test_sheet_decodes_to_its_own_id(marker_id):
    """One marker per page, its own id, printed at the declared size."""
    page = render_sheet(marker_id)
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, MARKER_DICTIONARY)),
        cv2.aruco.DetectorParameters(),
    )
    corners, ids, _ = detector.detectMarkers(page)

    assert ids is not None and ids.ravel().tolist() == [marker_id]
    found = corners[0].reshape(4, 2)
    width_px = np.linalg.norm(found[1] - found[0])
    assert width_px == pytest.approx(MARKER_SIDE_PX, abs=1.0)
    assert found.mean(axis=0) == pytest.approx(
        [PAGE_WIDTH_PX / 2, PAGE_HEIGHT_PX / 2], abs=1.0
    )


def test_sheet_millimetres_per_pixel_matches_the_layout():
    """The printed marker and the derived layout describe one object."""
    assert MARKER_SIDE_MM / MARKER_SIDE_PX == pytest.approx(25.4 / 300, abs=1e-4)
