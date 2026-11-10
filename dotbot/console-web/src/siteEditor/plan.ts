import type { Camera, ViewGeom } from "../zoom";
import type { Area } from "../types";
import type { Doc, DocArea, Point } from "./model";

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

export type Handle = "nw" | "ne" | "sw" | "se";

/** `area` with `handle` dragged to `p`; the far corner stays put. */
export function resized(area: DocArea, handle: Handle, p: Point): DocArea {
  const x0 = handle === "nw" || handle === "sw" ? p[0] : area.x;
  const x1 = handle === "ne" || handle === "se" ? p[0] : area.x + area.w;
  const y0 = handle === "nw" || handle === "ne" ? p[1] : area.y;
  const y1 = handle === "sw" || handle === "se" ? p[1] : area.y + area.h;
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
