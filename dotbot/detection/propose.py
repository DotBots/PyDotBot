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

Stage two is `detect`: a robot carries coloured parts and a floor does not.

`cv2` is imported inside the functions that use it, so importing this
module costs nothing without the `[calibrate]` extra.
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

# Stage two: how much of the candidate's crop must be saturated colour.
SAT_LEVEL = 90
SAT_MIN = 2.0

# What a peak must already carry, before it is worth re-centring at full
# resolution. A quarter of `SAT_MIN`, so it can only discard what is nowhere
# near a robot: measured on the bench photographs, robots score at least
# 4.97 per cent at their raw peak and everything else scores 0.00.
PRE_SAT_MIN = SAT_MIN / 4


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


def _saturation(bgr, centre, half, sat_level=SAT_LEVEL):
    """Per cent of a box around `centre` carrying saturated colour.

    A robot carries coloured parts and a floor does not, which is the only
    thing that separates the two by the time a candidate is this size.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    x, y = int(centre[0]), int(centre[1])
    crop = bgr[max(0, y - half) : y + half, max(0, x - half) : x + half]
    if crop.size == 0:
        return 0.0
    channel = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 1]
    return float((channel > sat_level).mean()) * 100


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

    Normalised convolution. A box straddling a masked-out ArUco sheet would
    otherwise average in zeros and ring a false response around every sheet;
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


def _robust_sigma(values):
    """MAD-based scale and median; robots are a few per cent of the frame."""
    med = float(np.median(values))
    return float(np.median(np.abs(values - med))) * 1.4826, med


def response(
    bgr,
    keep_mask=None,
    mm_per_px=None,
    robot_mm=ROBOT_MM,
    samples_per_robot=SAMPLES_PER_ROBOT,
    inner_frac=INNER_FRAC,
    outer_frac=OUTER_FRAC,
    min_valid=MIN_VALID,
    _want_bg=False,
):
    """Whitened matched-filter response, in floor-sigmas.

    Returns `(R, ok, work_mmpp, (sx, sy), sigma)`, where `R` is a
    Mahalanobis distance in the floor's own per-channel noise metric and
    `(sx, sy)` scales working-grid pixels back to input pixels.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    if mm_per_px is None:
        raise ValueError("mm_per_px is required")
    bgr = as_bgr(bgr)
    # Work at a fixed number of samples per robot. The robust noise estimate
    # below needs a median over every floor pixel, which is an order of
    # magnitude cheaper here than at full resolution, and box-averaging
    # before decimating is both the anti-alias low-pass and the first half of
    # the band-pass. Never upsample: a camera already coarser than the grid
    # is used as it is.
    work_mmpp = max(robot_mm / samples_per_robot, mm_per_px)
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
    m_in, f_in = _masked_box_mean(lab, valid, _odd(inner_frac * robot_mm / work_mmpp))
    m_out, f_out = _masked_box_mean(lab, valid, _odd(outer_frac * robot_mm / work_mmpp))
    diff = m_in - m_out

    # A robot's whole footprint must lie on known floor for its colour to
    # mean anything, and it needs at least half a surround to be measured
    # against. That costs a half-robot band along the floor boundary and
    # around each ArUco sheet, where a robot could not be measured anyway.
    ok = (valid > 0) & (f_in >= min_valid - 1e-6) & (f_out >= 0.5)
    if ok.sum() < 64:
        zero = np.zeros((wh, ww), np.float32)
        out = (zero, ok, work_mmpp, (sx, sy), np.ones(3, np.float32))
        return out + (m_out,) if _want_bg else out

    # Whiten per channel by the floor's own spread, which is self-calibrating
    # since the floor is whatever the median of the frame is. The clamp is the
    # 8-bit quantisation limit propagated through the averaging, below which a
    # measured spread is only rounding: one LSB is 1/sqrt(12) uniform,
    # averaged over the inner box, doubled for the difference of two means.
    n_in = max(1.0, (inner_frac * robot_mm / work_mmpp) ** 2)
    floor_q = np.sqrt(2.0 / (12.0 * n_in))
    sigma = np.empty(3, np.float32)
    for channel in range(3):
        spread, _ = _robust_sigma(diff[:, :, channel][ok])
        sigma[channel] = max(spread, floor_q * (100.0 / 255.0 if channel == 0 else 1.0))

    scored = np.sqrt(((diff / sigma) ** 2).sum(axis=2)).astype(np.float32)
    scored[~ok] = 0.0
    out = (scored, ok, work_mmpp, (sx, sy), sigma)
    return out + (m_out,) if _want_bg else out


def propose(
    bgr,
    keep_mask=None,
    mm_per_px=None,
    robot_mm=ROBOT_MM,
    k=K_SIGMA,
    samples_per_robot=SAMPLES_PER_ROBOT,
    inner_frac=INNER_FRAC,
    outer_frac=OUTER_FRAC,
    nms_frac=NMS_FRAC,
    min_valid=MIN_VALID,
    max_out=MAX_OUT,
    pre_sat_min=PRE_SAT_MIN,
    sat_level=SAT_LEVEL,
):
    """Candidate robot-sized objects, as dicts with `centre` in input px."""
    bgr = as_bgr(bgr)
    scored, ok, work_mmpp, (sx, sy), sigma, m_out = response(
        bgr,
        keep_mask,
        mm_per_px,
        robot_mm,
        samples_per_robot,
        inner_frac,
        outer_frac,
        min_valid,
        _want_bg=True,
    )

    hits = np.argwhere(scored > k)
    if hits.size == 0:
        return []
    z = scored[hits[:, 0], hits[:, 1]]
    order = np.argsort(-z)

    rad = max(1, int(round(nms_frac * robot_mm / work_mmpp)))
    px_per_robot = robot_mm / work_mmpp
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
        # Re-centring is the expensive half of this loop and the response
        # answers for anything robot-sized, printed sheets included. A peak
        # with no colour on it at all cannot become a robot by being
        # re-centred, so it is dropped before the work rather than after.
        half = int(0.6 * robot_mm / mm_per_px)
        if _saturation(bgr, (cx, cy), half, sat_level) < pre_sat_min:
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
        out.append(
            {
                "centre": np.array([cx, cy]),
                "z": float(z[i]),
                "score": float(z[i]),
                "area": _footprint_mm2(scored, x, y, k, px_per_robot, work_mmpp),
            }
        )
        if len(out) >= max_out:
            break
    return out


def _refine(bgr, cx, cy, bg, sigma, robot_mm, mm_per_px, rfrac=REFINE_FRAC):
    """Re-centre on the object's own silhouette at full resolution.

    A matched-filter peak locates an object but does not centre on it: the
    response surface is skewed wherever the object sits on some larger
    structure's flank, far enough to walk stage two's sampling window off the
    robot. The outline is taken at half the object's own contrast, with the
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


def _footprint_mm2(scored, x, y, thr, px_per_robot, work_mmpp):
    """How much floor this peak covers, measured at half its own height.

    Half-height rather than the global threshold, so a strong object and a
    faint one are measured the same way and the number means a size rather
    than a contrast.
    """
    import cv2  # lazy: opencv-python is only required to run the detector

    r = int(round(1.5 * px_per_robot))
    win = scored[max(0, y - r) : y + r + 1, max(0, x - r) : x + r + 1]
    m = (win > max(0.5 * scored[y, x], thr)).astype(np.uint8)
    _, labels = cv2.connectedComponents(m)
    label = labels[min(y, r), min(x, r)]
    if label == 0:
        return 0.0
    return float((labels == label).sum()) * work_mmpp**2


def detect(
    bgr,
    keep_mask=None,
    mm_per_px=None,
    robot_mm=ROBOT_MM,
    sat_min=SAT_MIN,
    sat_level=SAT_LEVEL,
    **kwargs,
):
    """Candidates with the stage-two verdict on each, as `robot`.

    Colour conversions run on the candidate crop rather than the whole
    frame, so a generous stage one stays affordable. The verdict is taken at
    the re-centred position, which is the one a pose is seeded from.
    """
    bgr = as_bgr(bgr)
    cands = propose(
        bgr,
        keep_mask,
        mm_per_px,
        robot_mm,
        pre_sat_min=sat_min / 4,
        sat_level=sat_level,
        **kwargs,
    )
    if not cands:
        return []
    half = int(0.6 * robot_mm / mm_per_px)
    out = []
    for cand in cands:
        cand = dict(cand)
        cand["sat"] = _saturation(bgr, cand["centre"], half, sat_level)
        cand["robot"] = cand["sat"] >= sat_min
        out.append(cand)
    return out
