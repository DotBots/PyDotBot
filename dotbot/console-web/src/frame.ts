import type { Area, LH2Position, Site } from "./types";

// The frame, and the single place the console states it.
//
// Origin is the site's anchor, x grows right, y grows down. Every position the
// console receives is in frame millimetres; the viewport says which part of
// the frame is drawn, so the box origin is subtracted before scaling.

/** How much frame lies outside the site on every side of the default view. */
export const VIEWPORT_MARGIN_MM = 2000;

/** Frame mm to a fraction of a rectangle, 0..1 from its top-left corner. */
export function areaToFraction(p: LH2Position, a: Area): { fx: number; fy: number } {
  return { fx: (p.x - a.x) / a.w, fy: (p.y - a.y) / a.h };
}

/** A fraction of a rectangle back to frame mm. */
export function fractionToArea(fx: number, fy: number, a: Area): LH2Position {
  return { x: a.x + fx * a.w, y: a.y + fy * a.h };
}

/** The bounding box of a set of rectangles, for a renderer that needs one box. */
export function unionAreas(list: Area[], fallback: Area): Area {
  if (list.length === 0) return fallback;
  const x = Math.min(...list.map((a) => a.x));
  const y = Math.min(...list.map((a) => a.y));
  const xMax = Math.max(...list.map((a) => a.x + a.w));
  const yMax = Math.max(...list.map((a) => a.y + a.h));
  return { x, y, w: xMax - x, h: yMax - y };
}

/**
 * The box the map shows by default: the whole site with a margin on every
 * side, so a bot that drives out of the site is still drawn rather than
 * clipped at the wall. A site with no measured extent falls back to what is
 * active.
 */
export function siteViewport(site: Site | null, active: Area[], fallback: Area): Area {
  const m = VIEWPORT_MARGIN_MM;
  const inner = site?.extent_mm
    ? { x: 0, y: 0, w: site.extent_mm[0], h: site.extent_mm[1] }
    : unionAreas(active, fallback);
  return { x: inner.x - m, y: inner.y - m, w: inner.w + 2 * m, h: inner.h + 2 * m };
}

/**
 * Heading in degrees to the CSS rotation for a nose-up glyph. Heading 0 is +y,
 * which points at the bottom of the map, so the glyph turns half a circle
 * before the heading itself applies.
 */
export function headingToGlyphRotation(heading: number): number {
  return 180 + heading;
}
