// The colour an area is drawn in, on the map and beside its name in Layers.
//
// An area's colour says its role, so every field is drawn alike, every
// staging area alike, and every corner alike. An area with no role takes one
// of the remaining colours from its place in the sorted names of the other
// role-less areas, so hiding areas, reloading, or the order the controller
// lists them in cannot move it.

import type { Area, AreaRole } from "./types";

/** How many `--area-N` tokens tokens.css defines. */
export const AREA_PALETTE_SIZE = 6;

/** The token index each role is drawn in. */
const ROLE_COLOR: Record<AreaRole, number> = { field: 0, staging: 3, corner: 2 };

/** The token indices left for areas without a role. */
const FREE_COLORS = [...Array(AREA_PALETTE_SIZE).keys()].filter(
  (i) => !Object.values(ROLE_COLOR).includes(i),
);

/** The colour token for `area` among `areas`, the site's whole set. */
export function areaColor(area: Area, areas: Area[]): string {
  if (area.role) return `var(--area-${ROLE_COLOR[area.role]})`;
  const names = areas
    .filter((a) => !a.role)
    .map((a) => a.name)
    .filter((n): n is string => !!n);
  const sorted = [...new Set(names)].sort();
  const at = Math.max(0, sorted.indexOf(area.name ?? ""));
  return `var(--area-${FREE_COLORS[at % FREE_COLORS.length]})`;
}
