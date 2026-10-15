import { describe, expect, it } from "vitest";

import { boxIssues, boxesOf, cornersOf, rectOf, sameBoxes } from "./boxes";
import type { CalibrationOverlay } from "./types";

const overlay: CalibrationOverlay = {
  id: "abcd1234abcd1234",
  id8: "abcd1234",
  free: true,
  fence: [0, 0, 2000, 4000],
  stations: [
    {
      index: 0,
      channel: 1,
      rect: [0, 0, 2000, 4000],
      centres: [[500, 500]],
      circles: [{ name: "robot0", x: 500, y: 500, radius_mm: 51.4 }],
      solved_from: "conics-joint",
    },
  ],
  links: [],
  tag: "",
  created_at: "",
  site: "arena",
  anchor: "the door corner",
};

describe("station boxes", () => {
  it("turns the file's corners into x, y, w, h and back", () => {
    expect(rectOf([100, 200, 1100, 2200])).toEqual({ x: 100, y: 200, w: 1000, h: 2000 });
    expect(cornersOf({ x: 100, y: 200, w: 1000, h: 2000 })).toEqual([100, 200, 1100, 2200]);
    expect(sameBoxes(boxesOf(overlay), [{ x: 0, y: 0, w: 2000, h: 4000 }])).toBe(true);
  });

  it("refuses an empty box, one below zero and one outside the extent", () => {
    const errors = (r: { x: number; y: number; w: number; h: number }) =>
      boxIssues(overlay, [r], [2000, 4000])
        .filter((i) => i.level === "error")
        .map((i) => i.message);
    expect(errors({ x: 0, y: 0, w: 2000, h: 4000 })).toEqual([]);
    expect(errors({ x: 0, y: 0, w: 0, h: 4000 })[0]).toMatch(/is empty/);
    expect(errors({ x: -50, y: 0, w: 1000, h: 4000 })[0]).toMatch(/below zero/);
    expect(errors({ x: 1500, y: 0, w: 1000, h: 4000 })[0]).toMatch(/outside the site's extent/);
  });

  it("warns when a box leaves out a circle its station saw", () => {
    const [warning] = boxIssues(overlay, [{ x: 1000, y: 0, w: 1000, h: 4000 }], [2000, 4000]);
    expect(warning.level).toBe("warning");
    expect(warning.message).toMatch(/leaves out 1 of its 1 spin circle/);
  });
});
