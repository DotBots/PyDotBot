import { Area, Site } from '../types';

// The site frame: zero at the site's anchor, x growing right, y growing down,
// millimetres. The viewport says which part of it the map draws.

/** How much frame lies outside the site on every side of the default view. */
export const viewportMarginMm = 2000;

/** What the map draws when the site has no measured extent. */
export const areaFallback: Area = { x: 0, y: 0, w: 2000, h: 2000 };

/** The site as one rectangle, when its extent is measured. */
export const siteExtentArea = (site: Site | undefined): Area | null =>
  site?.extent_mm
    ? { x: 0, y: 0, w: site.extent_mm[0], h: site.extent_mm[1], name: site.name }
    : null;

/**
 * The box the map shows: the whole site with a margin on every side, so a bot
 * that drives out of the site is still drawn rather than clipped at the wall.
 * A site with no measured extent falls back to a 2 x 2 m square at the origin.
 */
export const siteViewport = (site: Site | undefined, fallback: Area): Area => {
  const m = viewportMarginMm;
  const inner = siteExtentArea(site) ?? fallback;
  return { x: inner.x - m, y: inner.y - m, w: inner.w + 2 * m, h: inner.h + 2 * m };
};
