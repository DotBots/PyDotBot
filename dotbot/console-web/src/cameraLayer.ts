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
// The opacity, the offset, and how solid the robots over the layer are drawn
// are all ways of looking at the map, like which area outlines are drawn: they
// reach no controller and are remembered in this browser only. The offset
// shifts the image and the outline drawn on it, and nothing else: the glyph is
// the measurement, so moving it to meet the picture would corrupt the thing
// being checked. Fading the glyph moves nothing either, and lets the
// photographed robot be read under the position reported for it, which is the
// comparison the layer exists to make.

import { loadRecord, store } from "./persisted";
import type { Area, CameraDetection, LH2Position } from "./types";

const OPACITY_KEY = "dotbot.console.cameraOpacity";
const OFFSET_KEY = "dotbot.console.cameraOffset";
const ROBOT_KEY = "dotbot.console.robotOpacity";

/** Visible on arrival, and still plainly an underlay under the grid. */
export const DEFAULT_CAMERA_OPACITY = 0.6;

/** Robots are drawn solid until the slider is reached for. */
export const DEFAULT_ROBOT_OPACITY = 1;

// Where the falloff starts and ends, as multiples of the span's own smaller
// side. A quarter of the span beyond it the extrapolated error is a few times
// the registration's own; a whole span beyond it there is nothing left to
// believe.
const FADE_START_OF_SPAN = 0.25;
const FADE_END_OF_SPAN = 1.0;

/** Layer opacity by area name, 0 to 1. */
export type CameraOpacity = Record<string, number>;

/** How solid the robots standing on an area are drawn, 0 to 1. */
export type RobotOpacity = Record<string, number>;

const usable = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1;

const withValue = (
  opacity: CameraOpacity,
  area: string,
  value: number,
): CameraOpacity => ({ ...opacity, [area]: Math.min(1, Math.max(0, value)) });

/** What this browser last set, empty when storage says nothing usable. */
export function loadCameraOpacity(): CameraOpacity {
  return loadRecord(OPACITY_KEY, usable);
}

/** Remember it; a browser that refuses storage just forgets it. */
export function saveCameraOpacity(opacity: CameraOpacity): void {
  store(OPACITY_KEY, opacity);
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
  return withValue(opacity, area, value);
}

/** What this browser last set, empty when storage says nothing usable. */
export function loadRobotOpacity(): RobotOpacity {
  return loadRecord(ROBOT_KEY, usable);
}

/** Remember it; a browser that refuses storage just forgets it. */
export function saveRobotOpacity(opacity: RobotOpacity): void {
  store(ROBOT_KEY, opacity);
}

/** One area's robots, falling back to solid. */
export function robotOpacityFor(opacity: RobotOpacity, area: string): number {
  const v = opacity[area];
  return usable(v) ? v : DEFAULT_ROBOT_OPACITY;
}

/** The map with one area's robots replaced, clamped to 0..1. */
export function withRobotOpacity(
  opacity: RobotOpacity,
  area: string,
  value: number,
): RobotOpacity {
  return withValue(opacity, area, value);
}

/** One camera's area, and how solid the robots standing on it are drawn. */
export interface RobotFade {
  area: Area;
  opacity: number;
}

/**
 * How solid the robot reporting itself at `p` is drawn: the least any camera
 * it stands on asks for, and solid where none does.
 *
 * A robot is faded whole or not at all, by the position it reports. That
 * position is the measurement the layer is being compared against, so it is
 * also what decides which camera the comparison belongs to; a robot straddling
 * the boundary belongs to the area its own reading puts it in.
 */
export function robotOpacityAt(faded: RobotFade[], p: LH2Position): number {
  return faded.reduce(
    (least, f) => (inArea(p, f.area) ? Math.min(least, f.opacity) : least),
    DEFAULT_ROBOT_OPACITY,
  );
}

/** Whether a point of floor falls inside a rectangle of it. */
export function inArea(p: LH2Position, area: Area): boolean {
  return (
    p.x >= area.x &&
    p.x <= area.x + area.w &&
    p.y >= area.y &&
    p.y <= area.y + area.h
  );
}

// Well past any parallax correction, so a mistyped value cannot throw the
// layer clear of its area, and still ample on a large floor.
const OFFSET_LIMIT_MM = 1000;

/** How far one area's image is nudged, in frame millimetres. */
export interface OffsetMm {
  dx: number;
  dy: number;
}

/** Layer offset by area name. */
export type CameraOffset = Record<string, OffsetMm>;

/** No nudge, which is where every camera starts. */
export const NO_OFFSET: OffsetMm = Object.freeze({ dx: 0, dy: 0 });

// An empty or unparseable field reads as no nudge rather than as NaN, which
// would otherwise reach the transform and blank the layer.
const clampMm = (v: number): number =>
  Number.isFinite(v)
    ? Math.min(OFFSET_LIMIT_MM, Math.max(-OFFSET_LIMIT_MM, v))
    : 0;

const usableOffset = (v: unknown): v is OffsetMm =>
  !!v &&
  typeof v === "object" &&
  !Array.isArray(v) &&
  Number.isFinite((v as OffsetMm).dx) &&
  Number.isFinite((v as OffsetMm).dy);

/** What this browser last set, empty when storage says nothing usable. */
export function loadCameraOffset(): CameraOffset {
  return loadRecord(OFFSET_KEY, usableOffset, (v) => ({
    dx: clampMm(v.dx),
    dy: clampMm(v.dy),
  }));
}

/** Remember it; a browser that refuses storage just forgets it. */
export function saveCameraOffset(offset: CameraOffset): void {
  store(OFFSET_KEY, offset);
}

/** One area's offset, falling back to no nudge at all. */
export function offsetFor(offset: CameraOffset, area: string): OffsetMm {
  const v = offset[area];
  return usableOffset(v) ? v : NO_OFFSET;
}

/** The map with one area's offset replaced, clamped to the limit. */
export function withOffset(
  offset: CameraOffset,
  area: string,
  value: OffsetMm,
): CameraOffset {
  return {
    ...offset,
    [area]: { dx: clampMm(value.dx), dy: clampMm(value.dy) },
  };
}

// A millimetre as a percentage of the box side it runs along, rounded to six
// places so the value reads as the millimetres behind it rather than as
// binary-float noise. A millionth of the box is orders below a pixel.
const sidePct = (mm: number, side: number): number =>
  Math.round((mm / side) * 1e8) / 1e6;

/**
 * The offset as a CSS `transform` for the layer's box, or undefined when it
 * is not nudged, so an untouched layer carries no transform at all.
 *
 * The box is the area, so a millimetre is a percentage of the matching side.
 */
export function offsetTransform(
  offset: OffsetMm,
  area: Area,
): string | undefined {
  if (!offset.dx && !offset.dy) return undefined;
  if (!(area.w > 0) || !(area.h > 0)) return undefined;
  return `translate(${sidePct(offset.dx, area.w)}%, ${sidePct(offset.dy, area.h)}%)`;
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

/** How one detection's outline is stroked, or null when there is nothing to draw. */
export interface DetectionStroke {
  stroke: string;
  dasharray?: string;
}

/**
 * Solid for a pose the estimator stands behind, dashed for one it fitted but
 * would not vouch for, nothing at all when it found no robot.
 *
 * A refused pose is drawn rather than dropped so an operator sees the
 * estimator hesitating instead of seeing an empty floor.
 */
export function detectionStroke(
  detection: CameraDetection | undefined,
): DetectionStroke | null {
  if (!detection || !detection.pose) return null;
  if (detection.status === "found") return { stroke: "var(--accent)" };
  if (detection.status === "refused")
    return { stroke: "var(--muted)", dasharray: "6 4" };
  return null;
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
