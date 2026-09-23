import type { Area, LH2Position, Site } from "./types";

// The frame, and the single place the console states it.
//
// Origin is the site's anchor, x grows right, y grows down. Every position the
// console receives is in frame millimetres; the viewport says which part of
// the frame is drawn, so the box origin is subtracted before scaling.

/**
 * How much frame lies outside the site on every side of the default view, as a
 * fraction of the site's longer side, floored at a minimum in millimetres. It
 * is kept modest so the whole-site view is mostly site: a margin as wide as
 * the site shrinks every robot on it to a mark.
 */
export const VIEWPORT_MARGIN_FRAC = 0.1;
export const VIEWPORT_MARGIN_MIN_MM = 250;

/** The margin the default view leaves around `a`. */
export function viewportMarginMm(a: Area): number {
  return Math.max(VIEWPORT_MARGIN_MIN_MM, VIEWPORT_MARGIN_FRAC * Math.max(a.w, a.h));
}

/** What a renderer draws when the site has no measured extent. */
export const AREA_FALLBACK: Area = { x: 0, y: 0, w: 2000, h: 2000 };

/** The site as one rectangle, when its extent is measured. */
export function siteExtentArea(site: Site | null): Area | null {
  const [w, h] = site?.extent_mm ?? [0, 0];
  if (!(w > 0) || !(h > 0)) return null;
  return { x: 0, y: 0, w, h, name: site!.name };
}

/** Frame mm to a fraction of a rectangle, 0..1 from its top-left corner. */
export function areaToFraction(p: LH2Position, a: Area): { fx: number; fy: number } {
  return { fx: (p.x - a.x) / a.w, fy: (p.y - a.y) / a.h };
}

/** A fraction of a rectangle back to frame mm. */
export function fractionToArea(fx: number, fy: number, a: Area): LH2Position {
  return { x: a.x + fx * a.w, y: a.y + fy * a.h };
}

/** A rectangle grown by the same margin on every side. */
export function withMargin(a: Area, m = viewportMarginMm(a)): Area {
  return { x: a.x - m, y: a.y - m, w: a.w + 2 * m, h: a.h + 2 * m, name: a.name };
}

/**
 * The box the map draws: the whole site with a margin on every side, so a bot
 * that drives out of the site is still drawn rather than clipped at the wall.
 * A site with no measured extent falls back to a 2 x 2 m square at the origin.
 */
export function siteViewport(site: Site | null, fallback: Area): Area {
  return withMargin(siteExtentArea(site) ?? fallback);
}

/**
 * Heading in degrees to the CSS rotation for a nose-up glyph. Heading 0 is +y,
 * which points at the bottom of the map, so the glyph turns half a circle
 * before the heading itself applies.
 */
export function headingToGlyphRotation(heading: number): number {
  return 180 + heading;
}
