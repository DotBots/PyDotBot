// The camera layer: how opaque it is drawn, and where it stops claiming to be
// accurate.
//
// The controller warps one camera into its area's own raster, so the image's
// box is the area. Inside `span_mm`, the quadrilateral the four ArUco sheets
// spanned, the homography was fitted and the image lands where the floor is;
// outside it the projective error grows with the square of the distance, so
// the image is faded out rather than drawn as if it were still true.
//
// The opacity is a way of looking at the map, like which area outlines are
// drawn: it reaches no controller and is remembered in this browser only.

import type { Area } from "./types";

const KEY = "dotbot.console.cameraOpacity";

/** Visible on arrival, and still plainly an underlay under the grid. */
export const DEFAULT_CAMERA_OPACITY = 0.6;

// How far past the span the image fades, as a fraction of the room between
// the span and the area's edge, and the most it may be whatever that room is.
const FADE_OF_MARGIN = 0.5;
const FADE_MAX_FRACTION = 0.06;

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

/** Whether a span is a polygon at all, rather than a missing or stub field. */
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
 * The span's corners as SVG polygon points in the area's own millimetres,
 * which is the image box's coordinate system: the raster is the area.
 */
export function spanPoints(span: number[][], area: Area): string {
  return span.map(([x, y]) => `${x - area.x},${y - area.y}`).join(" ");
}

/**
 * How wide the fade past the span is, in millimetres.
 *
 * It takes half the room between the span and the nearest area edge, so the
 * image has gone before the raster ends and the layer never cuts off mid-fade;
 * a span that reaches the area's edge leaves no room and gets a hard edge,
 * which is the truthful answer there.
 */
export function fadeMm(span: number[][], area: Area): number {
  const xs = span.map(([x]) => x);
  const ys = span.map(([, y]) => y);
  const margin = Math.min(
    Math.min(...xs) - area.x,
    area.x + area.w - Math.max(...xs),
    Math.min(...ys) - area.y,
    area.y + area.h - Math.max(...ys),
  );
  const cap = FADE_MAX_FRACTION * Math.min(area.w, area.h);
  return Math.max(0, Math.min(margin * FADE_OF_MARGIN, cap));
}

/**
 * A CSS `mask-image` holding the span, grown by the fade and blurred over it,
 * so the image is whole inside the span and gone by `span + 2 * fade`.
 *
 * The mask is drawn in the area's millimetres and stretched over the image
 * box, which is the same rectangle, so a millimetre is a millimetre in both.
 */
export function spanMask(span: number[][], area: Area): string {
  if (!hasSpan(span)) return "";
  const fade = fadeMm(span, area);
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${area.w} ${area.h}"` +
    ` preserveAspectRatio="none">` +
    `<filter id="f" x="-30%" y="-30%" width="160%" height="160%">` +
    `<feMorphology operator="dilate" radius="${fade}"/>` +
    `<feGaussianBlur stdDeviation="${fade / 2}"/>` +
    `</filter>` +
    `<polygon points="${spanPoints(span, area)}" fill="#fff"` +
    ` filter="url(#f)"/>` +
    `</svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}
