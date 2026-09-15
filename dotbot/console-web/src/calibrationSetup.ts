import type { Area, Site } from "./types";

// What the Calibrate tab asks for before a session exists: which rectangle
// the four corner marks are taken from, and how many reads each point
// averages.
//
// The rectangle is named or typed. A name is one of the site's areas; a typed
// rectangle is `x,y,w,h` in frame millimetres, which is the same literal the
// controller's area resolver takes, so both forms leave here as one `--points`
// specification and the controller resolves either.

/** The picker entry that means "a rectangle typed as x,y,w,h". */
export const TYPED_RECT = "typed";

/** The area a site is opened on: `arena` when it has one, else its first. */
export const AREA_PREFERRED = "arena";

/** The area names the picker offers, in the site's own order. */
export function areaChoices(site: Site | null): string[] {
  return (site?.areas ?? []).map((a) => a.name ?? "").filter(Boolean);
}

/** Which entry the picker opens on; the typed rectangle when there is no area. */
export function defaultChoice(site: Site | null): string {
  const names = areaChoices(site);
  if (names.includes(AREA_PREFERRED)) return AREA_PREFERRED;
  return names[0] ?? TYPED_RECT;
}

/** A typed `x,y,w,h` in frame mm, or null when it is not four whole numbers. */
export function parseRect(text: string): Area | null {
  const parts = text.split(",").map((p) => p.trim());
  if (parts.length !== 4) return null;
  if (!parts.every((p) => /^-?\d+$/.test(p))) return null;
  const [x, y, w, h] = parts.map(Number);
  if (w <= 0 || h <= 0) return null;
  return { x, y, w, h, name: parts.join(",") };
}

/**
 * The `--points` specification a Start sends, or null when the typed
 * rectangle is not yet four whole millimetre numbers.
 */
export function pointsSpec(choice: string, rect: string): string | null {
  if (choice !== TYPED_RECT) return `${choice}:corners`;
  const parsed = parseRect(rect);
  return parsed === null ? null : `${parsed.name}:corners`;
}

/** A reads-per-point entry the controller will take, or null while it is not one. */
export function parseReads(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const n = Number(text.trim());
  return n >= 1 ? n : null;
}
