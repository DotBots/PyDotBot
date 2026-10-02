import { describe, expect, it } from "vitest";

import { applyMove, movedBox, snapAngle, turnAbout } from "./rigid";

describe("rigid moves", () => {
  it("turns about the origin, then shifts", () => {
    const [x, y] = applyMove({ dx_mm: 1000, dy_mm: 0, theta_deg: 90 }, [100, 0]);
    expect(x).toBeCloseTo(1000);
    expect(y).toBeCloseTo(100);
  });

  it("keeps the pivot of a turn where it is", () => {
    const start = { dx_mm: 250, dy_mm: -75, theta_deg: 30 };
    const pivot: [number, number] = [800, 400];
    const turned = turnAbout(start, pivot, 90);
    const p: [number, number] = [120, 340];
    const before = applyMove(start, p);
    const after = applyMove(turned, p);
    expect(turned.theta_deg).toBe(120);
    expect(Math.hypot(after[0] - pivot[0], after[1] - pivot[1])).toBeCloseTo(
      Math.hypot(before[0] - pivot[0], before[1] - pivot[1]),
    );
  });

  it("boxes a quarter-turned rectangle exactly", () => {
    const box = movedBox({ dx_mm: 3000, dy_mm: 0, theta_deg: 90 }, [0, 0, 2000, 1000]);
    expect(box.map((v) => Math.round(v))).toEqual([2000, 0, 3000, 2000]);
  });

  it("snaps a turn to 90 degrees unless free", () => {
    expect(snapAngle(52, false)).toBe(90);
    expect(snapAngle(-140, false)).toBe(180);
    expect(snapAngle(271, false)).toBe(-90);
    expect(snapAngle(37.46, true)).toBe(37.5);
  });
});
