// Where this browser was last looking, per site.
//
// A camera is not portable. The same `{scale, tx, ty}` frames a different
// patch of floor in a canvas of another size, so a view stored as the camera
// itself lands somewhere else on a laptop screen than on the monitor it was
// left on, and anywhere at all once the rail or the right pane has been
// opened. What is stored is the floor the canvas was showing - a rectangle in
// frame millimetres - and the camera is derived from it again on arrival,
// through the same fit a named zoom goes through, so the clamps that keep the
// map reachable apply to a restored view as well.
//
// Per site, because a rectangle of one floor means nothing on another, and
// this browser's own like the other map layers: it reaches no controller.
// `?zoom=` outranks it, being an instruction where this is only a default.

import type { Area } from "./types";

const KEY = "dotbot.console.mapView";

/** How long the camera has to sit still before the view is written. */
export const VIEW_SETTLE_MS = 250;

/** The floor one canvas was showing, in frame millimetres. */
export interface ViewRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** The last view by site name. */
export type SavedViews = Record<string, ViewRect>;

const usable = (v: unknown): v is ViewRect => {
  const r = v as ViewRect;
  return (
    !!r &&
    typeof r === "object" &&
    !Array.isArray(r) &&
    Number.isFinite(r.x) &&
    Number.isFinite(r.y) &&
    r.w > 0 &&
    r.h > 0
  );
};

/** What this browser last looked at, empty when storage says nothing usable. */
export function loadSavedViews(): SavedViews {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>)
        .filter(([, v]) => usable(v))
        .map(([site, v]) => [site, { ...(v as ViewRect) }]),
    ) as SavedViews;
  } catch {
    return {};
  }
}

/** Remember them; a browser that refuses storage just forgets. */
export function saveSavedViews(views: SavedViews): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(views));
  } catch {
    /* private window, cleared site data, storage blocked */
  }
}

/** The map with one site's view replaced. */
export function withView(
  views: SavedViews,
  site: string,
  rect: Area,
): SavedViews {
  return {
    ...views,
    [site]: { x: rect.x, y: rect.y, w: rect.w, h: rect.h },
  };
}

/**
 * The rectangle to open a site on, or null when there is nothing usable to
 * open on: no site yet, nothing stored for it, or a view that no longer meets
 * the floor. A site remeasured or re-anchored under a stored view leaves one
 * of those, and restoring it would open the map on nothing; the whole site is
 * the better answer.
 */
export function viewFor(
  views: SavedViews,
  site: string | null | undefined,
  viewport: Area,
): Area | null {
  if (!site) return null;
  const rect = views[site];
  if (!usable(rect)) return null;
  const meetsFloor =
    rect.x < viewport.x + viewport.w &&
    rect.x + rect.w > viewport.x &&
    rect.y < viewport.y + viewport.h &&
    rect.y + rect.h > viewport.y;
  return meetsFloor ? { ...rect } : null;
}
