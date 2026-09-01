import { describe, expect, it } from "vitest";

import { arenaToFraction, fractionToArena, headingToGlyphRotation } from "./arenaFrame";
import type { MapSize } from "./types";

const MAP: MapSize = { width: 1000, height: 800 };

describe("arena frame", () => {
  it("puts the origin at the top-left of the map", () => {
    expect(arenaToFraction({ x: 0, y: 0 }, MAP)).toEqual({ fx: 0, fy: 0 });
  });

  it("grows y downward, so max-y draws at the bottom", () => {
    expect(arenaToFraction({ x: 1000, y: 800 }, MAP)).toEqual({ fx: 1, fy: 1 });
    expect(arenaToFraction({ x: 250, y: 200 }, MAP)).toEqual({ fx: 0.25, fy: 0.25 });
  });

  it("round-trips a click back to the position it was drawn from", () => {
    const p = { x: 612, y: 149 };
    const { fx, fy } = arenaToFraction(p, MAP);
    expect(fractionToArena(fx, fy, MAP)).toEqual(p);
  });

  it("faces a zero-heading bot at the bottom of the map", () => {
    expect(headingToGlyphRotation(0)).toBe(180);
  });

  it("turns clockwise on screen for a positive heading", () => {
    // Heading 90 is -x in the arena frame, which is a left-pointing glyph:
    // three quarter turns clockwise from nose-up.
    expect(headingToGlyphRotation(90)).toBe(270);
  });
});
