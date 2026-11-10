import { describe, expect, it } from "vitest";

import { anchorErrors, fitAnchors, forbidden, frameTwin, NO_MOVE, toNew, toOld, withOrigin, zeroAt } from "./frameMove";

describe("a move of the frame", () => {
  it("goes there and back", () => {
    const m = { theta_deg: 2, pivot: [530, 610] as [number, number], dx: 10, dy: -5, note: null };
    const p: [number, number] = [100, 900];
    const back = toOld(m, toNew(m, p));
    expect(back[0]).toBeCloseTo(100, 9);
    expect(back[1]).toBeCloseTo(900, 9);
  });

  it("puts zero on the first robot and the x axis through the second", () => {
    const m = zeroAt([200, 300], [400, 500], null);
    expect(m.theta_deg).toBe(45);
    const z = toNew(m, [200, 300]);
    expect(z[0]).toBeCloseTo(0, 6);
    expect(z[1]).toBeCloseTo(0, 6);
    const q = toNew(m, [400, 500]);
    expect(q[1]).toBeCloseTo(0, 6);
    expect(q[0]).toBeCloseTo(Math.hypot(200, 200), 6);
  });

  it("prints its terminal twin", () => {
    expect(frameTwin("inria-2lh", "4640cfde", { theta_deg: 2, pivot: [530, 610], dx: 3, dy: 0, note: null })).toBe(
      "dotbot site turn inria-2lh --rotate 2 --about 530,610 --shift 3,0 --calibration 4640cfde",
    );
  });
});

describe("the stillness gate", () => {
  it("opens once a fix stays within 3 mm for 2 s", async () => {
    const { stillness } = await import("./FramePanel");
    const track = [0, 500, 1000, 1500, 2000].map((t, i) => ({ t, p: [100 + (i % 2), 200] as [number, number] }));
    expect(stillness(track, 2000).still).toBe(true);
    expect(stillness(track.slice(-2), 2000).still).toBe(false);
    const moving = track.map((s, i) => ({ ...s, p: [100 + 10 * i, 200] as [number, number] }));
    expect(stillness(moving, 2000).still).toBe(false);
  });
});

describe("the origin from robots on spots", () => {
  it("shifts for one robot and recovers a turn and shift for two", () => {
    const one = fitAnchors([{ robot: "a", fix: [430, 458], spot: [300, 400] }], null)!;
    expect(one.theta_deg).toBe(0);
    expect(toOld(one, [300, 400])).toEqual([430, 458]);
    // A known move: turn 5 degrees about (530, 610), origin shifted by (40, -20)
    const truth = { theta_deg: 5, pivot: [530, 610] as [number, number], dx: 40, dy: -20, note: null };
    const spots: [number, number][] = [
      [300, 400],
      [900, 700],
      [600, 1000],
    ];
    const fitted = fitAnchors(spots.map((spot, i) => ({ robot: String(i), fix: toOld(truth, spot), spot })), null)!;
    expect(fitted.theta_deg).toBeCloseTo(5, 1);
    for (const e of anchorErrors(fitted, spots.map((spot, i) => ({ robot: String(i), fix: toOld(truth, spot), spot })))) expect(e).toBeLessThan(1.5);
  });

  it("keeps the origin out of the quadrant that would give a measured point a negative coordinate", () => {
    const points: [number, number][] = [
      [200, 300],
      [800, 900],
    ];
    const ok = forbidden({ ...NO_MOVE, dx: 100, dy: 100 }, points)!;
    expect(ok.originOk).toBe(true);
    expect(ok.corner).toEqual([200, 300]);
    const bad = forbidden({ ...NO_MOVE, dx: 250, dy: 100 }, points)!;
    expect(bad.originOk).toBe(false);
    const moved = withOrigin({ ...NO_MOVE, dx: 250, dy: 100 }, bad.corner);
    expect(toOld(moved, [0, 0])).toEqual([200, 300]);
    expect(forbidden(moved, points)!.originOk).toBe(true);
    expect(forbidden(NO_MOVE, [])).toBeNull();
  });
});
