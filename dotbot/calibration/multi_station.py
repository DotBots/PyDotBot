# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Several LH2 stations in one frame, from the circles robots spin.

Each station is first solved on its own circles (`conics.solve`), which
makes it metric through the spin radius but leaves it free to turn and
shift. A circle seen by two stations ties them: the station graph says which
stations are tied and how strongly, a spanning tree of rigid fits seeds one
joint refinement over every station and every circle, and the frame is then
set over every kept centre exactly as free mode sets it for one station.

The predicted error map propagates the joint solve's covariance onto a floor
grid, so a reviewer sees where the calibration is weak without a camera.
"""

# pylint: disable=invalid-name,too-many-locals,too-many-arguments

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from dotbot.calibration.conics import (
    TRACK_AXIS_RATIO_MIN,
    CircleKey,
    ConicSolution,
    Track,
    _circle_fit,
    apply,
    axis_ratio,
    field_angle,
    fit_tracks,
    health_gate,
    similarity,
    solve,
)
from dotbot.calibration.lighthouse2 import (
    Calibration,
    LinkRecord,
    TrackSample,
    station_label,
    union_rect,
)
from dotbot.robots import robot_geometry

__all__ = [
    "CircleKey",
    "ErrorMap",
    "JointSolution",
    "MultiStationError",
    "StationGraph",
    "error_map_from_calibration",
    "multi_station_report",
    "solve_joint",
    "station_graph",
]

LINK_SHARED_MIN = 2
LINK_SPREAD_MIN_MM = 300.0
LINK_SHARED_ADVISED = 4
LINK_SPREAD_ADVISED_MM = 600.0
RECT_MARGIN_MM = 300
ERROR_MAP_CELL_MM = 100.0
# Cells whose predicted error is over this are counted in the report.
ERROR_MAP_LIMIT_MM = 10.0

# Largest share a station's own scale may differ from the joint one.
SCALE_RATIO_TOLERANCE = 0.02
# A tied circle whose station centres are further apart than this many
# times the typical disagreement is untied.
TIE_GATE_SIGMAS = 3.0
# Least per-axis centre disagreement the tie gate and a link's yaw sigma
# assume, mm: a fit to two or three circles leaves almost none to measure.
TIE_SIGMA_FLOOR_MM = 1.0
# Tied circles needed before the typical disagreement means anything.
TIE_GATE_MIN = 4
TIE_ROUNDS_MAX = 4

# Huber threshold on the radial residual, mm.
ROBUST_MM = 5.0
# Weight of the prior holding the root station's centres where the seed put
# them: it only removes the rigid freedom of the whole floor.
GAUGE_PRIOR_WEIGHT = 1e-3
JOINT_ITERATIONS = 60

# The median of the distance between two centres each off by sigma per axis,
# in units of sigma * sqrt(2) (Rayleigh).
_RAYLEIGH_MEDIAN = math.sqrt(2 * math.log(2))


@dataclass
class StationGraph:
    """Stations as nodes, and a link per pair that shares a kept circle.

    `components` are the groups of stations joined by links that hold
    (`link_holds`), largest first.
    """

    stations: list[int]
    links: list[LinkRecord]
    components: list[list[int]]

    def link(self, a: int, b: int) -> LinkRecord | None:
        a, b = min(a, b), max(a, b)
        for link in self.links:
            if (link.a, link.b) == (a, b):
                return link
        return None


@dataclass
class ErrorMap:
    """Predicted 1-sigma position error on a floor grid, mm.

    Cell (row, col) is centred on `origin_mm + (col + 0.5, row + 0.5) *
    cell_mm`; NaN where no station's rectangle covers it.
    """

    origin_mm: tuple[float, float]
    cell_mm: float
    sigma_mm: np.ndarray
    worst_mm: float
    cells_over_10mm: int

    def centre(self, row: int, col: int) -> tuple[float, float]:
        return (
            self.origin_mm[0] + (col + 0.5) * self.cell_mm,
            self.origin_mm[1] + (row + 0.5) * self.cell_mm,
        )

    @property
    def worst_cell(self) -> tuple[float, float] | None:
        if np.all(np.isnan(self.sigma_mm)):
            return None
        row, col = np.unravel_index(np.nanargmax(self.sigma_mm), self.sigma_mm.shape)
        return self.centre(int(row), int(col))

    @property
    def covered(self) -> int:
        return int(np.sum(~np.isnan(self.sigma_mm)))


@dataclass
class JointSolution:
    """Every station in one frame, and the evidence of how well it holds."""

    homographies: dict[int, np.ndarray]
    centres: dict[CircleKey, np.ndarray]
    rectangles: dict[int, tuple[int, int, int, int]]
    valid_mm: tuple[int, int, int, int]
    field_mm: tuple[int, int]
    graph: StationGraph
    loops: list[tuple[list[int], float]]
    station_rms_mm: dict[int, float]
    scale_ratio: dict[int, float]
    dropped: dict[CircleKey, str]
    error_map: ErrorMap
    # Each solved station's circles under its final homography, kept and dropped.
    solutions: dict[int, ConicSolution] = field(default_factory=dict)
    # Stations with tracks that could not be solved, and why.
    unsolved: dict[int, str] = field(default_factory=dict)
    # Per link (a, b): rms centre disagreement after the seed, before refinement.
    seed_disagreement_mm: dict[tuple[int, int], float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def joint(self) -> bool:
        return len(self.homographies) > 1


class MultiStationError(ValueError):
    """The stations cannot be put in one frame: an island, or a weak tie."""

    def __init__(
        self,
        message: str,
        islands: Sequence[int] = (),
        weak: Sequence[LinkRecord] = (),
    ):
        super().__init__(message)
        self.islands = list(islands)
        self.weak = list(weak)


def link_holds(link: LinkRecord) -> bool:
    """Whether a link is strong enough to tie its two stations at all."""
    return link.shared >= LINK_SHARED_MIN and link.spread_mm >= LINK_SPREAD_MIN_MM


def link_advised(link: LinkRecord) -> bool:
    """Whether a link is as strong as the report advises."""
    return (
        link.shared >= LINK_SHARED_ADVISED and link.spread_mm >= LINK_SPREAD_ADVISED_MM
    )


# --- Graph ------------------------------------------------------------------


def _spread(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    diff = points[:, None, :] - points[None, :, :]
    return float(np.max(np.linalg.norm(diff, axis=2)))


def _tie_stats(pa: np.ndarray, pb: np.ndarray) -> tuple[float, float]:
    """rms distance between paired centres, and the relative yaw it leaves.

    The yaw sigma is that of a rigid fit on the pairs: per-axis noise, at
    least `TIE_SIGMA_FLOOR_MM`, over the root of the centres' second moment
    about their mean.
    """
    d = np.linalg.norm(pa - pb, axis=1)
    rms = float(np.sqrt(np.mean(d**2)))
    moment = float(np.sum((pa - pa.mean(axis=0)) ** 2))
    if len(pa) < 2 or moment <= 0:
        return rms, math.inf
    sigma = max(rms / math.sqrt(2), TIE_SIGMA_FLOOR_MM)
    return rms, 1000.0 * sigma / math.sqrt(moment)


def _components(
    stations: Sequence[int], links: Sequence[LinkRecord]
) -> list[list[int]]:
    parent = {s: s for s in stations}

    def find(s):
        while parent[s] != s:
            parent[s] = parent[parent[s]]
            s = parent[s]
        return s

    for link in links:
        if link_holds(link) and link.a in parent and link.b in parent:
            parent[find(link.a)] = find(link.b)
    groups: dict[int, list[int]] = {}
    for s in stations:
        groups.setdefault(find(s), []).append(s)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g[0]))


def _kept_centres(solution: ConicSolution) -> dict[CircleKey, np.ndarray]:
    return {t.key: np.array(t.centre_mm) for t in solution.tracks}


def _graph_from_centres(
    centres: Mapping[int, Mapping[CircleKey, np.ndarray]],
    tied: Mapping[CircleKey, set[int]] | None = None,
) -> StationGraph:
    """The graph, with each station's centres expressed in one frame or its own.

    A pair's spread is measured in the first station's centres, which are
    metric either way; the disagreement is only meaningful when every
    station's centres are in one frame. `tied` limits which stations a
    circle ties (all that kept it, by default).
    """
    stations = sorted(centres)
    links = []
    for i, a in enumerate(stations):
        for b in stations[i + 1 :]:
            shared = sorted(
                (set(centres[a]) & set(centres[b])),
                key=lambda k: (k.name, k.round),
            )
            if tied is not None:
                shared = [k for k in shared if {a, b} <= tied.get(k, set())]
            if not shared:
                continue
            pa = np.array([centres[a][k] for k in shared])
            pb = np.array([centres[b][k] for k in shared])
            rms, yaw = _tie_stats(pa, pb)
            links.append(
                LinkRecord(
                    a=a,
                    b=b,
                    shared=len(shared),
                    spread_mm=_spread(pa),
                    disagreement_mm=rms,
                    yaw_sigma_mrad=yaw,
                )
            )
    return StationGraph(
        stations=stations, links=links, components=_components(stations, links)
    )


def _solve_stations(
    tracks: Mapping[int, Sequence[Track]], margin_mm: float
) -> tuple[dict[int, ConicSolution], dict[int, str]]:
    solutions, unsolved = {}, {}
    for station in sorted(tracks):
        try:
            solutions[station] = solve(tracks[station], margin_mm=margin_mm)
        except ValueError as exc:
            unsolved[station] = str(exc)
    return solutions, unsolved


def station_graph(
    tracks: Mapping[int, Sequence[Track]],
    solutions: Mapping[int, ConicSolution] | None = None,
) -> StationGraph:
    """Which stations the kept circles tie, from each station's own solve.

    Spreads are in each station's own metric frame; disagreements are those
    left by a rigid fit of one station's shared centres onto the other's.
    """
    if solutions is None:
        solutions, _ = _solve_stations(tracks, robot_geometry().axle_reach_mm)
    own = {s: _kept_centres(sol) for s, sol in solutions.items()}
    graph = _graph_from_centres(own)
    for link in graph.links:
        keys = sorted(
            set(own[link.a]) & set(own[link.b]), key=lambda k: (k.name, k.round)
        )
        pa = np.array([own[link.a][k] for k in keys])
        pb = np.array([own[link.b][k] for k in keys])
        if len(keys) >= 2:
            pb = apply(similarity(pb, pa, scale=False), pb)
            link.disagreement_mm, link.yaw_sigma_mrad = _tie_stats(pa, pb)
        else:
            link.disagreement_mm, link.yaw_sigma_mrad = 0.0, math.inf
    return graph


# --- Seed -------------------------------------------------------------------


def _spanning_tree(graph: StationGraph, root: int) -> dict[int, int]:
    """Parent of each station in a maximum spanning tree of holding links,
    weighted by shared count times spread, rooted at `root`."""
    holding = sorted(
        (k for k in graph.links if link_holds(k)),
        key=lambda k: (-k.shared * k.spread_mm, k.a, k.b),
    )
    parent_uf = {s: s for s in graph.stations}

    def find(s):
        while parent_uf[s] != s:
            s = parent_uf[s]
        return s

    adjacency: dict[int, list[int]] = {s: [] for s in graph.stations}
    for link in holding:
        ra, rb = find(link.a), find(link.b)
        if ra != rb:
            parent_uf[ra] = rb
            adjacency[link.a].append(link.b)
            adjacency[link.b].append(link.a)
    parent = {root: root}
    queue = [root]
    while queue:
        s = queue.pop(0)
        for n in sorted(adjacency[s]):
            if n not in parent:
                parent[n] = s
                queue.append(n)
    return parent


def _loops(
    graph: StationGraph,
    parent: Mapping[int, int],
    own: Mapping[int, Mapping[CircleKey, np.ndarray]],
) -> list[tuple[list[int], float]]:
    """Each fundamental cycle of the holding links, and how far a point moves
    when carried round it by the pairwise rigid fits."""
    tree = {(min(a, b), max(a, b)) for a, b in parent.items() if a != b}
    out = []

    def path_to_root(s):
        path = [s]
        while parent[path[-1]] != path[-1]:
            path.append(parent[path[-1]])
        return path

    def fit(a, b):
        keys = sorted(set(own[a]) & set(own[b]), key=lambda k: (k.name, k.round))
        return similarity(
            np.array([own[a][k] for k in keys]),
            np.array([own[b][k] for k in keys]),
            scale=False,
        )

    for link in graph.links:
        if not link_holds(link) or (link.a, link.b) in tree:
            continue
        if link.a not in parent or link.b not in parent:
            continue
        pa, pb = path_to_root(link.a), path_to_root(link.b)
        common = next(s for s in pa if s in pb)
        cycle = pa[: pa.index(common) + 1] + list(reversed(pb[: pb.index(common)]))
        # cycle runs a -> ... -> common -> ... -> b, closed by the link b -> a
        T = np.eye(3)
        for x, y in zip(cycle, cycle[1:] + cycle[:1]):
            T = fit(x, y) @ T
        start = np.mean(list(own[cycle[0]].values()), axis=0)
        moved = apply(T, start[None, :])[0]
        out.append((cycle, float(np.linalg.norm(moved - start))))
    return out


# --- Joint refinement -------------------------------------------------------


def _h_params(H: np.ndarray) -> np.ndarray:
    H = H / H[2, 2]
    return np.array(
        [H[0, 0], H[0, 1], H[0, 2], H[1, 0], H[1, 1], H[1, 2], H[2, 0], H[2, 1]]
    )


def _h_matrix(p: np.ndarray) -> np.ndarray:
    return np.array([[p[0], p[1], p[2]], [p[3], p[4], p[5]], [p[6], p[7], 1.0]])


def _map(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """H(q) for the 8 parameters `p`."""
    qx, qy = q[:, 0], q[:, 1]
    w = p[6] * qx + p[7] * qy + 1.0
    return np.c_[(p[0] * qx + p[1] * qy + p[2]) / w, (p[3] * qx + p[4] * qy + p[5]) / w]


def _map_jacobian(p: np.ndarray, q: np.ndarray):
    """H(q) for the 8 parameters `p`, and its derivative, (n, 2, 8)."""
    qx, qy = q[:, 0], q[:, 1]
    w = p[6] * qx + p[7] * qy + 1.0
    u = (p[0] * qx + p[1] * qy + p[2]) / w
    v = (p[3] * qx + p[4] * qy + p[5]) / w
    G = np.zeros((len(q), 2, 8))
    G[:, 0, 0], G[:, 0, 1], G[:, 0, 2] = qx / w, qy / w, 1 / w
    G[:, 1, 3], G[:, 1, 4], G[:, 1, 5] = qx / w, qy / w, 1 / w
    G[:, 0, 6], G[:, 0, 7] = -u * qx / w, -u * qy / w
    G[:, 1, 6], G[:, 1, 7] = -v * qx / w, -v * qy / w
    return np.c_[u, v], G


@dataclass
class _Problem:
    """The joint least-squares problem: which parameters each read touches."""

    stations: list[int]
    centre_ids: list  # CircleKey for a tied circle, (CircleKey, station) otherwise
    blocks: list  # (station, centre id, camera points, radius)
    prior: dict  # centre id -> (target xy)

    def __post_init__(self):
        self.s_col = {s: 8 * i for i, s in enumerate(self.stations)}
        base = 8 * len(self.stations)
        self.c_col = {c: base + 2 * i for i, c in enumerate(self.centre_ids)}
        self.n = base + 2 * len(self.centre_ids)

    def pack(self, H: Mapping[int, np.ndarray], C: Mapping) -> np.ndarray:
        x = np.zeros(self.n)
        for s, col in self.s_col.items():
            x[col : col + 8] = _h_params(H[s])
        for c, col in self.c_col.items():
            x[col : col + 2] = C[c]
        return x

    def unpack(self, x: np.ndarray):
        H = {s: _h_matrix(x[col : col + 8]) for s, col in self.s_col.items()}
        C = {c: x[col : col + 2].copy() for c, col in self.c_col.items()}
        return H, C

    def residuals(self, x: np.ndarray, prior: bool = True) -> np.ndarray:
        """The radial residual of every read, in block order, then the prior's."""
        rows = []
        for s, cid, q, radius in self.blocks:
            sc, cc = self.s_col[s], self.c_col[cid]
            uv = _map(x[sc : sc + 8], q)
            rows.append(np.linalg.norm(uv - x[cc : cc + 2], axis=1) - radius)
        if prior:
            for cid, target in self.prior.items():
                cc = self.c_col[cid]
                rows.append(GAUGE_PRIOR_WEIGHT * (x[cc : cc + 2] - target))
        return np.concatenate(rows)

    def normal(
        self, x: np.ndarray, w: np.ndarray, prior: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """`J.T W² J` and `J.T W² r` for the row weights `w`, block by block.

        Each read touches its station's 8 parameters and its centre's 2, so
        the Jacobian is never formed whole.
        """
        A = np.zeros((self.n, self.n))
        g = np.zeros(self.n)
        row = 0
        for s, cid, q, radius in self.blocks:
            sc, cc = self.s_col[s], self.c_col[cid]
            uv, G = _map_jacobian(x[sc : sc + 8], q)
            d = uv - x[cc : cc + 2]
            rho = np.linalg.norm(d, axis=1)
            e = d / np.maximum(rho, 1e-12)[:, None]
            wb = w[row : row + len(q), None]
            row += len(q)
            J = np.empty((len(q), 10))
            J[:, :8] = np.einsum("ni,nij->nj", e, G)
            J[:, 8:] = -e
            J *= wb
            idx = np.r_[sc : sc + 8, cc : cc + 2]
            A[np.ix_(idx, idx)] += J.T @ J
            g[idx] += J.T @ ((rho - radius) * wb[:, 0])
        if prior:
            for cid, target in self.prior.items():
                cc = self.c_col[cid]
                A[cc, cc] += GAUGE_PRIOR_WEIGHT**2
                A[cc + 1, cc + 1] += GAUGE_PRIOR_WEIGHT**2
                g[cc : cc + 2] += GAUGE_PRIOR_WEIGHT**2 * (x[cc : cc + 2] - target)
        return A, g

    def read_rows(self) -> int:
        return sum(len(b[2]) for b in self.blocks)


def _huber(r: np.ndarray, reads: int) -> np.ndarray:
    w = np.ones_like(r)
    big = np.abs(r[:reads]) > ROBUST_MM
    w[:reads][big] = np.sqrt(ROBUST_MM / np.abs(r[:reads][big]))
    return w


def _refine(problem: _Problem, x0: np.ndarray) -> np.ndarray:
    """Levenberg-Marquardt on the Huber-weighted residuals, Marquardt scaling."""
    reads = problem.read_rows()
    x = x0.copy()
    r = problem.residuals(x)
    w = _huber(r, reads)
    A, g = problem.normal(x, w)
    cost = float(np.sum((w * r) ** 2))
    lam = 1e-3
    for _ in range(JOINT_ITERATIONS):
        D = np.diag(A).copy()
        D[D <= 0] = 1e-12
        improved = False
        while lam < 1e12:
            try:
                dx = np.linalg.solve(A + lam * np.diag(D), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            r_new = problem.residuals(x + dx)
            cost_new = float(np.sum((w * r_new) ** 2))
            if np.isfinite(cost_new) and cost_new < cost:
                gain = cost - cost_new
                x = x + dx
                r = problem.residuals(x)
                w = _huber(r, reads)
                A, g = problem.normal(x, w)
                cost = float(np.sum((w * r) ** 2))
                lam = max(lam / 10, 1e-12)
                improved = gain > 1e-12 * max(cost, 1e-12)
                break
            lam *= 10
        if not improved:
            break
    return x


def _covariance(problem: _Problem, x: np.ndarray) -> np.ndarray:
    """Parameter covariance with the rigid freedom of the floor removed.

    From the read rows only (no prior): the information matrix, scaled to
    unit diagonal, loses its 3 smallest eigen-directions (the gauge), is
    inverted, and is scaled by the residual variance.
    """
    r = problem.residuals(x, prior=False)
    w = _huber(r, problem.read_rows())
    A, _ = problem.normal(x, w, prior=False)
    rw = r * w
    d = np.sqrt(np.maximum(np.diag(A), 1e-30))
    As = A / np.outer(d, d)
    vals, vecs = np.linalg.eigh(As)
    gauge = 3
    keep = np.arange(len(vals)) >= gauge
    keep &= vals > vals.max() * 1e-14
    inv = (vecs[:, keep] / vals[keep]) @ vecs[:, keep].T
    dof = max(len(r) - (problem.n - gauge), 1)
    variance = float(np.sum(rw**2) / dof)
    return variance * inv / np.outer(d, d)


def _error_map(
    problem: _Problem,
    x: np.ndarray,
    rectangles: Mapping[int, Sequence[int]],
    cell_mm: float = ERROR_MAP_CELL_MM,
) -> ErrorMap:
    cov = _covariance(problem, x)
    H, _ = problem.unpack(x)
    x0, y0, x1, y1 = union_rect(rectangles.values())
    cols = max(1, int(math.ceil((x1 - x0) / cell_mm)))
    rows = max(1, int(math.ceil((y1 - y0) / cell_mm)))
    gx = x0 + (np.arange(cols) + 0.5) * cell_mm
    gy = y0 + (np.arange(rows) + 0.5) * cell_mm
    XX, YY = np.meshgrid(gx, gy)
    info = np.zeros((rows, cols))
    for s, (rx0, ry0, rx1, ry1) in rectangles.items():
        inside = (XX >= rx0) & (XX <= rx1) & (YY >= ry0) & (YY <= ry1)
        if not inside.any():
            continue
        p = np.c_[XX[inside], YY[inside]]
        q = apply(np.linalg.inv(H[s]), p)
        col = problem.s_col[s]
        _, G = _map_jacobian(x[col : col + 8], q)
        S = cov[col : col + 8, col : col + 8]
        var = np.einsum("nij,jk,nik->n", G, S, G)
        var = np.maximum(var, 1e-12)
        info[inside] += 1.0 / var
    sigma = np.full((rows, cols), np.nan)
    covered = info > 0
    sigma[covered] = 1.0 / np.sqrt(info[covered])
    worst = float(np.nanmax(sigma)) if covered.any() else float("nan")
    return ErrorMap(
        origin_mm=(float(x0), float(y0)),
        cell_mm=float(cell_mm),
        sigma_mm=sigma,
        worst_mm=worst,
        cells_over_10mm=int(np.sum(sigma[covered] > ERROR_MAP_LIMIT_MM)),
    )


# --- Frame ------------------------------------------------------------------


def _rotation(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def _upright_turns(mapped: Sequence[np.ndarray], centres: np.ndarray) -> int:
    """`conics.upright_turns` over the tracks of every station at once."""
    dirs = []
    for p in mapped:
        d = p[0] - _circle_fit(p)[0]
        dirs.append(d / np.linalg.norm(d))
    mean = np.mean(dirs, axis=0)
    if np.linalg.norm(mean) >= 0.5:
        heading = np.arctan2(mean[1], mean[0])
        return int(np.round((np.pi / 2 - heading) / (np.pi / 2))) % 4
    width, height = np.ptp(centres, axis=0)
    return 1 if width > height else 0


def _rect_around(points: np.ndarray, margin: float) -> tuple[int, int, int, int]:
    lo = np.floor(points.min(axis=0) - margin)
    hi = np.ceil(points.max(axis=0) + margin)
    lo = np.maximum(lo, 0)
    return (int(lo[0]), int(lo[1]), int(hi[0]), int(hi[1]))


def _frame(
    H: dict[int, np.ndarray],
    C: dict,
    kept: Mapping[int, Sequence[Track]],
    margin_mm: float,
) -> tuple[np.ndarray, tuple[int, int]]:
    """The move into the free-mode frame over every kept centre, and the field."""
    centres = np.array(list(C.values()))
    T = _rotation(-field_angle(centres))
    mapped = [apply(T @ H[s], t.points) for s in kept for t in kept[s]]
    turns = _upright_turns(mapped, apply(T, centres))
    T = np.linalg.matrix_power(_rotation(np.pi / 2), turns) @ T
    moved = apply(T, centres)
    lo = moved.min(axis=0) - margin_mm
    size = np.ceil(moved.max(axis=0) + margin_mm - lo)
    T = np.array([[1, 0, -lo[0]], [0, 1, -lo[1]], [0, 0, 1.0]]) @ T
    return T, (int(size[0]), int(size[1]))


# --- The solve --------------------------------------------------------------


def _island_message(
    islands: Sequence[int], main: Sequence[int], graph: StationGraph
) -> tuple[str, list[LinkRecord]]:
    lines, weak = [], []
    for s in islands:
        touching = [k for k in graph.links if s in (k.a, k.b)]
        weak += touching
        if touching:
            ties = "; ".join(
                f"shares {k.shared} circle(s) {k.spread_mm:.0f} mm apart with "
                f"{station_label(k.b if k.a == s else k.a)}"
                for k in touching
            )
        else:
            ties = "shares no kept circle with any station"
        lines.append(f"{station_label(s)} is not tied to the others: {ties}")
    names = ", ".join(station_label(s) for s in main)
    lines.append(
        f"A tie needs {LINK_SHARED_MIN} or more shared circles at least "
        f"{LINK_SPREAD_MIN_MM:.0f} mm apart. Put 2 or more robots, well apart, "
        f"where the station and one of {names} both see them and collect "
        "another round, or leave it out with "
        + " ".join(f"--drop-station {s}" for s in islands)
        + "."
    )
    return "\n".join(lines), weak


def _single(
    station: int,
    solution: ConicSolution,
    tracks: Sequence[Track],
    rect_margin_mm: int,
    unsolved: dict[int, str],
) -> JointSolution:
    """One station, exactly as `conics.solve` solves it."""
    H = solution.homography / solution.homography[2, 2]
    kept_names = {t.key for t in solution.tracks}
    kept = [t for t in tracks if t.key in kept_names]
    centres = {t.key: np.array(t.centre_mm) for t in solution.tracks}
    rect = _rect_around(np.array(list(centres.values())), rect_margin_mm)
    problem = _Problem(
        stations=[station],
        centre_ids=list(centres),
        blocks=[(station, t.key, t.points, t.radius_mm) for t in kept],
        prior={},
    )
    x = problem.pack({station: H}, centres)
    graph = StationGraph(stations=[station], links=[], components=[[station]])
    return JointSolution(
        homographies={station: H},
        centres=centres,
        rectangles={station: rect},
        valid_mm=rect,
        field_mm=solution.field_mm,
        graph=graph,
        loops=[],
        station_rms_mm={station: solution.residual_mm},
        scale_ratio={station: 1.0},
        dropped={},
        error_map=_error_map(problem, x, {station: rect}),
        solutions={station: solution},
        unsolved=unsolved,
    )


def solve_joint(
    tracks: Mapping[int, Sequence[Track]],
    *,
    margin_mm: float | None = None,
    rect_margin_mm: int = RECT_MARGIN_MM,
    drop: Collection[int] = (),
) -> JointSolution:
    """Every station's homography in one metric frame, from circle tracks.

    Each station is solved on its own circles first; a station that cannot
    be is listed in `unsolved` and left out. `drop` leaves stations out on
    purpose. Raises MultiStationError when a solved station is not tied to
    the rest by links that hold (`link_holds`), naming it.
    """
    if margin_mm is None:
        margin_mm = robot_geometry().axle_reach_mm
    tracks = {s: list(t) for s, t in tracks.items() if s not in set(drop) and t}
    if not tracks:
        raise ValueError("no tracks to solve")
    solutions, unsolved = _solve_stations(tracks, margin_mm)
    if not solutions:
        raise ValueError(
            "no station could be solved: "
            + "; ".join(f"{station_label(s)}: {why}" for s, why in unsolved.items())
        )
    graph = station_graph(tracks, solutions)
    root = min(solutions, key=lambda s: (-len(solutions[s].tracks), s))
    main = next(c for c in graph.components if root in c)
    islands = [s for s in sorted(solutions) if s not in main]
    if islands:
        message, weak = _island_message(islands, main, graph)
        raise MultiStationError(message, islands=islands, weak=weak)
    if len(solutions) == 1:
        return _single(root, solutions[root], tracks[root], rect_margin_mm, unsolved)

    own = {s: _kept_centres(sol) for s, sol in solutions.items()}
    kept = {s: [t for t in tracks[s] if t.key in own[s]] for s in sorted(solutions)}
    # Stage 3: seed by composing rigid fits down a maximum spanning tree.
    parent = _spanning_tree(graph, root)
    H0: dict[int, np.ndarray] = {}
    world: dict[int, dict[CircleKey, np.ndarray]] = {}
    order = sorted(parent, key=lambda s: _depth(parent, s))
    for s in order:
        Hs = solutions[s].homography / solutions[s].homography[2, 2]
        if s != root:
            p = parent[s]
            keys = sorted(set(own[s]) & set(own[p]), key=lambda k: (k.name, k.round))
            S = similarity(
                np.array([own[s][k] for k in keys]),
                np.array([world[p][k] for k in keys]),
                scale=False,
            )
            Hs = S @ Hs
            Hs = Hs / Hs[2, 2]
        H0[s] = Hs
        world[s] = {t.key: _circle_fit(apply(Hs, t.points))[0] for t in kept[s]}
    seed_graph = _graph_from_centres(world)
    seed_disagreement = {(k.a, k.b): k.disagreement_mm for k in seed_graph.links}

    # Stage 4: one refinement over every station and every circle, untying
    # circles the stations disagree on.
    tied: dict[CircleKey, set[int]] = {}
    for s, centres in world.items():
        for k in centres:
            tied.setdefault(k, set()).add(s)
    dropped: dict[CircleKey, str] = {}
    H, C = dict(H0), {}
    problem = None
    x = None
    for tie_round in range(TIE_ROUNDS_MAX + 1):
        problem, x0 = _build_problem(kept, world, tied, H, root)
        x = _refine(problem, x0)
        H, C = problem.unpack(x)
        per_station = {
            s: {t.key: _circle_fit(apply(H[s], t.points))[0] for t in kept[s]}
            for s in kept
        }
        if tie_round == TIE_ROUNDS_MAX:
            break
        untie = _gate_ties(per_station, tied)
        if not untie:
            break
        for k, why in untie.items():
            dropped[k] = why
            tied[k] = set()
        world = per_station
    graph_after = _graph_from_centres(per_station, tied)
    main_after = next(c for c in graph_after.components if root in c)
    islands = [s for s in sorted(kept) if s not in main_after]
    if islands:
        message, weak = _island_message(islands, main_after, graph_after)
        raise MultiStationError(
            "after untying the circles the stations disagree on:\n" + message,
            islands=islands,
            weak=weak,
        )

    # Stage 5: the frame over every kept centre.
    T, field = _frame(H, C, kept, margin_mm)
    H = {s: (T @ Hs) / (T @ Hs)[2, 2] for s, Hs in H.items()}
    C = {c: apply(T, v[None, :])[0] for c, v in C.items()}
    x = problem.pack(H, C)
    per_station = {
        s: {t.key: _circle_fit(apply(H[s], t.points))[0] for t in kept[s]} for s in kept
    }
    final_graph = _graph_from_centres(per_station, tied)
    rectangles = {
        s: _rect_around(np.array(list(per_station[s].values())), rect_margin_mm)
        for s in sorted(kept)
    }
    for s, rect in rectangles.items():
        if rect[0] >= rect[2] or rect[1] >= rect[3]:
            raise ValueError(f"{station_label(s)}: its rectangle {rect} is empty")
    warnings: list[str] = []
    final_solutions: dict[int, ConicSolution] = {}
    scale_ratio: dict[int, float] = {}
    for s, sol in solutions.items():
        why = {t.key: t.why for t in sol.dropped}
        out = [t for t in tracks[s] if t.key in why]
        sol.homography = H[s]
        sol.tracks = fit_tracks(kept[s], H[s])
        sol.dropped = fit_tracks(out, H[s], {t: why[t.key] for t in out})
        sol.field_mm = field
        final_solutions[s] = sol
        pts = np.vstack([t.points for t in kept[s]])
        own_mapped = apply(H0[s], pts)
        S = similarity(own_mapped, apply(H[s], pts), scale=True)
        scale_ratio[s] = float(math.sqrt(abs(np.linalg.det(S[:2, :2]))))
        if abs(scale_ratio[s] - 1) > SCALE_RATIO_TOLERANCE:
            warnings.append(
                f"{station_label(s)}: its own circles' scale is "
                f"{100 * (scale_ratio[s] - 1):+.1f} % off the joint one"
            )
        for t in kept[s]:
            ratio = axis_ratio(t, H[s])
            if ratio < TRACK_AXIS_RATIO_MIN:
                warnings.append(
                    f"{station_label(s)}: circle {_key_text(t.key)} has axis "
                    f"ratio {ratio:.3f} after the joint solve"
                )
    loops = _loops(graph, parent, own)
    centres_out: dict[CircleKey, np.ndarray] = {}
    for c, v in C.items():
        centres_out.setdefault(c if isinstance(c, CircleKey) else c[0], v)
    return JointSolution(
        homographies=H,
        centres=centres_out,
        rectangles=rectangles,
        valid_mm=union_rect(rectangles.values()),
        field_mm=field,
        graph=final_graph,
        loops=loops,
        station_rms_mm={s: final_solutions[s].residual_mm for s in final_solutions},
        scale_ratio=scale_ratio,
        dropped=dropped,
        error_map=_error_map(problem, x, rectangles),
        solutions=final_solutions,
        unsolved=unsolved,
        seed_disagreement_mm=seed_disagreement,
        warnings=warnings,
    )


def _depth(parent: Mapping[int, int], s: int) -> int:
    depth = 0
    while parent[s] != s:
        s = parent[s]
        depth += 1
    return depth


def _key_text(key: CircleKey) -> str:
    return key.name if key.round == 0 else f"{key.name} round {key.round}"


def _build_problem(kept, world, tied, H, root):
    centre_ids, C0 = [], {}
    blocks = []
    for s in sorted(kept):
        for t in kept[s]:
            cid = (
                t.key
                if len(tied.get(t.key, ())) >= 2 and s in tied[t.key]
                else (t.key, s)
            )
            if cid not in C0:
                centre_ids.append(cid)
                if isinstance(cid, CircleKey):
                    C0[cid] = np.mean([world[x][cid] for x in tied[cid]], axis=0)
                else:
                    C0[cid] = world[s][t.key]
            blocks.append((s, cid, t.points, t.radius_mm))
    prior = {}
    for t in kept[root]:
        cid = t.key if t.key in C0 else (t.key, root)
        prior[cid] = C0[cid].copy()
    problem = _Problem(
        stations=sorted(kept), centre_ids=centre_ids, blocks=blocks, prior=prior
    )
    return problem, problem.pack(H, C0)


def _gate_ties(
    per_station: Mapping[int, Mapping[CircleKey, np.ndarray]],
    tied: Mapping[CircleKey, set[int]],
) -> dict[CircleKey, str]:
    """The tied circles whose station centres disagree beyond the gate, and why."""
    spans = {}
    for k, stations in tied.items():
        if len(stations) < 2:
            continue
        pts = np.array([per_station[s][k] for s in sorted(stations)])
        spans[k] = _spread(pts)
    if len(spans) < TIE_GATE_MIN:
        return {}
    scale = max(np.median(list(spans.values())) / _RAYLEIGH_MEDIAN, TIE_SIGMA_FLOOR_MM)
    limit = TIE_GATE_SIGMAS * scale
    return {
        k: (
            f"its centres from {', '.join(station_label(s) for s in sorted(tied[k]))} "
            f"are {d:.1f} mm apart, over {limit:.1f} mm"
        )
        for k, d in spans.items()
        if d > limit
    }


# --- From a file ------------------------------------------------------------


def tracks_by_station(samples: Sequence[TrackSample]) -> dict[int, list[Track]]:
    """Calibration tracks as the solver's camera-point tracks, per station."""
    by_station: dict[int, list[Track]] = {}
    for sample in samples:
        by_station.setdefault(sample.station, []).append(
            Track(
                points=sample.camera_points(),
                radius_mm=sample.radius_mm,
                turn=sample.turn,
                name=sample.name,
                round=sample.round,
            )
        )
    return by_station


def error_map_from_calibration(
    calibration: Calibration, cell_mm: float = ERROR_MAP_CELL_MM
) -> ErrorMap | None:
    """The predicted error map of a spin calibration, from its file alone.

    Uses each station's stored homography and the tracks that pass the
    health gate under it; every circle kept by several stations ties them.
    None when the file holds no spin-solved station.
    """
    stations = {
        st.index: st
        for st in calibration.stations
        if st.solved_from.startswith("conics")
    }
    by_station = {
        s: t for s, t in tracks_by_station(calibration.tracks).items() if s in stations
    }
    if not by_station:
        return None
    kept, world = {}, {}
    for s, tracks in by_station.items():
        H = stations[s].matrix
        gate = health_gate(tracks, H)
        kept[s] = [t for t in tracks if t not in gate and len(t.points) >= 6]
        world[s] = {t.key: _circle_fit(apply(H, t.points))[0] for t in kept[s]}
    kept = {s: t for s, t in kept.items() if t}
    if not kept:
        return None
    tied: dict[CircleKey, set[int]] = {}
    for s, centres in world.items():
        for k in centres:
            tied.setdefault(k, set()).add(s)
    H = {s: stations[s].matrix for s in kept}
    root = min(kept, key=lambda s: (-len(kept[s]), s))
    problem, x = _build_problem(kept, world, tied, H, root)
    rectangles = {s: stations[s].valid_mm for s in kept}
    return _error_map(problem, x, rectangles, cell_mm)


# --- Report -----------------------------------------------------------------


def _link_line(link: LinkRecord, before: float | None = None) -> str:
    verdict = ""
    if not link_holds(link):
        verdict = (
            f"  not a tie: under {LINK_SHARED_MIN} circles over "
            f"{LINK_SPREAD_MIN_MM:.0f} mm"
        )
    elif not link_advised(link):
        verdict = (
            f"  weak: {LINK_SHARED_ADVISED} or more circles over "
            f"{LINK_SPREAD_ADVISED_MM:.0f} mm advised"
        )
    disagreement = f"{link.disagreement_mm:.1f} mm"
    if before is not None:
        disagreement = f"{before:.1f} -> {disagreement}"
    yaw = (
        "unknown"
        if math.isinf(link.yaw_sigma_mrad)
        else f"{link.yaw_sigma_mrad:.1f} mrad"
    )
    return (
        f"  {station_label(link.a)} - {station_label(link.b)}: {link.shared} shared, "
        f"spread {link.spread_mm:.0f} mm, disagreement {disagreement}, "
        f"yaw {yaw}{verdict}"
    )


def _error_map_lines(error_map: ErrorMap | None) -> list[str]:
    if error_map is None or error_map.covered == 0:
        return []
    worst = error_map.worst_cell
    return [
        f"predicted error ({error_map.cell_mm:.0f} mm cells): worst "
        f"{error_map.worst_mm:.1f} mm near ({worst[0]:.0f}, {worst[1]:.0f}) mm, "
        f"{error_map.cells_over_10mm} of {error_map.covered} cells over "
        f"{ERROR_MAP_LIMIT_MM:.0f} mm"
    ]


def multi_station_report(
    calibration: Calibration, joint: JointSolution | None = None
) -> list[str]:
    """What the operator reads about how the stations hold together.

    From `joint` when the solve just ran; otherwise from the file's
    stations, links and tracks, with the error map recomputed from them.
    """
    lines = ["stations:"]
    circles: dict[int, int] = {}
    for track in calibration.tracks:
        circles[track.station] = circles.get(track.station, 0) + 1
    for st in sorted(calibration.stations, key=lambda s: s.index):
        rect = list(st.valid_mm)
        if joint is not None and st.index in joint.solutions:
            sol = joint.solutions[st.index]
            kept = f"{len(sol.tracks)} kept, {len(sol.dropped)} dropped circles"
            scale = f", scale {joint.scale_ratio.get(st.index, 1.0):.3f}"
        else:
            kept = f"{circles.get(st.index, 0)} circles"
            scale = ""
        lines.append(
            f"  {station_label(st.index)}: {kept}, rms {st.residual_mm:.1f} mm, "
            f"rectangle {rect}{scale}"
        )
    if joint is not None:
        for s, why in sorted(joint.unsolved.items()):
            lines.append(f"  {station_label(s)}: not solved, {why}")
    links = joint.graph.links if joint is not None else calibration.links
    if links:
        lines.append("links:")
        for link in sorted(links, key=lambda k: (k.a, k.b)):
            before = None
            if joint is not None:
                before = joint.seed_disagreement_mm.get((link.a, link.b))
            lines.append(_link_line(link, before))
    if joint is not None:
        for cycle, closure in joint.loops:
            path = " - ".join(str(s) for s in cycle + cycle[:1])
            lines.append(f"loop {path}: closure {closure:.1f} mm")
        for key, why in sorted(joint.dropped.items(), key=lambda kv: kv[0].name):
            lines.append(f"untied circle {_key_text(key)}: {why}")
        error_map = joint.error_map
    else:
        try:
            error_map = error_map_from_calibration(calibration)
        except (ValueError, np.linalg.LinAlgError):
            error_map = None
    lines += _error_map_lines(error_map)
    if joint is not None:
        lines += [f"warning: {w}" for w in joint.warnings]
    return lines
