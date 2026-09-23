import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_PANELS, loadPanels, savePanel } from "./panels";

const KEY = "dotbot.console.panels";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("the side panels, per browser", () => {
  it("are open with nothing stored", () => {
    expect(loadPanels()).toEqual({ left: false, right: false });
  });

  it("read back each side as saved, leaving the other alone", () => {
    savePanel("right", true);
    expect(loadPanels()).toEqual({ left: false, right: true });
    savePanel("left", true);
    savePanel("right", false);
    expect(loadPanels()).toEqual({ left: true, right: false });
  });

  it("keep a valid side and open the other", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ left: true, right: "yes" }));
    expect(loadPanels()).toEqual({ left: true, right: false });
  });

  it("read anything but a stored record as open", () => {
    for (const raw of ["not json", "true", "[]", "null", "{"]) {
      window.localStorage.setItem(KEY, raw);
      expect(loadPanels()).toEqual(DEFAULT_PANELS);
    }
  });

  it("are open when storage refuses, and forget quietly on a save", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadPanels()).toEqual(DEFAULT_PANELS);
    expect(() => savePanel("left", true)).not.toThrow();
  });
});
