import { describe, expect, it } from "vitest";

import {
  VIEWPORT_MARGIN_MIN_MM,
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

  it("surrounds the site extent by a tenth of its longer side on every side", () => {
    expect(siteViewport(site([2000, 4000]), ARENA)).toMatchObject({
      x: -400,
      y: -400,
      w: 2800,
      h: 4800,
    });
  });

  it("keeps a small site's margin at the floor", () => {
    expect(siteViewport(site([1000, 1000]), ARENA)).toMatchObject({
      x: -VIEWPORT_MARGIN_MIN_MM,
      y: -VIEWPORT_MARGIN_MIN_MM,
      w: 1000 + 2 * VIEWPORT_MARGIN_MIN_MM,
    });
  });

  it("puts the site at the same place in the box on both axes", () => {
    const vp = siteViewport(site([2000, 4000]), ARENA);
    const zero = areaToFraction({ x: 0, y: 0 }, vp);
    const far = areaToFraction({ x: 2000, y: 4000 }, vp);
    expect(zero.fx).toBeCloseTo(1 / 7, 12);
    expect(zero.fy).toBeCloseTo(1 / 12, 12);
    expect(far.fx).toBeCloseTo(6 / 7, 12);
    expect(far.fy).toBeCloseTo(11 / 12, 12);
  });

  it("falls back when the site has no measured extent", () => {
    expect(siteViewport(site(null), ARENA)).toMatchObject({
      x: -250,
      y: -250,
      w: 1500,
      h: 1300,
    });
  });

  it("falls back again when the controller has not answered yet", () => {
    expect(siteViewport(null, ARENA)).toMatchObject({
      x: -250,
      y: -250,
      w: 1500,
      h: 1300,
    });
  });
});
