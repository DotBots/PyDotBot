import { describe, expect, it } from "vitest";

import { FIT, lens, zoomAt, ZOOM_MAX, ZOOM_MIN } from "./mapView";
import { placeLabels, PRESETS, type Want } from "./RoomView";

const want = (key: string, at: [number, number], prio: number, must = false): Want => ({ key, at, w: 120, h: 16, prio, must, gap: 6 });

describe("the room view's labels", () => {
  it("keeps a label off a robot and off a label placed before it", () => {
    // A robot sits right of the handover's anchor, where the label would go first
    const robot: [number, number, number, number] = [306, 92, 330, 108];
    const placed = placeLabels([want("handover", [300, 100], 2, true), want("field", [302, 104], 4)], [robot], [0, 0, 900, 600]);
    const box = (k: string) => {
      const [x, y] = placed.get(k)!;
      return [x, y, x + 120, y + 16];
    };
    const overlaps = (a: number[], b: number[]) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
    expect(overlaps(box("handover"), robot)).toBe(false);
    expect(overlaps(box("handover"), box("field"))).toBe(false);
  });

  it("drops a label with nowhere to go, unless it must show", () => {
    const wall: [number, number, number, number] = [0, 0, 900, 600];
    const placed = placeLabels([want("tick", [300, 100], 7), want("origin", [300, 100], 3, true)], [wall], [0, 0, 900, 600]);
    expect(placed.has("tick")).toBe(false);
    expect(placed.has("origin")).toBe(true);
  });
});

describe("the room view's camera", () => {
  it("looks down on the plan's own orientation from the top, and keeps elevation in range", () => {
    const top = lens(PRESETS.find((p) => p.key === "top")!.cam);
    // x to the right, y down, as on the plan
    expect(top(1000, 0)[0]).toBeGreaterThan(top(0, 0)[0]);
    expect(top(0, 1000)[1]).toBeGreaterThan(top(0, 0)[1]);
    for (const p of PRESETS) {
      expect(p.cam.el).toBeGreaterThanOrEqual(10);
      expect(p.cam.el).toBeLessThanOrEqual(p.key === "top" ? 90 : 85);
    }
  });
});

describe("the room view's zoom", () => {
  it("holds the point under the pointer still, and stays between 0.3x and 6x of the fit", () => {
    const size = { w: 900, h: 600 };
    const z = zoomAt(FIT, 2, [700, 100], size);
    expect(z.k).toBe(2);
    const screenOf = (p: [number, number], v: typeof z) => [size.w / 2 + (p[0] - size.w / 2) * v.k + v.tx, size.h / 2 + (p[1] - size.h / 2) * v.k + v.ty];
    expect(screenOf([700, 100], z)).toEqual([700, 100]);
    expect(zoomAt(FIT, 100, [0, 0], size).k).toBe(ZOOM_MAX);
    expect(zoomAt(FIT, 0.001, [0, 0], size).k).toBe(ZOOM_MIN);
    expect(zoomAt({ k: ZOOM_MAX, tx: 0, ty: 0 }, 2, [10, 10], size)).toEqual({ k: ZOOM_MAX, tx: 0, ty: 0 });
  });
});
