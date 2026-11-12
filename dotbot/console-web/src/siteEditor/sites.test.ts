import { describe, expect, it } from "vitest";

import { parseFloorSize, siteNameProblem } from "./sites";

describe("a new site's name", () => {
  it("takes what robots can carry and nothing else", () => {
    expect(siteNameProblem("bench-b")).toBe("");
    expect(siteNameProblem("a-name-of-17-char")).toMatch(/17 characters/);
    expect(siteNameProblem("with space")).toMatch(/letters, digits/);
    expect(siteNameProblem("café")).toMatch(/letters, digits/);
    expect(siteNameProblem("inria-2lh", ["inria-2lh"])).toMatch(/exists/);
  });
});

describe("a floor's size", () => {
  it("reads millimetres by default and metres when said", () => {
    expect(parseFloorSize("3000x2000")).toEqual([3000, 2000]);
    expect(parseFloorSize("3 x 2.5 m")).toEqual([3000, 2500]);
    expect(parseFloorSize("120 × 80 cm")).toEqual([1200, 800]);
    expect(parseFloorSize("3000")).toBeNull();
  });
});
