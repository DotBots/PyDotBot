import { afterEach, describe, expect, it, vi } from "vitest";

import {
  hiddenAreaNames,
  isShown,
  loadAreaVisibility,
  saveAreaVisibility,
  toggleShown,
} from "./areas";
import type { Area } from "./types";

const FIELD: Area = { x: 0, y: 0, w: 2000, h: 2000, name: "field", role: "field" };
const STAGING: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: "staging", role: "staging" };
const CORNER: Area = { x: 1000, y: 0, w: 1000, h: 1000, name: "dev-corner", role: "corner" };
const VIEW: Area = { x: 0, y: 0, w: 2000, h: 4000, name: "field+staging" };
const AREAS = [FIELD, STAGING, VIEW, CORNER];

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("which areas are drawn with no choice made", () => {
  it("hides corners and shows every other role, and no role", () => {
    expect(hiddenAreaNames(AREAS, {})).toEqual(new Set(["dev-corner"]));
  });

  it("lets a choice override the role, either way", () => {
    expect(isShown(CORNER, { "dev-corner": true })).toBe(true);
    expect(isShown(FIELD, { field: false })).toBe(false);
  });
});

describe("the choices Layers > Areas remembers", () => {
  it("starts with none", () => {
    expect(loadAreaVisibility()).toEqual({});
  });

  it("round-trips through storage", () => {
    saveAreaVisibility({ "dev-corner": true, staging: false });
    expect(loadAreaVisibility()).toEqual({ "dev-corner": true, staging: false });
  });

  it("falls back to the roles when storage refuses to answer", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(loadAreaVisibility()).toEqual({});
  });

  it("keeps working when storage refuses to remember", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(() => saveAreaVisibility({ staging: false })).not.toThrow();
  });

  it("drops entries that are not true or false", () => {
    window.localStorage.setItem(
      "dotbot.console.areaVisibility",
      '{"staging": false, "field": "yes"}',
    );
    expect(loadAreaVisibility()).toEqual({ staging: false });
  });
});

describe("toggling one area", () => {
  it("hides an area shown by default", () => {
    expect(toggleShown({}, AREAS, "field")).toEqual({ field: false });
  });

  it("shows a corner hidden by default", () => {
    expect(toggleShown({}, AREAS, "dev-corner")).toEqual({ "dev-corner": true });
  });

  it("flips a choice already made, leaving the rest alone", () => {
    expect(toggleShown({ field: false, staging: false }, AREAS, "field")).toEqual({
      field: true,
      staging: false,
    });
  });
});
