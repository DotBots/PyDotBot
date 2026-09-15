"""Tests for the camera sheets: the derived layout and the printed page.

The layout numbers are checked against `dev-corner`, the 1 x 1 m area the
camera plan works through, so a change to the page geometry or the corner
order shows up as a coordinate a human can compare with the plan. A sheet
is checked by decoding it back with the detector that will read it off the
floor, which is what catches a wrong id or a marker drawn at the wrong
scale. The PDF is checked the same way, on pages read back out of the
written file rather than on the arrays that went in.
"""

import io
import re

import cv2
import numpy as np
import pytest
from PIL import Image

from dotbot.area import Area
from dotbot.calibration import camera
from dotbot.calibration.camera import (
    MARKER_DICTIONARY,
    MARKER_SIDE_MM,
    MARKER_SIDE_PX,
    MM_PER_INCH,
    PAGE_HEIGHT_MM,
    PAGE_HEIGHT_PX,
    PAGE_WIDTH_MM,
    PAGE_WIDTH_PX,
    SHEET_DPI,
    _diagram_frame_px,
    _px,
    marker_layout,
    render_sheet,
    render_sheets,
    sheet_marker,
    span_mm,
    write_sheets,
)
from dotbot.calibration.points import CORNERS

# The camera plan's worked example: 1 x 1 m, its top-left corner one metre
# along the site's x axis.
DEV_CORNER = Area(1000, 0, 1000, 1000, "dev-corner")

POINTS_PER_INCH = 72.0

# A4 to well inside a printer's own placement tolerance. The page is a
# whole number of pixels, so its size in points is 2480 and 3508 rounded
# pixels back at `SHEET_DPI` rather than A4 to the micron.
PAGE_TOLERANCE_MM = 0.05


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
    with pytest.raises(ValueError, match="names no area corner"):
        render_sheet(len(CORNERS))


def test_sheet_is_a4_at_300_dpi():
    page = render_sheet(0)
    assert page.shape == (PAGE_HEIGHT_PX, PAGE_WIDTH_PX) == (3508, 2480)
    assert MARKER_SIDE_PX == 1772  # 150 mm at 300 dpi


def _detector():
    """The detector that will read these markers off the floor."""
    return cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, MARKER_DICTIONARY)),
        cv2.aruco.DetectorParameters(),
    )


@pytest.mark.parametrize("marker_id", range(len(CORNERS)))
def test_sheet_decodes_to_its_own_id(marker_id):
    """One marker per page, its own id, printed at the declared size."""
    page = render_sheet(marker_id)
    corners, ids, _ = _detector().detectMarkers(page)

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


def _pdf_pages(path):
    """A written PDF read back as its page sizes in mm and one image per page.

    Pillow stores a page as a single full-page image, so lifting that
    stream out is the nearest thing to rendering the file, and the page
    size comes from the file's own `/MediaBox` rather than from the density
    it was written at. Pages come back in the order the catalogue lists.
    """
    raw = path.read_bytes()
    starts = {}
    for match in re.finditer(rb"\n(\d+) 0 obj<<", raw):
        starts.setdefault(int(match[1]), match.end())
    kids = re.search(rb"/Kids \[([^\]]*)\]", raw)[1]

    sizes, pages = [], []
    for number in (int(ref) for ref in re.findall(rb"(\d+) 0 R", kids)):
        page = raw[starts[number] : raw.index(b">>endobj", starts[number])]
        box = re.search(rb"/MediaBox \[([^\]]*)\]", page)[1].split()
        sizes.append(tuple(float(v) * MM_PER_INCH / POINTS_PER_INCH for v in box[2:]))

        image = starts[int(re.search(rb"/image (\d+) 0 R", page)[1])]
        stream = raw.index(b">>stream\n", image) + len(b">>stream\n")
        length = int(re.search(rb"/Length (\d+)", raw[image:stream])[1])
        with Image.open(io.BytesIO(raw[stream : stream + length])) as rendered:
            pages.append(np.array(rendered.convert("L")))
    return sizes, pages


def test_sheets_pdf_is_one_a4_page_per_corner(tmp_path):
    """One file is one print job, and every page states A4 in points."""
    written = write_sheets(render_sheets(), tmp_path)
    assert [path.name for path in written] == ["camera-markers.pdf"]

    sizes, pages = _pdf_pages(written[0])
    assert len(pages) == len(CORNERS)
    for width_mm, height_mm in sizes:
        assert width_mm == pytest.approx(PAGE_WIDTH_MM, abs=PAGE_TOLERANCE_MM)
        assert height_mm == pytest.approx(PAGE_HEIGHT_MM, abs=PAGE_TOLERANCE_MM)


def test_sheets_pdf_pages_carry_their_own_marker_at_its_printed_size(tmp_path):
    """Measured against the size the file declares, which is what prints."""
    sizes, pages = _pdf_pages(write_sheets(render_sheets(), tmp_path)[0])
    detector = _detector()

    for marker_id, (page, (width_mm, _)) in enumerate(zip(pages, sizes)):
        corners, ids, _ = detector.detectMarkers(page)
        assert ids is not None and ids.ravel().tolist() == [marker_id]
        found = corners[0].reshape(4, 2)
        mm_per_px = width_mm / page.shape[1]
        assert np.linalg.norm(found[1] - found[0]) * mm_per_px == pytest.approx(
            MARKER_SIDE_MM, abs=0.1
        )


def test_sheets_png_writes_one_image_per_corner(tmp_path):
    """The image path stays, and each file carries the density in its header."""
    written = write_sheets(render_sheets(), tmp_path, "png")
    assert [path.name for path in written] == [
        f"camera-marker-{marker_id}.png" for marker_id in range(len(CORNERS))
    ]

    for marker_id, path in enumerate(written):
        with Image.open(path) as image:
            assert image.size == (PAGE_WIDTH_PX, PAGE_HEIGHT_PX)
            assert image.info["dpi"] == pytest.approx((SHEET_DPI, SHEET_DPI), abs=0.01)
            page = np.array(image.convert("L"))
        _, ids, _ = _detector().detectMarkers(page)
        assert ids is not None and ids.ravel().tolist() == [marker_id]


def test_write_sheets_rejects_a_format_it_cannot_write(tmp_path):
    with pytest.raises(ValueError, match="unknown sheet format"):
        write_sheets([], tmp_path, "svg")
