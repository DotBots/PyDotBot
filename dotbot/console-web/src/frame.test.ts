import { describe, expect, it } from "vitest";

import {
  VIEWPORT_MARGIN_MM,
  areaToFraction,
  fractionToArea,
  headingToGlyphRotation,
  siteViewport,
} from "./frame";
import type { Area, Site } from "./types";

const ARENA: Area = { x: 0, y: 0, w: 1000, h: 800 };
// The 2 x 2 m square below the arena in the C405 layout.
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000 };

describe("the site frame", () => {
  it("puts the origin at the top-left of the box", () => {
    expect(areaToFraction({ x: 0, y: 0 }, ARENA)).toEqual({ fx: 0, fy: 0 });
  });

  it("grows y downward, so max-y draws at the bottom", () => {
    expect(areaToFraction({ x: 1000, y: 800 }, ARENA)).toEqual({ fx: 1, fy: 1 });
    expect(areaToFraction({ x: 250, y: 200 }, ARENA)).toEqual({ fx: 0.25, fy: 0.25 });
  });

  it("subtracts the box origin, so a frame position draws inside it", () => {
    expect(areaToFraction({ x: 1500, y: 2500 }, ANNEX)).toEqual({ fx: 0.75, fy: 0.25 });
  });

  it("round-trips a click back to the frame position it was drawn from", () => {
    const p = { x: 612, y: 149 };
    const { fx, fy } = areaToFraction(p, ARENA);
    expect(fractionToArea(fx, fy, ARENA)).toEqual(p);
  });

  it("round-trips through an offset area too", () => {
    const p = { x: 1500, y: 2500 };
    const { fx, fy } = areaToFraction(p, ANNEX);
    expect(fractionToArea(fx, fy, ANNEX)).toEqual(p);
  });

  it("faces a zero-heading bot at the bottom of the map", () => {
    expect(headingToGlyphRotation(0)).toBe(180);
  });

  it("turns clockwise on screen for a positive heading", () => {
    // Heading 90 is -x in the frame, which is a left-pointing glyph: three
    // quarter turns clockwise from nose-up.
    expect(headingToGlyphRotation(90)).toBe(270);
  });
});

describe("the default viewport", () => {
  const site = (extent: [number, number] | null): Site => ({
    name: "c405-arena",
    anchor: "the arena top-left corner",
    extent_mm: extent,
    areas: [ARENA, ANNEX],
  });

  it("surrounds the site extent by the margin on every side", () => {
    expect(VIEWPORT_MARGIN_MM).toBe(2000);
    expect(siteViewport(site([2000, 4000]), [ARENA], ARENA)).toEqual({
      x: -2000,
      y: -2000,
      w: 6000,
      h: 8000,
    });
  });

  it("keeps the site's zero at the same fraction of the box on both axes", () => {
    const vp = siteViewport(site([2000, 4000]), [ARENA], ARENA);
    expect(areaToFraction({ x: 0, y: 0 }, vp)).toEqual({ fx: 1 / 3, fy: 0.25 });
    expect(areaToFraction({ x: 2000, y: 4000 }, vp)).toEqual({ fx: 2 / 3, fy: 0.75 });
  });

  it("falls back to the areas shown when the site has no measured extent", () => {
    expect(siteViewport(site(null), [ARENA, ANNEX], ARENA)).toEqual({
      x: -2000,
      y: -2000,
      w: 6000,
      h: 8000,
    });
  });

  it("falls back again when the controller has not answered yet", () => {
    expect(siteViewport(null, [], ARENA)).toEqual({
      x: -2000,
      y: -2000,
      w: 5000,
      h: 4800,
    });
  });
});
