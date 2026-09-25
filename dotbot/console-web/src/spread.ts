import { Area, BotPose, LH2Position, UnifiedBot, Waypoint } from "./types";

// Spread: N selected robots, N targets, one each. The assignment is the one
// with the least total straight-line distance unless the operator swaps it;
// the hazards are hints only - nothing here plans around another robot.

/** A robot's body radius about its axle when no pose gives one: DotBot v3's, rounded up. */
export const FALLBACK_BODY_RADIUS_MM = 84;

/**
 * Minimal-cost assignment of rows to distinct columns, rows <= columns.
 * Returns the column of each row. O(rows^2 * columns).
 */
export function hungarian(cost: number[][]): number[] {
  const n = cost.length;
  if (n === 0) return [];
  const m = cost[0].length;
  if (m < n) throw new Error("hungarian: more rows than columns");
  const INF = Number.POSITIVE_INFINITY;
  // 1-based potentials and matching, as in the classic formulation.
  const u = new Array(n + 1).fill(0);
  const v = new Array(m + 1).fill(0);
  const p = new Array(m + 1).fill(0); // row matched to each column
  const way = new Array(m + 1).fill(0);
  for (let i = 1; i <= n; i++) {
    p[0] = i;
    let j0 = 0;
    const minv = new Array(m + 1).fill(INF);
    const used = new Array(m + 1).fill(false);
    do {
      used[j0] = true;
      const i0 = p[j0];
      let delta = INF;
      let j1 = 0;
      for (let j = 1; j <= m; j++) {
        if (used[j]) continue;
        const cur = cost[i0 - 1][j - 1] - u[i0] - v[j];
        if (cur < minv[j]) {
          minv[j] = cur;
          way[j] = j0;
        }
        if (minv[j] < delta) {
          delta = minv[j];
          j1 = j;
        }
      }
      for (let j = 0; j <= m; j++) {
        if (used[j]) {
          u[p[j]] += delta;
          v[j] -= delta;
        } else {
          minv[j] -= delta;
        }
      }
      j0 = j1;
    } while (p[j0] !== 0);
    do {
      const j1 = way[j0];
      p[j0] = p[j1];
      j0 = j1;
    } while (j0 !== 0);
  }
  const colOf = new Array(n).fill(-1);
  for (let j = 1; j <= m; j++) if (p[j] > 0) colOf[p[j] - 1] = j - 1;
  return colOf;
}

const dist = (a: LH2Position, b: LH2Position) => Math.hypot(a.x - b.x, a.y - b.y);

/** Where a robot starts from, measured as a waypoint is: its axle, else its fix. */
export function startOf(b: UnifiedBot): LH2Position | null {
  return b.axle ?? b.pose?.axle ?? b.position ?? null;
}

/**
 * The robot id for each target, least total distance first. A robot with no
 * known position costs the same to every target.
 */
export function assign(bots: UnifiedBot[], targets: Waypoint[]): string[] {
  if (targets.length === 0 || bots.length < targets.length) return [];
  const cost = targets.map((t) =>
    bots.map((b) => {
      const s = startOf(b);
      return s ? dist(s, t) : 0;
    }),
  );
  return hungarian(cost).map((j) => bots[j].id);
}

/**
 * `order` with target `t` given to robot `id`; whoever held it takes the
 * target `id` had, if any.
 */
export function swap(order: string[], t: number, id: string): string[] {
  const next = [...order];
  const had = next.indexOf(id);
  const holder = next[t];
  next[t] = id;
  if (had >= 0 && had !== t) next[had] = holder;
  return next;
}

/** Whether an operator's order still fits: same targets, the same robots. */
export function orderFits(order: string[] | null | undefined, ids: string[], targets: number): order is string[] {
  return (
    !!order &&
    order.length === targets &&
    new Set(order).size === order.length &&
    order.every((id) => ids.includes(id))
  );
}

const orient = (a: LH2Position, b: LH2Position, c: LH2Position) =>
  Math.sign((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x));

const onSegment = (a: LH2Position, b: LH2Position, p: LH2Position) =>
  Math.min(a.x, b.x) <= p.x &&
  p.x <= Math.max(a.x, b.x) &&
  Math.min(a.y, b.y) <= p.y &&
  p.y <= Math.max(a.y, b.y);

/** Whether segment a-b meets segment c-d, touching and overlapping included. */
export function segmentsCross(a: LH2Position, b: LH2Position, c: LH2Position, d: LH2Position): boolean {
  const o1 = orient(a, b, c);
  const o2 = orient(a, b, d);
  const o3 = orient(c, d, a);
  const o4 = orient(c, d, b);
  if (o1 !== o2 && o3 !== o4) return true;
  return (
    (o1 === 0 && onSegment(a, b, c)) ||
    (o2 === 0 && onSegment(a, b, d)) ||
    (o3 === 0 && onSegment(c, d, a)) ||
    (o4 === 0 && onSegment(c, d, b))
  );
}

/** The farthest point of the body, tyres included, from the axle a waypoint places. */
export function bodyRadiusMm(pose: BotPose | null): number | null {
  if (!pose) return null;
  const points = [...pose.outline, ...pose.wheels.flat()];
  if (points.length === 0) return null;
  return Math.max(...points.map((p) => dist(pose.axle, p)));
}

/** How far apart two targets must be for the robots parked on them not to touch. */
export function spacingMm(bots: UnifiedBot[]): number {
  const radii = bots.map((b) => bodyRadiusMm(b.pose)).filter((r): r is number => r !== null);
  return 2 * (radii.length ? Math.max(...radii) : FALLBACK_BODY_RADIUS_MM);
}

export interface SpreadLeg {
  id: string;
  target: number;
  from: LH2Position | null;
  to: Waypoint;
}

export interface SpreadHazards {
  /** Pairs of target indices whose straight paths cross. */
  crossings: [number, number][];
  /** Pairs of target indices closer than the spacing. */
  tooClose: [number, number][];
  /** Target indices outside the site. */
  outside: number[];
  /** Robots with no known position, whose path cannot be drawn. */
  unplaced: string[];
}

export function legsOf(bots: UnifiedBot[], targets: Waypoint[], order: string[]): SpreadLeg[] {
  const byId = new Map(bots.map((b) => [b.id, b]));
  return order.map((id, t) => {
    const b = byId.get(id);
    return { id, target: t, from: b ? startOf(b) : null, to: targets[t] };
  });
}

export function hazardsOf(legs: SpreadLeg[], spacing: number, extent: Area | null): SpreadHazards {
  const crossings: [number, number][] = [];
  const tooClose: [number, number][] = [];
  for (let i = 0; i < legs.length; i++) {
    for (let j = i + 1; j < legs.length; j++) {
      const a = legs[i];
      const b = legs[j];
      if (a.from && b.from && segmentsCross(a.from, a.to, b.from, b.to)) crossings.push([a.target, b.target]);
      if (dist(a.to, b.to) < spacing) tooClose.push([a.target, b.target]);
    }
  }
  const outside = extent
    ? legs
        .filter(
          (l) =>
            l.to.x < extent.x || l.to.y < extent.y || l.to.x > extent.x + extent.w || l.to.y > extent.y + extent.h,
        )
        .map((l) => l.target)
    : [];
  const unplaced = legs.filter((l) => !l.from).map((l) => l.id);
  return { crossings, tooClose, outside, unplaced };
}

export const hazardCount = (h: SpreadHazards) =>
  h.crossings.length + h.tooClose.length + h.outside.length + h.unplaced.length;

const short = (id: string) => id.slice(-4).toUpperCase();

/** The hazards, one line each, targets numbered from 1. */
export function describeHazards(h: SpreadHazards, legs: SpreadLeg[], spacing: number): string[] {
  const who = (t: number) => short(legs[t]?.id ?? "");
  return [
    ...h.crossings.map(([a, b]) => `${who(a)} and ${who(b)}: paths cross`),
    ...h.tooClose.map(([a, b]) => `targets ${a + 1} and ${b + 1}: closer than ${Math.round(spacing)} mm`),
    ...h.outside.map((t) => `target ${t + 1}: outside the site`),
    ...h.unplaced.map((id) => `${short(id)}: no position, path unknown`),
  ];
}

/** A colour per target, told apart from its neighbours. */
export const SPREAD_COLORS = [
  "#38bdf8",
  "#f59e0b",
  "#a855f7",
  "#22c55e",
  "#f43f5e",
  "#14b8a6",
  "#eab308",
  "#6366f1",
];
export const spreadColor = (t: number) => SPREAD_COLORS[t % SPREAD_COLORS.length];

export interface SpreadPlan {
  /** The robot for each target placed so far. */
  order: string[];
  /** Whether `order` is the operator's rather than the shortest. */
  swapped: boolean;
  legs: SpreadLeg[];
  hazards: SpreadHazards;
  spacing: number;
  /** Target indices a hazard names. */
  flagged: Set<number>;
}

export function planSpread(
  bots: UnifiedBot[],
  targets: Waypoint[],
  operatorOrder: string[] | null | undefined,
  extent: Area | null,
): SpreadPlan {
  const ids = bots.map((b) => b.id);
  const swapped = orderFits(operatorOrder, ids, targets.length);
  const order = swapped ? operatorOrder : assign(bots, targets);
  const legs = legsOf(bots, targets, order);
  const spacing = spacingMm(bots);
  const hazards = hazardsOf(legs, spacing, extent);
  const flagged = new Set<number>([...hazards.tooClose.flat(), ...hazards.outside]);
  return { order, swapped, legs, hazards, spacing, flagged };
}
