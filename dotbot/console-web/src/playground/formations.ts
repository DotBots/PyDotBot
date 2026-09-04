import { assignTargets, gather, type Points } from "./assign";
import type { Box, OverlayItem, Vec2 } from "./types";

// Where the demos send the swarm: rings around a pin, a grid inside a region,
// and the show's five figures. The geometry is the Python demos' own, so a bot
// stands in the same place whichever world is driving it. Pure and DOM-free,
// so the worker and vitest both run it.

/** Points evenly spaced on a circle, starting at `phase` radians. */
export function ringPoints(
  cx: number,
  cy: number,
  count: number,
  radius: number,
  phase = 0,
): Points {
  const out = new Float64Array(Math.max(0, count) * 2);
  for (let i = 0; i < count; i++) {
    const a = phase + i * ((2 * Math.PI) / count);
    out[i * 2] = cx + radius * Math.cos(a);
    out[i * 2 + 1] = cy + radius * Math.sin(a);
  }
  return out;
}

/** Every point pulled inside the walls, which the bots cannot drive through. */
export function clampToArena(points: Points, w: number, h: number, margin = 90): Points {
  for (let i = 0; i < points.length; i += 2) {
    points[i] = Math.min(Math.max(points[i], margin), w - margin);
    points[i + 1] = Math.min(Math.max(points[i + 1], margin), h - margin);
  }
  return points;
}

/**
 * Somewhere to park the bots a formation does not need: a ring just inside the
 * walls, so the spares frame what the rest are spelling.
 */
export function spareRing(count: number, w: number, h: number, margin = 150): Points {
  if (count <= 0) return new Float64Array(0);
  const radius = Math.min(w, h) / 2 - margin;
  return clampToArena(ringPoints(w / 2, h / 2, count, radius), w, h, margin);
}

/** The pin each bot belongs to: the nearest one, by squared distance. */
export function splitByProximity(bots: Points, pins: Points): Int32Array {
  const n = bots.length >> 1;
  const k = pins.length >> 1;
  const out = new Int32Array(n);
  if (k === 0) return out;
  for (let i = 0; i < n; i++) {
    let best = 0;
    let bestCost = Infinity;
    for (let p = 0; p < k; p++) {
      const dx = pins[p * 2] - bots[i * 2];
      const dy = pins[p * 2 + 1] - bots[i * 2 + 1];
      const c = dx * dx + dy * dy;
      if (c < bestCost) {
        bestCost = c;
        best = p;
      }
    }
    out[i] = best;
  }
  return out;
}

/**
 * A target per bot: its group's ring around its pin, assigned within the
 * group. A ring of one bot is the pin itself.
 */
export function ringTargets(
  bots: Points,
  pins: Points,
  radius: number,
  w: number,
  h: number,
): Points {
  const n = bots.length >> 1;
  const groups = splitByProximity(bots, pins);
  const out = new Float64Array(n * 2);
  for (let pin = 0; pin < pins.length >> 1; pin++) {
    const members: number[] = [];
    for (let i = 0; i < n; i++) if (groups[i] === pin) members.push(i);
    if (members.length === 0) continue;
    if (members.length === 1) {
      out[members[0] * 2] = pins[pin * 2];
      out[members[0] * 2 + 1] = pins[pin * 2 + 1];
      continue;
    }
    const slots = clampToArena(
      ringPoints(pins[pin * 2], pins[pin * 2 + 1], members.length, radius),
      w,
      h,
    );
    const from = new Float64Array(members.length * 2);
    members.forEach((i, k) => {
      from[k * 2] = bots[i * 2];
      from[k * 2 + 1] = bots[i * 2 + 1];
    });
    const taken = gather(slots, assignTargets(from, slots));
    members.forEach((i, k) => {
      out[i * 2] = taken[k * 2];
      out[i * 2 + 1] = taken[k * 2 + 1];
    });
  }
  return out;
}

/**
 * How many bots each region gets: its share of the total area, with the
 * rounding leftovers going to the largest regions. Every region gets at least
 * one bot as long as there are bots to go round.
 */
export function shareByArea(rects: Box[], bots: number): number[] {
  if (rects.length === 0 || bots <= 0) return rects.map(() => 0);
  const areas = rects.map((r) => Math.max(r.w * r.h, 1));
  const bigFirst = areas.map((a, i) => i).sort((a, b) => areas[b] - areas[a]);
  if (bots <= rects.length) {
    const counts = rects.map(() => 0);
    for (const i of bigFirst.slice(0, bots)) counts[i] = 1;
    return counts;
  }
  const total = areas.reduce((a, b) => a + b, 0);
  const exact = areas.map((a) => (a / total) * (bots - rects.length));
  const counts = exact.map((e) => Math.floor(e) + 1);
  const short = bots - counts.reduce((a, b) => a + b, 0);
  const byFraction = exact
    .map((e, i) => i)
    .sort((a, b) => (exact[b] - Math.floor(exact[b])) - (exact[a] - Math.floor(exact[a])));
  for (const i of byFraction.slice(0, short)) counts[i] += 1;
  return counts;
}

/**
 * `count` points over a rectangle on the squarest grid that holds them, inset
 * from the edges. The last row is centred, so a partly filled grid still looks
 * deliberate.
 */
export function fillPoints(rect: Box, count: number, inset = 60): Points {
  if (count <= 0) return new Float64Array(0);
  const x0 = rect.x + inset;
  const y0 = rect.y + inset;
  const w = Math.max(rect.w - 2 * inset, 1);
  const h = Math.max(rect.h - 2 * inset, 1);
  const columns = Math.max(1, Math.round(Math.sqrt((count * w) / h)));
  const rows = Math.ceil(count / columns);
  const out = new Float64Array(count * 2);
  for (let i = 0; i < count; i++) {
    const row = Math.floor(i / columns);
    const column = i % columns;
    const inRow = Math.min(columns, count - row * columns);
    out[i * 2] = x0 + ((column + 0.5) / inRow) * w;
    out[i * 2 + 1] = y0 + ((row + 0.5) / rows) * h;
  }
  return out;
}

/** Every region's slots, in region order, for `bots` bots to share. */
export function regionSlots(rects: Box[], bots: number, inset = 60): Points {
  const counts = shareByArea(rects, bots);
  const parts = rects.map((r, i) => fillPoints(r, counts[i], inset));
  const out = new Float64Array(parts.reduce((a, p) => a + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

export const FIGURES = ["ring", "double ring", "spiral", "pulse", "wave"] as const;

/** `count` points making one figure at `phase` radians, inside the arena. */
export function formation(
  figure: string,
  count: number,
  w: number,
  h: number,
  phase: number,
): Points {
  if (count <= 0) return new Float64Array(0);
  const cx = w / 2;
  const cy = h / 2;
  const reach = Math.min(w, h) / 2 - 200;

  let points: Points;
  if (figure === "double ring") {
    const inner = Math.floor(count / 2);
    points = new Float64Array(count * 2);
    points.set(ringPoints(cx, cy, inner, reach * 0.5, phase), 0);
    points.set(ringPoints(cx, cy, count - inner, reach, -phase), inner * 2);
  } else if (figure === "spiral") {
    points = new Float64Array(count * 2);
    for (let i = 0; i < count; i++) {
      const t = count === 1 ? 0 : i / (count - 1);
      const angle = phase + t * 2.5 * 2 * Math.PI;
      const radius = reach * (0.15 + 0.85 * t);
      points[i * 2] = cx + radius * Math.cos(angle);
      points[i * 2 + 1] = cy + radius * Math.sin(angle);
    }
  } else if (figure === "pulse") {
    points = ringPoints(cx, cy, count, reach * (0.55 + 0.45 * Math.sin(phase)), phase * 0.2);
  } else if (figure === "wave") {
    const columns = Math.max(1, Math.ceil(Math.sqrt(count * 2)));
    const rows = Math.ceil(count / columns);
    points = new Float64Array(count * 2);
    for (let i = 0; i < count; i++) {
      const column = i % columns;
      const row = Math.floor(i / columns);
      points[i * 2] = cx + (column / Math.max(1, columns - 1) - 0.5) * 2 * reach;
      points[i * 2 + 1] =
        cy + (row - (rows - 1) / 2) * 180 + reach * 0.45 * Math.sin(phase + column * 0.7);
    }
  } else {
    points = ringPoints(cx, cy, count, reach, phase);
  }
  return clampToArena(points, w, h);
}

/** Each point's bearing from the arena centre, in degrees. */
export function hueByAngle(points: Points, w: number, h: number): Float32Array {
  const out = new Float32Array(points.length >> 1);
  for (let i = 0; i < out.length; i++) {
    const a = Math.atan2(points[i * 2 + 1] - h / 2, points[i * 2] - w / 2);
    out[i] = ((a * 180) / Math.PI + 360) % 360;
  }
  return out;
}

function pathItem(points: Points, from: number, to: number, closed: boolean): OverlayItem[] {
  if (to - from < 2) return [];
  const pts: Vec2[] = [];
  for (let i = from; i < to; i++) pts.push({ x: points[i * 2], y: points[i * 2 + 1] });
  return [{ type: "polyline", points: pts, closed, color: "muted" }];
}

/** The figure as a path: closed for a ring, open for a spiral or a wave. */
export function figureOverlay(figure: string, points: Points): OverlayItem[] {
  const count = points.length >> 1;
  if (figure === "double ring") {
    const half = Math.floor(count / 2);
    return [...pathItem(points, 0, half, true), ...pathItem(points, half, count, true)];
  }
  return pathItem(points, 0, count, figure === "ring" || figure === "pulse");
}
