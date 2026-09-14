import { describe, expect, it } from "vitest";

import {
  GRID_LADDER_MM,
  GRID_SUB_STEP_MM,
  GRID_TARGET_PX,
  RULER_MIN_GAP_PX,
  SCALE_BAR_LADDER_MM,
  SCALE_BAR_PX,
  axisTicks,
  barLabel,
  canvasPx,
  frameMm,
  gridStepMm,
  gridSubStepMm,
  metreLabel,
  pxPerMm,
  rulerStepMm,
  scaleBar,
  ticksInSite,
} from "./grid";
import type { Area } from "./types";
import { viewGeom } from "./zoom";
import type { Camera, ViewGeom } from "./zoom";

// The c405 floor: 3330 x 4000 mm of site, so 7330 x 8000 mm of drawn frame.
const VIEWPORT: Area = { x: -2000, y: -2000, w: 7330, h: 8000 };
const GEOM: ViewGeom = viewGeom(900, 600, VIEWPORT);
const SITE_CAM: Camera = { scale: 1, tx: 0, ty: 0 };

describe("the grid step", () => {
  it("is the finest ladder step still at the target spacing", () => {
    // 1 m across 20 px: the finest step at least 40 px apart is 2 m.
    expect(gridStepMm(20 / 1000)).toBe(2000);
    // 1 m across 60 px: it clears the target on its own.
    expect(gridStepMm(60 / 1000)).toBe(1000);
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

  it("stops at the metre however far the camera zooms in", () => {
    [0.1, 1, 10, 100].forEach((scale) => {
      expect(gridStepMm(scale)).toBeGreaterThanOrEqual(1000);
    });
    expect(gridStepMm(100)).toBe(1000);
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

describe("the half-metre sub-grid", () => {
  it("stays away until half a metre is itself at the target spacing", () => {
    expect(gridSubStepMm(60 / 1000)).toBeNull();
    expect(gridSubStepMm(80 / 1000)).toBe(GRID_SUB_STEP_MM);
  });

  it("comes in under a metre step, never in place of one", () => {
    const perMm = 200 / 1000;
    expect(gridStepMm(perMm)).toBe(1000);
    expect(gridSubStepMm(perMm)).toBe(500);
  });

  it("is the floor: nothing finer is ever drawn", () => {
    [1, 10, 100].forEach((perMm) => {
      expect(gridSubStepMm(perMm)).toBe(GRID_SUB_STEP_MM);
    });
  });
});

describe("the ruler step", () => {
  it("is the grid's own step wherever the labels fit", () => {
    // 1 m across 60 px: a label every metre clears the gap on its own.
    expect(rulerStepMm(1000, 60 / 1000)).toBe(1000);
    expect(rulerStepMm(5000, 94 / 5000)).toBe(5000);
  });

  it("is a multiple of it where they do not, never a step of its own", () => {
    // The case the map got wrong: 5 m labels over a 2 m grid name lines the
    // grid never draws. 2 m at 40 px needs doubling, not a jump to 5 m.
    const perMm = 20 / 1000;
    expect(gridStepMm(perMm)).toBe(2000);
    const step = rulerStepMm(2000, perMm);
    expect(step % 2000).toBe(0);
    expect(step).toBe(4000);
  });

  it("lands every label on a drawn grid line, at any zoom", () => {
    [0.004, 0.01, 0.02, 0.05, 0.1, 0.3, 1].forEach((perMm) => {
      const grid = gridStepMm(perMm);
      const ruler = rulerStepMm(grid, perMm);
      expect(ruler % grid).toBe(0);
      expect(ruler * perMm).toBeGreaterThanOrEqual(RULER_MIN_GAP_PX);
    });
  });

  it("never names anything finer than the metre", () => {
    [1, 10, 100].forEach((perMm) => {
      expect(rulerStepMm(gridStepMm(perMm), perMm)).toBeGreaterThanOrEqual(1000);
    });
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

describe("the scale bar", () => {
  it("stands for a round distance, never a measured one", () => {
    [0.004, 0.02, 0.05, 0.2, 1, 4].forEach((perMm) => {
      expect(SCALE_BAR_LADDER_MM).toContain(scaleBar(perMm).mm);
    });
  });

  it("is the longest distance that still fits the space it has", () => {
    // Up past the finest the map can ever be zoomed, where the bar would
    // otherwise run out of the panel it sits in.
    [0.004, 0.02, 0.05, 0.2, 1, 1.5, 2.5].forEach((perMm) => {
      const { mm, px } = scaleBar(perMm);
      expect(px).toBeLessThanOrEqual(SCALE_BAR_PX);
      const next = SCALE_BAR_LADDER_MM[SCALE_BAR_LADDER_MM.indexOf(mm) + 1];
      if (next) expect(next * perMm).toBeGreaterThan(SCALE_BAR_PX);
    });
  });

  it("stands for less floor the further the map zooms in", () => {
    const wide = scaleBar(0.02).mm;
    const close = scaleBar(0.4).mm;
    expect(close).toBeLessThan(wide);
  });

  it("keeps its shortest rung rather than vanishing when zoomed right in", () => {
    const { mm, px } = scaleBar(50);
    expect(mm).toBe(SCALE_BAR_LADDER_MM[0]);
    expect(px).toBeGreaterThan(0);
  });

  it("names its distance in the unit that needs no leading zeros", () => {
    expect(barLabel(20)).toBe("20 mm");
    expect(barLabel(500)).toBe("500 mm");
    expect(barLabel(1000)).toBe("1 m");
    expect(barLabel(5000)).toBe("5 m");
  });
});

describe("the ticks a ruler names", () => {
  // The c405 floor inside the viewport the tests draw: 3330 x 4000 mm of
  // measured site, with 2 m of unmeasured margin on every side.
  const SITE: Area = { x: 0, y: 0, w: 3330, h: 4000, name: "c405-arena" };
  const ticks = (axis: "x" | "y", step: number) =>
    axisTicks(axis, VIEWPORT, GEOM, SITE_CAM, step);

  it("never counts backwards from the site's zero", () => {
    (["x", "y"] as const).forEach((axis) => {
      const named = ticksInSite(ticks(axis, 1000), axis, SITE);
      expect(named.length).toBeGreaterThan(0);
      named.forEach((t) => expect(t.mm).toBeGreaterThanOrEqual(0));
    });
  });

  it("stops at the site's far edge rather than naming the margin", () => {
    expect(ticksInSite(ticks("x", 1000), "x", SITE).map((t) => t.mm)).toEqual([
      0, 1000, 2000, 3000,
    ]);
    expect(ticksInSite(ticks("y", 1000), "y", SITE).map((t) => t.mm)).toEqual([
      0, 1000, 2000, 3000, 4000,
    ]);
  });

  it("keeps the line on the far edge itself", () => {
    const edge: Area = { x: 0, y: 0, w: 3000, h: 4000 };
    expect(
      ticksInSite(ticks("x", 1000), "x", edge).map((t) => t.mm),
    ).toContain(3000);
  });

  it("drops nothing the site covers, at any zoom", () => {
    [1, 2, 4, 8].forEach((scale) => {
      const cam: Camera = { scale, tx: 0, ty: 0 };
      const all = axisTicks("x", VIEWPORT, GEOM, cam, 1000);
      const named = ticksInSite(all, "x", SITE);
      expect(named).toEqual(all.filter((t) => t.mm >= 0 && t.mm <= 3330));
    });
  });

  it("fences only the zero side when the site has no measured extent", () => {
    const named = ticksInSite(ticks("x", 1000), "x", null);
    expect(named.length).toBeGreaterThan(0);
    named.forEach((t) => expect(t.mm).toBeGreaterThanOrEqual(0));
    // Everything from zero out, including past where a site would have ended.
    expect(named.map((t) => t.mm)).toEqual(
      ticks("x", 1000)
        .filter((t) => t.mm >= 0)
        .map((t) => t.mm),
    );
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
