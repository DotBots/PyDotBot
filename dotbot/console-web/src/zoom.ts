import { areaToFraction, fractionToArea, siteView } from "./frame";
import type { Area, Site } from "./types";

// The viewport: which part of the drawn frame fills the canvas.
//
// The map draws the whole viewport into a box of `boxW` x `boxH` pixels
// centred in the canvas, then applies the camera about the canvas centre. The
// box carries the viewport's own aspect ratio, so one frame millimetre is the
// same number of pixels on both axes and the slack axis is letterboxed. A
// named zoom is one rectangle of the frame plus a pad, resolved to the camera
// that frames it.

export interface Camera {
  scale: number;
  tx: number;
  ty: number;
}

export interface ViewGeom {
  w: number;
  h: number;
  boxW: number;
  boxH: number;
}

/** Canvas kept clear around the drawn box, so the frame has visible margins. */
export const CANVAS_INSET_PX = 48;

/** The smallest box the map draws into, however little canvas it is given. */
export const BOX_MIN_PX = 200;

/**
 * The drawn box for a canvas: the viewport's aspect ratio, as large as the
 * canvas holds once the inset is taken off both axes.
 */
export function viewGeom(w: number, h: number, viewport: Area): ViewGeom {
  const availW = Math.max(BOX_MIN_PX, w - CANVAS_INSET_PX);
  const availH = Math.max(BOX_MIN_PX, h - CANVAS_INSET_PX);
  const aspect =
    viewport.w > 0 && viewport.h > 0 ? viewport.w / viewport.h : 1;
  const boxH = Math.min(availW / aspect, availH);
  return { w, h, boxW: boxH * aspect, boxH };
}

/** The drawn box's own extent on one axis. */
export const boxSpan = (axis: "x" | "y", geom: ViewGeom) =>
  axis === "x" ? geom.boxW : geom.boxH;

/**
 * The ceiling a site with no area to measure gets. A site is drawn with a
 * margin several metres wide on every side, so a ceiling fixed at a small
 * multiple cannot frame a room-sized rectangle inside a floor-sized one;
 * `zoomMax` raises this to whatever the site needs.
 */
export const ZOOM_MAX_FLOOR = 4;

/**
 * The finest the map can always be zoomed, in screen pixels per millimetre of
 * floor. A ceiling taken from the site's areas alone caps a floor whose areas
 * are all room-sized long before a robot is more than a mark; at one pixel to
 * the millimetre a 95 mm DotBot is 95 px, which is a board rather than a
 * mark. Stated in pixels per millimetre so the same zoom shows the same
 * robot at the same size whatever site it is on.
 */
export const ZOOM_MAX_PX_PER_MM = 1;

/** The zoom that shows the whole site: the map's own default. */
export const SITE_ZOOM = "site";

/** The identity camera: the whole drawn viewport in the box. */
export const FRAME_CAMERA: Camera = { scale: 1, tx: 0, ty: 0 };

/** How much of a rectangle's own size is left around it when zoomed to. */
export const ZOOM_PAD = 0.15;

/**
 * The far end of the range: the whole viewport in view, which is everywhere
 * the pan can reach. Zooming out past it would only add empty canvas.
 */
export const ZOOM_MIN = 1;

/**
 * What one press of the zoom buttons is worth. Doubling jumps a press clean
 * past whatever was being read; much under 1.4 and a press stops being
 * visible at all.
 */
export const ZOOM_STEP = 1.5;

/** Wheel travel, in pixels, worth one press of the zoom buttons. */
export const WHEEL_PX_PER_STEP = 100;

/**
 * A wheel event's travel in pixels, down positive. A wheel that reports
 * lines or pages is scaled to about what they span.
 */
export function wheelDeltaPx(e: { deltaY: number; deltaMode: number }): number {
  if (e.deltaMode === 1) return e.deltaY * 16;
  if (e.deltaMode === 2) return e.deltaY * 400;
  return e.deltaY;
}

/** The scale a wheel of `deltaPx` lands on: in when scrolled up, out when down. */
export function wheelScale(scale: number, deltaPx: number, max: number): number {
  if (!Number.isFinite(deltaPx)) return clampScale(scale, max);
  return steppedScale(scale, -deltaPx / WHEEL_PX_PER_STEP, max);
}

/** A scale held inside the range the map can show. */
export function clampScale(scale: number, max: number): number {
  const top = Number.isFinite(max) ? Math.max(ZOOM_MIN, max) : ZOOM_MIN;
  if (!(scale > 0)) return ZOOM_MIN;
  return Math.min(top, Math.max(ZOOM_MIN, scale));
}

/** The scale `delta` presses away, held inside the range at both ends. */
export function steppedScale(
  scale: number,
  delta: number,
  max: number,
): number {
  return clampScale(scale * ZOOM_STEP ** delta, max);
}

/**
 * Where a scale sits in the range: 0 fully zoomed out, 1 at the ceiling.
 * Measured in ratios rather than differences, so the same travel along a
 * slider is the same magnification wherever the handle already is.
 */
export function zoomFraction(scale: number, max: number): number {
  const top = Number.isFinite(max) ? Math.max(ZOOM_MIN, max) : ZOOM_MIN;
  if (!(top > ZOOM_MIN)) return 0;
  return (
    Math.log(clampScale(scale, top) / ZOOM_MIN) / Math.log(top / ZOOM_MIN)
  );
}

/** The scale one position along the range stands for: `zoomFraction` back. */
export function scaleForFraction(fraction: number, max: number): number {
  const top = Number.isFinite(max) ? Math.max(ZOOM_MIN, max) : ZOOM_MIN;
  const f = Number.isFinite(fraction)
    ? Math.max(0, Math.min(1, fraction))
    : 0;
  return ZOOM_MIN * (top / ZOOM_MIN) ** f;
}

/**
 * The camera held to the viewport: the pan reaches as far past the site as
 * the viewport runs, and no further.
 */
export function clampCam(cam: Camera, geom: ViewGeom): Camera {
  // A box much wider than the canvas pans until its edge meets the canvas
  // edge. Up to that point it keeps the slack the letterbox gave it at the
  // far end of the range, so zooming about an edge never snaps it inward.
  const padX = Math.max(0, (geom.w - geom.boxW) / 2);
  const padY = Math.max(0, (geom.h - geom.boxH) / 2);
  const mx = Math.max(padX, (geom.boxW * cam.scale - geom.w) / 2);
  const my = Math.max(padY, (geom.boxH * cam.scale - geom.h) / 2);
  return {
    ...cam,
    tx: Math.max(-mx, Math.min(mx, cam.tx)),
    ty: Math.max(-my, Math.min(my, cam.ty)),
  };
}

/**
 * The camera at a new scale with one canvas point held where it is. That is
 * what a zoom is: the thing being looked at stays put and only the scale
 * changes. Leaving the pan alone across a scale change moves it instead, by
 * more the further the camera has been panned from the frame's centre.
 */
export function zoomAbout(
  cam: Camera,
  scale: number,
  anchor: { x: number; y: number },
  geom: ViewGeom,
): Camera {
  const k = scale / cam.scale;
  if (!Number.isFinite(k) || k <= 0) return cam;
  const ax = anchor.x - geom.w / 2;
  const ay = anchor.y - geom.h / 2;
  return clampCam(
    { scale, tx: ax * (1 - k) + cam.tx * k, ty: ay * (1 - k) + cam.ty * k },
    geom,
  );
}

/** The canvas point the zoom buttons hold still: whatever is in the middle. */
export const viewCentre = (geom: ViewGeom) => ({
  x: geom.w / 2,
  y: geom.h / 2,
});

/** A rectangle grown by a fraction of its own size on every side. */
export function padArea(a: Area, frac = ZOOM_PAD): Area {
  return {
    x: a.x - a.w * frac,
    y: a.y - a.h * frac,
    w: a.w * (1 + 2 * frac),
    h: a.h * (1 + 2 * frac),
    name: a.name,
  };
}

/** The named zooms, in menu order: the site, then one per area it defines. */
export function zoomNames(site: Site | null): string[] {
  const areas = (site?.areas ?? []).map((a) => a.name ?? "").filter(Boolean);
  return [SITE_ZOOM, ...areas];
}

/**
 * The scale at which `target` exactly fills the canvas, before any ceiling.
 * Zero when the rectangle has no area to fit.
 */
export function fitScale(target: Area, viewport: Area, geom: ViewGeom): number {
  const wPx = (target.w / viewport.w) * geom.boxW;
  const hPx = (target.h / viewport.h) * geom.boxH;
  if (!(wPx > 0) || !(hPx > 0)) return 0;
  return Math.min(geom.w / wPx, geom.h / hPx);
}

/**
 * How far this site can be zoomed in: far enough for its smallest area to
 * fill the canvas, pad included, and always far enough to read one robot.
 * An area the site defines is a place the operator works in, so every one of
 * them has to be reachable; a robot is what they are looking at, so its own
 * size sets a ceiling no site can be too plain to reach.
 */
export function zoomMax(
  site: Site | null,
  viewport: Area,
  geom: ViewGeom,
): number {
  const needed = (site?.areas ?? [])
    .map((a) => fitScale(padArea(a), viewport, geom))
    .filter((s) => Number.isFinite(s) && s > 0);
  const perMm = viewport.w > 0 ? geom.boxW / viewport.w : 0;
  const forDetail = perMm > 0 ? ZOOM_MAX_PX_PER_MM / perMm : 0;
  return Math.max(ZOOM_MAX_FLOOR, forDetail, ...needed);
}

/**
 * The camera that frames `target` (frame mm) inside `viewport`: the scale
 * that exactly fits it, held inside the range the map can show.
 */
export function cameraForArea(
  target: Area,
  viewport: Area,
  geom: ViewGeom,
  max: number,
): Camera {
  const tl = areaToFraction({ x: target.x, y: target.y }, viewport);
  const br = areaToFraction(
    { x: target.x + target.w, y: target.y + target.h },
    viewport,
  );
  const wPx = (br.fx - tl.fx) * geom.boxW;
  const hPx = (br.fy - tl.fy) * geom.boxH;
  if (!(wPx > 0) || !(hPx > 0)) return FRAME_CAMERA;
  const scale = clampScale(Math.min(geom.w / wPx, geom.h / hPx), max);
  // Where the target's centre sits in canvas pixels before the camera runs.
  const cx = (geom.w - geom.boxW) / 2 + ((tl.fx + br.fx) / 2) * geom.boxW;
  const cy = (geom.h - geom.boxH) / 2 + ((tl.fy + br.fy) / 2) * geom.boxH;
  return clampCam(
    {
      scale,
      tx: -(cx - geom.w / 2) * scale,
      ty: -(cy - geom.h / 2) * scale,
    },
    geom,
  );
}

/**
 * The floor the canvas is showing, in frame millimetres: the rectangle
 * `cameraForArea` takes back to this camera, since a view that fills the
 * canvas is fitted to the canvas exactly.
 *
 * This is what a camera means, and the portable half of it. The same
 * `{scale, tx, ty}` frames a different patch of floor in a canvas of another
 * size, so a view that has to survive a resize - or a move to another screen
 * - travels as the rectangle and is fitted again on arrival.
 */
export function visibleArea(cam: Camera, viewport: Area, geom: ViewGeom): Area {
  const scale = cam.scale > 0 ? cam.scale : ZOOM_MIN;
  // The camera undone: a canvas pixel back to a fraction of the drawn box.
  const f = (px: number, canvas: number, box: number, t: number) =>
    ((px - canvas / 2 - t) / scale + box / 2) / box;
  const tl = fractionToArea(
    f(0, geom.w, geom.boxW, cam.tx),
    f(0, geom.h, geom.boxH, cam.ty),
    viewport,
  );
  const br = fractionToArea(
    f(geom.w, geom.w, geom.boxW, cam.tx),
    f(geom.h, geom.h, geom.boxH, cam.ty),
    viewport,
  );
  return { x: tl.x, y: tl.y, w: br.x - tl.x, h: br.y - tl.y };
}

/**
 * The camera one named zoom asks for: the site with its modest margin, or an
 * area with its pad. A name no area answers to leaves the camera alone, which
 * is what an unknown `?zoom=` should do.
 */
export function cameraForZoom(
  name: string,
  site: Site | null,
  viewport: Area,
  geom: ViewGeom,
): Camera | null {
  const max = zoomMax(site, viewport, geom);
  if (name === SITE_ZOOM) return cameraForArea(siteView(viewport), viewport, geom, max);
  const area = (site?.areas ?? []).find((a) => a.name === name);
  if (!area) return null;
  return cameraForArea(padArea(area), viewport, geom, max);
}

/** The zoom `?zoom=` asks for, or null when it names nothing this site has. */
export function zoomFromSearch(search: string, site: Site | null): string | null {
  const asked = new URLSearchParams(search).get("zoom");
  if (!asked) return null;
  return zoomNames(site).includes(asked) ? asked : null;
}
