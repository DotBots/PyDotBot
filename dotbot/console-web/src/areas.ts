// Which area outlines the map draws, per browser.
//
// Every area of the site is an outline; Layers > Areas ticks which ones are
// visible. An area is shown unless its role is `corner`, and a tick in Layers
// overrides that per name. Nothing reaches the controller, so the overrides
// are remembered locally and a browser that refuses storage falls back to
// the role defaults.

import { loadRecord, store } from "./persisted";
import type { Area } from "./types";

const KEY = "dotbot.console.areaVisibility";

/** Per-name show/hide choices this browser made, `{name: shown}`. */
export type AreaVisibility = Record<string, boolean>;

/** The choices storage holds, empty when it says nothing. */
export function loadAreaVisibility(): AreaVisibility {
  return loadRecord(KEY, (v): v is boolean => typeof v === "boolean");
}

/** Remember the choices; a browser that refuses storage just forgets them. */
export function saveAreaVisibility(visibility: AreaVisibility): void {
  store(KEY, visibility);
}

/** Whether `area` is drawn: this browser's choice, else its role's default. */
export function isShown(area: Area, visibility: AreaVisibility): boolean {
  return visibility[area.name ?? ""] ?? area.role !== "corner";
}

/** The names of the areas not drawn. */
export function hiddenAreaNames(areas: Area[], visibility: AreaVisibility): Set<string> {
  return new Set(
    areas.filter((a) => !isShown(a, visibility)).map((a) => a.name ?? ""),
  );
}

/** The choices with area `name` flipped from how it is drawn now. */
export function toggleShown(
  visibility: AreaVisibility,
  areas: Area[],
  name: string,
): AreaVisibility {
  const area = areas.find((a) => a.name === name) ?? { x: 0, y: 0, w: 0, h: 0, name };
  return { ...visibility, [name]: !isShown(area, visibility) };
}
