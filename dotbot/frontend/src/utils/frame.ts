import { Area, Site } from '../types';

// The site frame: zero at the site's anchor, x growing right, y growing down,
// millimetres. The viewport says which part of it the map draws.

/** How much frame lies outside the site on every side of the default view. */
export const viewportMarginMm = 2000;

/** The bounding box of a set of rectangles. */
export const unionAreas = (list: Area[], fallback: Area): Area => {
  if (list.length === 0) return fallback;
  const x = Math.min(...list.map(a => a.x));
  const y = Math.min(...list.map(a => a.y));
  const xMax = Math.max(...list.map(a => a.x + a.w));
  const yMax = Math.max(...list.map(a => a.y + a.h));
  return { x, y, w: xMax - x, h: yMax - y };
};

/**
 * The box the map shows by default: the whole site with a margin on every
 * side, so a bot that drives out of the site is still drawn rather than
 * clipped at the wall. A site with no measured extent falls back to what is
 * active.
 */
export const siteViewport = (site: Site | undefined, active: Area[], fallback: Area): Area => {
  const m = viewportMarginMm;
  const inner = site?.extent_mm
    ? { x: 0, y: 0, w: site.extent_mm[0], h: site.extent_mm[1] }
    : unionAreas(active, fallback);
  return { x: inner.x - m, y: inner.y - m, w: inner.w + 2 * m, h: inner.h + 2 * m };
};
