import type { Point } from "./model";

// Putting a spin calibration, solved in its own frame, into the room: one
// turn and shift, from two robots that spun on taped marks, from typed
// numbers, or round the robots as they stood. The same move the controller's
// place route applies: p' = R p + d, a positive angle turning +x toward +y.

/** What a spinning robot sweeps round its turning centre, DotBot v3, mm. */
export const REACH_MM = 84;
/** Floor left round the field when the room's size is not known yet, mm. */
export const MARGIN_MM = 500;

export interface Rigid {
  theta_deg: number;
  dx: number;
  dy: number;
}

export interface SpunRobot {
  name: string;
  /** Turning centre in the spin's own frame, mm */
  at: Point;
}

export function moveBy(r: Rigid, p: Point): Point {
  const t = (r.theta_deg * Math.PI) / 180;
  const c = Math.cos(t);
  const s = Math.sin(t);
  return [c * p[0] - s * p[1] + r.dx, s * p[0] + c * p[1] + r.dy];
}

/** Each robot that spun, once: the mean of its circles' centres over the
 * stations that saw it. */
export function spunRobots(stations: { circles: { name: string; x: number; y: number }[] }[]): SpunRobot[] {
  const by = new Map<string, Point[]>();
  for (const st of stations) for (const c of st.circles) by.set(c.name, [...(by.get(c.name) ?? []), [c.x, c.y]]);
  return [...by.entries()]
    .map(([name, ps]) => ({ name, at: [ps.reduce((a, p) => a + p[0], 0) / ps.length, ps.reduce((a, p) => a + p[1], 0) / ps.length] as Point }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** The move putting robot `a`'s centre on mark `aRoom` and pointing it at
 * `bRoom` through `b`; with how far apart the tape and the spin put them. */
export function fromMarks(a: Point, aRoom: Point, b: Point, bRoom: Point): { move: Rigid; spinMm: number; tapeMm: number } {
  const spin = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const room = Math.atan2(bRoom[1] - aRoom[1], bRoom[0] - aRoom[0]);
  let theta = ((room - spin) * 180) / Math.PI;
  theta = ((((theta + 180) % 360) + 360) % 360) - 180;
  const turned = moveBy({ theta_deg: theta, dx: 0, dy: 0 }, a);
  return {
    move: { theta_deg: theta, dx: aRoom[0] - turned[0], dy: aRoom[1] - turned[1] },
    spinMm: Math.hypot(b[0] - a[0], b[1] - a[1]),
    tapeMm: Math.hypot(bRoom[0] - aRoom[0], bRoom[1] - aRoom[1]),
  };
}

const down = (v: number) => Math.floor(v / 10) * 10;
const up = (v: number) => Math.ceil(v / 10) * 10;

export interface Proposal {
  /** The robots' field, grown by what a spinning robot sweeps */
  field: [number, number, number, number];
  /** The floor: the room's if known, else the field with a margin */
  extent: [number, number];
  /** Robots whose centre lands below zero: the place route refuses those */
  below: string[];
  /** Robots outside a known floor, where positions are dropped */
  outside: string[];
}

export function propose(robots: SpunRobot[], move: Rigid, extent: [number, number] | null): Proposal {
  const placed = robots.map((r) => ({ name: r.name, at: moveBy(move, r.at) }));
  const xs = placed.map((p) => p.at[0]);
  const ys = placed.map((p) => p.at[1]);
  const x0 = Math.max(0, down(Math.min(...xs) - REACH_MM));
  const y0 = Math.max(0, down(Math.min(...ys) - REACH_MM));
  const x1 = up(Math.max(...xs) + REACH_MM);
  const y1 = up(Math.max(...ys) + REACH_MM);
  const floor: [number, number] = extent ?? [x1 + MARGIN_MM, y1 + MARGIN_MM];
  return {
    field: [x0, y0, x1 - x0, y1 - y0],
    extent: floor,
    below: placed.filter((p) => p.at[0] < 0 || p.at[1] < 0).map((p) => p.name),
    outside: extent ? placed.filter((p) => p.at[0] > extent[0] || p.at[1] > extent[1]).map((p) => p.name) : [],
  };
}

/** Round the robots as they stood: zero `margin` above and left of the
 * spin's own zero, which is at its robots' top-left. */
export const aroundRobots = (margin = MARGIN_MM): Rigid => ({ theta_deg: 0, dx: margin, dy: margin });
