# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Stage two: the pose of the robot near a seed point on the floor raster.

Three steps, each one settling a different thing:

1. `coarse_pose` puts the axle on the two red motor connectors and decides
   which end is the nose from where the green board mass lies relative to
   that axle. This is what settles the 180 degree question, and its two
   abort signals - `green_flare` and `tmpl_margin` - are what stop the
   estimator lying when it is out of its depth.
2. `template_search` scores a synthetic top-down robot against the frame's
   evidence maps, at the coarse heading and at the coarse heading plus 180.
   The difference, `tmpl_margin`, is the only thing the template produces:
   it says how much better the nose fits one way round than the other.
3. `OutlineFit` does a sub-pixel rigid fit of the real board outline to a
   signed board-versus-floor evidence map, which is what puts the centre and
   the heading where they are finally reported from.

HEADING CONVENTION IN THIS MODULE: degrees, `atan2(dy, dx)` with image y
growing down. `dotbot.camera.detection.robot.frame_pose` has the two
conventions and the conversion between them.

ROBOT FRAME: `OUTLINE_MM` and the offsets below are +x to the robot's right
and +y forward, origin at the outline centre. That is the frame `poly_px`
rotates by the heading above, and it is NOT the frame `dotbot.robots`
measures its own offsets in.
"""

from __future__ import annotations

import numpy as np

from dotbot.camera.detection.propose import floor_ab, floor_selector
from dotbot.robots import robot_geometry

_GEOMETRY = robot_geometry()
_CENTRE = _GEOMETRY.outline_centre


def _robot_frame(point):
    """A board-frame point in this module's robot frame (y flipped to forward)."""
    return (point.x - _CENTRE.x, _CENTRE.y - point.y)


# Outline centre to the axle, backwards.
AXLE_BEHIND_CENTRE_MM = -_robot_frame(_GEOMETRY.axle_midpoint)[1]

# Outline centre to the LH2 photodiode, forwards. The lighthouse reports the
# photodiode's position, so this is the offset that makes the camera's point
# and the lighthouse's point the same point.
PHOTODIODE_AHEAD_MM = _GEOMETRY.diode_ahead_of_centre_mm

# Board outline in the robot frame: an 84 mm nose and the step down to the
# 57 mm tail at y = +1.5.
OUTLINE_MM = np.array([_robot_frame(p) for p in _GEOMETRY.outline_path], float)

# Outline centre to the tip of the nose, forwards: the outline's own extent.
NOSE_AHEAD_MM = float(OUTLINE_MM[:, 1].max())

# The board is 94 mm across at the nose and 57 mm at the tail, so green mass
# further from the centre line than the tail's own half-width belongs to the
# nose and to nothing else. The 4.5 mm margin is a little over two raster
# pixels at 2 mm/px, which is what the board edge is blurred over.
TAIL_HALF_MM = float(np.abs(OUTLINE_MM[OUTLINE_MM[:, 1] < 1.5][:, 0]).max())
NOSE_BAND_MM = TAIL_HALF_MM + 4.5

# The two motor connectors, in the same robot frame.
CONN_MM = [
    np.array([(-19.5, -29.5), (-7.5, -29.5), (-7.5, -19.5), (-19.5, -19.5)], float),
    np.array([(7.5, -29.5), (19.5, -29.5), (19.5, -19.5), (7.5, -19.5)], float),
]

# The tyres, as the template draws them: the track between their centres,
# and one tyre's width and depth.
TRACK_MM = _GEOMETRY.track_mm
TYRE_W_MM = _GEOMETRY.tyre_width_mm
TYRE_D_MM = 40.0

# The template's canvas, as a half-width in millimetres: the robot at any
# heading, with room for the search to slide it.
TEMPLATE_HALF_MM = 78.0

SS = 4  # supersampling for anti-aliased template rendering

# Weighted pixels a coloured mass needs before a direction is fitted to it.
MIN_EVIDENCE_PX = 25

# A mask component smaller than this is not a robot: the footprint is about
# 9000 mm2, so this admits a badly cut one and rejects a marker or a cable.
MIN_COMPONENT_MM2 = 2500.0

# A refinement that wandered further than this is reporting something other
# than the robot the coarse pose found, so it is dropped and the coarse
# answer stands.
MAX_REFINE_SHIFT_MM = 14.0
MAX_REFINE_TURN_DEG = 18.0


# The outline fit's window, in millimetres: the board's 134 mm diagonal, so
# it holds the robot at any heading, plus the shift tolerance either side.
FIT_ROI_MM = 170.0


def axes(heading_deg):
    """The robot's right and forward unit vectors, as image pixel directions."""
    t = np.radians(heading_deg)
    forward = np.array([np.cos(t), np.sin(t)])
    return np.array([-forward[1], forward[0]]), forward


def _nelder_mead(f, x0, step, tol=1e-5, maxfev=1200):
    """Downhill simplex, stopping when the simplex is `tol` of one step wide."""
    x0 = np.asarray(x0, float)
    n = len(x0)
    sim = np.vstack([x0] + [x0 + np.eye(n)[i] * step[i] for i in range(n)])
    val = np.array([f(s) for s in sim])
    nf = n + 1
    while nf < maxfev:
        order = np.argsort(val)
        sim, val = sim[order], val[order]
        if np.max(np.abs(sim[1:] - sim[0]) / np.asarray(step)) < tol:
            break
        cen = sim[:-1].mean(0)
        xr = cen + (cen - sim[-1])
        fr = f(xr)
        nf += 1
        if fr < val[0]:
            xe = cen + 2.0 * (cen - sim[-1])
            fe = f(xe)
            nf += 1
            sim[-1], val[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < val[-2]:
            sim[-1], val[-1] = xr, fr
        else:
            xc = cen + 0.5 * ((xr if fr < val[-1] else sim[-1]) - cen)
            fc = f(xc)
            nf += 1
            if fc < min(fr, val[-1]):
                sim[-1], val[-1] = xc, fc
            else:
                sim[1:] = sim[0] + 0.5 * (sim[1:] - sim[0])
                val[1:] = [f(s) for s in sim[1:]]
                nf += n
    best = int(np.argmin(val))
    return sim[best], float(val[best])


def poly_px(pts_mm, cx, cy, heading_deg, mm_per_px):
    """Robot-frame millimetres to image pixels, at one pose."""
    right, forward = axes(heading_deg)
    p = np.asarray(pts_mm, float) / mm_per_px
    return np.stack(
        [
            cx + p[:, 0] * right[0] + p[:, 1] * forward[0],
            cy + p[:, 0] * right[1] + p[:, 1] * forward[1],
        ],
        1,
    )


def render(polys, n, cx, cy, heading_deg, mm_per_px):
    """Anti-aliased coverage of one or more polygons on an n x n grid."""
    import cv2  # lazy: opencv-python is only required to run the detector

    buf = np.zeros((n * SS, n * SS), np.uint8)
    for p in polys if isinstance(polys, (list, tuple)) else [polys]:
        q = poly_px(p, cx, cy, heading_deg, mm_per_px)
        cv2.fillPoly(buf, [np.round((q + 0.5) * SS).astype(np.int32)], 255)
    resized = cv2.resize(buf, (n, n), interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32) / 255.0


def features(bgr, keep_mask=None):
    """Scene-adaptive evidence maps, in robust sigmas above the floor's spread.

    `keep_mask` restricts the floor statistics to the pixels it marks, so the
    warp's black border does not shift the median a camera covering part of
    its area is measured against. The maps themselves are computed
    everywhere.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    value = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.float32)
    a, b, (ma, mb, sa, sb) = floor_ab(bgr, keep_mask)

    floor_of = floor_selector(keep_mask)
    mv = float(np.median(floor_of(value)))
    sv = max(mv - float(np.percentile(floor_of(value), 16.0)), 1.0)
    sab = float(np.hypot(sa, sb))
    chroma = np.hypot(a - ma, b - mb) / sab
    return dict(
        chroma=chroma,
        # Signed board-versus-floor evidence: +1 well inside the PCB, -1 on
        # carpet. The outline fit's gradient lives only on the polygon
        # boundary, so what this map has to get right is the edge, not the
        # interior texture.
        board=np.tanh((chroma - 3.0) / 2.0),
        green=np.clip((ma - a) / sa - 2.0, 0, None) * ((a - ma) / sa < 2.0),
        red=np.clip((a - ma) / sa - 3.0, 0, None),
        dark=np.clip((mv - value) / sv - 2.5, 0, None),
        bright=np.clip((value - mv) / sv - 3.0, 0, None),
    )


def robot_mask(features_map):
    """Anything coloured, dark or bright enough not to be floor."""
    import cv2  # lazy: opencv-python is only required to run the detector

    m = (
        (features_map["chroma"] > 2.5)
        | (features_map["dark"] > 0)
        | (features_map["bright"] > 0)
    ).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _wpca(px, py, w):
    """Weighted mean, principal direction and the two spreads about it."""
    s = w.sum()
    mu = np.array([(px * w).sum() / s, (py * w).sum() / s])
    x = np.stack([px - mu[0], py - mu[1]], 1)
    ev, evec = np.linalg.eigh((x * w[:, None]).T @ x / s)
    return mu, evec[:, -1], np.sqrt(np.maximum(ev, 0))


def _nose_flare(gx, gy, gw, centre, n, mm_per_px):
    """Signed share of the wide green mass lying ahead of `centre`, in [-1, 1].

    Only mass further from the centre line than `NOSE_BAND_MM` counts, which
    on this board is nose and never tail, and it is measured about the green
    mass's own centroid. A displacement of the whole mass therefore moves the
    mass and the point it is measured about together and cancels, which a
    distance from the differently-coloured axle does not.
    """
    d = np.array([-n[1], n[0]])
    ahead = (gx - centre[0]) * n[0] + (gy - centre[1]) * n[1]
    across = np.abs((gx - centre[0]) * d[0] + (gy - centre[1]) * d[1]) * mm_per_px
    wide = across > NOSE_BAND_MM
    front = gw[wide & (ahead > 0)].sum()
    back = gw[wide & (ahead < 0)].sum()
    if front + back <= 0:
        return 0.0
    return float((front - back) / (front + back))


def coarse_pose(features_map, reg, mm_per_px):
    """Axle from the red motor connectors, nose from the green board's shape.

    The lever, how far the green mass sits toward the nose from the axle, is
    what picks which end leads. `green_flare` is what a caller gates on: the
    board is wide at the nose and narrow at the tail, so the share of the
    wide green mass lying forward says which end is the nose without
    depending on where that mass sits relative to the axle.
    """
    red = features_map["red"] * reg
    ry, rx = np.nonzero(red > 0)
    if len(rx) >= MIN_EVIDENCE_PX:
        mu, d, _ = _wpca(rx.astype(float), ry.astype(float), red[ry, rx].astype(float))
    else:
        dk = features_map["dark"] * reg
        dy, dx = np.nonzero(dk > 0)
        if len(dx) < MIN_EVIDENCE_PX:
            return None
        mu, d, _ = _wpca(dx.astype(float), dy.astype(float), dk[dy, dx].astype(float))
    n = np.array([-d[1], d[0]])
    green = features_map["green"] * reg
    gy, gx = np.nonzero(green > 0)
    if len(gx) < MIN_EVIDENCE_PX:
        return None
    gw = green[gy, gx].astype(float)
    lever = (
        (((gx - mu[0]) * n[0] + (gy - mu[1]) * n[1]) * gw).sum() / gw.sum() * mm_per_px
    )
    if lever < 0:
        n, lever = -n, -lever
    d = np.array([-n[1], n[0]])
    heading = float(np.degrees(np.arctan2(n[1], n[0])))
    my, mx = np.nonzero(reg)
    v = ((mx - mu[0]) * d[0] + (my - mu[1]) * d[1]) * mm_per_px
    gc = np.array([(gx * gw).sum() / gw.sum(), (gy * gw).sum() / gw.sum()])
    out = dict(
        heading=heading,
        green_flare=_nose_flare(gx, gy, gw, gc, n, mm_per_px),
    )
    lat = float(np.median([(gc - mu) @ d, 0.0, 0.5 * (v.max() + v.min()) / mm_per_px]))
    out["coarse_centre"] = mu + d * lat + n * (AXLE_BEHIND_CENTRE_MM / mm_per_px)
    return out


class OutlineFit:
    """Sub-pixel rigid fit of the board outline to signed evidence.

    The window is `FIT_ROI_MM` across whatever the raster's scale, so a
    finer camera does not end up fitting inside a window smaller than the
    robot.
    """

    def __init__(self, features_map, mm_per_px, roi_mm=FIT_ROI_MM):
        self.bev = features_map["board"]
        self.mmpp = float(mm_per_px)
        self.roi = int(np.ceil(roi_mm / self.mmpp))

    def _win(self, c):
        n = self.roi
        h, w = self.bev.shape
        if h < n or w < n:
            return None
        x0 = min(max(int(round(c[0])) - n // 2, 0), w - n)
        y0 = min(max(int(round(c[1])) - n // 2, 0), h - n)
        return self.bev[y0 : y0 + n, x0 : x0 + n], x0, y0

    def score(self, c, heading, win=None):
        """Board evidence under the outline at one pose, normalised by its area."""
        if win is None:
            win = self._win(c)
        if win is None:
            return -1e9
        board, x0, y0 = win
        n = self.roi
        template = render(OUTLINE_MM, n, c[0] - x0, c[1] - y0, heading, self.mmpp)
        s = float(template.sum())
        if s < 1:
            return -1e9
        return float((board * template).sum()) / np.sqrt(s)

    def refine(self, c0, heading0):
        """The best pose near `(c0, heading0)` as (centre, heading), or None."""
        win = self._win(c0)
        if win is None:
            return None
        _, x0, y0 = win
        n = self.roi

        def neg(p):
            if not (8 < p[0] - x0 < n - 8 and 8 < p[1] - y0 < n - 8):
                return 1e9
            return -self.score((p[0], p[1]), p[2], win)

        st = [0.8, 0.8, 2.0]
        p, _ = _nelder_mead(neg, [c0[0], c0[1], heading0], st)
        p, _ = _nelder_mead(neg, p, [s * 0.25 for s in st])
        return np.array([p[0], p[1]]), float(p[2])


class Template:
    """Synthetic top-down DotBot, used only for the 180 degree margin check."""

    def __init__(self, mm_per_px):
        import cv2  # lazy: opencv-python is only required to run the detector

        self.mmpp = float(mm_per_px)
        n = int(2 * TEMPLATE_HALF_MM / self.mmpp) // 2 * 2 + 1
        self.n = n

        def poly(canvas, pts):
            k = n / 2.0
            cv2.fillPoly(
                canvas,
                [
                    np.array(
                        [[k + x / self.mmpp, k - y / self.mmpp] for x, y in pts],
                        np.int32,
                    )
                ],
                1.0,
            )

        board = np.zeros((n, n), np.float32)
        wheel = np.zeros_like(board)
        conn = np.zeros_like(board)
        poly(board, OUTLINE_MM)
        axle = -AXLE_BEHIND_CENTRE_MM
        for side in (-1, 1):
            x0 = side * TRACK_MM / 2 - TYRE_W_MM / 2
            x1 = side * TRACK_MM / 2 + TYRE_W_MM / 2
            poly(
                wheel,
                [
                    (x0, axle - TYRE_D_MM / 2),
                    (x1, axle - TYRE_D_MM / 2),
                    (x1, axle + TYRE_D_MM / 2),
                    (x0, axle + TYRE_D_MM / 2),
                ],
            )
        for side in (-13.5, 13.5):
            poly(
                conn,
                [
                    (side - 6, axle - 5),
                    (side + 6, axle - 5),
                    (side + 6, axle + 5),
                    (side - 6, axle + 5),
                ],
            )
        self.maps = dict(
            green=np.clip(board - wheel - conn, 0, 1), dark=wheel, red=conn
        )

    def rot(self, key, heading_deg):
        """One evidence map of the template, turned to `heading_deg`."""
        import cv2  # lazy: opencv-python is only required to run the detector

        n = self.n
        centre = (n / 2 - 0.5, n / 2 - 0.5)
        m = cv2.getRotationMatrix2D(centre, -(heading_deg + 90.0), 1.0)
        return cv2.warpAffine(
            self.maps[key], m, (n, n), flags=cv2.INTER_LINEAR, borderValue=0
        )


def template_search(features_map, centre, tmpl, angles, search_mm=10.0):
    """The best score the template reaches at each of `angles`."""
    import cv2  # lazy: opencv-python is only required to run the detector

    ev = {
        "green": features_map["green"],
        "dark": features_map["dark"],
        "red": features_map["red"],
    }
    n, s = tmpl.n, int(np.ceil(search_mm / tmpl.mmpp))
    pad = n // 2 + s + 2
    ev = {
        k: cv2.copyMakeBorder(v, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        for k, v in ev.items()
    }
    cx, cy = int(round(centre[0])) + pad, int(round(centre[1])) + pad
    half = n // 2
    x0, y0 = cx - half - s, cy - half - s
    win = {k: v[y0 : y0 + n + 2 * s, x0 : x0 + n + 2 * s].copy() for k, v in ev.items()}
    scores = {}
    for ang in angles:
        tot = None
        for k in ("green", "dark", "red"):
            r = cv2.matchTemplate(win[k], tmpl.rot(k, float(ang)), cv2.TM_CCOEFF_NORMED)
            tot = r if tot is None else tot + r
        scores[float(ang)] = float(tot.max())
    return scores


def pose_one(features_map, reg, mm_per_px, tmpl, fit):
    """Pose of the one robot the region `reg` covers, or None.

    `centre`, `heading`, `green_flare`, `tmpl_margin` and `refined` are what
    a caller reads.
    """
    out = coarse_pose(features_map, reg, mm_per_px)
    if out is None:
        return None
    out["centre"] = out["coarse_centre"]
    out["refined"] = False
    # The template answers one question: is the nose at the coarse heading or
    # at its flip? Two scores answer it, and nothing else the template could
    # say is used - the pose comes from the outline fit below, seeded and
    # bounded by the coarse heading, never by this.
    ahead, behind = out["heading"], out["heading"] + 180.0
    scores = template_search(features_map, out["centre"], tmpl, [ahead, behind])
    out["tmpl_margin"] = scores[float(ahead)] - scores[float(behind)]
    # Nelder-Mead can stop short of the optimum when the evidence is soft
    # (blurred or low-contrast scenes), leaving the answer dependent on
    # where it started. Restart from its own output until it stops moving.
    r = fit.refine(out["centre"], out["heading"])
    for _ in range(3):
        if r is None:
            break
        r2 = fit.refine(r[0], r[1])
        if r2 is None:
            break
        if np.linalg.norm(r2[0] - r[0]) < 0.02 and abs(r2[1] - r[1]) < 0.02:
            r = r2
            break
        r = r2
    if r is not None:
        c, th = r
        # The limits are measured from the coarse pose, which is what
        # stops a fit wandering off this robot onto something else.
        moved = float(np.linalg.norm(c - out["coarse_centre"])) * mm_per_px
        turned = abs(((th - out["heading"]) + 180) % 360 - 180)
        if moved <= MAX_REFINE_SHIFT_MM and turned <= MAX_REFINE_TURN_DEG:
            out["centre"], out["heading"], out["refined"] = c, float(th), True
    return out


def pose_at(
    seed_px,
    mm_per_px,
    features_map,
    mask,
    tmpl,
    fit,
    win_mm=110.0,
    snap_mm=45.0,
):
    """Pose of the robot near `seed_px`.

    Tolerates a seed tens of millimetres off: the region is the mask
    component whose centroid is nearest the seed, within `snap_mm`.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    h, w = mask.shape
    r = int(round(win_mm / mm_per_px))
    x0, y0 = max(0, int(seed_px[0]) - r), max(0, int(seed_px[1]) - r)
    x1, y1 = min(w, int(seed_px[0]) + r), min(h, int(seed_px[1]) + r)
    sub = np.zeros_like(mask)
    sub[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(sub, 8)
    best, best_dist = None, None
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] * mm_per_px**2 < MIN_COMPONENT_MM2:
            continue
        dd = (
            float(np.hypot(centroids[k][0] - seed_px[0], centroids[k][1] - seed_px[1]))
            * mm_per_px
        )
        if dd > snap_mm:
            continue
        if best_dist is None or dd < best_dist:
            best, best_dist = k, dd
    if best is None:
        return None
    return pose_one(features_map, labels == best, mm_per_px, tmpl, fit)
