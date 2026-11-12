import { describe, expect, it } from "vitest";

import { docFromSite } from "./model";
import { canvasToMm, coincident, moved, removed, resized, snap, toBox } from "./plan";

const VIEW = { x: -100, y: -100, w: 1260, h: 1420 };
const GEOM = { w: 800, h: 700, boxW: 1260 * 0.4, boxH: 1420 * 0.4 };

describe("the plan's geometry", () => {
  it("goes from the canvas to frame mm and back through the camera", () => {
    for (const cam of [{ scale: 1, tx: 0, ty: 0 }, { scale: 3, tx: 40, ty: -25 }]) {
      const box = toBox([530, 610], VIEW, GEOM);
      const local: [number, number] = [
        GEOM.w / 2 + cam.tx + cam.scale * (box[0] + (GEOM.w - GEOM.boxW) / 2 - GEOM.w / 2),
        GEOM.h / 2 + cam.ty + cam.scale * (box[1] + (GEOM.h - GEOM.boxH) / 2 - GEOM.h / 2),
      ];
      const back = canvasToMm(local, cam, VIEW, GEOM);
      expect(back[0]).toBeCloseTo(530, 6);
      expect(back[1]).toBeCloseTo(610, 6);
    }
  });

  it("snaps to 10 mm unless asked not to", () => {
    expect(snap(434, true)).toBe(430);
    expect(snap(434.4, false)).toBe(434);
  });

  it("resizes an area from a corner, keeping the far one", () => {
    const area = docFromSite({ anchor: null, extent_mm: null, areas: [{ name: "a", x: 0, y: 0, w: 100, h: 100 }] }).areas[0];
    expect(resized(area, "se", [300, 200])).toMatchObject({ x: 0, y: 0, w: 300, h: 200 });
    expect(resized(area, "nw", [150, 120])).toMatchObject({ x: 100, y: 100, w: 50, h: 20 });
  });

  it("moves and removes one entity by its key", () => {
    const doc = docFromSite({
      anchor: null,
      extent_mm: [1000, 1000],
      areas: [{ name: "a", x: 0, y: 0, w: 100, h: 100 }],
      walls: [{ points: [[0, 0], [10, 0]] }],
    });
    expect(moved(doc, "wall:0", 5, 5).walls[0].points).toEqual([[5, 5], [15, 5]]);
    expect(moved(doc, "wall:0", 5, 5).areas[0].x).toBe(0);
    expect(removed(doc, "area:a").areas).toEqual([]);
  });

  it("finds rectangles drawn as one outline", () => {
    const r: [number, number, number, number] = [0, 0, 1060, 1220];
    expect(
      coincident([
        { label: "floor", rect: r },
        { label: "field", rect: r },
        { label: "S0 coverage", rect: r },
        { label: "staging", rect: [0, 1000, 1060, 1220] },
      ]),
    ).toEqual([["floor", "field", "S0 coverage"]]);
  });
});
