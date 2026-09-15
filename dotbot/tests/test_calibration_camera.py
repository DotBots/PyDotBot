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
from dotbot.calibration import camera
from dotbot.calibration.camera import (
    MARKER_DICTIONARY,
    MARKER_SIDE_MM,
    MARKER_SIDE_PX,
    PAGE_HEIGHT_PX,
    PAGE_WIDTH_PX,
    _diagram_frame_px,
    _px,
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


def _diagram(page):
    """The bottom-margin region the placement diagram is drawn in."""
    left, top, right, bottom = _diagram_frame_px()
    return page[top : bottom + 1, left : right + 1]


@pytest.mark.parametrize("marker_id", range(len(CORNERS)))
def test_sheet_diagram_fills_the_seat_its_caption_names(marker_id):
    """The solid seat lands in the quadrant the printed corner name points at."""
    ink = _diagram(render_sheet(marker_id)) < 128
    height, width = ink.shape
    quadrants = {
        "top-left": ink[: height // 2, : width // 2],
        "top-right": ink[: height // 2, width // 2 :],
        "bottom-left": ink[height // 2 :, : width // 2],
        "bottom-right": ink[height // 2 :, width // 2 :],
    }
    counts = {name: int(area.sum()) for name, area in quadrants.items()}
    filled = max(counts, key=counts.get)

    assert filled == CORNERS[marker_id]
    assert counts[filled] > 2 * max(
        count for name, count in counts.items() if name != filled
    )


def test_sheet_diagram_differs_between_the_four_sheets():
    """A corner-indexing slip would leave two sheets pointing at one corner."""
    diagrams = [_diagram(render_sheet(marker_id)) for marker_id in range(len(CORNERS))]
    for first in range(len(CORNERS)):
        for second in range(first + 1, len(CORNERS)):
            assert not np.array_equal(diagrams[first], diagrams[second])


def _filled_seat_box(page):
    """The solid seat's bounds within the diagram, in pixels.

    Found by eroding, which eats the thin strokes and leaves only the one
    filled shape, so the measurement does not restate the drawing's own
    arithmetic.
    """
    left, top, right, bottom = _diagram_frame_px()
    diagram = page[top : bottom + 1, left : right + 1]
    solid = cv2.erode((diagram < 128).astype(np.uint8), np.ones((9, 9), np.uint8))
    rows, columns = np.nonzero(solid)
    return columns.min(), rows.min(), columns.max(), rows.max()


def test_sheet_diagram_is_square_and_its_seats_are_one_shape_moved():
    """Two spans rounded apart is exactly the near-square that ships unnoticed."""
    left, top, right, bottom = _diagram_frame_px()
    assert right - left == bottom - top

    pages = [render_sheet(marker_id) for marker_id in range(len(CORNERS))]
    assert len({int((_diagram(page) < 128).sum()) for page in pages}) == 1

    side = right - left
    boxes = [_filled_seat_box(page) for page in pages]
    assert len({(x1 - x0, y1 - y0) for x0, y0, x1, y1 in boxes}) == 1
    insets = {(min(x0, side - x1), min(y0, side - y1)) for x0, y0, x1, y1 in boxes}
    assert len(insets) == 1
    assert max(insets.pop()) <= 5  # flush to both edges, within the erosion


def test_sheet_keeps_a_marker_cell_of_white_below_the_marker():
    """The quiet zone the detector needs, which the diagram must not creep into."""
    cell_px = _px(MARKER_SIDE_MM / 6)  # a 4x4 marker is six cells across
    marker_bottom = (PAGE_HEIGHT_PX + MARKER_SIDE_PX) // 2
    for marker_id in range(len(CORNERS)):
        page = render_sheet(marker_id)
        assert (page[marker_bottom : marker_bottom + cell_px, :] == 255).all()
    assert _diagram_frame_px()[1] >= marker_bottom + cell_px


def test_sheet_diagram_clears_the_caption_beside_it():
    """A gutter of white between the longest caption and the diagram's frame."""
    left, top, _, bottom = _diagram_frame_px()
    for marker_id in range(len(CORNERS)):
        gutter = render_sheet(marker_id)[top:bottom, left - _px(4.0) : left - _px(1.0)]
        assert (gutter == 255).all()


def test_sheet_renders_without_any_of_the_candidate_fonts(monkeypatch):
    """The lab machine may carry none of them; a sheet still has to print."""
    monkeypatch.setattr(camera, "_FONT_CANDIDATES", ())
    camera._font_file.cache_clear()
    camera._font.cache_clear()
    try:
        page = render_sheet(0)
    finally:
        camera._font_file.cache_clear()
        camera._font.cache_clear()

    assert page.shape == (PAGE_HEIGHT_PX, PAGE_WIDTH_PX)
    caption = page[_px(250.0) : _px(270.0), _px(30.0) : _px(150.0)]
    assert (caption < 128).any()
