import type { Camera, ViewGeom } from "../zoom";
import type { Area } from "../types";
import type { Doc, Point } from "./model";

// The plan's geometry: frame millimetres to the drawn box's pixels and back,
// through the console's camera, and the edits a drag makes.

/** Frame mm to the drawn box's own pixels. */
export function toBox(p: Point, viewport: Area, geom: ViewGeom): Point {
  return [((p[0] - viewport.x) / viewport.w) * geom.boxW, ((p[1] - viewport.y) / viewport.h) * geom.boxH];
}

/** A point of the canvas, in its own pixels, to frame mm through `cam`. */
export function canvasToMm(local: Point, cam: Camera, viewport: Area, geom: ViewGeom): Point {
  const lx = (local[0] - geom.w / 2 - cam.tx) / cam.scale + geom.w / 2;
  const ly = (local[1] - geom.h / 2 - cam.ty) / cam.scale + geom.h / 2;
  const bx = lx - (geom.w - geom.boxW) / 2;
  const by = ly - (geom.h - geom.boxH) / 2;
  return [viewport.x + (bx / geom.boxW) * viewport.w, viewport.y + (by / geom.boxH) * viewport.h];
}

/** Screen pixels per frame millimetre at this camera. */
export const pxPerMmAt = (cam: Camera, viewport: Area, geom: ViewGeom) =>
  viewport.w > 0 ? (geom.boxW / viewport.w) * cam.scale : 0;

export const SNAP_MM = 10;

/** `v` on the snap grid, or as it is when snapping is off. */
export const snap = (v: number, on: boolean, step = SNAP_MM) => (on ? Math.round(v / step) * step : Math.round(v));

export type Handle = "nw" | "ne" | "sw" | "se" | "n" | "e" | "s" | "w";

export const HANDLES: Handle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

/** `area` with `handle` dragged to `p`; the far side stays put. */
export function resized<T extends { x: number; y: number; w: number; h: number }>(area: T, handle: Handle, p: Point): T {
  const x0 = handle.includes("w") ? p[0] : area.x;
  const x1 = handle.includes("e") ? p[0] : area.x + area.w;
  const y0 = handle.includes("n") ? p[1] : area.y;
  const y1 = handle.includes("s") ? p[1] : area.y + area.h;
  return {
    ...area,
    x: Math.min(x0, x1),
    y: Math.min(y0, y1),
    w: Math.max(1, Math.abs(x1 - x0)),
    h: Math.max(1, Math.abs(y1 - y0)),
  };
}

/** The rectangle two drag ends span. */
export function spanned(a: Point, b: Point): { x: number; y: number; w: number; h: number } {
  return { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), w: Math.abs(b[0] - a[0]), h: Math.abs(b[1] - a[1]) };
}

/** `doc` with the entity `key` moved by (dx, dy) mm. */
export function moved(doc: Doc, key: string, dx: number, dy: number): Doc {
  const shift = (pts: Point[]) => pts.map(([x, y]) => [x + dx, y + dy] as Point);
  return {
    ...doc,
    areas: doc.areas.map((a) => (a.key === key ? { ...a, x: a.x + dx, y: a.y + dy } : a)),
    walls: doc.walls.map((w) => (w.key === key ? { ...w, points: shift(w.points) } : w)),
    obstacles: doc.obstacles.map((o) => (o.key === key ? { ...o, points: shift(o.points) } : o)),
    objects: doc.objects.map((o) => (o.key === key ? { ...o, x: o.x + dx, y: o.y + dy } : o)),
  };
}

/** `doc` without the entity `key`. */
export function removed(doc: Doc, key: string): Doc {
  return {
    ...doc,
    areas: doc.areas.filter((a) => a.key !== key),
    walls: doc.walls.filter((w) => w.key !== key),
    obstacles: doc.obstacles.filter((o) => o.key !== key),
    objects: doc.objects.filter((o) => o.key !== key),
  };
}

/** Rectangles drawn as one outline: two entries with the same corners. */
export function coincident(rects: { label: string; rect: [number, number, number, number] }[]): string[][] {
  const groups = new Map<string, string[]>();
  for (const r of rects) {
    const k = r.rect.join(",");
    groups.set(k, [...(groups.get(k) ?? []), r.label]);
  }
  return [...groups.values()].filter((g) => g.length > 1);
}

/** Where `handle` of a rectangle is. */
export function handleAt(r: { x: number; y: number; w: number; h: number }, h: Handle): Point {
  const x = h.includes("w") ? r.x : h.includes("e") ? r.x + r.w : r.x + r.w / 2;
  const y = h.includes("n") ? r.y : h.includes("s") ? r.y + r.h : r.y + r.h / 2;
  return [x, y];
}

export type Bounds = [number, number, number, number];

/** The rectangle an entity spans, frame mm; null for a key the doc lacks. */
export function boundsOf(doc: Doc, key: string): Bounds | null {
  const a = doc.areas.find((e) => e.key === key);
  if (a) return [a.x, a.y, a.x + a.w, a.y + a.h];
  const o = doc.objects.find((e) => e.key === key);
  if (o) return [o.x, o.y, o.x, o.y];
  const b = [...doc.walls, ...doc.obstacles].find((e) => e.key === key);
  if (b && b.points.length) {
    const xs = b.points.map((p) => p[0]);
    const ys = b.points.map((p) => p[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  }
  return null;
}

/** Keys of the entities of `keys`' kinds lying wholly inside `r`. */
export function keysWithin(doc: Doc, r: Bounds, prefixes: string[]): string[] {
  const all = [...doc.areas, ...doc.walls, ...doc.obstacles, ...doc.objects].map((e) => e.key);
  return all.filter((k) => {
    if (!prefixes.some((p) => k.startsWith(p))) return false;
    const b = boundsOf(doc, k);
    return !!b && b[0] >= r[0] && b[1] >= r[1] && b[2] <= r[2] && b[3] <= r[3];
  });
}

/** `doc` with every entity of `keys` moved by (dx, dy). */
export function movedAll(doc: Doc, keys: string[], dx: number, dy: number): Doc {
  return keys.reduce((d, k) => moved(d, k, dx, dy), doc);
}

/** `doc` with one edge or corner of an area moved by (dx, dy); the far side stays. */
export function edgeMoved(doc: Doc, key: string, handle: Handle, dx: number, dy: number): Doc {
  return {
    ...doc,
    areas: doc.areas.map((a) => {
      if (a.key !== key) return a;
      const [hx, hy] = handleAt(a, handle);
      return resized(a, handle, [hx + dx, hy + dy]);
    }),
  };
}

export type Arrange = "left" | "right" | "top" | "bottom" | "centre-x" | "centre-y" | "spread-x" | "spread-y";

export const ARRANGE_LABEL: Record<Arrange, string> = {
  left: "Align lefts",
  right: "Align rights",
  top: "Align tops",
  bottom: "Align bottoms",
  "centre-x": "Centre on x",
  "centre-y": "Centre on y",
  "spread-x": "Distribute along x",
  "spread-y": "Distribute along y",
};

/** `doc` with the entities of `keys` lined up or spread out as `how` says. */
export function arranged(doc: Doc, keys: string[], how: Arrange): Doc {
  const boxes = keys.map((k) => [k, boundsOf(doc, k)] as const).filter((e): e is [string, Bounds] => e[1] !== null);
  if (boxes.length < 2) return doc;
  const cx = (b: Bounds) => (b[0] + b[2]) / 2;
  const cy = (b: Bounds) => (b[1] + b[3]) / 2;
  if (how === "spread-x" || how === "spread-y") {
    const c = how === "spread-x" ? cx : cy;
    const sorted = [...boxes].sort((a, b) => c(a[1]) - c(b[1]));
    const first = c(sorted[0][1]);
    const gap = (c(sorted[sorted.length - 1][1]) - first) / (sorted.length - 1);
    return sorted.reduce((d, [k, b], i) => {
      const delta = Math.round(first + i * gap - c(b));
      return how === "spread-x" ? moved(d, k, delta, 0) : moved(d, k, 0, delta);
    }, doc);
  }
  const target = {
    left: Math.min(...boxes.map(([, b]) => b[0])),
    right: Math.max(...boxes.map(([, b]) => b[2])),
    top: Math.min(...boxes.map(([, b]) => b[1])),
    bottom: Math.max(...boxes.map(([, b]) => b[3])),
    "centre-x": cx(boxes[0][1]),
    "centre-y": cy(boxes[0][1]),
  }[how];
  return boxes.reduce((d, [k, b]) => {
    switch (how) {
      case "left":
        return moved(d, k, target - b[0], 0);
      case "right":
        return moved(d, k, target - b[2], 0);
      case "top":
        return moved(d, k, 0, target - b[1]);
      case "bottom":
        return moved(d, k, 0, target - b[3]);
      case "centre-x":
        return moved(d, k, Math.round(target - cx(b)), 0);
      default:
        return moved(d, k, 0, Math.round(target - cy(b)));
    }
  }, doc);
}

export interface SnapTarget {
  value: number;
  label: string;
}

/** The edges a moving point may snap to on each axis: the floor's, and
 * every area's but those being moved. */
export function snapTargets(doc: Doc, skip: string[]): { x: SnapTarget[]; y: SnapTarget[] } {
  const x: SnapTarget[] = [];
  const y: SnapTarget[] = [];
  if (doc.extent_mm) {
    x.push({ value: 0, label: "the extent's left edge" }, { value: doc.extent_mm[0], label: "the extent's right edge" });
    y.push({ value: 0, label: "the extent's top edge" }, { value: doc.extent_mm[1], label: "the extent's bottom edge" });
  }
  for (const a of doc.areas) {
    if (skip.includes(a.key)) continue;
    x.push({ value: a.x, label: `${a.name}'s left edge` }, { value: a.x + a.w, label: `${a.name}'s right edge` });
    y.push({ value: a.y, label: `${a.name}'s top edge` }, { value: a.y + a.h, label: `${a.name}'s bottom edge` });
  }
  for (const o of doc.objects) {
    if (skip.includes(o.key)) continue;
    x.push({ value: o.x, label: `${o.name}` });
    y.push({ value: o.y, label: `${o.name}` });
  }
  return { x, y };
}

/** `p` snapped: to the nearest target within `reach` mm on each axis, else
 * to the 10 mm grid; with `on` false, left as it is. Says what it snapped to. */
export function snapPoint(
  p: Point,
  targets: { x: SnapTarget[]; y: SnapTarget[] },
  reach: number,
  on: boolean,
): { point: Point; to: string } {
  if (!on) return { point: [Math.round(p[0]), Math.round(p[1])], to: "off" };
  const pick = (v: number, ts: SnapTarget[]) => {
    let best: SnapTarget | null = null;
    for (const t of ts) if (Math.abs(t.value - v) <= reach && (!best || Math.abs(t.value - v) < Math.abs(best.value - v))) best = t;
    return best;
  };
  const tx = pick(p[0], targets.x);
  const ty = pick(p[1], targets.y);
  const to = [tx?.label, ty?.label].filter((s, i, all) => s && all.indexOf(s) === i).join(" and ");
  return {
    point: [tx ? tx.value : snap(p[0], true), ty ? ty.value : snap(p[1], true)],
    to: to || `grid ${SNAP_MM} mm`,
  };
}
