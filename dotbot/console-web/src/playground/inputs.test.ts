import { describe, expect, it } from "vitest";

import {
  addGoal,
  goalAt,
  moveGoal,
  normalizeRect,
  pruneRects,
  rectHandleAt,
  removeGoal,
  removeRect,
  replaceRect,
  resizeRect,
} from "./inputs";
import type { Goal, RectShape } from "./types";

const pins: Goal[] = [
  { id: 1, x: 300, y: 300 },
  { id: 2, x: 1500, y: 1500 },
];

describe("goals", () => {
  it("finds the pin under a tap and nothing under empty arena", () => {
    expect(goalAt(pins, { x: 320, y: 310 })).toBe(0);
    expect(goalAt(pins, { x: 1480, y: 1520 })).toBe(1);
    expect(goalAt(pins, { x: 900, y: 900 })).toBe(-1);
  });

  it("takes the nearer pin when two are within reach", () => {
    const close: Goal[] = [
      { id: 1, x: 0, y: 0 },
      { id: 2, x: 100, y: 0 },
    ];
    expect(goalAt(close, { x: 70, y: 0 })).toBe(1);
  });

  it("replaces the set on a plain tap and appends on a shift-tap", () => {
    expect(addGoal(pins, { x: 900, y: 100 }, false)).toHaveLength(1);
    const added = addGoal(pins, { x: 900, y: 100 }, true);
    expect(added).toHaveLength(3);
    expect(added[2]).toMatchObject({ x: 900, y: 100 });
  });

  it("gives every pin a distinct id", () => {
    const one = addGoal([], { x: 0, y: 0 }, false);
    const two = addGoal(one, { x: 10, y: 10 }, true);
    expect(new Set(two.map((g) => g.id)).size).toBe(2);
  });

  it("moves one pin and leaves the others alone", () => {
    const moved = moveGoal(pins, 0, { x: 700, y: 800 });
    expect(moved[0]).toMatchObject({ id: 1, x: 700, y: 800 });
    expect(moved[1]).toEqual(pins[1]);
  });

  it("removes the pin a click landed on", () => {
    expect(removeGoal(pins, 0)).toEqual([pins[1]]);
  });
});

const rects: RectShape[] = [{ id: 1, x: 400, y: 400, w: 800, h: 600 }];

describe("rects", () => {
  it("normalises a drag from any corner", () => {
    expect(normalizeRect({ x: 900, y: 800 }, { x: 300, y: 200 })).toEqual({
      x: 300,
      y: 200,
      w: 600,
      h: 600,
    });
  });

  it("grabs an edge, a corner or the body", () => {
    expect(rectHandleAt(rects, { x: 400, y: 400 })).toEqual({ index: 0, handle: "nw" });
    expect(rectHandleAt(rects, { x: 1200, y: 1000 })).toEqual({ index: 0, handle: "se" });
    expect(rectHandleAt(rects, { x: 800, y: 400 })).toEqual({ index: 0, handle: "n" });
    expect(rectHandleAt(rects, { x: 400, y: 700 })).toEqual({ index: 0, handle: "w" });
    expect(rectHandleAt(rects, { x: 800, y: 700 })).toEqual({ index: 0, handle: "inside" });
    expect(rectHandleAt(rects, { x: 1800, y: 1800 })).toEqual({ index: -1, handle: null });
  });

  it("takes the topmost rectangle when two overlap", () => {
    const two = [...rects, { id: 2, x: 700, y: 600, w: 400, h: 300 }];
    expect(rectHandleAt(two, { x: 800, y: 700 }).index).toBe(1);
  });

  it("resizes from the edge that was grabbed", () => {
    expect(resizeRect(rects[0], "w", { x: 200, y: 0 })).toMatchObject({ x: 200, w: 1000 });
    expect(resizeRect(rects[0], "e", { x: 1600, y: 0 })).toMatchObject({ x: 400, w: 1200 });
    expect(resizeRect(rects[0], "s", { x: 0, y: 1400 })).toMatchObject({ y: 400, h: 1000 });
    expect(resizeRect(rects[0], "se", { x: 1600, y: 1400 })).toMatchObject({ w: 1200, h: 1000 });
  });

  it("keeps a dragged edge from inverting the rectangle", () => {
    expect(resizeRect(rects[0], "w", { x: 1500, y: 0 })).toMatchObject({ x: 1200, w: 0 });
  });

  it("replaces and removes by index", () => {
    const grown = { ...rects[0], w: 900 };
    expect(replaceRect(rects, 0, grown)).toEqual([grown]);
    expect(removeRect(rects, 0)).toEqual([]);
  });

  it("drops the slivers a stray click leaves behind", () => {
    const kept = pruneRects([...rects, { id: 2, x: 0, y: 0, w: 3, h: 900 }]);
    expect(kept).toEqual(rects);
  });
});
