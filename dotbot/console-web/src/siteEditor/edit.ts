import type { AreaRole } from "../types";
import type { BarrierKind, EditArea, SiteModel } from "./types";

/** The fewest points a wall and an obstacle take, as site.toml's schema. */
export const BARRIER_MIN_POINTS: Record<BarrierKind, number> = { walls: 2, obstacles: 3 };

// The editor's geometry and checks, apart from any drawing: snapping, moving,
// resizing and drawing a rectangle in frame millimetres, and what a site must
// satisfy before it is saved.

export const ROLES: AreaRole[] = ["field", "staging", "corner"];

/** The snap steps offered, in mm; 1 is free placement. */
export const SNAP_STEPS_MM = [1, 10, 50, 100, 250, 500];
export const SNAP_DEFAULT_MM = 50;

/** Above this, one LH2 base station rarely covers the field; keep in step with
 * FIELD_COVERAGE_MM in dotbot/cli/config_cmd.py. */
export const FIELD_COVERAGE_MM = 5000;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Handle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
export const HANDLES: Handle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

export function snap(v: number, step: number): number {
  return Math.round(v / step) * step;
}

/** `start` moved by (dx, dy), its top-left corner on the snap grid. */
export function moveRect(start: Rect, dx: number, dy: number, step: number): Rect {
  return { ...start, x: snap(start.x + dx, step), y: snap(start.y + dy, step) };
}

/**
 * `start` with the edges `handle` names dragged to `p`, each on the snap grid
 * and never closer than `step` to the opposite edge, so a rectangle cannot
 * flip or vanish under the pointer.
 */
export function resizeRect(
  start: Rect,
  handle: Handle,
  p: { x: number; y: number },
  step: number,
): Rect {
  const min = Math.max(1, step);
  let left = start.x;
  let top = start.y;
  let right = start.x + start.w;
  let bottom = start.y + start.h;
  if (handle.includes("w")) left = Math.min(snap(p.x, step), right - min);
  if (handle.includes("e")) right = Math.max(snap(p.x, step), left + min);
  if (handle.includes("n")) top = Math.min(snap(p.y, step), bottom - min);
  if (handle.includes("s")) bottom = Math.max(snap(p.y, step), top + min);
  return { x: left, y: top, w: right - left, h: bottom - top };
}

/** The rectangle a drag from `a` to `b` draws, on the snap grid; null when too small. */
export function rectFromDrag(
  a: { x: number; y: number },
  b: { x: number; y: number },
  step: number,
): Rect | null {
  const x0 = snap(Math.min(a.x, b.x), step);
  const y0 = snap(Math.min(a.y, b.y), step);
  const x1 = snap(Math.max(a.x, b.x), step);
  const y1 = snap(Math.max(a.y, b.y), step);
  if (x1 - x0 < Math.max(1, step) || y1 - y0 < Math.max(1, step)) return null;
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

/** The role an area has: the one it declares, else the one its name is. */
export function effectiveRole(area: Pick<EditArea, "name" | "role">): AreaRole | null {
  if (area.role) return area.role;
  return (ROLES as string[]).includes(area.name) ? (area.name as AreaRole) : null;
}

/** The role to declare for a chosen role: none when the name already implies it. */
export function declaredRole(name: string, chosen: AreaRole | null): AreaRole | null {
  if (chosen === null) return null;
  return (ROLES as string[]).includes(name) && name === chosen ? null : chosen;
}

/** A name not yet taken, `area-1`, `area-2`, ... */
export function freshName(areas: EditArea[], base = "area"): string {
  const taken = new Set(areas.map((a) => a.name));
  for (let n = 1; ; n += 1) {
    if (!taken.has(`${base}-${n}`)) return `${base}-${n}`;
  }
}

export interface Issue {
  level: "error" | "warning";
  message: string;
  area?: string;
}

function bbox(rects: Rect[]): Rect {
  const x = Math.min(...rects.map((r) => r.x));
  const y = Math.min(...rects.map((r) => r.y));
  const x1 = Math.max(...rects.map((r) => r.x + r.w));
  const y1 = Math.max(...rects.map((r) => r.y + r.h));
  return { x, y, w: x1 - x, h: y1 - y };
}

/** What stops a save (errors) and what is worth knowing (warnings). */
export function siteIssues(site: SiteModel): Issue[] {
  const issues: Issue[] = [];
  const names = new Map<string, number>();
  for (const a of site.areas) names.set(a.name, (names.get(a.name) ?? 0) + 1);

  const fields = site.areas.filter((a) => effectiveRole(a) === "field");
  if (fields.length > 1) {
    issues.push({
      level: "error",
      message: `a site has at most one field, and ${fields.map((a) => a.name).join(" and ")} are both one`,
    });
  }
  const extent = site.extent_mm;
  if (extent && (!Number.isFinite(extent[0]) || !Number.isFinite(extent[1]) || !(extent[0] > 0) || !(extent[1] > 0))) {
    issues.push({ level: "error", message: "the extent needs a width and a height" });
  }
  for (const a of site.areas) {
    const name = a.name;
    if (!name.trim()) {
      issues.push({ level: "error", area: name, message: "an area needs a name" });
    } else if (name !== name.trim()) {
      issues.push({ level: "error", area: name, message: `${name}: no spaces around the name` });
    } else if (name.includes(",")) {
      issues.push({
        level: "error",
        area: name,
        message: `${name}: a comma makes the name read as an x,y,w,h literal`,
      });
    }
    if ((names.get(name) ?? 0) > 1) {
      issues.push({ level: "error", area: name, message: `two areas are named ${name}` });
    }
    if (![a.x, a.y, a.w, a.h].every(Number.isFinite)) {
      issues.push({ level: "error", area: name, message: `${name}: x, y, w and h must be numbers` });
    } else if (!(a.w > 0) || !(a.h > 0)) {
      issues.push({ level: "error", area: name, message: `${name} needs a width and a height` });
    }
    if (
      extent &&
      (a.x < 0 || a.y < 0 || a.x + a.w > extent[0] || a.y + a.h > extent[1])
    ) {
      issues.push({
        level: "warning",
        area: name,
        message: `${name} reaches outside the extent, where the bot drops positions`,
      });
    }
    if (effectiveRole(a) === "field" && Math.max(a.w, a.h) > FIELD_COVERAGE_MM) {
      issues.push({
        level: "warning",
        area: name,
        message: `${name}: one LH2 base station rarely covers a field over ${FIELD_COVERAGE_MM / 1000} x ${FIELD_COVERAGE_MM / 1000} m`,
      });
    }
    const parts = name.split("+");
    if (parts.length > 1) {
      const found = parts.map((p) => site.areas.find((b) => b.name === p));
      if (found.every((b): b is EditArea => !!b)) {
        const box = bbox(found);
        if (box.x !== a.x || box.y !== a.y || box.w !== a.w || box.h !== a.h) {
          issues.push({
            level: "warning",
            area: name,
            message: `${name} is not the bounding box of ${parts.join(" and ")} (${box.x}, ${box.y}, ${box.w} x ${box.h})`,
          });
        }
      }
    }
  }
  for (const kind of ["walls", "obstacles"] as BarrierKind[]) {
    (site[kind] ?? []).forEach((b, i) => {
      const label = b.name || `${kind === "walls" ? "wall" : "obstacle"} ${i + 1}`;
      if (b.points.length < BARRIER_MIN_POINTS[kind]) {
        issues.push({ level: "error", message: `${label} needs at least ${BARRIER_MIN_POINTS[kind]} points` });
      }
      if (extent && b.points.some(([x, y]) => x < 0 || y < 0 || x > extent[0] || y > extent[1])) {
        issues.push({ level: "warning", message: `${label} reaches outside the extent` });
      }
    });
  }
  return issues;
}

/** `points` moved by (dx, dy), its first point on the snap grid. */
export function movePoints(points: [number, number][], dx: number, dy: number, step: number): [number, number][] {
  if (points.length === 0) return points;
  const ox = snap(points[0][0] + dx, step) - points[0][0];
  const oy = snap(points[0][1] + dy, step) - points[0][1];
  return points.map(([x, y]) => [x + ox, y + oy]);
}

/** A drawn polyline without the repeats a double-click leaves at its end. */
export function finishPoints(points: [number, number][]): [number, number][] {
  return points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
}

/** `x, y` per line, as the inspector shows points; null when a line does not read. */
export function parsePoints(text: string): [number, number][] | null {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const out: [number, number][] = [];
  for (const line of lines) {
    const parts = line.split(/[\s,]+/).filter(Boolean).map(Number);
    if (parts.length !== 2 || parts.some((v) => !Number.isFinite(v))) return null;
    out.push([Math.round(parts[0]), Math.round(parts[1])]);
  }
  return out;
}

/** Whether the anchor or the extent differ, which a calibration depends on. */
export function frameChanged(a: SiteModel, b: SiteModel): boolean {
  return (
    (a.anchor ?? "") !== (b.anchor ?? "") ||
    JSON.stringify(a.extent_mm) !== JSON.stringify(b.extent_mm)
  );
}

/** Whether two models would write the same file. */
export function sameSite(a: SiteModel, b: SiteModel): boolean {
  const strip = (s: SiteModel) =>
    JSON.stringify({
      anchor: s.anchor || null,
      extent_mm: s.extent_mm,
      areas: s.areas.map(({ name, x, y, w, h, role, comment, was }) => ({
        name, x, y, w, h, role, comment: comment || null, was: was ?? null,
      })),
      walls: (s.walls ?? []).map(({ name, points, comment, was }) => ({
        name: name || null, points, comment: comment || null, was: was ?? null,
      })),
      obstacles: (s.obstacles ?? []).map(({ name, points, comment, was }) => ({
        name: name || null, points, comment: comment || null, was: was ?? null,
      })),
    });
  return strip(a) === strip(b);
}
