import { describe, expect, it } from "vitest";

import {
  AREA_PREFERRED,
  TYPED_RECT,
  areaChoices,
  defaultChoice,
  parseReads,
  parseRect,
  pointsSpec,
} from "./calibrationSetup";
import type { Site } from "./types";

const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner",
  extent_mm: [2000, 4000],
  areas: [
    { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" },
    { x: 0, y: 0, w: 2000, h: 2000, name: "arena" },
  ],
};

describe("the rectangle picker", () => {
  it("offers the site's areas in the site's own order", () => {
    expect(areaChoices(C405)).toEqual(["annex", "arena"]);
  });

  it("opens on the arena when the site has one, whatever its order", () => {
    expect(defaultChoice(C405)).toBe(AREA_PREFERRED);
  });

  it("opens on the first area when the site has no arena", () => {
    expect(defaultChoice({ ...C405, areas: [C405.areas[0]] })).toBe("annex");
  });

  it("opens on the typed rectangle when the site defines no areas", () => {
    expect(defaultChoice({ ...C405, areas: [] })).toBe(TYPED_RECT);
    expect(defaultChoice(null)).toBe(TYPED_RECT);
  });
});

describe("a typed rectangle", () => {
  it("is four whole millimetres, spaces allowed", () => {
    expect(parseRect(" 750, 750 ,500,500 ")).toEqual({
      x: 750,
      y: 750,
      w: 500,
      h: 500,
      name: "750,750,500,500",
    });
  });

  it("is refused while it is not yet four numbers", () => {
    expect(parseRect("750,750,500")).toBeNull();
    expect(parseRect("")).toBeNull();
    expect(parseRect("750,750,500,500,500")).toBeNull();
  });

  it("is refused when a number is not whole millimetres", () => {
    expect(parseRect("750,750,500.5,500")).toBeNull();
  });

  it("is refused when it has no area", () => {
    expect(parseRect("750,750,0,500")).toBeNull();
    expect(parseRect("750,750,500,-10")).toBeNull();
  });

  it("keeps a negative origin, which is frame mm outside the site", () => {
    expect(parseRect("-500,-500,1000,1000")?.x).toBe(-500);
  });
});

describe("the specification Start sends", () => {
  it("is the named area's four corners", () => {
    expect(pointsSpec("arena", "")).toBe("arena:corners");
  });

  it("is the typed rectangle's four corners", () => {
    expect(pointsSpec(TYPED_RECT, "750,750,500,500")).toBe(
      "750,750,500,500:corners",
    );
  });

  it("normalises the typed rectangle's spacing, so one spec means one thing", () => {
    expect(pointsSpec(TYPED_RECT, " 750 , 750 , 500 , 500 ")).toBe(
      "750,750,500,500:corners",
    );
  });

  it("is absent while the typed rectangle is incomplete", () => {
    expect(pointsSpec(TYPED_RECT, "750,750")).toBeNull();
  });
});

describe("reads per point", () => {
  it("takes a whole count of at least one", () => {
    expect(parseReads("25")).toBe(25);
    expect(parseReads(" 1 ")).toBe(1);
  });

  it("refuses anything that is not one", () => {
    expect(parseReads("")).toBeNull();
    expect(parseReads("0")).toBeNull();
    expect(parseReads("-5")).toBeNull();
    expect(parseReads("2.5")).toBeNull();
    expect(parseReads("lots")).toBeNull();
  });
});
