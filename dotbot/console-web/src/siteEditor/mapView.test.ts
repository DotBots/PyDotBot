import { describe, expect, it } from "vitest";

import { contextBounds, EDIT_INSETS, FIT, planFitCam, floorStep, planCamFromRoom, planProject, planViewport, roomFit, roomProject, roomZoomFromPlan, stationLabel, TOP_DOWN } from "./mapView";

const EXTENT: [number, number] = [1060, 1220];
const STATIONS: [number, number, number][] = [
  [-542, 1268, 2423],
  [1387, -245, 1606],
];
const SIZE = { w: 1013, h: 857 };
const INSETS = { top: 64, bottom: 64 };
const POINTS: [number, number][] = [
  [0, 0],
  [1060, 1220],
  [530, 610],
  [-542, 1268],
  [1387, -245],
];

describe("the 3D view and the plan, straight down", () => {
  const viewport = planViewport(EXTENT, STATIONS.map(([x, y]) => ({ x, y })));
  const fit = roomFit(TOP_DOWN, EXTENT, STATIONS, SIZE, INSETS);

  it("draw every floor point on the same pixel, within 1 px, after the hand-over to the plan", () => {
    for (const zoom of [FIT, { k: 2.3, tx: -140, ty: 55 }, { k: 0.4, tx: 12, ty: -30 }]) {
      const cam = planCamFromRoom(fit, zoom, SIZE, viewport);
      for (const p of POINTS) {
        const a = roomProject(TOP_DOWN, fit, zoom, SIZE, p[0], p[1]);
        const b = planProject(cam, viewport, SIZE, p);
        expect(Math.abs(a[0] - b[0])).toBeLessThan(1);
        expect(Math.abs(a[1] - b[1])).toBeLessThan(1);
      }
    }
  });

  it("and back: the plan's zoom and pan hand over to the 3D view the same way", () => {
    const cam = { scale: 1.7, tx: 80, ty: -40 };
    const zoom = roomZoomFromPlan(fit, cam, SIZE, viewport);
    for (const p of POINTS) {
      const a = planProject(cam, viewport, SIZE, p);
      const b = roomProject(TOP_DOWN, fit, zoom, SIZE, p[0], p[1]);
      expect(Math.abs(a[0] - b[0])).toBeLessThan(1);
      expect(Math.abs(a[1] - b[1])).toBeLessThan(1);
    }
  });
});

describe("the grid and labels both views share", () => {
  it("draws the floor finer than the context, as fine as the screen allows", () => {
    expect(floorStep(0.2, [1060, 1220])).toBe(100);
    expect(floorStep(0.1, [1060, 1220])).toBe(250);
    expect(floorStep(0.03, [1060, 1220])).toBe(500);
    expect(floorStep(0.001, [6000, 4000])).toBe(1000);
  });

  it("runs the context a step beyond the floor and the stations' feet", () => {
    expect(contextBounds([1060, 1220], [[-542, 1268]], 500)).toEqual([-1500, -500, 2000, 2000]);
  });

  it("says a station the same way in 3D and top-down", () => {
    expect(stationLabel(0, 2423, 1.1)).toBe("S0 ≈ 2.4 m up · fit 1.10 mm");
    expect(stationLabel(1, 1606)).toBe("S1 ≈ 1.6 m up");
  });
});

describe("the plan's fit", () => {
  it("keeps the floor's origin clear of the tool rail on the left, wide or tall", () => {
    for (const [size, extent] of [
      [{ w: 820, h: 690 }, [1930, 1910]],
      [{ w: 1200, h: 500 }, [1930, 1910]],
      [{ w: 500, h: 900 }, [4000, 1000]],
    ] as [{ w: number; h: number }, [number, number]][]) {
      const viewport = planViewport(extent, []);
      const cam = planFitCam(size, viewport, EDIT_INSETS);
      const [x0, y0] = planProject(cam, viewport, size, [0, 0]);
      const [x1] = planProject(cam, viewport, size, [extent[0], 0]);
      expect(x0).toBeGreaterThanOrEqual(EDIT_INSETS.left! + 8);
      expect(x1).toBeLessThanOrEqual(size.w);
      expect(y0).toBeGreaterThan(0);
    }
  });
});
