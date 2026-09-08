import { describe, expect, it } from "vitest";

import {
  arenaToScreen,
  clampCamera,
  fitCamera,
  MAX_SCALE_FACTOR,
  MIN_SCALE_FACTOR,
  panBy,
  screenToArena,
  zoomAt,
} from "./camera";

describe("fitCamera", () => {
  it("centres the arena in a wide box and leaves margins", () => {
    const cam = fitCamera(2000, 1200, 800);
    const tl = arenaToScreen(cam, 0, 0);
    const br = arenaToScreen(cam, 2000, 2000);
    expect(br.sx - tl.sx).toBeCloseTo(br.sy - tl.sy, 6);
    expect(tl.sx + br.sx).toBeCloseTo(1200, 6);
    expect(tl.sy + br.sy).toBeCloseTo(800, 6);
    expect(br.sy - tl.sy).toBeLessThan(800);
  });

  it("round-trips a point through screen space", () => {
    const cam = fitCamera(4000, 900, 700);
    const { sx, sy } = arenaToScreen(cam, 1234, 567);
    const back = screenToArena(cam, sx, sy);
    expect(back.x).toBeCloseTo(1234, 6);
    expect(back.y).toBeCloseTo(567, 6);
  });
});

describe("zoomAt", () => {
  it("keeps the arena point under the cursor fixed", () => {
    const fit = fitCamera(2000, 900, 700);
    const before = screenToArena(fit, 300, 420);
    const zoomed = zoomAt(fit, 300, 420, 2.5, fit);
    const after = screenToArena(zoomed, 300, 420);
    expect(after.x).toBeCloseTo(before.x, 6);
    expect(after.y).toBeCloseTo(before.y, 6);
  });

  it("stays inside the zoom range whatever the gesture asks for", () => {
    const fit = fitCamera(2000, 900, 700);
    expect(zoomAt(fit, 0, 0, 1000, fit).scale).toBeCloseTo(fit.scale * MAX_SCALE_FACTOR, 9);
    expect(zoomAt(fit, 0, 0, 0.001, fit).scale).toBeCloseTo(fit.scale * MIN_SCALE_FACTOR, 9);
  });
});

describe("clampCamera", () => {
  it("leaves a fitted camera alone", () => {
    const fit = fitCamera(2000, 900, 700);
    expect(clampCamera(fit, 2000, 900, 700)).toEqual(fit);
  });

  it("keeps a quarter of the viewport over arena after a big pan", () => {
    const fit = fitCamera(2000, 900, 700);
    const flung = clampCamera(panBy(fit, 100000, -100000), 2000, 900, 700);
    const tl = arenaToScreen(flung, 0, 0);
    const br = arenaToScreen(flung, 2000, 2000);
    expect(tl.sx).toBeLessThanOrEqual(900 * 0.75 + 1e-6);
    expect(br.sy).toBeGreaterThanOrEqual(700 * 0.25 - 1e-6);
  });
});
