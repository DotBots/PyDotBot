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

/** The move that puts zero at `p` and, with `q`, the x axis through it. */
export function zeroAt(p: Point, q: Point | null, note: string | null): FrameMove {
  const theta = q ? (Math.atan2(q[1] - p[1], q[0] - p[0]) * 180) / Math.PI : 0;
  return { theta_deg: Math.round(theta * 100) / 100, pivot: [Math.round(p[0]), Math.round(p[1])], dx: Math.round(p[0]), dy: Math.round(p[1]), note };
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
