# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""LH2 calibration from the circles robots trace on the floor.

The image of any circle passes through the images of the plane's two
circular points, and those fix the floor up to a similarity (Alvarado-Marin
et al., RA-L 2025). This module recovers that rectification from tracks of
pinhole camera points, takes the scale from the circles' known radius and
puts the frame on the rectangle around the circles (free mode).

Camera points are those of `lighthouse2.calculate_camera_point`. Rectified
and site coordinates follow the firmware frame: x right, y down, mm.
"""

# pylint: disable=invalid-name

from __future__ import annotations

import datetime
import itertools
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from dotbot.area import Area
from dotbot.calibration.lighthouse2 import (
    Calibration,
    StationSolution,
    TrackSample,
)
from dotbot.robots import ROBOT_DEFAULT, robot_geometry
from dotbot.site import Site

# Post-rectification minor/major axis ratio under which a track is not a circle.
TRACK_AXIS_RATIO_MIN = 0.95

# Largest share a track's radius may differ from the median of its peers' (a
# binding caster moves the pivot and shrinks the circle).
TRACK_RADIUS_SPREAD_MAX = 0.06

TRACK_POINTS_MIN = 12

# Two imaged circles meet in two conjugate pairs that both rectify them
# exactly; a third circle tells the pairs apart.
TRACKS_MIN = 3

# Under this many circles the solve holds but the frame is loosely held.
TRACKS_ADVISED = 8

# Pairs the closed form tries at most; beyond it a fixed random subset.
CLOSED_FORM_PAIRS_MAX = 400

# Gate-and-refine rounds at most before the kept set must have settled.
GATE_ROUNDS_MAX = 4


@dataclass(eq=False)
class Track:
    """One circle's camera points, in the order they were read.

    `radius_mm` is the circle's true radius when known; tracks that share a
    radius are fitted with one. `turn` is +1 when the robot turned counter
    clockwise as drawn (right wheel faster), -1 clockwise, 0 unknown.
    """

    points: np.ndarray
    radius_mm: float | None = None
    turn: int = 0
    name: str = ""

    def __post_init__(self):
        self.points = np.asarray(self.points, dtype=np.float64).reshape(-1, 2)


@dataclass
class TrackFit:
    """How one track looks after the solve, in site millimetres.

    `why` says why a track was left out of the solve, "" for a kept one.
    """

    name: str
    points: int
    centre_mm: tuple[float, float]
    radius_mm: float
    axis_ratio: float
    rms_mm: float
    why: str = ""


@dataclass
class ConicSolution:
    """A camera-to-site homography and the evidence of how well it holds."""

    homography: np.ndarray
    tracks: list[TrackFit] = field(default_factory=list)
    dropped: list[TrackFit] = field(default_factory=list)
    closed_form_eccentricity: float = float("nan")
    # Width and height of the field the spin centres define.
    field_mm: tuple[int, int] | None = None

    @property
    def rejected(self) -> list[str]:
        return [t.name for t in self.dropped]

    @property
    def residual_mm(self) -> float:
        """RMS distance of every kept track point to its fitted circle."""
        if not self.tracks:
            return float("nan")
        sq = sum(t.rms_mm**2 * t.points for t in self.tracks)
        return float(np.sqrt(sq / sum(t.points for t in self.tracks)))


# --- Projective helpers -----------------------------------------------------


def to_h(points: np.ndarray) -> np.ndarray:
    points = np.atleast_2d(points)
    return np.c_[points, np.ones(len(points))]


def apply(H: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Points mapped through a homography."""
    v = to_h(points) @ H.T
    return v[:, :2] / v[:, 2:3]


def normalizer(points: np.ndarray) -> np.ndarray:
    """Similarity taking `points` to zero mean and mean distance sqrt(2)."""
    mean = points.mean(axis=0)
    spread = np.mean(np.linalg.norm(points - mean, axis=1))
    s = np.sqrt(2) / spread
    return np.array([[s, 0, -s * mean[0]], [0, s, -s * mean[1]], [0, 0, 1.0]])


def transform_conic(C: np.ndarray, H: np.ndarray) -> np.ndarray:
    """The conic `C` after points move by x' = H x."""
    Hi = np.linalg.inv(H)
    out = Hi.T @ C @ Hi
    return out / np.linalg.norm(out)


# --- Conics -----------------------------------------------------------------


def fit_conic(points: np.ndarray) -> np.ndarray:
    """Least-squares ellipse through `points` (Halir and Flusser), as a 3x3 matrix.

    Conditioned internally, so any coordinates will do.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 6:
        raise ValueError(f"an ellipse needs at least 6 points, got {len(points)}")
    T = normalizer(points)
    x, y = apply(T, points).T
    D1 = np.c_[x * x, x * y, y * y]
    D2 = np.c_[x, y, np.ones_like(x)]
    S1, S2, S3 = D1.T @ D1, D1.T @ D2, D2.T @ D2
    Tm = -np.linalg.solve(S3, S2.T)
    M = S1 + S2 @ Tm
    M = np.array([M[2] / 2, -M[1], M[0] / 2])
    w, v = np.linalg.eig(M)
    v = np.real(v)
    cond = 4 * v[0] * v[2] - v[1] ** 2
    candidates = np.flatnonzero(cond > 0)
    if len(candidates) == 0:
        raise ValueError("the points do not describe an ellipse")
    a1 = v[:, candidates[np.argmin(np.abs(np.real(w[candidates])))]]
    a, b, c = a1
    d, e, f = Tm @ a1
    Cn = np.array([[a, b / 2, d / 2], [b / 2, c, e / 2], [d / 2, e / 2, f]])
    C = T.T @ Cn @ T
    return C / np.linalg.norm(C)


def ellipse_axes(C: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Centre, semi-major and semi-minor axis of the ellipse `C`."""
    A = C[:2, :2]
    centre = np.linalg.solve(A, -C[:2, 2])
    k = centre @ A @ centre - C[2, 2]
    ev = np.linalg.eigvalsh(A / k)
    if np.any(ev <= 0):
        raise ValueError("the conic is not a real ellipse")
    axes = 1 / np.sqrt(ev)
    return centre, float(axes.max()), float(axes.min())


def eccentricity(C: np.ndarray) -> float:
    """Eccentricity of a conic (paper eq. 11): 0 for a circle."""
    A, B, Cc = C[0, 0], 2 * C[0, 1], C[1, 1]
    root = np.sqrt((A - Cc) ** 2 + B**2)
    eta = 1.0 if np.linalg.det(C) < 0 else -1.0
    denom = eta * (A + Cc) + root
    if denom <= 0:
        return 1.0
    return float(np.sqrt(min(2 * root / denom, 1.0)))


def conic_intersections(C1: np.ndarray, C2: np.ndarray) -> list[np.ndarray]:
    """The (up to four, complex) points two conics share, as (x, y, 1).

    y is eliminated with the resultant of the two conics read as quadratics
    in y, leaving a quartic in x. A fixed generic rotation keeps the
    elimination away from axis-aligned degeneracies.
    """
    angle = 0.5235987755982988 * 0.7  # any angle that is not a multiple of 90
    c, s = np.cos(angle), np.sin(angle)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
    K1, K2 = transform_conic(C1, R), transform_conic(C2, R)

    def coeffs(K):
        # p y^2 + q(x) y + r(x), polynomials in x with the highest power first
        p = np.array([K[1, 1]])
        q = np.array([2 * K[0, 1], 2 * K[1, 2]])
        r = np.array([K[0, 0], 2 * K[0, 2], K[2, 2]])
        return p, q, r

    p1, q1, r1 = coeffs(K1)
    p2, q2, r2 = coeffs(K2)
    pm = np.polysub(np.polymul(p1, r2), np.polymul(p2, r1))
    pq = np.polysub(np.polymul(p1, q2), np.polymul(p2, q1))
    qr = np.polysub(np.polymul(q1, r2), np.polymul(q2, r1))
    quartic = np.polysub(np.polymul(pm, pm), np.polymul(pq, qr))
    points = []
    Ri = R.T
    for x in np.roots(quartic):
        denom = np.polyval(pq, x)
        if abs(denom) < 1e-14:
            continue
        y = -np.polyval(pm, x) / denom
        v = Ri @ np.array([x, y, 1.0], dtype=np.complex128)
        points.append(v / v[2])
    return points


def circular_point_candidates(C1: np.ndarray, C2: np.ndarray) -> list[np.ndarray]:
    """Images of the circular point I the two conics allow, one per conjugate pair."""
    pts = conic_intersections(C1, C2)
    out = []
    used = set()
    for i, p in enumerate(pts):
        if i in used or abs(p[:2].imag).max() < 1e-12:
            continue
        for j in range(i + 1, len(pts)):
            if j in used:
                continue
            if np.allclose(pts[j], np.conj(p), rtol=1e-6, atol=1e-9):
                used |= {i, j}
                out.append(p)
                break
    return out


def rectifier(image_i: np.ndarray) -> np.ndarray:
    """Image-to-plane homography that sends the imaged circular point
    `image_i` back to (1, i, 0), so circles come out as circles.

    Its inverse is [Re I, Im I, Re I x Im I]: any third column works, the
    choice only moves the result by a similarity.
    """
    a, b = np.real(image_i), np.imag(image_i)
    H = np.c_[a, b, np.cross(a, b)]
    return np.linalg.inv(H)


def closed_form(tracks: Sequence[Track]) -> tuple[np.ndarray, float]:
    """The paper's solve: every pair of conics, keep the rectifier whose
    rectified conics are roundest on average (eq. 12).

    Returns the image-to-rectified homography and that mean eccentricity.
    """
    if len(tracks) < 2:
        raise ValueError(
            f"the rectification needs at least 2 circles, got {len(tracks)}"
        )
    T = normalizer(np.vstack([t.points for t in tracks]))
    conics = [transform_conic(fit_conic(t.points), T) for t in tracks]
    best, best_e = None, np.inf
    pairs = list(itertools.combinations(range(len(conics)), 2))
    if len(pairs) > CLOSED_FORM_PAIRS_MAX:
        rng = np.random.default_rng(0)
        pairs = [
            pairs[k]
            for k in rng.choice(len(pairs), CLOSED_FORM_PAIRS_MAX, replace=False)
        ]
    for i, j in pairs:
        C1, C2 = conics[i], conics[j]
        for image_i in circular_point_candidates(C1, C2):
            Hr = rectifier(image_i)
            e = np.mean([eccentricity(transform_conic(C, Hr)) for C in conics])
            if e < best_e:
                best, best_e = Hr, e
    if best is None:
        raise ValueError("no pair of tracks intersects in a complex conjugate pair")
    return best @ T, float(best_e)


# --- Refinement -------------------------------------------------------------


def _lm(residual, x0, iterations=100):
    """Levenberg-Marquardt with a forward-difference Jacobian."""
    x = np.asarray(x0, dtype=np.float64).copy()
    r = residual(x)
    cost = r @ r
    lam = 1e-3
    for _ in range(iterations):
        J = np.empty((len(r), len(x)))
        for k in range(len(x)):
            step = 1e-7 * max(1.0, abs(x[k]))
            xk = x.copy()
            xk[k] += step
            J[:, k] = (residual(xk) - r) / step
        g = J.T @ r
        A = J.T @ J
        improved = False
        while lam < 1e10:
            dx = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), -g)
            r_new = residual(x + dx)
            cost_new = r_new @ r_new
            if cost_new < cost:
                x, r = x + dx, r_new
                lam = max(lam / 10, 1e-12)
                improved = cost - cost_new > 1e-14 * cost
                cost = cost_new
                break
            lam *= 10
        if not improved:
            break
    return x


def _circle_fit(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Algebraic (Kasa) circle through `points`: centre and radius."""
    A = np.c_[2 * points, np.ones(len(points))]
    b = (points**2).sum(axis=1)
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    centre = sol[:2]
    return centre, float(np.sqrt(sol[2] + centre @ centre))


def _radius_groups(tracks: Sequence[Track]) -> list[int]:
    """Index of each track's radius group: tracks of one known radius share it."""
    keys: dict = {}
    groups = []
    for i, t in enumerate(tracks):
        key = round(t.radius_mm, 6) if t.radius_mm else ("free", i)
        groups.append(keys.setdefault(key, len(keys)))
    return groups


def refine(tracks: Sequence[Track], Hr0: np.ndarray) -> np.ndarray:
    """Adjust the rectifier so every track is as close to a circle as it can be.

    Four parameters move the plane: two of affine shape and two of the line
    at infinity. For each trial the tracks' centres are fitted in closed
    form and each radius group takes its mean radius; the residual is each
    point's distance to its centre relative to that radius, so shrinking the
    plane cannot pay.
    """
    groups = np.array(_radius_groups(tracks))
    radii = [_circle_fit(apply(Hr0, t.points))[1] for t in tracks]
    H0 = np.diag([1 / np.median(radii), 1 / np.median(radii), 1.0]) @ Hr0

    def D(p):
        return np.array([[1 + p[0], p[1], 0], [0, 1, 0], [p[2], p[3], 1.0]])

    def residual(p):
        H = D(p) @ H0
        dists = []
        for t in tracks:
            q = apply(H, t.points)
            centre, _ = _circle_fit(q)
            dists.append(np.linalg.norm(q - centre, axis=1))
        out = []
        for g in set(groups):
            members = [d for d, k in zip(dists, groups) if k == g]
            r = np.mean(np.concatenate(members))
            out += [d / r - 1 for d in members]
        return np.concatenate(out)

    return D(_lm(residual, np.zeros(4))) @ H0


# --- Similarity -------------------------------------------------------------


def signed_area(points: np.ndarray) -> float:
    """Shoelace area: negative for a counter-clockwise loop in a y-down frame."""
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def fix_handedness(tracks: Sequence[Track], Hr: np.ndarray) -> np.ndarray:
    """Mirror the rectified plane if the tracks turn the wrong way in it.

    A robot turning counter clockwise as drawn (turn = +1) traces a loop of
    negative area in the y-down frame. Tracks with an unknown turn do not vote.
    """
    votes = sum(
        t.turn * (1 if signed_area(apply(Hr, t.points)) < 0 else -1)
        for t in tracks
        if t.turn
    )
    if votes < 0:
        return np.diag([1.0, -1.0, 1.0]) @ Hr
    return Hr


def similarity(src: np.ndarray, dst: np.ndarray, scale: bool = True) -> np.ndarray:
    """Least-squares similarity (Umeyama) taking `src` onto `dst`, no reflection."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    U, sv, Vt = np.linalg.svd(b.T @ a)
    d = np.sign(np.linalg.det(U @ Vt))
    E = np.diag([1.0, d])
    R = U @ E @ Vt
    s = (sv * np.diag(E)).sum() / (a**2).sum() if scale else 1.0
    t = md - s * R @ ms
    return np.array(
        [
            [s * R[0, 0], s * R[0, 1], t[0]],
            [s * R[1, 0], s * R[1, 1], t[1]],
            [0, 0, 1.0],
        ]
    )


def _scale_to_mm(tracks: Sequence[Track], Hr: np.ndarray) -> float:
    """Millimetres per rectified unit, from the tracks of known radius."""
    ratios = []
    for t in tracks:
        if t.radius_mm:
            ratios.append(t.radius_mm / _circle_fit(apply(Hr, t.points))[1])
    if not ratios:
        raise ValueError("free mode needs at least one track of known radius")
    return float(np.median(ratios))


def station_frame(Hr: np.ndarray) -> np.ndarray:
    """Rotation and origin of the free-mode frame, in the rectified plane.

    The origin is the station's nadir, where the ray along the plane normal
    meets the floor, and +y points from it towards where the station's
    optical axis meets the floor. Both read the camera as a pinhole with
    identity intrinsics, which only affects where the frame sits, never the
    distances in it.
    """
    Hi = np.linalg.inv(Hr)
    normal = np.cross(Hi[:, 0], Hi[:, 1])
    nadir = apply(Hr, (normal / normal[2])[:2])[0]
    axis = apply(Hr, np.zeros((1, 2)))[0]
    fwd = axis - nadir
    fwd /= np.linalg.norm(fwd)
    # +y along fwd, +x = -y turned a quarter clockwise in a y-down frame
    R = np.array([[fwd[1], -fwd[0]], [fwd[0], fwd[1]]])
    return np.array(
        [[R[0, 0], R[0, 1], 0], [R[1, 0], R[1, 1], 0], [0, 0, 1.0]]
    ) @ np.array([[1, 0, -nadir[0]], [0, 1, -nadir[1]], [0, 0, 1.0]])


def axis_ratio(track: Track, H: np.ndarray) -> float:
    """Minor over major axis of the ellipse through a track mapped by `H`."""
    try:
        _, a, b = ellipse_axes(fit_conic(apply(H, track.points)))
    except (ValueError, np.linalg.LinAlgError):
        return 0.0
    return b / a


def fit_tracks(
    tracks: Sequence[Track], H: np.ndarray, why: dict | None = None
) -> list[TrackFit]:
    """Each track seen through the camera-to-site homography `H`.

    `why` maps a track to the reason it was left out, if it was.
    """
    why = why or {}
    fits = []
    for t in tracks:
        q = apply(H, t.points)
        centre, radius = _circle_fit(q)
        rms = float(
            np.sqrt(np.mean((np.linalg.norm(q - centre, axis=1) - radius) ** 2))
        )
        fits.append(
            TrackFit(
                name=t.name,
                points=len(q),
                centre_mm=(float(centre[0]), float(centre[1])),
                radius_mm=radius,
                axis_ratio=axis_ratio(t, H),
                rms_mm=rms,
                why=why.get(t, ""),
            )
        )
    return fits


def health_gate(tracks: Sequence[Track], Hr: np.ndarray) -> dict[Track, str]:
    """The tracks that are not circles of their peers' size under `Hr`, and why.

    A track must come out round (`TRACK_AXIS_RATIO_MIN`) and, among the round
    tracks of the same true radius, within `TRACK_RADIUS_SPREAD_MAX` of their
    median radius.
    """
    why: dict[Track, str] = {}
    for t in tracks:
        ratio = axis_ratio(t, Hr)
        if ratio < TRACK_AXIS_RATIO_MIN:
            why[t] = f"axis ratio {ratio:.3f}, under {TRACK_AXIS_RATIO_MIN}"
    round_tracks = [t for t in tracks if t not in why]
    groups = _radius_groups(round_tracks)
    radii = np.array([_circle_fit(apply(Hr, t.points))[1] for t in round_tracks])
    for g in set(groups):
        members = [k for k, gk in enumerate(groups) if gk == g]
        if len(members) < TRACKS_MIN:
            continue
        median = np.median(radii[members])
        for k in members:
            off = radii[k] / median - 1
            if abs(off) > TRACK_RADIUS_SPREAD_MAX:
                why[round_tracks[k]] = f"radius {100 * off:+.1f} % off its peers'"
    return why


def solve(tracks: Sequence[Track], margin_mm: float | None = None) -> ConicSolution:
    """Camera-to-site homography from circle tracks of known radius (free mode).

    Scale from the tracks' radius; axes along the minimum-area rectangle of
    the circle centres (`field_angle`), turned a quarter at a time so the
    robots' starting headings point along +y (`upright_turns`); zero at the
    top-left of that rectangle grown by
    `margin_mm` (default: what a spinning robot sweeps), which is the field
    (`field_mm`).
    """
    if margin_mm is None:
        margin_mm = robot_geometry().axle_reach_mm
    why: dict[Track, str] = {
        t: f"{len(t.points)} reads, under {TRACK_POINTS_MIN}"
        for t in tracks
        if len(t.points) < TRACK_POINTS_MIN
    }
    usable = [t for t in tracks if t not in why]
    if len(usable) < TRACKS_MIN:
        raise ValueError(
            f"the solve needs at least {TRACKS_MIN} circles, got {len(usable)}"
        )
    Hr, e0 = closed_form(usable)
    if len(usable) - len(health_gate(usable, Hr)) < TRACKS_MIN:
        Hr = refine(usable, Hr)
    fitted_on = None
    for _ in range(GATE_ROUNDS_MAX):
        gate = health_gate(usable, Hr)
        inliers = [t for t in usable if t not in gate]
        if len(inliers) < TRACKS_MIN:
            raise ValueError(
                f"only {len(inliers)} of {len(usable)} tracks are circles of one size under "
                f"the best rectification; at least {TRACKS_MIN} are needed"
            )
        if inliers == fitted_on:
            break
        Hr = refine(inliers, Hr)
        fitted_on = inliers
    why.update(gate)
    Hr = fix_handedness(inliers, Hr)
    s = _scale_to_mm(inliers, Hr)
    Hm = np.diag([s, s, 1.0]) @ Hr
    H = station_frame(Hm) @ Hm
    centres = np.array([_circle_fit(apply(H, t.points))[0] for t in inliers])
    angle = field_angle(centres)
    c, sn = np.cos(-angle), np.sin(-angle)
    H = np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1.0]]) @ H
    c, sn = np.cos(np.pi / 2), np.sin(np.pi / 2)
    quarter = np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1.0]])
    H = np.linalg.matrix_power(quarter, upright_turns(inliers, H)) @ H
    centres = np.array([_circle_fit(apply(H, t.points))[0] for t in inliers])
    lo = centres.min(axis=0) - margin_mm
    size = np.ceil(centres.max(axis=0) + margin_mm - lo)
    H = np.array([[1, 0, -lo[0]], [0, 1, -lo[1]], [0, 0, 1.0]]) @ H
    H = H / H[2, 2]
    return ConicSolution(
        homography=H,
        tracks=fit_tracks(inliers, H),
        dropped=fit_tracks([t for t in tracks if t in why], H, why),
        closed_form_eccentricity=e0,
        field_mm=(int(size[0]), int(size[1])),
    )


def _hull(points: np.ndarray) -> np.ndarray:
    """Convex hull (monotone chain), counter clockwise in a y-up sense."""
    pts = sorted(map(tuple, np.unique(points, axis=0)))
    if len(pts) < 3:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def upright_turns(tracks: Sequence[Track], H: np.ndarray) -> int:
    """Quarter turns (+90 degrees each, as drawn) that point the robots along +y.

    +y is the firmware's heading zero, so robots that start their spin at
    heading zero read heading zero in the new frame too.

    A track's first read is the photodiode as the spin starts, ahead of the
    axle on the robot's centreline, so the circle's centre to that read is the
    robot's starting heading. When the headings do not agree, the field is
    stood with its long side along y instead.
    """
    dirs = []
    for t in tracks:
        p = apply(H, t.points)
        d = p[0] - _circle_fit(p)[0]
        dirs.append(d / np.linalg.norm(d))
    mean = np.mean(dirs, axis=0)
    if np.linalg.norm(mean) >= 0.5:
        heading = np.arctan2(mean[1], mean[0])
        return int(np.round((np.pi / 2 - heading) / (np.pi / 2))) % 4
    centres = np.array([_circle_fit(apply(H, t.points))[0] for t in tracks])
    width, height = np.ptp(centres, axis=0)
    return 1 if width > height else 0


def field_angle(centres: np.ndarray) -> float:
    """Rotation, in radians, that the minimum-area rectangle around `centres` has.

    Of the four right-angle turns of it, the one nearest to no rotation is
    returned, so the frame stays close to the station's own.
    """
    hull = _hull(np.asarray(centres, dtype=np.float64))
    if len(hull) < 3:
        if len(hull) < 2:
            return 0.0
        d = hull[1] - hull[0]
        best = np.arctan2(d[1], d[0])
    else:
        best, best_area = 0.0, np.inf
        for a, b in zip(hull, np.roll(hull, -1, axis=0)):
            theta = np.arctan2(b[1] - a[1], b[0] - a[0])
            c, s = np.cos(-theta), np.sin(-theta)
            q = hull @ np.array([[c, s], [-s, c]])
            area = np.prod(np.ptp(q, axis=0))
            if area < best_area - 1e-9:
                best, best_area = theta, area
    return float((best + np.pi / 4) % (np.pi / 2) - np.pi / 4)


# --- Calibration ------------------------------------------------------------

# What a free-mode calibration records as its site's anchor: no mark in the
# room is its origin.
FREE_FRAME_ANCHOR = (
    "free mode: zero at the top-left of the rectangle around the spinning "
    "robots, grown by a robot's footprint; axes along that rectangle"
)


def solve_calibration(
    samples: Sequence[TrackSample],
    site: Site,
    robot: str = ROBOT_DEFAULT,
    tag: str = "",
) -> tuple[Calibration, dict[int, ConicSolution], dict[int, str]]:
    """A free-mode calibration from circle tracks, one homography per station.

    The station with the most tracks sets the frame; every other station is
    aligned to it through the centres of the circles both saw. Returns the
    calibration, each solved station's solution, and why each other station
    was not solved. The calibration records `site`'s name only, with
    `FREE_FRAME_ANCHOR` for its anchor.
    """
    by_station: dict[int, list[Track]] = {}
    for sample in samples:
        by_station.setdefault(sample.station, []).append(
            Track(
                points=sample.camera_points(),
                radius_mm=sample.radius_mm,
                turn=sample.turn,
                name=sample.name,
            )
        )
    if not by_station:
        raise ValueError("no tracks to solve")
    margin_mm = robot_geometry(robot).axle_reach_mm
    order = sorted(by_station, key=lambda k: (-len(by_station[k]), k))
    reference = order[0]
    solutions = {reference: solve(by_station[reference], margin_mm=margin_mm)}
    unsolved: dict[int, str] = {}
    centres = {t.name: t.centre_mm for t in solutions[reference].tracks}
    for station in order[1:]:
        try:
            own = solve(by_station[station], margin_mm=margin_mm)
        except ValueError as exc:
            unsolved[station] = str(exc)
            continue
        common = [t for t in own.tracks if t.name in centres]
        if len(common) < 2:
            unsolved[station] = (
                f"shares {len(common)} circle(s) with station {reference}; 2 are "
                "needed to put both in one frame"
            )
            continue
        S = similarity(
            np.array([t.centre_mm for t in common]),
            np.array([centres[t.name] for t in common]),
            scale=False,
        )
        H = S @ own.homography
        own.homography = H / H[2, 2]
        why = {t.name: t.why for t in own.dropped}
        own.tracks = fit_tracks(
            [t for t in by_station[station] if t.name not in why], own.homography
        )
        dropped = [t for t in by_station[station] if t.name in why]
        own.dropped = fit_tracks(
            dropped, own.homography, {t: why[t.name] for t in dropped}
        )
        solutions[station] = own
    width, height = solutions[reference].field_mm
    stations = [
        StationSolution(
            index=station,
            homography=[[float(v) for v in row] for row in sol.homography],
            points=sum(t.points for t in sol.tracks),
            residual_mm=sol.residual_mm,
            solved_from="conics-free",
        )
        for station, sol in sorted(solutions.items())
    ]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    calibration = Calibration(
        site=Site(name=site.name, anchor=FREE_FRAME_ANCHOR),
        valid_mm=(0, 0, width, height),
        stations=stations,
        tracks=list(samples),
        created_at=now,
        tag=tag,
        robot=robot,
    )
    return calibration, solutions, unsolved


def self_defined_site(
    calibration: Calibration,
    name: str,
    size_mm: tuple[int, int] | None = None,
) -> tuple[Site, Calibration]:
    """A site pack's site from a free-mode calibration, and the calibration in it.

    The field is the calibration's own fence, the rectangle around the
    spinning robots. With `size_mm` the site is that big and the field sits in
    its middle, so the calibration is shifted by the field's offset; without,
    the site is the field. A tag gets `-<name>` appended, so the two files
    answer to different tags.
    """
    if (
        not calibration.stations
        or calibration.site.anchor != FREE_FRAME_ANCHOR
        or any(st.solved_from != "conics-free" for st in calibration.stations)
    ):
        raise ValueError(
            f"calibration {calibration.id8} is not a free-mode spin calibration; "
            "a site can only be defined from one"
        )
    x0, y0, field_w, field_h = calibration.valid_mm
    if (x0, y0) != (0, 0):
        raise ValueError(
            f"a free-mode fence starts at (0, 0), got {list(calibration.valid_mm)}"
        )
    width, height = size_mm or (field_w, field_h)
    if width < field_w or height < field_h:
        raise ValueError(
            f"the robots span a {field_w} x {field_h} mm field, which does not fit "
            f"a {width} x {height} mm site"
        )
    dx, dy = (width - field_w) // 2, (height - field_h) // 2
    shift = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1.0]])
    anchor = f"self-defined from spin calibration {calibration.id8}"
    stations = []
    for st in calibration.stations:
        H = shift @ st.matrix
        H = H / H[2, 2]
        stations.append(
            StationSolution(
                index=st.index,
                homography=[[float(v) for v in row] for row in H],
                points=st.points,
                residual_mm=st.residual_mm,
                solved_from=st.solved_from,
            )
        )
    site = Site(
        name=name,
        anchor=anchor,
        extent_mm=(width, height),
        areas={"field": Area(dx, dy, field_w, field_h, "field", role="field")},
    )
    placed = Calibration(
        site=Site(name=name, anchor=anchor),
        valid_mm=(0, 0, width, height),
        placements=calibration.placements,
        stations=stations,
        tracks=calibration.tracks,
        created_at=calibration.created_at,
        tag=f"{calibration.tag}-{name}" if calibration.tag else "",
        robot=calibration.robot,
    )
    return site, placed
