# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""What the site editor can draw under a site, read-only: where each of the
site's LH2 calibrations was fitted, and each registered camera's still
warped into the frame.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from dotbot.area import Area
from dotbot.calibration.lighthouse2 import (
    CALIBRATION_TOML_GLOB,
    read_calibration_file,
)
from dotbot.calibration.placement import spin_centres
from dotbot.config import SiteSection
from dotbot.site import site_from_table

CAMERA_TOML_GLOB = "camera-*.toml"
# Millimetres per pixel of a warped still: coarse, it is a backdrop
STILL_MM_PER_PX = 5.0


def _glob(folders: Sequence[Path], pattern: str) -> list[Path]:
    seen, out = set(), []
    for folder in folders:
        for path in sorted(folder.glob(pattern)):
            if path.resolve() not in seen:
                seen.add(path.resolve())
                out.append(path)
    return out


def calibration_backdrop(path: Path) -> dict | None:
    """One LH2 calibration's placements and spin centres, in frame mm."""
    try:
        calibration = read_calibration_file(path)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return None
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
    scale = np.array(
        [
            [1.0 / STILL_MM_PER_PX, 0.0, -area.x / STILL_MM_PER_PX],
            [0.0, 1.0 / STILL_MM_PER_PX, -area.y / STILL_MM_PER_PX],
            [0.0, 0.0, 1.0],
        ]
    )
    size = (
        max(1, round(area.w / STILL_MM_PER_PX)),
        max(1, round(area.h / STILL_MM_PER_PX)),
    )
    warped = cv2.warpPerspective(
        frame, scale @ np.array(matrix, dtype=np.float64), size
    )
    ok, png = cv2.imencode(".png", warped)
    return png.tobytes() if ok else None


def create_router(
    name: str, folders: Callable[[], list[Path]], site_text: Callable[[], str]
) -> APIRouter:
    """Routes for the site `name`, whose calibration files are in `folders`."""
    from dotbot.camera.registration import read_camera_calibration_file

    router = APIRouter()

    def cameras() -> list[tuple[Path, object]]:
        out = []
        for path in _glob(folders(), CAMERA_TOML_GLOB):
            try:
                out.append((path, read_camera_calibration_file(path)))
            except (OSError, ValueError, tomllib.TOMLDecodeError):
                continue
        return out

    def area_of(camera) -> Area | None:
        try:
            table = SiteSection.model_validate(tomllib.loads(site_text()))
            return site_from_table(name, table).registry().resolve(camera.area)
        except Exception:  # noqa: BLE001
            return None

    @router.get("/api/backdrops")
    def backdrops():
        calibrations = [
            found
            for found in map(
                calibration_backdrop, _glob(folders(), CALIBRATION_TOML_GLOB)
            )
            if found is not None
        ]
        listed = []
        for path, camera in cameras():
            area = area_of(camera)
            still = path.with_suffix(".jpg")
            listed.append(
                {
                    "id8": camera.id8,
                    "area": camera.area,
                    "rect": [area.x, area.y, area.w, area.h] if area else None,
                    "span": [list(p) for p in camera.span_mm],
                    "still": (
                        f"api/backdrops/camera/{camera.id8}.png"
                        if area and still.is_file()
                        else None
                    ),
                }
            )
        return {"calibrations": calibrations, "cameras": listed}

    @router.get("/api/backdrops/camera/{id8}.png")
    def still(id8: str):
        for path, camera in cameras():
            if camera.id8 != id8:
                continue
            area = area_of(camera)
            image = path.with_suffix(".jpg")
            png = warp_still(image, camera.matrix, area) if area else None
            if png is None:
                break
            return Response(png, media_type="image/png")
        raise HTTPException(404, f"no still for camera {id8}")

    return router
