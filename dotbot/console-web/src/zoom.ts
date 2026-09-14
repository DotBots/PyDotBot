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

export const ZOOM_MIN = 0.5;

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

/** The camera that frames `target` (frame mm) inside `viewport`. */
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
  if (!(wPx > 0) || !(hPx > 0)) return SITE_CAMERA;
  const scale = Math.max(
    ZOOM_MIN,
    Math.min(max, Math.min(geom.w / wPx, geom.h / hPx)),
  );
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
    zoomMax(site, viewport, geom),
  );
}

/** The zoom `?zoom=` asks for, or null when it names nothing this site has. */
export function zoomFromSearch(search: string, site: Site | null): string | null {
  const asked = new URLSearchParams(search).get("zoom");
  if (!asked) return null;
  return zoomNames(site).includes(asked) ? asked : null;
}
