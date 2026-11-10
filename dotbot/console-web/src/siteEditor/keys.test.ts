import { describe, expect, it } from "vitest";

import { ACTION_KEY, SHORTCUTS_KEY } from "../shortcuts";
import { editorKeys, keyAction, SHARED_KEY } from "./keys";

describe("the editor's keys against the console's", () => {
  it("binds nothing to the console's Start, Go or pose mode", () => {
    const keys = editorKeys();
    for (const k of [ACTION_KEY.start, ACTION_KEY.go, ACTION_KEY.poseMode]) {
      expect(keys.has(k)).toBe(false);
      expect(keys.has(k.toLowerCase())).toBe(false);
    }
  });

  it("keeps Stop, the panes and the shortcuts list as the console has them", () => {
    expect(SHARED_KEY).toEqual({
      stop: ACTION_KEY.stop,
      leftPanel: ACTION_KEY.leftPanel,
      rightPanel: ACTION_KEY.rightPanel,
      shortcuts: SHORTCUTS_KEY,
    });
    expect(["X", "[", "]", "?"].every((k) => editorKeys().has(k))).toBe(true);
  });

  it("gives X no tool in any kind, so it is only ever Stop", () => {
    for (const kind of ["view", "frame", "areas", "walls", "objects", "stations"] as const) {
      expect(keyAction("x", kind)).toBeNull();
    }
  });

  it("picks kinds by number and tools by letter within a kind", () => {
    expect(keyAction("2", "view")).toEqual({ kind: "areas" });
    expect(keyAction("Escape", "walls")).toEqual({ kind: "view" });
    expect(keyAction("a", "areas")).toEqual({ tool: "area" });
    expect(keyAction("a", "walls")).toBeNull();
    expect(keyAction("c", "objects")).toEqual({ tool: "charger" });
  });
});
