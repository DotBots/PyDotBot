# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""What the site editor can draw under a site, read-only: where each of the
site's LH2 calibrations was fitted, and each registered camera's still
warped into the frame.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from dotbot.area import Area
from dotbot.calibration.lighthouse2 import (
    CALIBRATION_TOML_GLOB,
    check_calibration_site,
    read_calibration_file,
)
from dotbot.calibration.placement import spin_centres
from dotbot.config import SiteSection
from dotbot.site import Site, site_from_table

LOGGER = logging.getLogger(__name__)
CAMERA_TOML_GLOB = "camera-*.toml"
# Millimetres per pixel of a warped still: coarse, it is a backdrop
STILL_MM_PER_PX = 5.0
# Longest side of a warped still; a larger area is drawn coarser
STILL_MAX_PX = 4096


def _glob(folders: Sequence[Path], pattern: str) -> list[Path]:
    seen, out = set(), []
    for folder in folders:
        for path in sorted(folder.glob(pattern)):
            if path.resolve() not in seen:
                seen.add(path.resolve())
                out.append(path)
    return out


def calibration_backdrop(path: Path, site: Site | None) -> dict | None:
    """One LH2 calibration's placements and spin centres, in frame mm; None
    when the file cannot be read or was made in another frame than `site`'s."""
    try:
        calibration = read_calibration_file(path)
        if site is not None:
            check_calibration_site(calibration.site, site, path)
        return {
            "id8": calibration.id8,
            "tag": calibration.tag,
            "created_at": calibration.created_at,
            "placements": [
                [list(point) for point in placement.points_mm]
                for placement in calibration.placements
            ],
            "centres": [
                [c["x"], c["y"]]
                for circles in spin_centres(calibration).values()
                for c in circles
            ],
        }
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("no backdrop from %s: %s", path, exc)
        return None


def _homography(matrix):
    import numpy as np

    array = np.array(matrix, dtype=np.float64)
    if array.shape != (3, 3) or not np.isfinite(array).all():
        raise ValueError("a camera's homography is not a 3 x 3 matrix")
    return array


def warp_still(image: Path, matrix, area: Area) -> bytes | None:
    """The still at `image` warped onto `area` as a PNG, or None when it
    cannot be (no OpenCV, no readable image)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    frame = cv2.imread(str(image))
    if frame is None:
        return None
    mm_per_px = max(STILL_MM_PER_PX, max(area.w, area.h) / STILL_MAX_PX)
    scale = np.array(
        [
            [1.0 / mm_per_px, 0.0, -area.x / mm_per_px],
            [0.0, 1.0 / mm_per_px, -area.y / mm_per_px],
            [0.0, 0.0, 1.0],
        ]
    )
    size = (
        min(STILL_MAX_PX, max(1, round(area.w / mm_per_px))),
        min(STILL_MAX_PX, max(1, round(area.h / mm_per_px))),
    )
    try:
        warped = cv2.warpPerspective(frame, scale @ _homography(matrix), size)
    except (ValueError, cv2.error):
        return None
    ok, png = cv2.imencode(".png", warped)
    return png.tobytes() if ok else None


def _can_warp() -> bool:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


def create_router(
    name: str, folders: Callable[[], list[Path]], site_text: Callable[[], str]
) -> APIRouter:
    """Routes for the site `name`, whose calibration files are in `folders`."""
    from dotbot.camera.registration import read_camera_calibration_file

    router = APIRouter()

    def cameras() -> list[tuple[Path, object, list]]:
        out = []
        for path in _glob(folders(), CAMERA_TOML_GLOB):
            try:
                camera = read_camera_calibration_file(path)
                _homography(camera.matrix)
                span = [[float(x), float(y)] for x, y in camera.span_mm]
            except Exception as exc:  # noqa: BLE001
                LOGGER.info("no backdrop from %s: %s", path, exc)
                continue
            out.append((path, camera, span))
        return out

    def site() -> Site | None:
        try:
            table = SiteSection.model_validate(tomllib.loads(site_text()))
            return site_from_table(name, table)
        except Exception:  # noqa: BLE001
            return None

    def area_of(camera, current: Site | None) -> Area | None:
        try:
            return current.registry().resolve(camera.area) if current else None
        except Exception:  # noqa: BLE001
            return None

    @router.get("/api/backdrops")
    def backdrops():
        current = site()
        seen: set[str] = set()
        calibrations = []
        for path in _glob(folders(), CALIBRATION_TOML_GLOB):
            found = calibration_backdrop(path, current)
            if found is not None and found["id8"] not in seen:
                seen.add(found["id8"])
                calibrations.append(found)
        listed = []
        warps = _can_warp()
        for path, camera, span in cameras():
            area = area_of(camera, current)
            still = path.with_suffix(".jpg")
            version = f"{still.stat().st_mtime_ns:x}" if still.is_file() else ""
            listed.append(
                {
                    "id8": camera.id8,
                    "area": camera.area,
                    "rect": [area.x, area.y, area.w, area.h] if area else None,
                    "span": span,
                    "still": (
                        f"api/backdrops/camera/{camera.id8}.png?v={version}"
                        f"-{area.x}-{area.y}-{area.w}-{area.h}"
                        if area and version and warps
                        else None
                    ),
                }
            )
        return {"calibrations": calibrations, "cameras": listed}

    @router.get("/api/backdrops/camera/{id8}.png")
    def still(id8: str):
        for path, camera, _ in cameras():
            if camera.id8 != id8:
                continue
            area = area_of(camera, site())
            image = path.with_suffix(".jpg")
            png = warp_still(image, camera.matrix, area) if area else None
            if png is None:
                break
            return Response(png, media_type="image/png")
        raise HTTPException(404, f"no still for camera {id8}")

    return router
