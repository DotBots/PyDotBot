import { describe, expect, it } from "vitest";

import { FIT, planCamFromRoom, planProject, planViewport, roomFit, roomProject, roomZoomFromPlan, TOP_DOWN } from "./mapView";

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
