"""Text as a set of arena points, one per bot, for the letters demo."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - exercised by the missing extra
    raise ImportError(
        "the letters demo needs Pillow: pip install 'pydotbot[letters]'"
    ) from exc

#: Pixel height the word is rendered at before it is sampled. High enough that
#: a sample grid has something to average, low enough to stay instant.
RENDER_PX = 240

#: A cell counts as ink when this fraction of it is covered.
COVERAGE = 0.32


def render_mask(text: str, height_px: int = RENDER_PX) -> np.ndarray:
    """The word as a boolean ink mask, cropped to its own bounding box."""
    font = ImageFont.load_default(size=height_px)
    left, top, right, bottom = font.getbbox(text)
    width = max(1, right - left)
    height = max(1, bottom - top)
    image = Image.new("L", (width + 4, height + 4), 0)
    ImageDraw.Draw(image).text((2 - left, 2 - top), text, font=font, fill=255)
    box = image.getbbox()
    if box is None:
        return np.zeros((0, 0), dtype=bool)
    return np.asarray(image.crop(box)) > 127


def sample_mask(mask: np.ndarray, step_px: float) -> np.ndarray:
    """
    Ink cells of a `step_px` grid, as (x, y) pixel centres.

    The grid, rather than one point per lit pixel: the spacing between two
    bots is the thing being controlled, and a grid states it directly.
    """
    rows, columns = mask.shape
    if rows == 0 or columns == 0 or step_px <= 0:
        return np.zeros((0, 2))
    step = max(1.0, step_px)
    points: List[Tuple[float, float]] = []
    for y in np.arange(0, rows, step):
        y0, y1 = int(y), min(rows, int(y + step))
        for x in np.arange(0, columns, step):
            x0, x1 = int(x), min(columns, int(x + step))
            cell = mask[y0:y1, x0:x1]
            # The nominal centre, not the clipped one: a cell cut short at the
            # edge would otherwise sit closer than `step` to its neighbour.
            if cell.size and cell.mean() >= COVERAGE:
                points.append((x + step / 2, y + step / 2))
    return np.asarray(points, dtype=float).reshape(-1, 2)


def word_points(
    text: str,
    *,
    budget: int,
    height_mm: float,
    arena: Tuple[float, float],
    min_spacing_mm: float,
    margin_mm: float = 150.0,
) -> np.ndarray:
    """
    Up to `budget` arena points spelling `text`, centred in the arena.

    The word is scaled to `height_mm`, or to whatever fits the arena width if
    that is smaller. Spacing starts at `min_spacing_mm` and is widened until
    the point count is inside the budget, so bots never end up closer than
    the caller's floor whatever the word.
    """
    mask = render_mask(text.strip())
    if mask.size == 0 or budget <= 0:
        return np.zeros((0, 2))

    rows, columns = mask.shape
    mm_per_px = height_mm / rows
    widest = arena[0] - 2 * margin_mm
    if columns * mm_per_px > widest:
        mm_per_px = widest / columns
    tallest = arena[1] - 2 * margin_mm
    if rows * mm_per_px > tallest:
        mm_per_px = tallest / rows

    spacing = max(min_spacing_mm, 1e-6)
    points = sample_mask(mask, spacing / mm_per_px)
    # Widening the grid drops points roughly as the square of the step, so a
    # 12% step per try converges in a handful of rounds even from far over.
    for _ in range(60):
        if len(points) <= budget:
            break
        spacing *= 1.12
        points = sample_mask(mask, spacing / mm_per_px)
    if len(points) > budget:
        points = points[:budget]

    scaled = points * mm_per_px
    span = np.array([columns * mm_per_px, rows * mm_per_px])
    origin = np.array([arena[0] / 2, arena[1] / 2]) - span / 2
    return scaled + origin


def ring_points(
    center: Tuple[float, float],
    count: int,
    radius: float,
    *,
    phase: float = 0.0,
) -> np.ndarray:
    """`count` points evenly spaced on a circle, starting at `phase` radians."""
    if count <= 0:
        return np.zeros((0, 2))
    angles = phase + np.arange(count) * (2 * np.pi / count)
    return np.stack(
        [center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)],
        axis=1,
    )


def clamp_to_arena(
    points: np.ndarray, arena: Tuple[float, float], margin: float = 90.0
) -> np.ndarray:
    """Keep every point inside the walls, which the bots cannot drive through."""
    if len(points) == 0:
        return points
    return np.stack(
        [
            np.clip(points[:, 0], margin, arena[0] - margin),
            np.clip(points[:, 1], margin, arena[1] - margin),
        ],
        axis=1,
    )


def spare_ring(
    count: int, arena: Tuple[float, float], *, margin: float = 150.0
) -> np.ndarray:
    """
    Somewhere to park the bots a formation does not need: a ring just inside
    the walls, so the spares frame what the rest are spelling.
    """
    if count <= 0:
        return np.zeros((0, 2))
    center = (arena[0] / 2, arena[1] / 2)
    radius = min(arena[0], arena[1]) / 2 - margin
    return clamp_to_arena(ring_points(center, count, radius), arena, margin)
