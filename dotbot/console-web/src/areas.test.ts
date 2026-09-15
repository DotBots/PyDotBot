import { afterEach, describe, expect, it, vi } from "vitest";

import { loadHiddenAreas, saveHiddenAreas, toggleHidden } from "./areas";

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("the areas Layers > Areas hides", () => {
  it("starts with none hidden, so every outline is drawn", () => {
    expect(loadHiddenAreas()).toEqual(new Set());
  });

  it("round-trips the hidden set through storage", () => {
    saveHiddenAreas(new Set(["annex"]));
    expect(loadHiddenAreas()).toEqual(new Set(["annex"]));
  });

  it("draws every outline when storage refuses to answer", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(loadHiddenAreas()).toEqual(new Set());
  });

  it("keeps working when storage refuses to remember", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(() => saveHiddenAreas(new Set(["annex"]))).not.toThrow();
  });

  it("ignores a stored value that is not a list of names", () => {
    window.localStorage.setItem("dotbot.console.hiddenAreas", '{"annex": true}');
    expect(loadHiddenAreas()).toEqual(new Set());
  });
});

describe("toggling one area", () => {
  it("hides an area that was shown", () => {
    expect(toggleHidden(new Set(), "arena")).toEqual(new Set(["arena"]));
  });

  it("shows an area that was hidden, leaving the rest alone", () => {
    expect(toggleHidden(new Set(["arena", "annex"]), "arena")).toEqual(
      new Set(["annex"]),
    );
  });
});
