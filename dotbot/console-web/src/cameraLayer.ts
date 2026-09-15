// The camera layer: how opaque it is drawn, how far past the registration it
// still claims to be accurate, and where the camera stops seeing floor at all.
//
// The controller warps one camera into its area's own raster, so the image's
// box is the area. `span_mm`, the quadrilateral the four ArUco sheets spanned,
// is where the homography was fitted; past it the image is an extrapolation
// whose error grows with the square of the distance. The falloff is therefore
// measured in the span's own size rather than in the room left to the area's
// edge: a span that nearly fills its area is drawn whole out to that edge,
// four sheets in the middle of a large one fade to nothing well inside it.
//
// `coverage_mm` is the source frame's own rectangle through the same
// homography, so it is the floor the camera can see. Outside it the warp had
// no source to read, and the layer is cut there rather than drawn, so the map
// shows through and the edge of the camera's view is visible.
//
// The opacity is a way of looking at the map, like which area outlines are
// drawn: it reaches no controller and is remembered in this browser only.

import type { Area } from "./types";

const KEY = "dotbot.console.cameraOpacity";

/** Visible on arrival, and still plainly an underlay under the grid. */
export const DEFAULT_CAMERA_OPACITY = 0.6;

// Where the falloff starts and ends, as multiples of the span's own smaller
// side. A quarter of the span beyond it the extrapolated error is a few times
// the registration's own; a whole span beyond it there is nothing left to
// believe.
const FADE_START_OF_SPAN = 0.25;
const FADE_END_OF_SPAN = 1.0;

/** Layer opacity by area name, 0 to 1. */
export type CameraOpacity = Record<string, number>;

const usable = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1;

/** What this browser last set, empty when storage says nothing usable. */
export function loadCameraOpacity(): CameraOpacity {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(([, v]) =>
        usable(v),
      ),
    ) as CameraOpacity;
  } catch {
    return {};
  }
}

/** Remember it; a browser that refuses storage just forgets it. */
export function saveCameraOpacity(opacity: CameraOpacity): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(opacity));
  } catch {
    /* private window, cleared site data, storage blocked */
  }
}

/** One area's opacity, falling back to the default it arrives at. */
export function opacityFor(opacity: CameraOpacity, area: string): number {
  const v = opacity[area];
  return usable(v) ? v : DEFAULT_CAMERA_OPACITY;
}

/** The map with one area's opacity replaced, clamped to 0..1. */
export function withOpacity(
  opacity: CameraOpacity,
  area: string,
  value: number,
): CameraOpacity {
  return { ...opacity, [area]: Math.min(1, Math.max(0, value)) };
}

/** Whether a polygon is one at all, rather than a missing or stub field. */
export function hasSpan(span: number[][] | undefined): span is number[][] {
  return (
    Array.isArray(span) &&
    span.length >= 3 &&
    span.every(
      (p) => Array.isArray(p) && p.length >= 2 && p.every(Number.isFinite),
    )
  );
}

/**
 * A polygon's corners as SVG points in the area's own millimetres, which is
 * the image box's coordinate system: the raster is the area.
 */
export function polygonPoints(polygon: number[][], area: Area): string {
  return polygon.map(([x, y]) => `${x - area.x},${y - area.y}`).join(" ");
}

/** A polygon's bounding box in frame millimetres, as x0, y0, x1, y1. */
function bounds(polygon: number[][]): [number, number, number, number] {
  const xs = polygon.map(([x]) => x);
  const ys = polygon.map(([, y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/**
 * The span's own size in millimetres: the smaller side of the rectangle the
 * four sheets stand in, which is the scale an extrapolation is measured
 * against.
 */
export function spanSizeMm(span: number[][]): number {
  const [x0, y0, x1, y1] = bounds(span);
  return Math.min(x1 - x0, y1 - y0);
}

/** How far past the span the falloff starts and ends, in millimetres. */
export function fadeMm(span: number[][]): { start: number; end: number } {
  const size = spanSizeMm(span);
  return { start: FADE_START_OF_SPAN * size, end: FADE_END_OF_SPAN * size };
}

/** The farthest any point of the area lies past the span, in millimetres. */
export function reachMm(span: number[][], area: Area): number {
  const [x0, y0, x1, y1] = bounds(span);
  const corners: number[][] = [
    [area.x, area.y],
    [area.x + area.w, area.y],
    [area.x + area.w, area.y + area.h],
    [area.x, area.y + area.h],
  ];
  return Math.max(
    ...corners.map(([x, y]) =>
      Math.hypot(
        Math.max(0, x0 - x, x - x1),
        Math.max(0, y0 - y, y - y1),
      ),
    ),
  );
}

/**
 * A CSS `mask-image` cutting the layer to what the camera saw and can still
 * be believed: the span grown by the falloff and blurred across it, clipped
 * to the camera's coverage.
 *
 * The dilation and the blur put the mask at full inside `fade.start` past the
 * span and at nothing by `fade.end`, three standard deviations either side of
 * the dilated edge. An area wholly inside `fade.start` needs no falloff at
 * all and gets none, so the image runs to the area's edge undimmed.
 *
 * The mask is drawn in the area's millimetres and stretched over the image
 * box, which is the same rectangle, so a millimetre is a millimetre in both.
 */
export function spanMask(
  span: number[][],
  area: Area,
  coverage?: number[][],
): string {
  const clipped = hasSpan(coverage);
  const faded = hasSpan(span) && reachMm(span, area) > fadeMm(span).start;
  if (!clipped && !faded) return "";

  let defs = "";
  let shape = `<rect width="${area.w}" height="${area.h}" fill="#fff"/>`;
  if (faded) {
    const { start, end } = fadeMm(span);
    defs +=
      `<filter id="f" filterUnits="userSpaceOnUse"` +
      ` x="0" y="0" width="${area.w}" height="${area.h}">` +
      `<feMorphology operator="dilate" radius="${(start + end) / 2}"/>` +
      `<feGaussianBlur stdDeviation="${(end - start) / 6}"/>` +
      `</filter>`;
    shape =
      `<polygon points="${polygonPoints(span, area)}" fill="#fff"` +
      ` filter="url(#f)"/>`;
  }
  if (clipped) {
    defs +=
      `<clipPath id="c">` +
      `<polygon points="${polygonPoints(coverage, area)}"/>` +
      `</clipPath>`;
    shape = `<g clip-path="url(#c)">${shape}</g>`;
  }

  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${area.w} ${area.h}"` +
    ` preserveAspectRatio="none">` +
    `<defs>${defs}</defs>` +
    shape +
    `</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}
