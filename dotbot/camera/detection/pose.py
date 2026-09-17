# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Stage two: the pose of the robot near a seed point on the floor raster.

Three steps, each one settling a different thing:

1. `coarse_pose` puts the axle on the two red motor connectors and decides
   which end is the nose from where the green board mass lies relative to
   that axle. This is what settles the 180 degree question, and its two
   abort signals - `green_lever_mm` and `tmpl_margin` - are what stop the
   estimator lying when it is out of its depth.
2. `template_search` scores a synthetic top-down robot against the frame's
   evidence maps, at the coarse heading and at the coarse heading plus 180.
   The difference, `tmpl_margin`, is the only thing the template produces:
   it says how much better the nose fits one way round than the other.
3. `OutlineFit` does a sub-pixel rigid fit of the real board outline to a
   signed board-versus-floor evidence map, which is what puts the centre and
   the heading where they are finally reported from.

HEADING CONVENTION IN THIS MODULE: degrees, `atan2(dy, dx)` with image y
growing down, so 0 points along +x (frame right) and +90 along +y (frame
down). `dotbot.camera.detection.robot` converts it to the robot `direction`
convention the firmware and the console use; nothing here does.

ROBOT FRAME: `OUTLINE_MM` and the offsets below are +x to the robot's right
and +y forward, origin at the outline centre. That is the frame `poly_px`
rotates by the heading above, and it is NOT the frame `dotbot.robots`
measures its own offsets in.
"""

from __future__ import annotations

import numpy as np

from dotbot.camera.detection.propose import as_bgr
from dotbot.robots import robot_geometry

_GEOMETRY = robot_geometry()

# Outline centre to the axle, backwards.
AXLE_BEHIND_CENTRE_MM = 24.5

# Outline centre to the LH2 photodiode, forwards. The lighthouse reports the
# photodiode's position, so this is the offset that makes the camera's point
# and the lighthouse's point the same point.
PHOTODIODE_AHEAD_MM = _GEOMETRY.board_length_mm / 2 - _GEOMETRY.diode_to_front_mm

# Board outline in the robot frame, transcribed from the Edge.Cuts layer of
# the v3 main board: an 84 mm nose and the step down to the 57 mm tail at
# y = +1.5.
OUTLINE_MM = np.array(
    [
        (-42.0, 47.5),
        (42.0, 47.5),
        (42.0, 40.5),
        (43.0, 39.5),
        (47.0, 39.5),
        (47.0, 1.5),
        (28.5, 1.5),
        (28.5, -47.5),
        (-28.5, -47.5),
        (-28.5, 1.5),
        (-47.0, 1.5),
        (-47.0, 39.5),
        (-43.0, 39.5),
        (-42.0, 40.5),
    ],
    float,
)

# Outline centre to the tip of the nose, forwards: the outline's own extent.
NOSE_AHEAD_MM = float(OUTLINE_MM[:, 1].max())

# The two motor connectors, in the same robot frame.
CONN_MM = [
    np.array([(-19.5, -29.5), (-7.5, -29.5), (-7.5, -19.5), (-19.5, -19.5)], float),
    np.array([(7.5, -29.5), (19.5, -29.5), (19.5, -19.5), (7.5, -19.5)], float),
]

# The tyres, as the template draws them: the track between their centres,
# and one tyre's width and depth.
TRACK_MM = 85.0
TYRE_W_MM = 18.0
TYRE_D_MM = 40.0

SS = 4  # supersampling for anti-aliased template rendering

# A refinement that wandered further than this is reporting something other
# than the robot the coarse pose found, so it is dropped and the coarse
# answer stands.
MAX_REFINE_SHIFT_MM = 14.0
MAX_REFINE_TURN_DEG = 18.0


# The outline fit's window, in millimetres: a 95 mm robot plus the shift
# tolerance either side.
FIT_ROI_MM = 170.0


def _mad(x, med):
    """Robust scale, floored at one 8-bit step.

    An 8-bit chroma channel's smallest real spread is one step; below that
    the floor itself reads as outliers and the evidence maps saturate.
    """
    return max(1.4826 * float(np.median(np.abs(x - med))), 1.0)


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


def poly_px(pts_mm, cx, cy, heading_deg, mm_per_px, scale=1.0):
    """Robot-frame millimetres to image pixels, at one pose."""
    right, forward = axes(heading_deg)
    p = np.asarray(pts_mm, float) * scale / mm_per_px
    return np.stack(
        [
            cx + p[:, 0] * right[0] + p[:, 1] * forward[0],
            cy + p[:, 0] * right[1] + p[:, 1] * forward[1],
        ],
        1,
    )


def render(polys, n, cx, cy, heading_deg, mm_per_px, scale=1.0):
    """Anti-aliased coverage of one or more polygons on an n x n grid."""
    import cv2  # lazy: opencv-python is only required to run the detector

    buf = np.zeros((n * SS, n * SS), np.uint8)
    for p in polys if isinstance(polys, (list, tuple)) else [polys]:
        q = poly_px(p, cx, cy, heading_deg, mm_per_px, scale)
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

    bgr = as_bgr(bgr)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    value = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.float32)
    a, b = lab[:, :, 1], lab[:, :, 2]

    if keep_mask is None:
        floor_of = lambda m: m[::3, ::3].ravel()  # noqa: E731
    else:
        kept = np.asarray(keep_mask)[::3, ::3] > 0
        if kept.sum() < 64:
            kept = np.ones_like(kept, bool)
        floor_of = lambda m: m[::3, ::3][kept]  # noqa: E731

    ma, mb, mv = (float(np.median(floor_of(m))) for m in (a, b, value))
    sa, sb = _mad(floor_of(a), ma), _mad(floor_of(b), mb)
    sv = max(mv - float(np.percentile(floor_of(value), 16.0)), 1.0)
    sab = float(np.hypot(sa, sb))
    chroma = np.hypot(a - ma, b - mb) / sab
    return dict(
        a=a,
        b=b,
        V=value,
        floor=(ma, mb, mv, sa, sb, sv),
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


def robot_mask(features_map, chroma_sigma=2.5, close_px=5):
    """Anything coloured, dark or bright enough not to be floor."""
    import cv2  # lazy: opencv-python is only required to run the detector

    m = (
        (features_map["chroma"] > chroma_sigma)
        | (features_map["dark"] > 0)
        | (features_map["bright"] > 0)
    ).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_px, close_px))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _wpca(px, py, w):
    """Weighted mean, principal direction and the two spreads about it."""
    s = w.sum()
    mu = np.array([(px * w).sum() / s, (py * w).sum() / s])
    x = np.stack([px - mu[0], py - mu[1]], 1)
    ev, evec = np.linalg.eigh((x * w[:, None]).T @ x / s)
    return mu, evec[:, -1], np.sqrt(np.maximum(ev, 0))


def coarse_pose(features_map, reg, mm_per_px):
    """Axle from the red motor connectors, nose from the green mass ahead of it.

    `green_lever_mm` is how far the green board mass sits toward the nose
    from the axle. It is the signal that decides the nose end, so a small
    value means the estimator could not tell the two ends apart.
    """
    red = features_map["red"] * reg
    ry, rx = np.nonzero(red > 0)
    if len(rx) >= 25:
        mu, d, ex = _wpca(rx.astype(float), ry.astype(float), red[ry, rx].astype(float))
        axis_src = "red-bar"
    else:
        dk = features_map["dark"] * reg
        dy, dx = np.nonzero(dk > 0)
        if len(dx) < 25:
            return None
        mu, d, ex = _wpca(dx.astype(float), dy.astype(float), dk[dy, dx].astype(float))
        axis_src = "tyres"
    n = np.array([-d[1], d[0]])
    green = features_map["green"] * reg
    gy, gx = np.nonzero(green > 0)
    if len(gx) < 25:
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
    u = ((mx - mu[0]) * n[0] + (my - mu[1]) * n[1]) * mm_per_px
    v = ((mx - mu[0]) * d[0] + (my - mu[1]) * d[1]) * mm_per_px
    corr = np.abs(v) < 26.0
    su = (gx - mu[0]) * n[0] + (gy - mu[1]) * n[1]
    out = dict(
        heading=heading,
        axle_pt=mu,
        n=n,
        d=d,
        axis_src=axis_src,
        axis_len_mm=float(ex[-1] * mm_per_px),
        green_lever_mm=float(lever),
        ext_fwd_mm=float(u[corr].max()),
        ext_rear_mm=float(-u[corr].min()),
        green_ratio=float(gw[su > 0].sum() / max(gw[su <= 0].sum(), 1e-9)),
    )
    gc = np.array([(gx * gw).sum() / gw.sum(), (gy * gw).sum() / gw.sum()])
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

    def score(self, c, heading, scale=1.0, win=None):
        """Board evidence under the outline at one pose, normalised by its area."""
        if win is None:
            win = self._win(c)
        if win is None:
            return -1e9
        board, x0, y0 = win
        n = self.roi
        template = render(
            OUTLINE_MM, n, c[0] - x0, c[1] - y0, heading, self.mmpp, scale
        )
        s = float(template.sum())
        if s < 1:
            return -1e9
        return float((board * template).sum()) / np.sqrt(s)

    def refine(self, c0, heading0, scale=1.0, free_scale=False):
        """The best pose near `(c0, heading0)`, or None off the raster."""
        win = self._win(c0)
        if win is None:
            return None
        _, x0, y0 = win
        n = self.roi

        def neg(p):
            if not (8 < p[0] - x0 < n - 8 and 8 < p[1] - y0 < n - 8):
                return 1e9
            sc = p[3] if free_scale else scale
            if free_scale and not (0.85 < sc < 1.15):
                return 1e9
            return -self.score((p[0], p[1]), p[2], sc, win)

        p0 = [c0[0], c0[1], heading0] + ([scale] if free_scale else [])
        st = [0.8, 0.8, 2.0] + ([0.01] if free_scale else [])
        p, _ = _nelder_mead(neg, p0, st)
        p, v = _nelder_mead(neg, p, [s * 0.25 for s in st])
        return (
            np.array([p[0], p[1]]),
            float(p[2]),
            float(p[3] if free_scale else scale),
            -v,
        )


class Template:
    """Synthetic top-down DotBot, used only for the 180 degree margin check."""

    def __init__(
        self,
        mm_per_px,
        half_mm=78.0,
        track=TRACK_MM,
        tyre_w=TYRE_W_MM,
        tyre_d=TYRE_D_MM,
    ):
        import cv2  # lazy: opencv-python is only required to run the detector

        self.mmpp = float(mm_per_px)
        n = int(2 * half_mm / self.mmpp) // 2 * 2 + 1
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
            x0 = side * track / 2 - tyre_w / 2
            x1 = side * track / 2 + tyre_w / 2
            poly(
                wheel,
                [
                    (x0, axle - tyre_d / 2),
                    (x1, axle - tyre_d / 2),
                    (x1, axle + tyre_d / 2),
                    (x0, axle + tyre_d / 2),
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
    """Best template match over `angles`, as (score, angle, x, y)."""
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
    best, scores = None, {}
    for ang in angles:
        tot = None
        for k in ("green", "dark", "red"):
            r = cv2.matchTemplate(win[k], tmpl.rot(k, float(ang)), cv2.TM_CCOEFF_NORMED)
            tot = r if tot is None else tot + r
        mx = float(tot.max())
        iy, ix = np.unravel_index(tot.argmax(), tot.shape)
        scores[float(ang)] = mx
        if best is None or mx > best[0]:
            best = (mx, float(ang), x0 + ix + half - pad, y0 + iy + half - pad)
    return best, scores


def pose_one(features_map, reg, mm_per_px, tmpl=None, refine=True, fit=None):
    """Pose of the one robot the region `reg` covers, or None.

    `centre`, `heading`, `green_lever_mm`, `tmpl_margin` and `refined` are
    what a caller reads; the rest of the dict is tuning diagnostics and may
    go without notice.
    """
    out = coarse_pose(features_map, reg, mm_per_px)
    if out is None:
        return None
    out["centre"] = out["coarse_centre"]
    out["refined"] = False
    if refine and tmpl is not None:
        # The template answers one question: is the nose at the coarse
        # heading or at its flip? Two scores answer it, and nothing else the
        # template could say is used - the pose comes from the outline fit
        # below, seeded and bounded by the coarse heading, never by this.
        ahead, behind = out["heading"], out["heading"] + 180.0
        _, scores = template_search(features_map, out["centre"], tmpl, [ahead, behind])
        out["tmpl_margin"] = scores[float(ahead)] - scores[float(behind)]
    if refine:
        if fit is None:
            fit = OutlineFit(features_map, mm_per_px)
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
            c, th, _, sv = r
            # The limits are measured from the coarse pose, which is what
            # stops a fit wandering off this robot onto something else.
            moved = float(np.linalg.norm(c - out["coarse_centre"])) * mm_per_px
            turned = abs(((th - out["heading"]) + 180) % 360 - 180)
            out.update(fit_shift_mm=moved, fit_turn_deg=turned, fit_score=sv)
            if moved <= MAX_REFINE_SHIFT_MM and turned <= MAX_REFINE_TURN_DEG:
                out["centre"], out["heading"], out["refined"] = c, float(th), True
    return out


def pose_at(
    bgr,
    seed_px,
    mm_per_px,
    refine=True,
    features_map=None,
    mask=None,
    win_mm=110.0,
    snap_mm=45.0,
    tmpl=None,
    fit=None,
):
    """Pose of the robot near `seed_px`.

    Tolerates a seed tens of millimetres off: the region is the mask
    component whose centroid is nearest the seed, within `snap_mm`.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    bgr = as_bgr(bgr)
    if features_map is None:
        features_map = features(bgr)
    if mask is None:
        mask = robot_mask(features_map)
    h, w = mask.shape
    r = int(round(win_mm / mm_per_px))
    x0, y0 = max(0, int(seed_px[0]) - r), max(0, int(seed_px[1]) - r)
    x1, y1 = min(w, int(seed_px[0]) + r), min(h, int(seed_px[1]) + r)
    sub = np.zeros_like(mask)
    sub[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(sub, 8)
    best, best_dist = None, None
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] * mm_per_px**2 < 2500:
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
    if refine and tmpl is None:
        tmpl = Template(mm_per_px)
    if refine and fit is None:
        fit = OutlineFit(features_map, mm_per_px)
    p = pose_one(features_map, labels == best, mm_per_px, tmpl, refine, fit)
    if p is not None:
        p["area_mm2"] = float(stats[best, cv2.CC_STAT_AREA] * mm_per_px**2)
        p["seed_dist_mm"] = best_dist
    return p
