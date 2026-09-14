import { boxSpan } from "./zoom";
import type { Camera, ViewGeom } from "./zoom";
import type { Area } from "./types";

// The map's metric grid: lines on whole metric steps of the frame, anchored at
// the site's zero, and the ruler that names them.
//
// A step is picked so the lines stay about as far apart on screen whatever the
// camera does, which is what makes the spacing readable as a distance rather
// than as a fraction of the canvas. The ladder is the 1-2-5 one and bottoms
// out at the metre, so every step is a round number of metres. Past that the
// half-metre comes in as a sub-grid drawn under the metre lines rather than in
// place of them, and nothing finer than a half-metre is ever drawn.

export type Axis = "x" | "y";

/** Grid steps in frame millimetres, coarsest first. */
export const GRID_LADDER_MM = [10000, 5000, 2000, 1000];

/**
 * The one step below the ladder, drawn weaker and only under the metre lines.
 * The floor on what the map draws: half a metre is as fine as the grid goes.
 */
export const GRID_SUB_STEP_MM = 500;

/** Screen pixels a drawn line aims to keep from the next one. */
export const GRID_TARGET_PX = 40;

/** Screen pixels a named line needs from the next named one to stay readable. */
export const RULER_MIN_GAP_PX = 44;

/**
 * The same, for the footer minimap. It is a couple of hundred pixels across
 * at most, so the map's spacing would leave it one line on each axis.
 */
export const MINIMAP_TARGET_PX = 24;

/** The finest ladder step still at least `targetPx` apart on screen. */
export function gridStepMm(pxPerMm: number, targetPx = GRID_TARGET_PX): number {
  let step = GRID_LADDER_MM[0];
  for (const candidate of GRID_LADDER_MM) {
    if (candidate * pxPerMm < targetPx) break;
    step = candidate;
  }
  return step;
}

/**
 * The half-metre sub-grid, once it is that far apart on screen, else null.
 * Drawn under the metre lines rather than instead of them, so the metre stays
 * the step the eye counts in and the half-metre only fills it in.
 */
export function gridSubStepMm(
  pxPerMm: number,
  targetPx = GRID_TARGET_PX,
): number | null {
  return GRID_SUB_STEP_MM * pxPerMm >= targetPx ? GRID_SUB_STEP_MM : null;
}

/**
 * The step the ruler names: the grid's own step, multiplied up until the
 * labels clear `minGapPx`. Multiplying is what keeps every label on a drawn
 * line, which a ladder of the ruler's own does not - 5 m labels over a 2 m
 * grid name lines that are not there.
 */
export function rulerStepMm(
  stepMm: number,
  pxPerMm: number,
  minGapPx = RULER_MIN_GAP_PX,
): number {
  const every = [1, 2, 5, 10, 20, 50, 100];
  for (const n of every) {
    if (stepMm * n * pxPerMm >= minGapPx) return stepMm * n;
  }
  return stepMm * every[every.length - 1];
}

/** Screen pixels a scale bar aims for: long enough to read, short enough to tuck in a corner. */
export const SCALE_BAR_PX = 52;

/**
 * The distances a scale bar is willing to stand for, in frame millimetres.
 * It reaches well under the metre so the bar still fits its budget at the
 * finest zoom, where a robot's own 95 mm is the length worth comparing to.
 */
export const SCALE_BAR_LADDER_MM = [
  20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000,
];

/**
 * The longest round distance a bar of about `targetPx` can carry, and what it
 * measures on screen. The ruler already names the frame's own metres; this
 * says how much floor a length of canvas is, without reading two labels.
 */
export function scaleBar(
  pxPerMm: number,
  targetPx = SCALE_BAR_PX,
): { mm: number; px: number } {
  let mm = SCALE_BAR_LADDER_MM[0];
  for (const candidate of SCALE_BAR_LADDER_MM) {
    if (candidate * pxPerMm > targetPx) break;
    mm = candidate;
  }
  return { mm, px: mm * pxPerMm };
}

/** A scale bar's distance, in the unit that states it without leading zeros. */
export function barLabel(mm: number): string {
  return mm < 1000 ? `${mm} mm` : metreLabel(mm, mm);
}

const canvasSpan = (axis: Axis, geom: ViewGeom) => (axis === "x" ? geom.w : geom.h);
const viewOrigin = (axis: Axis, viewport: Area) =>
  axis === "x" ? viewport.x : viewport.y;
const viewExtent = (axis: Axis, viewport: Area) =>
  axis === "x" ? viewport.w : viewport.h;
const pan = (axis: Axis, cam: Camera) => (axis === "x" ? cam.tx : cam.ty);

/** Where a frame coordinate lands on the canvas, once the camera has run. */
export function canvasPx(
  axis: Axis,
  mm: number,
  viewport: Area,
  geom: ViewGeom,
  cam: Camera,
): number {
  const span = canvasSpan(axis, geom);
  const box = boxSpan(axis, geom);
  const fraction = (mm - viewOrigin(axis, viewport)) / viewExtent(axis, viewport);
  const unscaled = (span - box) / 2 + fraction * box;
  return span / 2 + (unscaled - span / 2) * cam.scale + pan(axis, cam);
}

/** The frame coordinate at one canvas pixel: the camera, run backwards. */
export function frameMm(
  axis: Axis,
  px: number,
  viewport: Area,
  geom: ViewGeom,
  cam: Camera,
): number {
  const span = canvasSpan(axis, geom);
  const box = boxSpan(axis, geom);
  const unscaled = (px - span / 2 - pan(axis, cam)) / cam.scale + span / 2;
  const fraction = (unscaled - (span - box) / 2) / box;
  return viewOrigin(axis, viewport) + fraction * viewExtent(axis, viewport);
}

/**
 * Screen pixels one frame millimetre spans on this axis. The drawn box keeps
 * the viewport's aspect ratio, so both axes answer the same number.
 */
export function pxPerMm(
  axis: Axis,
  viewport: Area,
  geom: ViewGeom,
  cam: Camera,
): number {
  return (boxSpan(axis, geom) * cam.scale) / viewExtent(axis, viewport);
}

export interface Tick {
  mm: number;
  px: number;
}

/**
 * Every multiple of `stepMm` the canvas shows on one axis, as a frame
 * coordinate and the canvas pixel it lands on. Multiples of the step, so the
 * lines are anchored at the frame's zero rather than at a canvas corner.
 */
export function axisTicks(
  axis: Axis,
  viewport: Area,
  geom: ViewGeom,
  cam: Camera,
  stepMm: number,
): Tick[] {
  const from = frameMm(axis, 0, viewport, geom, cam);
  const to = frameMm(axis, canvasSpan(axis, geom), viewport, geom, cam);
  const first = Math.ceil(Math.min(from, to) / stepMm);
  const last = Math.floor(Math.max(from, to) / stepMm);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return [];
  const ticks: Tick[] = [];
  for (let n = first; n <= last; n += 1) {
    const mm = n * stepMm;
    ticks.push({ mm, px: canvasPx(axis, mm, viewport, geom, cam) });
  }
  return ticks;
}

/**
 * The ticks that fall on measured floor, for a ruler to name. The map draws a
 * margin around the site so a bot that leaves it is still visible, but the
 * margin is not floor anyone measured: naming it counts metres backwards from
 * the site's own zero. A site with no measured extent has a zero but no far
 * edge, so only the zero side is fenced.
 */
export function ticksInSite(
  ticks: Tick[],
  axis: Axis,
  extent: Area | null,
): Tick[] {
  const from = extent ? Math.max(0, viewOrigin(axis, extent)) : 0;
  const to = extent ? from + viewExtent(axis, extent) : Infinity;
  return ticks.filter((t) => t.mm >= from - 1e-6 && t.mm <= to + 1e-6);
}

/** A frame coordinate in metres, to the digits its step actually resolves. */
export function metreLabel(mm: number, stepMm: number): string {
  const digits = stepMm >= 1000 ? 0 : stepMm >= 100 ? 1 : 2;
  return `${(mm / 1000).toFixed(digits)} m`;
}
