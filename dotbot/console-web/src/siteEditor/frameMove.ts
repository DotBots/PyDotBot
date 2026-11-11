import type { Point } from "./model";

// A move of the site's frame: turned by `theta_deg` about `pivot`, then zero
// shifted by (dx, dy), all in the current frame's mm, as the server's
// site_turn.floor_move takes it.

export interface FrameMove {
  theta_deg: number;
  pivot: Point;
  dx: number;
  dy: number;
  note: string | null;
}

export const NO_MOVE: FrameMove = { theta_deg: 0, pivot: [0, 0], dx: 0, dy: 0, note: null };

export const moves = (m: FrameMove) => Math.abs(m.theta_deg) > 1e-9 || Math.abs(m.dx) > 1e-9 || Math.abs(m.dy) > 1e-9;

function turn(p: Point, about: Point, deg: number): Point {
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t);
  const s = Math.sin(t);
  const x = p[0] - about[0];
  const y = p[1] - about[1];
  return [about[0] + c * x - s * y, about[1] + s * x + c * y];
}

/** A floor point's coordinates in the new frame. */
export function toNew(m: FrameMove, p: Point): Point {
  const q = turn(p, m.pivot, -m.theta_deg);
  return [q[0] - m.dx, q[1] - m.dy];
}

/** A point given in the new frame, in the current frame's coordinates. */
export function toOld(m: FrameMove, p: Point): Point {
  return turn([p[0] + m.dx, p[1] + m.dy], m.pivot, m.theta_deg);
}

/** `m` as the server takes it. */
export const moveBody = (m: FrameMove) => ({ theta_deg: m.theta_deg, pivot: [m.pivot[0], m.pivot[1]] as [number, number], dx_mm: m.dx, dy_mm: m.dy });

/** Whether `a` and `b` put the origin in the same place; a missing move is none. */
export function sameMove(a: FrameMove | null, b: FrameMove | null): boolean {
  const x = a ?? NO_MOVE;
  const y = b ?? NO_MOVE;
  if (!moves(x) && !moves(y)) return true;
  return x.theta_deg === y.theta_deg && x.dx === y.dx && x.dy === y.dy && (x.theta_deg === 0 || (x.pivot[0] === y.pivot[0] && x.pivot[1] === y.pivot[1]));
}

/** Where a point given in the frame `m` makes lands on a plan drawn in the
 * frame `drawn` makes; both moves start from the saved frame. */
export function onPlan(m: FrameMove, drawn: FrameMove | null, p: Point): Point {
  const saved = toOld(m, p);
  return drawn ? toNew(drawn, saved) : saved;
}

/** The move that puts zero at `p` and, with `q`, the x axis through it. */
export function zeroAt(p: Point, q: Point | null, note: string | null): FrameMove {
  const theta = q ? (Math.atan2(q[1] - p[1], q[0] - p[0]) * 180) / Math.PI : 0;
  return { theta_deg: Math.round(theta * 100) / 100, pivot: [Math.round(p[0]), Math.round(p[1])], dx: Math.round(p[0]), dy: Math.round(p[1]), note };
}

/** A robot pinned to a spot: where it reports itself now, and where it stands in the room. */
export interface Anchor {
  robot: string;
  fix: Point;
  spot: Point;
  /** What the plan calls it; the robot's id when unset. */
  label?: string;
}

const round = (v: number, d = 10) => Math.round(v * d) / d;

/** `m` with its new origin at `o` (current frame's mm), the turn kept. */
export function withOrigin(m: FrameMove, o: Point): FrameMove {
  const back = turn(o, m.pivot, -m.theta_deg);
  return { ...m, dx: round(back[0]), dy: round(back[1]) };
}

/** `m` turned further by `deg` about `c` (current frame's mm): every point
 * of the new frame lands where `m` put it, turned about `c`. */
export function turnedAbout(m: FrameMove, c: Point, deg: number): FrameMove {
  const theta = Math.round((m.theta_deg + deg) * 100) / 100;
  const swung = turn([m.pivot[0] - c[0], m.pivot[1] - c[1]], [0, 0], theta - m.theta_deg);
  const back = turn([c[0] + swung[0] - m.pivot[0], c[1] + swung[1] - m.pivot[1]], [0, 0], -theta);
  return { ...m, theta_deg: theta, dx: round(m.dx + back[0]), dy: round(m.dy + back[1]) };
}

/** Each anchor's robot against its spot under `m`, mm. */
export function anchorErrors(m: FrameMove, anchors: Anchor[]): number[] {
  return anchors.map((a) => {
    const at = toOld(m, a.spot);
    return Math.hypot(at[0] - a.fix[0], at[1] - a.fix[1]);
  });
}

/** Where the origin may go for the turn of `m`: robots report positions as
 * unsigned millimetres, so every measured point must keep both coordinates
 * at or above zero. The corner, in the current frame's mm, and the two
 * half-planes beyond it as polygons to hatch; null without points. */
export function forbidden(m: FrameMove, points: Point[]): { corner: Point; beyond: Point[][]; originOk: boolean } | null {
  if (!points.length) return null;
  const rot = (p: Point): Point => turn(p, [0, 0], -m.theta_deg);
  const unrot = (p: Point): Point => turn(p, [0, 0], m.theta_deg);
  const rp = points.map(rot);
  const mx = Math.min(...rp.map((p) => p[0]));
  const my = Math.min(...rp.map((p) => p[1]));
  const far = 100000;
  const o = rot(toOld(m, [0, 0]));
  return {
    corner: unrot([mx, my]),
    beyond: [
      [unrot([mx, -far]), unrot([far, -far]), unrot([far, far]), unrot([mx, far])],
      [unrot([-far, my]), unrot([far, my]), unrot([far, far]), unrot([-far, far])],
    ],
    originOk: o[0] <= mx + 1e-6 && o[1] <= my + 1e-6,
  };
}

/** The CLI twin of a move of `site`'s frame for `calibration`. */
export function frameTwin(site: string, calibration: string, m: FrameMove): string {
  const parts = [`dotbot site turn ${site}`];
  if (m.theta_deg) parts.push(`--rotate ${m.theta_deg} --about ${Math.round(m.pivot[0])},${Math.round(m.pivot[1])}`);
  if (m.dx || m.dy) parts.push(`--shift ${Math.round(m.dx)},${Math.round(m.dy)}`);
  if (m.note) parts.push(`--anchor ${JSON.stringify(m.note)}`);
  parts.push(`--calibration ${calibration}`);
  return parts.join(" ");
}

/** A server warning about a move, without ids: "2 measured spots land
 * outside the floor, where robots drop their positions". */
export function plainWarning(w: string): string {
  return w
    .replace(/^[0-9a-f]{8,}: /, "")
    .replace(/(\d+) spin circle\(s\) \([^)]*\) land outside the site's extent/, (_, n) => `${n} measured spot${n === "1" ? "" : "s"} land${n === "1" ? "s" : ""} outside the extent`)
    .replace(/(\d+) placement point\(s\) land outside the site's extent/, (_, n) => `${n} placement point${n === "1" ? "" : "s"} land${n === "1" ? "s" : ""} outside the extent`);
}
