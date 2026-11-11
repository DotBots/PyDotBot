import type { Area } from "../types";
import { siteViewMarginMm, withMargin } from "../frame";
import { viewGeom, type Camera } from "../zoom";
import type { Point } from "./model";

// The one map, two ways: the room in 3D (an orthographic camera fitted to the
// floor and the stations, then zoomed and panned) and the plan in 2D (the
// console's camera over a viewport). Looked at from straight above, the two
// are the same affine map of the floor, so either view can hand its zoom and
// pan to the other without a visible jump.

/** A camera: turned `az` degrees about the vertical, looking down `el` degrees. */
export interface RoomCam {
  az: number;
  el: number;
}

/** Straight down, x to the right and y down, as the plan draws it. */
export const TOP_DOWN: RoomCam = { az: 0, el: 90 };

/** A zoom and pan over the fitted 3D view: scaled `k` times about the canvas
 * centre, then moved by (tx, ty) px. */
export interface Zoom {
  k: number;
  tx: number;
  ty: number;
}
export const FIT: Zoom = { k: 1, tx: 0, ty: 0 };
export const ZOOM_MIN = 0.3;
export const ZOOM_MAX = 6;

export interface Size {
  w: number;
  h: number;
}

/** Canvas kept clear at the top and bottom, px, for bars floating over it. */
export interface Insets {
  top: number;
  bottom: number;
}

const RAD = Math.PI / 180;

/** Floor mm and height to the camera's screen axes, before fitting: right,
 * down, and the distance from the viewer. */
export function lens(cam: RoomCam): (x: number, y: number, z?: number) => [number, number, number] {
  const ca = Math.cos(cam.az * RAD);
  const sa = Math.sin(cam.az * RAD);
  const se = Math.sin(cam.el * RAD);
  const ce = Math.cos(cam.el * RAD);
  return (x, y, z = 0) => {
    const u = x * ca - y * sa;
    const w = x * sa + y * ca;
    return [u, w * se - z * ce, -(w * ce + z * se)];
  };
}

/** The 3D view's fit: screen = (o + (lens - min) k), before the zoom. */
export interface RoomFit {
  k: number;
  ox: number;
  oy: number;
  minU: number;
  minV: number;
  dMin: number;
  dSpan: number;
}

/** The fit of the floor `extent` and the stations (x, y, height mm) into
 * `size`, with a small margin, clear of `insets`. */
export function roomFit(cam: RoomCam, extent: [number, number], stations: [number, number, number][], size: Size, insets: Insets, large = false): RoomFit {
  const L = lens(cam);
  const [w, h] = extent;
  const pts = [L(0, 0), L(w, 0), L(w, h), L(0, h)];
  for (const [x, y, z] of stations) pts.push(L(x, y, 0), L(x, y, z));
  const us = pts.map((p) => p[0]);
  const vs = pts.map((p) => p[1]);
  const ds = pts.map((p) => p[2]);
  const pad = Math.max(28, 0.05 * Math.min(size.w, size.h)) * (large ? 1.4 : 1);
  const minU = Math.min(...us);
  const minV = Math.min(...vs);
  const spanU = Math.max(...us) - minU || 1;
  const spanV = Math.max(...vs) - minV || 1;
  const room = Math.max(1, size.h - insets.top - insets.bottom);
  const k = Math.max(1e-6, Math.min((size.w - 2 * pad) / spanU, (room - 2 * pad) / spanV));
  const dMin = Math.min(...ds);
  return { k, ox: (size.w - k * spanU) / 2, oy: insets.top + (room - k * spanV) / 2, minU, minV, dMin, dSpan: Math.max(...ds) - dMin || 1 };
}

/** A floor point (and height) to the 3D view's canvas px. */
export function roomProject(cam: RoomCam, fit: RoomFit, zoom: Zoom, size: Size, x: number, y: number, z = 0): Point {
  const [u, v] = lens(cam)(x, y, z);
  const sx = fit.ox + (u - fit.minU) * fit.k;
  const sy = fit.oy + (v - fit.minV) * fit.k;
  return [size.w / 2 + (sx - size.w / 2) * zoom.k + zoom.tx, size.h / 2 + (sy - size.h / 2) * zoom.k + zoom.ty];
}

/** `z` zoomed by `factor`, held between ZOOM_MIN and ZOOM_MAX, with the
 * canvas point `at` staying where it is on screen. */
export function zoomAt(z: Zoom, factor: number, at: Point, size: Size): Zoom {
  const k = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z.k * factor));
  const r = k / z.k;
  const ax = at[0] - size.w / 2;
  const ay = at[1] - size.h / 2;
  return { k, tx: ax - (ax - z.tx) * r, ty: ay - (ay - z.ty) * r };
}

/** A station this close to the floor is framed with it on the plan, mm. */
export const NEAR_MM = 2000;

/** The rectangle the plan draws into: the floor and any station standing
 * near it, with the site's margin. */
export function planViewport(extent: [number, number], stations: { x: number; y: number }[]): Area {
  const near = stations.filter((s) => s.x > -NEAR_MM && s.y > -NEAR_MM && s.x < extent[0] + NEAR_MM && s.y < extent[1] + NEAR_MM);
  const x0 = Math.min(0, ...near.map((s) => s.x));
  const y0 = Math.min(0, ...near.map((s) => s.y));
  const x1 = Math.max(extent[0], ...near.map((s) => s.x));
  const y1 = Math.max(extent[1], ...near.map((s) => s.y));
  const floor: Area = { x: 0, y: 0, w: extent[0], h: extent[1] };
  return withMargin({ x: x0, y: y0, w: x1 - x0, h: y1 - y0 }, siteViewMarginMm(floor));
}

/** A floor point to the plan's canvas px under `cam`. */
export function planProject(cam: Camera, viewport: Area, size: Size, p: Point): Point {
  const g = viewGeom(size.w, size.h, viewport);
  const bx = ((p[0] - viewport.x) / viewport.w) * g.boxW;
  const by = ((p[1] - viewport.y) / viewport.h) * g.boxH;
  return [size.w / 2 + cam.tx + cam.scale * (bx - g.boxW / 2), size.h / 2 + cam.ty + cam.scale * (by - g.boxH / 2)];
}

/** The plan camera that draws the floor where the 3D view, straight down
 * with `fit` and `zoom`, draws it. */
export function planCamFromRoom(fit: RoomFit, zoom: Zoom, size: Size, viewport: Area): Camera {
  const g = viewGeom(size.w, size.h, viewport);
  const q = g.boxW / viewport.w;
  // The 3D view, straight down: screen = a p + b on each axis
  const a = fit.k * zoom.k;
  const bx = size.w / 2 + (fit.ox - fit.minU * fit.k - size.w / 2) * zoom.k + zoom.tx;
  const by = size.h / 2 + (fit.oy - fit.minV * fit.k - size.h / 2) * zoom.k + zoom.ty;
  const s = a / q;
  return { scale: s, tx: bx - size.w / 2 + s * q * viewport.x + (s * g.boxW) / 2, ty: by - size.h / 2 + s * q * viewport.y + (s * g.boxH) / 2 };
}

/** The 3D zoom that, straight down with `fit`, draws the floor where the
 * plan draws it under `cam`. */
export function roomZoomFromPlan(fit: RoomFit, cam: Camera, size: Size, viewport: Area): Zoom {
  const g = viewGeom(size.w, size.h, viewport);
  const q = g.boxW / viewport.w;
  const a = cam.scale * q;
  const bx = size.w / 2 + cam.tx - a * viewport.x - (cam.scale * g.boxW) / 2;
  const by = size.h / 2 + cam.ty - a * viewport.y - (cam.scale * g.boxH) / 2;
  const k = a / fit.k;
  return { k, tx: bx - size.w / 2 - (fit.ox - fit.minU * fit.k - size.w / 2) * k, ty: by - size.h / 2 - (fit.oy - fit.minV * fit.k - size.h / 2) * k };
}

/** The shortest turn from `from` to `to`, degrees, in -180 to 180. */
export const turn = (from: number, to: number) => ((((to - from) % 360) + 540) % 360) - 180;

// --- the grid both views draw ------------------------------------------------
// A faint context grid runs beyond the floor, to the stations' feet, for the
// room around it; the floor itself is a brighter rectangle with a finer grid,
// so the floor reads as the map in either view. Both use these steps, so the
// lines meet at the Top pose.

/** The context grid's step, mm: half a metre, or a metre on a large floor. */
export const contextStep = (extent: [number, number]) => (Math.max(extent[0], extent[1]) > 4000 ? 1000 : 500);

/** The floor grid's step at `pxPerMm`: the finest of 100, 250 or 500 mm still 14 px apart, never coarser than the context. */
export function floorStep(pxPerMm: number, extent: [number, number]): number {
  const ctx = contextStep(extent);
  const step = [100, 250, 500].find((s) => s * pxPerMm >= 14) ?? ctx;
  return Math.min(step, ctx);
}

/** The context grid's bounds, mm: the floor and the stations' feet, a step beyond. */
export function contextBounds(extent: [number, number], feet: Point[], step: number): [number, number, number, number] {
  const xs = [0, extent[0], ...feet.map((p) => p[0])];
  const ys = [0, extent[1], ...feet.map((p) => p[1])];
  return [Math.floor(Math.min(...xs) / step) * step - step, Math.floor(Math.min(...ys) / step) * step - step, Math.ceil(Math.max(...xs) / step) * step + step, Math.ceil(Math.max(...ys) / step) * step + step];
}

/** The floor's fill, the same in both views. */
export const FLOOR_FILL = "color-mix(in srgb, var(--text) 7%, transparent)";


/** A station's label, the same in both views: "S0 ≈ 2.4 m up · fit 1.10 mm". */
export const stationLabel = (index: number, heightMm: number, fit?: number) => `S${index} ≈ ${(heightMm / 1000).toFixed(1)} m up${fit !== undefined ? ` · fit ${fit.toFixed(2)} mm` : ""}`;
