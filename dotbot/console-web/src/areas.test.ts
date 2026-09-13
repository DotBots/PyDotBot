import { describe, expect, it } from "vitest";

import { shownAreaNames, toggledAreaNames } from "./areas";
import type { Area, Site } from "./types";

const ARENA: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "arena" };
const ANNEX: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "annex" };

const C405: Site = {
  name: "c405-arena",
  anchor: "the arena's top-left corner, against the door wall of C405",
  extent_mm: [3330, 4000],
  areas: [ARENA, ANNEX],
};

describe("the areas ticked in Layers > Areas", () => {
  it("ticks the areas shown", () => {
    expect(shownAreaNames(C405, [ARENA, ANNEX])).toEqual(["arena", "annex"]);
  });

  it("ticks nothing when nothing is shown, which is the whole site", () => {
    expect(shownAreaNames(C405, [])).toEqual([]);
  });

  it("ticks no box for a rectangle the site does not define", () => {
    // The whole-site rectangle a renderer draws is not an area of the site,
    // so it must never come back as a tick the next toggle would send on.
    const whole: Area = { x: 0, y: 0, w: 3330, h: 4000, name: "c405-arena" };
    expect(shownAreaNames(C405, [whole])).toEqual([]);
  });
});

describe("what a toggle sends", () => {
  it("unticks the last area to an empty set", () => {
    expect(toggledAreaNames(C405, [ARENA], "arena")).toEqual([]);
  });

  it("sends one name after untick-all, then tick-one", () => {
    expect(toggledAreaNames(C405, [], "arena")).toEqual(["arena"]);
  });

  it("sends one name even if the controller answered with the whole site", () => {
    const whole: Area = { x: 0, y: 0, w: 3330, h: 4000, name: "c405-arena" };
    expect(toggledAreaNames(C405, [whole], "arena")).toEqual(["arena"]);
  });

  it("adds to what is already shown", () => {
    expect(toggledAreaNames(C405, [ARENA], "annex")).toEqual(["arena", "annex"]);
  });
});
