import { store } from "./persisted";
import type { Area, PointsFrom, SiteCalibration } from "./types";

// Where the loaded LH2 calibration was fitted, and what is extrapolated: the
// map outlines each placement's span and hatches the rest of the site.

const SHOWN_KEY = "dotbot.console.calibratedSpan";

/** Whether this browser draws the span: on unless it was switched off here. */
export function loadSpanShown(): boolean {
  try {
    return window.localStorage.getItem(SHOWN_KEY) !== "false";
  } catch {
    return true;
  }
}

/** Remember the choice; a browser that refuses storage just forgets it. */
export function saveSpanShown(shown: boolean): void {
  store(SHOWN_KEY, shown);
}

export type Point = [number, number];

export interface Span {
  points: Point[];
  pointsFrom: PointsFrom | null;
}

const cross = (o: Point, a: Point, b: Point) =>
  (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

/** The convex hull of `points`, in order round it from the lowest x. */
export function convexHull(points: Point[]): Point[] {
  const sorted = [...points].sort((p, q) => p[0] - q[0] || p[1] - q[1]);
  if (sorted.length < 3) return sorted;
  const half = (pts: Point[]) => {
    const hull: Point[] = [];
    for (const p of pts) {
      while (hull.length >= 2 && cross(hull[hull.length - 2], hull[hull.length - 1], p) <= 0) {
        hull.pop();
      }
      hull.push(p);
    }
    hull.pop();
    return hull;
  };
  return [...half(sorted), ...half([...sorted].reverse())];
}

/** One outline per placement that spans an area: three points or more, not in a line. */
export function calibrationSpans(calibration: SiteCalibration | null | undefined): Span[] {
  return (calibration?.placements ?? []).flatMap((placement) => {
    const points = convexHull(placement.points_mm);
    return points.length >= 3 ? [{ points, pointsFrom: placement.points_from }] : [];
  });
}

/** The rectangle the hatch covers: the whole site, or nothing when its extent is unknown. */
export function hatchBox(extent: [number, number] | null): Area | null {
  return extent ? { x: 0, y: 0, w: extent[0], h: extent[1] } : null;
}

/** How a placement's points were chosen, as a phrase. */
export function describePointsFrom(pointsFrom: PointsFrom | null): string {
  switch (pointsFrom?.kind) {
    case "field":
      return "the field's corners";
    case "over":
      return `the corners of ${pointsFrom.area}`;
    case "square":
      return `a ${pointsFrom.side_mm} mm square in the field`;
    case "points":
      return "points given by hand";
    default:
      return "its recorded points";
  }
}

/** Whole days since `createdAt`, 0 for a time ahead of this browser's clock,
 * or null when it does not parse. */
export function ageDays(createdAt: string, now: Date = new Date()): number | null {
  const created = Date.parse(createdAt);
  if (Number.isNaN(created)) return null;
  return Math.max(0, Math.floor((now.getTime() - created) / 86_400_000));
}

/** The outline's tooltip: which calibration, how old, and what it covers. */
export function spanTitle(calibration: SiteCalibration, span: Span, now?: Date): string {
  const name = calibration.tag
    ? `${calibration.tag} (${calibration.id.slice(0, 8)})`
    : calibration.id.slice(0, 8);
  const age = ageDays(calibration.created_at, now);
  const old = age === null ? "" : age === 1 ? ", 1 day old" : `, ${age} days old`;
  return (
    `LH2 calibration ${name}${old}: calibrated over ${describePointsFrom(span.pointsFrom)}. ` +
    "Positions outside the outline are extrapolated."
  );
}
