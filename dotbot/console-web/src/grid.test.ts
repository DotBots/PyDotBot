import { describe, expect, it } from "vitest";

import {
  GRID_LADDER_MM,
  GRID_TARGET_PX,
  RULER_TARGET_PX,
  axisTicks,
  canvasPx,
  frameMm,
  gridStepMm,
  metreLabel,
  pxPerMm,
} from "./grid";
import type { Area } from "./types";
import type { Camera, ViewGeom } from "./zoom";

// The c405 floor: 3330 x 4000 mm of site, so 7330 x 8000 mm of drawn frame.
const VIEWPORT: Area = { x: -2000, y: -2000, w: 7330, h: 8000 };
const GEOM: ViewGeom = { w: 900, h: 600, side: 552 };
const SITE_CAM: Camera = { scale: 1, tx: 0, ty: 0 };

describe("the grid step", () => {
  it("is the finest ladder step still at the target spacing", () => {
    // 1 m across 20 px: the finest step at least 40 px apart is 2 m.
    expect(gridStepMm(20 / 1000)).toBe(2000);
    // 1 m across 60 px: 0.5 m lands at 30 px, so 1 m is the finest that holds.
    expect(gridStepMm(60 / 1000)).toBe(1000);
    // 1 m across 500 px: 0.1 m lands at 50 px, 0.05 m at 25 px.
    expect(gridStepMm(500 / 1000)).toBe(100);
  });

  it("holds every step it picks at or above the target", () => {
    [0.005, 0.02, 0.05, 0.1, 0.4, 1, 4].forEach((scale) => {
      const step = gridStepMm(scale);
      const finest = GRID_LADDER_MM[GRID_LADDER_MM.length - 1];
      const coarsest = GRID_LADDER_MM[0];
      if (step !== coarsest && step !== finest) {
        expect(step * scale).toBeGreaterThanOrEqual(GRID_TARGET_PX);
      }
      expect(GRID_LADDER_MM).toContain(step);
    });
  });

  it("falls back to the coarsest step rather than crowding the canvas", () => {
    expect(gridStepMm(1 / 1000)).toBe(GRID_LADDER_MM[0]);
  });

  it("stops at the finest step rather than splitting a centimetre", () => {
    expect(gridStepMm(100)).toBe(GRID_LADDER_MM[GRID_LADDER_MM.length - 1]);
  });

  it("names lines further apart than it draws them", () => {
    const perMm = pxPerMm("x", VIEWPORT, GEOM, SITE_CAM);
    expect(gridStepMm(perMm, RULER_TARGET_PX)).toBeGreaterThanOrEqual(
      gridStepMm(perMm, GRID_TARGET_PX),
    );
  });

  it("gets finer as the camera zooms in", () => {
    const at = (scale: number) =>
      gridStepMm(pxPerMm("x", VIEWPORT, GEOM, { scale, tx: 0, ty: 0 }));
    const steps = [0.5, 1, 2, 4, 8, 16].map(at);
    steps.slice(1).forEach((step, i) => {
      expect(step).toBeLessThanOrEqual(steps[i]);
    });
    expect(steps[steps.length - 1]).toBeLessThan(steps[0]);
  });
});

describe("a frame coordinate on the canvas", () => {
  it("round-trips through the camera", () => {
    const cam: Camera = { scale: 3.5, tx: -120, ty: 64 };
    [-2000, 0, 1665, 3330].forEach((mm) => {
      const px = canvasPx("x", mm, VIEWPORT, GEOM, cam);
      expect(frameMm("x", px, VIEWPORT, GEOM, cam)).toBeCloseTo(mm, 6);
    });
  });

  it("puts the drawn frame's own centre at the canvas centre with no camera", () => {
    const centreX = VIEWPORT.x + VIEWPORT.w / 2;
    expect(canvasPx("x", centreX, VIEWPORT, GEOM, SITE_CAM)).toBeCloseTo(
      GEOM.w / 2,
      6,
    );
  });
});

describe("the lines the ruler names", () => {
  it("are multiples of the step, so they are anchored at the frame's zero", () => {
    const ticks = axisTicks("x", VIEWPORT, GEOM, SITE_CAM, 1000);
    expect(ticks.length).toBeGreaterThan(0);
    ticks.forEach((t) => expect(Math.abs(t.mm % 1000)).toBe(0));
  });

  it("cover what the canvas shows and nothing outside it", () => {
    const ticks = axisTicks("x", VIEWPORT, GEOM, SITE_CAM, 1000);
    ticks.forEach((t) => {
      expect(t.px).toBeGreaterThanOrEqual(-1e-6);
      expect(t.px).toBeLessThanOrEqual(GEOM.w + 1e-6);
    });
    // One step further out on each side is off the canvas.
    const first = ticks[0].mm - 1000;
    const last = ticks[ticks.length - 1].mm + 1000;
    expect(canvasPx("x", first, VIEWPORT, GEOM, SITE_CAM)).toBeLessThan(0);
    expect(canvasPx("x", last, VIEWPORT, GEOM, SITE_CAM)).toBeGreaterThan(GEOM.w);
  });

  it("follow the camera when it pans", () => {
    const panned: Camera = { scale: 1, tx: 200, ty: 0 };
    const still = axisTicks("x", VIEWPORT, GEOM, SITE_CAM, 1000);
    const moved = axisTicks("x", VIEWPORT, GEOM, panned, 1000);
    const shared = moved.filter((m) => still.some((s) => s.mm === m.mm));
    expect(shared.length).toBeGreaterThan(0);
    shared.forEach((m) => {
      const before = still.find((s) => s.mm === m.mm)!;
      expect(m.px).toBeCloseTo(before.px + 200, 6);
    });
  });
});

describe("a metre label", () => {
  it("carries only the digits its step resolves", () => {
    expect(metreLabel(3000, 1000)).toBe("3 m");
    expect(metreLabel(3500, 500)).toBe("3.5 m");
    expect(metreLabel(3200, 100)).toBe("3.2 m");
    expect(metreLabel(3250, 50)).toBe("3.25 m");
  });

  it("names the site's zero as zero", () => {
    expect(metreLabel(0, 1000)).toBe("0 m");
  });

  it("keeps the sign of a coordinate outside the site", () => {
    expect(metreLabel(-2000, 1000)).toBe("-2 m");
  });
});
