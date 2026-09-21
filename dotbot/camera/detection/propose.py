# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Stage one: where on the floor raster a robot-sized object might be.

Every length here is a multiple of `ROBOT_MM` and every threshold is in
floor-sigmas, so nothing depends on the camera's `mm_per_px`. The response
is a difference of two box means - one robot across against three robots
across - whitened by the floor's own per-channel spread, which rejects
everything finer than a robot (carpet, sensor noise, JPEG blocks) and
everything coarser than a few robots (vignetting, lighting gradients).

Candidates are peaks rather than connected components, taken greedily best
first with one robot's separation enforced on the final centres, so no
morphology can bridge two objects into one blob.

`verify` adds the colour check to those candidates: a robot carries
coloured parts and a floor does not. That check is measured against the
floor this camera is actually seeing, in the floor's own chroma spread, so
it is the same kind of quantity as the response above it.
"""

from __future__ import annotations

import numpy as np

ROBOT_MM = 95.0  # DotBot footprint, a physical fact

# Design constants, all in units of the robot or of the floor's own noise.
SAMPLES_PER_ROBOT = 12.0  # working grid: a robot spans this many px
INNER_FRAC = 1.0  # matched-filter box = one robot across
OUTER_FRAC = 3.0  # local background = three robots across
NMS_FRAC = 1.0  # two candidates must be at least one robot apart
REFINE_FRAC = 0.75  # re-centring window half-width: the robot, plus peak error
# Floor-sigmas. Recall is flat for k <= 5 and false positives fall about
# tenfold from k = 5 to k = 9, so this is a trade-off, not an optimum: raise
# it toward 9 if a phantom costs more than a miss.
K_SIGMA = 6.0
MIN_VALID = 1.00  # the robot's whole footprint must be on known floor
MAX_OUT = 48  # candidate budget, about a third of the cells in a square metre

# The colour check: how much of the candidate's crop carries colour the floor
# does not. A pixel counts once its a*/b* distance from the floor's own centre
# clears `CHROMA_K` of the floor's own chroma spread, which is the same
# self-calibrating metric the response above is scored in. White balance,
# exposure and the compression of the source all move a candidate's chroma and
# the floor's together, so they cancel here; an absolute level cannot, and the
# level that separates the two is a property of the room, not of the detector.
CHROMA_K = 6.0
CHROMA_MIN = 2.0
CHROMA_CROP_FRAC = 0.6  # the verdict's window, in robots either side of the centre

# What a peak must already carry, before it is worth re-centring at full
# resolution. A peak sits up to half a robot from the object it found, so this
# window spans the verdict's own window plus how far `_refine` can move the
# centre. The threshold is a quarter of `CHROMA_MIN` rescaled by the area
# ratio, so it asks for the same absolute colour over the larger window.
PRE_CROP_FRAC = CHROMA_CROP_FRAC + REFINE_FRAC
PRE_CHROMA_SCALE = (CHROMA_CROP_FRAC / PRE_CROP_FRAC) ** 2
PRE_CHROMA_MIN = CHROMA_MIN / 4 * PRE_CHROMA_SCALE


def as_bgr(frame):
    """`frame` as three channels, passing a colour frame straight through.

    A grayscale source carries no chroma, so nothing downstream can find a
    robot in it; converting rather than refusing keeps a grayscale camera a
    served layer with no detection instead of a crashing thread.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    frame = np.asarray(frame)
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return frame


def _robust_sigma(values, med=None):
    """MAD-based scale, about `med` or about the values' own median."""
    if med is None:
        med = float(np.median(values))
    return 1.4826 * float(np.median(np.abs(values - med)))


def floor_selector(keep_mask):
    """The subsample of pixels the floor statistics are taken over.

    `keep_mask` marks the floor a camera can see, so the warp's black border
    does not shift the median every chroma is measured against.
    """
    if keep_mask is None:
        return lambda m: m[::3, ::3].ravel()  # noqa: E731
    kept = np.asarray(keep_mask)[::3, ::3] > 0
    if kept.sum() < 64:
        kept = np.ones_like(kept, bool)
    return lambda m: m[::3, ::3][kept]  # noqa: E731


def floor_ab(bgr, keep_mask=None):
    """The a* and b* planes, and the floor's own centre and spread in them.

    Returns `(a, b, (ma, mb, sa, sb))` in OpenCV's 8-bit Lab units. Only
    differences from the floor's centre are ever taken, so the 128 offset
    those channels carry cancels and is left in place.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    a, b = lab[:, :, 1], lab[:, :, 2]
    floor_of = floor_selector(keep_mask)
    ma, mb = (float(np.median(floor_of(m))) for m in (a, b))
    # Floored at one 8-bit step, which is a chroma channel's smallest real
    # spread; below it the floor reads as outliers and the maps saturate.
    sa, sb = (
        max(_robust_sigma(floor_of(plane), med), 1.0)
        for plane, med in ((a, ma), (b, mb))
    )
    return a, b, (ma, mb, sa, sb)


def _coloured(chroma, centre, half, k=CHROMA_K):
    """Per cent of a box around `centre` carrying colour the floor does not.

    A robot carries coloured parts and a floor does not, which is the only
    thing that separates the two by the time a candidate is this size.
    """
    x, y = int(centre[0]), int(centre[1])
    crop = chroma[max(0, y - half) : y + half, max(0, x - half) : x + half]
    if crop.size == 0:
        return 0.0
    return float((crop > k).mean()) * 100


def _true_lab(bgr):
    """CIE L*a*b* in its own units, so a Euclidean norm is dE76.

    OpenCV packs 8-bit Lab as L*2.55 with a and b offset by 128, which
    weights lightness 2.55x against chroma; undo the packing so the
    whitening below can decide the channel weights from the data.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[:, :, 0] *= 100.0 / 255.0
    lab[:, :, 1] -= 128.0
    lab[:, :, 2] -= 128.0
    return lab


def _odd(n):
    """`n` rounded to the nearest odd integer, at least 3."""
    return max(3, int(round(n)) | 1)


def _masked_box_mean(img, valid, ks):
    """Mean of `img` over a `ks` x `ks` box, counting only valid pixels.

    Normalised convolution. A box straddling a masked-out region would
    otherwise average in zeros and ring a false response along its edge;
    `BORDER_CONSTANT` on both numerator and weight makes outside-the-raster
    not exist rather than mirror into structure along every edge.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    border = cv2.BORDER_CONSTANT
    weight = cv2.boxFilter(valid, -1, (ks, ks), normalize=False, borderType=border)
    num = cv2.boxFilter(
        img * valid[:, :, None], -1, (ks, ks), normalize=False, borderType=border
    )
    return num / np.maximum(weight, 1e-6)[:, :, None], weight / float(ks * ks)


def response(bgr, keep_mask, mm_per_px):
    """Whitened matched-filter response, in floor-sigmas.

    Returns `(R, ok, work_mmpp, (sx, sy), sigma, background)`, where `R` is a
    Mahalanobis distance in the floor's own per-channel noise metric and
    `(sx, sy)` scales working-grid pixels back to input pixels.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    robot_mm = ROBOT_MM
    # Work at a fixed number of samples per robot. The robust noise estimate
    # below needs a median over every floor pixel, which is an order of
    # magnitude cheaper here than at full resolution, and box-averaging
    # before decimating is both the anti-alias low-pass and the first half of
    # the band-pass. Never upsample: a camera already coarser than the grid
    # is used as it is.
    work_mmpp = max(robot_mm / SAMPLES_PER_ROBOT, mm_per_px)
    h, w = bgr.shape[:2]
    sc = work_mmpp / mm_per_px
    ww, wh = max(8, int(round(w / sc))), max(8, int(round(h / sc)))
    sx, sy = w / ww, h / wh

    def _shrink(a):
        if (ww, wh) == (w, h):
            return a
        f = int(round(sc))
        if f < 2:  # too small a step to alias; area-average it
            return cv2.resize(a, (ww, wh), interpolation=cv2.INTER_AREA)
        # box-average then decimate: the same thing as INTER_AREA here, cheaper
        return cv2.resize(
            cv2.blur(a, (f, f)), (ww, wh), interpolation=cv2.INTER_NEAREST
        )

    small = _shrink(bgr)
    valid = (
        np.ones((wh, ww), np.float32)
        if keep_mask is None
        else (_shrink(keep_mask) > 127).astype(np.float32)
    )

    lab = _true_lab(small)
    m_in, f_in = _masked_box_mean(lab, valid, _odd(INNER_FRAC * robot_mm / work_mmpp))
    m_out, f_out = _masked_box_mean(lab, valid, _odd(OUTER_FRAC * robot_mm / work_mmpp))
    diff = m_in - m_out

    # A robot's whole footprint must lie on known floor for its colour to
    # mean anything, and it needs at least half a surround to be measured
    # against. That costs a half-robot band along the floor boundary, where
    # a robot could not be measured anyway.
    ok = (valid > 0) & (f_in >= MIN_VALID - 1e-6) & (f_out >= 0.5)
    if ok.sum() < 64:
        zero = np.zeros((wh, ww), np.float32)
        return zero, ok, work_mmpp, (sx, sy), np.ones(3, np.float32), m_out

    # Whiten per channel by the floor's own spread, which is self-calibrating
    # since the floor is whatever the median of the frame is. The clamp is the
    # 8-bit quantisation limit propagated through the averaging, below which a
    # measured spread is only rounding: one LSB is 1/sqrt(12) uniform,
    # averaged over the inner box, doubled for the difference of two means.
    n_in = max(1.0, (INNER_FRAC * robot_mm / work_mmpp) ** 2)
    floor_q = np.sqrt(2.0 / (12.0 * n_in))
    sigma = np.empty(3, np.float32)
    for channel in range(3):
        spread = _robust_sigma(diff[:, :, channel][ok])
        sigma[channel] = max(spread, floor_q * (100.0 / 255.0 if channel == 0 else 1.0))

    scored = np.sqrt(((diff / sigma) ** 2).sum(axis=2)).astype(np.float32)
    scored[~ok] = 0.0
    return scored, ok, work_mmpp, (sx, sy), sigma, m_out


def propose(bgr, keep_mask, mm_per_px, chroma):
    """Candidate robot-sized objects, as dicts with `centre` in input px.

    `chroma` is the floor-relative chroma field of this frame, measured once
    by the caller and read here rather than paid for twice.
    """
    robot_mm = ROBOT_MM
    scored, ok, work_mmpp, (sx, sy), sigma, m_out = response(bgr, keep_mask, mm_per_px)

    hits = np.argwhere(scored > K_SIGMA)
    if hits.size == 0:
        return []
    z = scored[hits[:, 0], hits[:, 1]]
    order = np.argsort(-z)

    rad = max(1, int(round(NMS_FRAC * robot_mm / work_mmpp)))
    taken = np.zeros(scored.shape, bool)
    out = []
    for i in order:
        y, x = int(hits[i, 0]), int(hits[i, 1])
        if taken[y, x]:
            continue
        taken[max(0, y - rad) : y + rad + 1, max(0, x - rad) : x + rad + 1] = True
        # The response is smooth, so parabolic interpolation recovers
        # position below the working grid.
        fx = _subpix(scored, x, y, 1, 0)
        fy = _subpix(scored, x, y, 0, 1)
        cx, cy = (x + fx) * sx, (y + fy) * sy
        # The response answers for anything robot-sized, printed sheets
        # included. A peak carrying no colour anywhere `_refine` could take it
        # cannot become a robot, so it is dropped before the work rather than
        # after. The window is the peak's own uncertainty, not the verdict's:
        # testing the verdict's window here asks about a point the peak has
        # not earned, and drops robots whose peak sat beside them.
        half = int(PRE_CROP_FRAC * robot_mm / mm_per_px)
        if _coloured(chroma, (cx, cy), half) < PRE_CHROMA_MIN:
            continue
        cx, cy = _refine(bgr, cx, cy, m_out[y, x], sigma, robot_mm, mm_per_px)
        # The one-robot separation has to hold on the final centres:
        # enforcing it only on the working grid lets refinement slide several
        # candidates onto the same robot, and a second hit on a robot already
        # found is a false positive.
        sep = robot_mm / mm_per_px
        if any(
            (cx - o["centre"][0]) ** 2 + (cy - o["centre"][1]) ** 2 < sep * sep
            for o in out
        ):
            continue
        out.append({"centre": np.array([cx, cy]), "z": float(z[i])})
        if len(out) >= MAX_OUT:
            break
    return out


def _refine(bgr, cx, cy, bg, sigma, robot_mm, mm_per_px, rfrac=REFINE_FRAC):
    """Re-centre on the object's own silhouette at full resolution.

    A matched-filter peak locates an object but does not centre on it: the
    response surface is skewed wherever the object sits on some larger
    structure's flank, far enough to walk the colour check's sampling window
    off the robot. The outline is taken at half the object's own contrast, with the
    99th percentile standing in for the maximum so one specular pixel on a
    tyre cannot set the level.
    """
    r = max(2, int(round(rfrac * robot_mm / mm_per_px)))
    x0, y0 = max(0, int(cx) - r), max(0, int(cy) - r)
    crop = bgr[y0 : int(cy) + r + 1, x0 : int(cx) + r + 1]
    if crop.size == 0:
        return cx, cy
    e = np.linalg.norm((_true_lab(crop) - bg) / sigma, axis=2)
    w = (e > 0.5 * np.percentile(e, 99)).astype(np.float32)
    tot = w.sum()
    if tot <= 0:
        return cx, cy
    gy, gx = np.mgrid[0 : crop.shape[0], 0 : crop.shape[1]]
    return x0 + float((w * gx).sum() / tot), y0 + float((w * gy).sum() / tot)


def _subpix(scored, x, y, dx, dy):
    """Parabolic peak offset along one axis, clamped to a cell either way."""
    h, w = scored.shape
    if x - dx < 0 or y - dy < 0 or x + dx >= w or y + dy >= h:
        return 0.0
    a = float(scored[y - dy, x - dx])
    b = float(scored[y, x])
    c = float(scored[y + dy, x + dx])
    den = a - 2 * b + c
    if abs(den) < 1e-9:
        return 0.0
    return float(np.clip(0.5 * (a - c) / den, -1.0, 1.0))


def verify(bgr, keep_mask, mm_per_px, chroma):
    """`propose`'s candidates with the colour verdict on each, as `robot`.

    The frame's chroma field is measured once and read per candidate, so a
    generous proposer stays affordable. The verdict is taken at the
    re-centred position, which is the one a pose is seeded from.
    """
    cands = propose(bgr, keep_mask, mm_per_px, chroma)
    if not cands:
        return []
    half = int(CHROMA_CROP_FRAC * ROBOT_MM / mm_per_px)
    out = []
    for cand in cands:
        cand = dict(cand)
        cand["chroma"] = _coloured(chroma, cand["centre"], half)
        cand["robot"] = cand["chroma"] >= CHROMA_MIN
        out.append(cand)
    return out
