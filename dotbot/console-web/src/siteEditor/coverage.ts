import fixtures from "../../../calibration/station_rule.json";
import { candidates, select } from "./stationRule";
import type { LibraryRow, Rect } from "./types";

// What the Stations kind draws: who gives the fix by the robots' rule, the
// predicted error the server computes, the handover line, and whether the
// stations look moved between spins.

export interface Coverage {
  id: string;
  limit_mm: number;
  geometry: Geometry;
  links: { a: number; b: number; shared: number; spread_mm: number; disagreement_mm: number; holds: boolean; advised: boolean }[];
  headline: { worst_mm: number; at: [number, number]; bound: boolean; fused_worst_mm: number; cells: number; cells_over_limit: number; cell_mm: number; per_station: Record<string, number | null> } | null;
  fog: { origin: [number, number]; cell_mm: number; cols: number; rows: number; sigma: (number | null)[]; undecided: boolean[]; own: Record<string, (number | null)[]> } | null;
  next: { x: number; y: number; stations: number[]; why: string }[];
}

export interface Geometry {
  stations: Record<string, { x_mm: number; y_mm: number; height_mm: number; off_square_deg: number }>;
  apart_mm: Record<string, number>;
}

export type Boxes = { index: number; rect: Rect }[];

const asRects = (boxes: Boxes) => Object.fromEntries(boxes.map((b) => [b.index, b.rect])) as Record<number, Rect>;

/** Whether this page's rule agrees with every case the Python rule wrote. */
export function fixtureAgreement(): { agree: number; total: number } {
  const rectsOf = (r: Record<string, number[] | undefined>) =>
    Object.fromEntries(Object.entries(r).flatMap(([k, v]) => (v ? [[Number(k), v]] : []))) as Record<number, number[]>;
  let agree = 0;
  for (const c of fixtures.cases) {
    const solves = c.solves.map(([s, x, y]) => ({ station: Number(s), x: Number(x), y: Number(y) }));
    if (select(solves, rectsOf(c.rects)) === c.expect) agree++;
  }
  return { agree, total: fixtures.cases.length };
}

/** Station hues as RGB, for drawing into a canvas. */
const HUE: Record<number, [number, number, number]> = { 0: [57, 135, 229], 1: [213, 81, 129] };
const hue = (s: number) => HUE[s % 2];

/** An image of who gives the fix over `extent` (frame mm, from zero), one
 * pixel per `cell` mm: a station's tint where its box decides, the two hues
 * in stripes where the boxes do not, grey stripes where nobody does. */
export function fixImage(boxes: Boxes, extent: [number, number], cell = 10): { url: string; w: number; h: number } | null {
  if (typeof document === "undefined" || !boxes.length) return null;
  const w = Math.max(1, Math.ceil(extent[0] / cell));
  const h = Math.max(1, Math.ceil(extent[1] / cell));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const img = ctx.createImageData(w, h);
  const rects = asRects(boxes);
  for (let j = 0; j < h; j++)
    for (let i = 0; i < w; i++) {
      const who = candidates(rects, (i + 0.5) * cell, (j + 0.5) * cell);
      const stripe = Math.floor((i + j) / 2) % 2;
      let rgb: [number, number, number];
      let a: number;
      if (who.length === 1) {
        rgb = hue(who[0]);
        a = 70;
      } else if (who.length > 1) {
        rgb = hue(who[stripe % who.length]);
        a = 80;
      } else {
        rgb = [128, 128, 128];
        a = stripe ? 40 : 0;
      }
      const k = 4 * (j * w + i);
      img.data[k] = rgb[0];
      img.data[k + 1] = rgb[1];
      img.data[k + 2] = rgb[2];
      img.data[k + 3] = a;
    }
  ctx.putImageData(img, 0, 0);
  return { url: canvas.toDataURL(), w: w * cell, h: h * cell };
}

/** The predicted error as a neutral fog: darker where it is larger, amber
 * where it passes `limit`; transparent where no station gives a fix. */
export function fogImage(fog: NonNullable<Coverage["fog"]>, limit: number, light: boolean): string | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = fog.cols;
  canvas.height = fog.rows;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const img = ctx.createImageData(fog.cols, fog.rows);
  const top = Math.max(limit, 0.1);
  fog.sigma.forEach((v, n) => {
    const k = 4 * n;
    if (v === null) return;
    if (v > limit) {
      img.data.set([245, 158, 11, 120], k);
      return;
    }
    const t = Math.min(1, v / top);
    const g = light ? 15 : 235;
    img.data.set([g, g, g, Math.round(20 + 150 * t)], k);
  });
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL();
}

/** Line segments where the fog crosses `level` mm, frame mm (marching squares). */
export function contours(fog: NonNullable<Coverage["fog"]>, level: number): [number, number, number, number][] {
  const { cols, rows, cell_mm: c, origin } = fog;
  const at = (i: number, j: number) => fog.sigma[j * cols + i];
  const segs: [number, number, number, number][] = [];
  const cx = (i: number) => origin[0] + (i + 0.5) * c;
  const cy = (j: number) => origin[1] + (j + 0.5) * c;
  for (let j = 0; j < rows - 1; j++)
    for (let i = 0; i < cols - 1; i++) {
      const v = [at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)];
      if (v.some((x) => x === null)) continue;
      const [a, b, d, e] = v as number[];
      const pts: [number, number][] = [];
      const edge = (p: number, q: number, x0: number, y0: number, x1: number, y1: number) => {
        if ((p < level) !== (q < level)) {
          const t = (level - p) / (q - p);
          pts.push([x0 + t * (x1 - x0), y0 + t * (y1 - y0)]);
        }
      };
      edge(a, b, cx(i), cy(j), cx(i + 1), cy(j));
      edge(b, d, cx(i + 1), cy(j), cx(i + 1), cy(j + 1));
      edge(e, d, cx(i), cy(j + 1), cx(i + 1), cy(j + 1));
      edge(a, e, cx(i), cy(j), cx(i), cy(j + 1));
      for (let k = 0; k + 1 < pts.length; k += 2) segs.push([pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1]]);
    }
  return segs;
}

/** The fog's value at a point, null outside it or where nobody gives a fix. */
export function sample(grid: (number | null)[], fog: NonNullable<Coverage["fog"]>, x: number, y: number): number | null {
  const i = Math.floor((x - fog.origin[0]) / fog.cell_mm);
  const j = Math.floor((y - fog.origin[1]) / fog.cell_mm);
  if (i < 0 || j < 0 || i >= fog.cols || j >= fog.rows) return null;
  return grid[j * fog.cols + i];
}

/** Where two boxes hand over: the line halfway between their centres, inside
 * their overlap; null when they share a centre or do not overlap. */
export function handover(a: Rect, b: Rect): { from: [number, number]; to: [number, number]; label: string } | null {
  const ox0 = Math.max(a[0], b[0]);
  const oy0 = Math.max(a[1], b[1]);
  const ox1 = Math.min(a[2], b[2]);
  const oy1 = Math.min(a[3], b[3]);
  if (ox1 <= ox0 || oy1 <= oy0) return null;
  const ca = [(a[0] + a[2]) / 2, (a[1] + a[3]) / 2];
  const cb = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
  const dx = cb[0] - ca[0];
  const dy = cb[1] - ca[1];
  if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) return null;
  const m = [(ca[0] + cb[0]) / 2, (ca[1] + cb[1]) / 2];
  if (Math.abs(dy) < 1e-9) {
    if (m[0] < ox0 || m[0] > ox1) return null;
    return { from: [m[0], oy0], to: [m[0], oy1], label: `handover x ${Math.round(m[0])} mm` };
  }
  if (Math.abs(dx) < 1e-9) {
    if (m[1] < oy0 || m[1] > oy1) return null;
    return { from: [ox0, m[1]], to: [ox1, m[1]], label: `handover y ${Math.round(m[1])} mm` };
  }
  // A slanted bisector: clip it to the overlap
  const dir = [-dy, dx];
  const ts: number[] = [];
  const add = (t: number) => {
    const p = [m[0] + t * dir[0], m[1] + t * dir[1]];
    if (p[0] >= ox0 - 1e-6 && p[0] <= ox1 + 1e-6 && p[1] >= oy0 - 1e-6 && p[1] <= oy1 + 1e-6) ts.push(t);
  };
  add((ox0 - m[0]) / dir[0]);
  add((ox1 - m[0]) / dir[0]);
  add((oy0 - m[1]) / dir[1]);
  add((oy1 - m[1]) / dir[1]);
  if (ts.length < 2) return null;
  const t0 = Math.min(...ts);
  const t1 = Math.max(...ts);
  return { from: [m[0] + t0 * dir[0], m[1] + t0 * dir[1]], to: [m[0] + t1 * dir[0], m[1] + t1 * dir[1]], label: "handover" };
}

/** The share of `extent` where `station` alone gives the fix. */
export function share(boxes: Boxes, extent: [number, number], station: number, cells = 40): number {
  const rects = asRects(boxes);
  let n = 0;
  let mine = 0;
  for (let j = 0; j < cells; j++)
    for (let i = 0; i < cells; i++) {
      n++;
      const who = candidates(rects, ((i + 0.5) * extent[0]) / cells, ((j + 0.5) * extent[1]) / cells);
      if (who.length === 1 && who[0] === station) mine++;
    }
  return mine / n;
}

/** Two boxes splitting the floor with `overlap` mm in common, cut across the
 * axis the stations stand apart on, each station on its own side. */
export function splitFloor(extent: [number, number], geometry: Geometry | null, stations: [number, number], overlap = 200): Record<number, Rect> {
  const [w, h] = extent;
  const [a, b] = stations;
  const pa = geometry?.stations[String(a)];
  const pb = geometry?.stations[String(b)];
  // Across the axis the stations stand farthest apart on, for the floor's size
  const along = pa && pb ? (Math.abs(pa.x_mm - pb.x_mm) / w >= Math.abs(pa.y_mm - pb.y_mm) / h ? 0 : 1) : w >= h ? 0 : 1;
  const span = along === 0 ? w : h;
  const cut = Math.round(span / 2 / 10) * 10;
  const lo: Rect = along === 0 ? [0, 0, cut + overlap / 2, h] : [0, 0, w, cut + overlap / 2];
  const hi: Rect = along === 0 ? [cut - overlap / 2, 0, w, h] : [0, cut - overlap / 2, w, h];
  const aLow = pa && pb ? (along === 0 ? pa.x_mm <= pb.x_mm : pa.y_mm <= pb.y_mm) : true;
  return aLow ? { [a]: lo, [b]: hi } : { [a]: hi, [b]: lo };
}

export interface Moved {
  /** Distinct spins compared, the shown one included. */
  spins: number;
  verdict: "no sign" | "moved?" | "one spin";
  /** "S0 2380-2482 mm up", per station and pair. */
  ranges: string[];
}

const SPREAD_OK_MM = 250;

/** Whether the stations look moved: the shown spin's frame-invariant shape
 * (heights, distance apart) against every other spin of this site's library. */
export function moved(shown: LibraryRow | null, rows: LibraryRow[]): Moved {
  if (!shown?.geometry) return { spins: 0, verdict: "one spin", ranges: [] };
  const seen = new Map<string, LibraryRow>();
  // This room's spins only: a file in another frame may be this one before a move
  for (const r of rows) if (r.geometry && r.in_frame && !seen.has(r.spin)) seen.set(r.spin, r);
  seen.set(shown.spin, shown);
  const all = [...seen.values()];
  if (all.length < 2) return { spins: all.length, verdict: "one spin", ranges: [] };
  const ranges: string[] = [];
  let off = false;
  for (const s of Object.keys(shown.geometry.stations)) {
    const hs = all.map((r) => r.geometry?.stations[s]?.height_mm).filter((v): v is number => typeof v === "number");
    if (hs.length < 2) continue;
    ranges.push(`S${s} ${Math.min(...hs)}-${Math.max(...hs)} mm up`);
    const mine = shown.geometry.stations[s].height_mm;
    const others = hs.filter((v) => v !== mine);
    if (others.length && Math.min(...others.map((v) => Math.abs(v - mine))) > SPREAD_OK_MM) off = true;
  }
  for (const pair of Object.keys(shown.geometry.apart_mm)) {
    const ds = all.map((r) => r.geometry?.apart_mm[pair]).filter((v): v is number => typeof v === "number");
    if (ds.length < 2) continue;
    ranges.push(`${pair.split("-").map((x) => `S${x}`).join("-")} ${Math.min(...ds)}-${Math.max(...ds)} mm apart`);
    const mine = shown.geometry.apart_mm[pair];
    const others = ds.filter((v) => v !== mine);
    if (others.length && Math.min(...others.map((v) => Math.abs(v - mine))) > SPREAD_OK_MM) off = true;
  }
  return { spins: all.length, verdict: off ? "moved?" : "no sign", ranges };
}
