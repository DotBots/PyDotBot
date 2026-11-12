// The robots' station rule, mirrored from dotbot/calibration/station_rule.py
// for drawing on the page; station_rule.json pins both copies.

export type StoredRect = readonly number[];

export const RECT_MAX_DEFAULT = 100_000;
export const STORED_ABSENT = 0xffffffff;

/** The box a stored one stands for: all 0xFF reads as (0, 0, default, default). */
export function resolveRect(stored: StoredRect): [number, number, number, number] {
  if (stored.every((v) => v === STORED_ABSENT)) return [0, 0, RECT_MAX_DEFAULT, RECT_MAX_DEFAULT];
  return [stored[0], stored[1], stored[2], stored[3]];
}

/** Edges included; NaN is outside. */
export function contains(rect: StoredRect, x: number, y: number): boolean {
  return x >= rect[0] && x <= rect[2] && y >= rect[1] && y <= rect[3];
}

function d2(rect: StoredRect, x: number, y: number): number {
  const cx = 0.5 * (rect[0] + rect[2]);
  const cy = 0.5 * (rect[1] + rect[3]);
  return (x - cx) ** 2 + (y - cy) ** 2;
}

/** The station whose solve a robot keeps, or null; `solves` in any order. */
export function select(
  solves: { station: number; x: number; y: number }[],
  rects: Record<number, StoredRect>,
): number | null {
  let best: { station: number; d2: number } | null = null;
  for (const s of [...solves].sort((a, b) => a.station - b.station)) {
    if (!Number.isFinite(s.x) || !Number.isFinite(s.y)) continue;
    const rect = resolveRect(rects[s.station]);
    if (!contains(rect, s.x, s.y)) continue;
    const dist = d2(rect, s.x, s.y);
    if (best !== null && !(dist < best.d2)) continue;
    best = { station: s.station, d2: dist };
  }
  return best === null ? null : best.station;
}

/** The stations that can give the fix at (x, y) when every station sees the
 * robot there: one when the boxes decide, several when they do not. */
export function candidates(rects: Record<number, StoredRect>, x: number, y: number): number[] {
  const inside: [number, number][] = [];
  for (const key of Object.keys(rects).map(Number).sort((a, b) => a - b)) {
    const rect = resolveRect(rects[key]);
    if (contains(rect, x, y)) inside.push([key, d2(rect, x, y)]);
  }
  if (inside.length === 0) return [];
  const least = Math.min(...inside.map(([, d]) => d));
  return inside.filter(([, d]) => d === least).map(([s]) => s);
}
