# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Robot-robot contact for the simulated fleet: bodies block, nothing pushes.

Each body is a disc of BODY_RADIUS_MM about the outline centre, which sits
BODY_CENTRE_AHEAD_MM ahead of the axle midpoint. A robot's move for one tick
is taken whole, else slid along the contact if it glances off it, else
refused, whichever is the first that brings it no closer to a robot it would
overlap. Pairs that already overlap may part but not close.
"""

import numpy as np

from dotbot.kinematics import forward
from dotbot.robots import robot_geometry

_GEOMETRY = robot_geometry()
# The v3 body is a 95 mm square about its outline centre; a disc a little wider
# than its inscribed circle
BODY_RADIUS_MM = 50.0
BODY_CENTRE_AHEAD_MM = _GEOMETRY.axle_midpoint.y - _GEOMETRY.outline_centre.y
CONTACT_MM = 2 * BODY_RADIUS_MM
# A blocked robot slides along the contact only when at least this share of
# its move runs along it; one driving more squarely into the other stalls
SLIDE_MIN_SHARE = 0.5

# Levels of a robot's move, in the order they are tried
_WHOLE, _SLIDE, _REFUSED = 0, 1, 2


def body_centres(x, y, heading_deg):
    """Each robot's body centre, as an (n, 2) array."""
    fx, fy = forward(heading_deg)
    return np.stack(
        [x + BODY_CENTRE_AHEAD_MM * fx, y + BODY_CENTRE_AHEAD_MM * fy], axis=1
    )


def _near_pairs(c0, reach):
    """Both orderings of every pair of robots whose centres are closer than
    `reach[i] + reach[j]`, found by a sweep along x."""
    order = np.argsort(c0[:, 0], kind="stable")
    xs = c0[order, 0]
    span = reach[order] + reach.max()
    ends = np.searchsorted(xs, xs + span, side="right")
    starts = np.arange(len(xs)) + 1
    counts = ends - starts
    left = np.repeat(np.arange(len(xs)), counts)
    offsets = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    right = left + 1 + offsets
    i, j = order[left], order[right]
    d = c0[i] - c0[j]
    near = np.einsum("ij,ij->i", d, d) < (reach[i] + reach[j]) ** 2
    i, j = i[near], j[near]
    return np.concatenate([i, j]), np.concatenate([j, i])


def resolve(before, after, contact_mm: float = CONTACT_MM):
    """Which move each robot makes this tick.

    `before` and `after` are (x, y, heading_deg) arrays: every robot's pose
    at the start of the tick and the one its wheels would take it to. Returns
    the poses kept, as new arrays, and a mask of the moving robots whose move
    was refused, which keep their pose from `before`.
    """
    x0, y0, h0 = before
    x1, y1, h1 = after
    c0 = body_centres(x0, y0, h0)
    c1 = body_centres(x1, y1, h1)
    step = c1 - c0
    length = np.linalg.norm(step, axis=1)
    moving = (length > 0) | (h0 != h1)
    level = np.where(moving, _WHOLE, _REFUSED)
    slide = c1.copy()
    limit = contact_mm * contact_mm
    rows, cols = _near_pairs(c0, contact_mm / 2 + length)
    rows_open = moving[rows]
    rows, cols = rows[rows_open], cols[rows_open]
    while rows.size:
        centres = np.where(
            (level == _WHOLE)[:, None],
            c1,
            np.where((level == _SLIDE)[:, None], slide, c0),
        )
        # Pairs that overlap and that the row's robot brings closer
        d = centres[rows] - centres[cols]
        gap = np.einsum("ij,ij->i", d, d)
        w = c0[rows] - centres[cols]
        conflict = (gap < limit) & (gap < np.einsum("ij,ij->i", w, w))
        conflict &= level[rows] != _REFUSED
        if not conflict.any():
            break
        r, c, g = rows[conflict], cols[conflict], gap[conflict]
        # Each blocked robot's nearest conflict
        first = np.lexsort((g, r))
        r, c = r[first], c[first]
        blocked, nearest = np.unique(r, return_index=True)
        nearest = c[nearest]
        sliding = level[blocked] == _WHOLE
        index, other = blocked[sliding], nearest[sliding]
        normal = c0[index] - centres[other]
        norm = np.linalg.norm(normal, axis=1, keepdims=True)
        normal = np.divide(normal, norm, out=np.zeros_like(normal), where=norm > 0)
        along = (
            step[index] - np.einsum("ij,ij->i", step[index], normal)[:, None] * normal
        )
        glancing = np.linalg.norm(along, axis=1) >= SLIDE_MIN_SHARE * length[index]
        slide[index[glancing]] = c0[index[glancing]] + along[glancing]
        level[index[~glancing]] = _SLIDE
        level[blocked] += 1

    refused = (level == _REFUSED) & moving
    fx, fy = forward(h1)
    x = np.where(level == _REFUSED, x0, slide[:, 0] - BODY_CENTRE_AHEAD_MM * fx)
    y = np.where(level == _REFUSED, y0, slide[:, 1] - BODY_CENTRE_AHEAD_MM * fy)
    whole = level == _WHOLE
    x = np.where(whole, x1, x)
    y = np.where(whole, y1, y)
    heading = np.where(level == _REFUSED, h0, h1)
    return (x, y, heading), refused
