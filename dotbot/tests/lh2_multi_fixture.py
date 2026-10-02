# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Synthetic LH2 stations over one floor, and the spins they would record.

Every station is the measured c405 station (a real corner calibration's
homography) moved and turned over the floor, so each sees its own patch the
way the real one sees the arena; `aspect` squashes one image axis, as the
bench's 0.902 does. A spin is seen by every station whose patch centre is
within `reach_mm` of it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dotbot.calibration.conics import Track, apply, similarity
from dotbot.calibration.lighthouse2 import TrackSample, counts_for_camera_point
from dotbot.robots import robot_geometry

RADIUS = robot_geometry().spin_radius_mm

# Camera point to floor mm of the c405 station (calibration b54cb043).
C405 = np.array(
    [
        [189.809398943489, 2711.3856245939314, 1001.2158981500457],
        [-2180.185035995121, 288.17989657057416, 2247.631285943657],
        [0.08275982451927269, 0.08570280253867424, 1.0],
    ]
)
# The middle of the patch C405 sees well, floor mm.
C405_PATCH = np.array([1000.0, 1500.0])
REACH_MM = 1500.0


def rigid(dx: float, dy: float, theta_deg: float = 0.0) -> np.ndarray:
    t = np.radians(theta_deg)
    return np.array(
        [[np.cos(t), -np.sin(t), dx], [np.sin(t), np.cos(t), dy], [0, 0, 1.0]]
    )


@dataclass
class Station:
    """A synthetic station: `index`, and its floor-to-camera map."""

    index: int
    floor_to_cam: np.ndarray
    patch: np.ndarray
    reach_mm: float = REACH_MM

    def sees(self, centre) -> bool:
        return bool(np.linalg.norm(np.asarray(centre) - self.patch) <= self.reach_mm)

    @property
    def cam_to_floor(self) -> np.ndarray:
        H = np.linalg.inv(self.floor_to_cam)
        return H / H[2, 2]


def station(
    index: int, move: np.ndarray | None = None, aspect: float = 1.0, reach_mm=REACH_MM
) -> Station:
    """C405 moved over the floor by the rigid `move`, one image axis by `aspect`."""
    move = np.eye(3) if move is None else move
    squash = np.diag([1.0, aspect, 1.0])
    floor_to_cam = squash @ np.linalg.inv(C405) @ np.linalg.inv(move)
    patch = apply(move, C405_PATCH[None, :])[0]
    return Station(index, floor_to_cam, patch, reach_mm)


def circle(centre, radius=RADIUS, n=120, noise=0.0, rng=None, start_deg=90.0):
    """A counter-clockwise spin as drawn (y down), starting with the nose at +y."""
    th = np.radians(start_deg) - np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = np.c_[centre[0] + radius * np.cos(th), centre[1] + radius * np.sin(th)]
    if noise:
        pts = pts + rng.normal(0, noise, pts.shape)
    return pts


def spins(
    stations: list[Station],
    centres,
    noise: float = 0.0,
    seed: int = 0,
    round_: int = 0,
    names: list[str] | None = None,
    points: int = 120,
) -> dict[int, list[Track]]:
    """Per station, the camera-point tracks of every spin it sees."""
    rng = np.random.default_rng(seed)
    out: dict[int, list[Track]] = {}
    for i, centre in enumerate(centres):
        name = names[i] if names else f"R{i:02d}"
        for st in stations:
            if not st.sees(centre):
                continue
            pts = circle(centre, n=points, noise=noise, rng=rng)
            out.setdefault(st.index, []).append(
                Track(
                    points=apply(st.floor_to_cam, pts),
                    radius_mm=RADIUS,
                    turn=1,
                    name=name,
                    round=round_,
                )
            )
    return out


def samples(tracks: dict[int, list[Track]]) -> list[TrackSample]:
    """The tracks as the robots' raw counts, as a capture delivers them."""
    out = []
    for index, station_tracks in sorted(tracks.items()):
        for t in station_tracks:
            counts = [counts_for_camera_point(x, y, index) for x, y in t.points]
            out.append(
                TrackSample(
                    station=index,
                    name=t.name,
                    radius_mm=RADIUS,
                    turn=1,
                    count1=[round(c.count1) for c in counts],
                    count2=[round(c.count2) for c in counts],
                    round=t.round,
                )
            )
    return out


def grid_in(station_: Station, step=150.0, inset=200.0) -> np.ndarray:
    """Floor points well inside a station's patch."""
    r = station_.reach_mm - inset
    xs = np.arange(-r, r + 1, step)
    pts = np.array([(x, y) for x in xs for y in xs if x * x + y * y <= r * r])
    return pts + station_.patch


def placed_error(homographies, stations: list[Station], step=150.0, centres=None):
    """Per station, rms and max mm between the solve and the truth over its
    patch, after the one rigid move that best aligns every station at once.

    With `centres`, only over the patch's points within 500 mm of a spin it
    saw: where the calibration has evidence, not where it extrapolates.
    """
    ours, truth, owner = [], [], []
    for st in stations:
        if st.index not in homographies:
            continue
        P = grid_in(st, step)
        if centres is not None:
            seen = np.array([c for c in centres if st.sees(c)])
            near = np.min(np.linalg.norm(P[:, None] - seen[None], axis=2), axis=1)
            P = P[near <= 500]
        ours.append(apply(homographies[st.index], apply(st.floor_to_cam, P)))
        truth.append(P)
        owner += [st.index] * len(P)
    ours, truth, owner = np.vstack(ours), np.vstack(truth), np.array(owner)

    S = similarity(ours, truth, scale=False)
    err = np.linalg.norm(apply(S, ours) - truth, axis=1)
    return {
        s: (float(np.sqrt(np.mean(err[owner == s] ** 2))), float(err[owner == s].max()))
        for s in np.unique(owner)
    }
