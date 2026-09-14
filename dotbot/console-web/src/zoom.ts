import { areaToFraction } from "./frame";
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
 * `zoomMax` raises this to whatever the site's smallest area needs.
 */
export const ZOOM_MAX_FLOOR = 4;

/** The zoom that shows the whole site: the map's own default. */
export const SITE_ZOOM = "site";
export const SITE_CAMERA: Camera = { scale: 1, tx: 0, ty: 0 };

/** How much of a rectangle's own size is left around it when zoomed to. */
export const ZOOM_PAD = 0.15;

/**
 * What one zoom level is worth. Doubling covers a whole site in four or five
 * levels and jumps a press clean past what was being read; much under 1.4
 * takes too many presses to cross the range and a press stops being visible.
 * At 1.5 a typical floor lands on seven or eight levels.
 */
export const ZOOM_RATIO = 1.5;

/**
 * The scales the map zooms through, level 1 first. Level 1 is the whole site
 * in view - the map's own default camera - and the ladder's last rung sits at
 * or past `max`, so every area the ceiling was raised for is reachable at a
 * whole level rather than between two.
 */
export function zoomLadder(max: number, ratio = ZOOM_RATIO): number[] {
  const top = Number.isFinite(max) ? Math.max(1, max) : 1;
  const levels = Math.max(1, Math.ceil(Math.log(top) / Math.log(ratio)));
  return Array.from({ length: levels + 1 }, (_, i) => ratio ** i);
}

/** Which rung a scale is nearest, counted by ratio rather than difference. */
function nearestRung(scale: number, ladder: number[]): number {
  if (!(scale > 0)) return 0;
  let best = 0;
  for (let i = 1; i < ladder.length; i += 1) {
    if (
      Math.abs(Math.log(scale / ladder[i])) <
      Math.abs(Math.log(scale / ladder[best]))
    ) {
      best = i;
    }
  }
  return best;
}

/** The level a scale is on, 1-based, for the operator to read off. */
export function zoomLevel(scale: number, ladder: number[]): number {
  return nearestRung(scale, ladder) + 1;
}

/** The rung a free scale rounds to, so every view sits on a whole level. */
export function snapToLadder(scale: number, ladder: number[]): number {
  return ladder[nearestRung(scale, ladder)];
}

/** The scale `delta` levels away, held inside the ladder at both ends. */
export function steppedScale(
  scale: number,
  delta: number,
  ladder: number[],
): number {
  const rung = nearestRung(scale, ladder) + delta;
  return ladder[Math.max(0, Math.min(ladder.length - 1, rung))];
}

// v1 clampPan: keep the arena reachable, never fling it off-screen.
export function clampCam(cam: Camera, geom: ViewGeom): Camera {
  const padX = Math.max(0, (geom.w - geom.boxW) / 2);
  const padY = Math.max(0, (geom.h - geom.boxH) / 2);
  const mx = Math.max(0, (geom.boxW * cam.scale - geom.w) / 2) + padX;
  const my = Math.max(0, (geom.boxH * cam.scale - geom.h) / 2) + padY;
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
 * How far this site has to be zoomed in for its smallest area to fill the
 * canvas, pad included. That is the ceiling: an area the site defines is a
 * place the operator works in, so every one of them has to be reachable.
 */
export function zoomMax(
  site: Site | null,
  viewport: Area,
  geom: ViewGeom,
): number {
  const needed = (site?.areas ?? [])
    .map((a) => fitScale(padArea(a), viewport, geom))
    .filter((s) => Number.isFinite(s) && s > 0);
  return Math.max(ZOOM_MAX_FLOOR, ...needed);
}

/**
 * The camera that frames `target` (frame mm) inside `viewport`, on the
 * nearest whole level of `ladder`. Rounding up can only eat into the pad a
 * named zoom leaves around its rectangle, never into the rectangle itself.
 */
export function cameraForArea(
  target: Area,
  viewport: Area,
  geom: ViewGeom,
  ladder: number[],
): Camera {
  const tl = areaToFraction({ x: target.x, y: target.y }, viewport);
  const br = areaToFraction(
    { x: target.x + target.w, y: target.y + target.h },
    viewport,
  );
  const wPx = (br.fx - tl.fx) * geom.boxW;
  const hPx = (br.fy - tl.fy) * geom.boxH;
  if (!(wPx > 0) || !(hPx > 0)) return SITE_CAMERA;
  const scale = snapToLadder(Math.min(geom.w / wPx, geom.h / hPx), ladder);
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
 * The camera one named zoom asks for. The site is the map's default view, so
 * it is the identity camera rather than a fit; a name no area answers to
 * leaves the camera alone, which is what an unknown `?zoom=` should do.
 */
export function cameraForZoom(
  name: string,
  site: Site | null,
  viewport: Area,
  geom: ViewGeom,
): Camera | null {
  if (name === SITE_ZOOM) return SITE_CAMERA;
  const area = (site?.areas ?? []).find((a) => a.name === name);
  if (!area) return null;
  return cameraForArea(
    padArea(area),
    viewport,
    geom,
    zoomLadder(zoomMax(site, viewport, geom)),
  );
}

/** The zoom `?zoom=` asks for, or null when it names nothing this site has. */
export function zoomFromSearch(search: string, site: Site | null): string | null {
  const asked = new URLSearchParams(search).get("zoom");
  if (!asked) return null;
  return zoomNames(site).includes(asked) ? asked : null;
}
