// Where this browser was last looking, per site.
//
// A camera is not portable: the same `{scale, tx, ty}` frames a different
// patch of floor in a canvas of another size, and the canvas changes size
// whenever a side panel opens or closes. What is stored is the floor point at
// the canvas centre and the floor's pixels per millimetre, and the camera is
// derived from them again on arrival, so the map opens on the same floor at
// the same size whatever the canvas, held only by the pan clamp.
//
// Per site, because a point of one floor means nothing on another, and this
// browser's own like the other map layers: it reaches no controller.
// `?zoom=` outranks it, being an instruction where this is only a default.

import { loadRecord, store } from "./persisted";
import type { Area } from "./types";
import type { ViewCentre } from "./zoom";

const KEY = "dotbot.console.mapView";

/** How long the camera has to sit still before the view is written. */
export const VIEW_SETTLE_MS = 250;

/** The last view by site name. */
export type SavedViews = Record<string, ViewCentre>;

const usable = (v: unknown): v is ViewCentre => {
  const r = v as ViewCentre;
  return (
    !!r &&
    typeof r === "object" &&
    !Array.isArray(r) &&
    Number.isFinite(r.x) &&
    Number.isFinite(r.y) &&
    Number.isFinite(r.pxPerMm) &&
    r.pxPerMm > 0
  );
};

/** What this browser last looked at, empty when storage says nothing usable. */
export function loadSavedViews(): SavedViews {
  return loadRecord(KEY, usable, (view) => ({ x: view.x, y: view.y, pxPerMm: view.pxPerMm }));
}

/** Remember them; a browser that refuses storage just forgets. */
export function saveSavedViews(views: SavedViews): void {
  store(KEY, views);
}

/** The map with one site's view replaced. */
export function withView(views: SavedViews, site: string, view: ViewCentre): SavedViews {
  return { ...views, [site]: { x: view.x, y: view.y, pxPerMm: view.pxPerMm } };
}

/**
 * The view to open a site on, or null when there is nothing usable to open
 * on: no site yet, nothing stored for it, or a centre off the floor. A site
 * remeasured or re-anchored under a stored view leaves one of those, and
 * restoring it would open the map on nothing; the whole site is the better
 * answer.
 */
export function viewFor(
  views: SavedViews,
  site: string | null | undefined,
  viewport: Area,
): ViewCentre | null {
  if (!site) return null;
  const view = views[site];
  if (!usable(view)) return null;
  const onFloor =
    view.x >= viewport.x &&
    view.x <= viewport.x + viewport.w &&
    view.y >= viewport.y &&
    view.y <= viewport.y + viewport.h;
  return onFloor ? { ...view } : null;
}
