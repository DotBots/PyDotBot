import { describe, expect, it } from "vitest";

import { frameTwin, toNew, toOld, zeroAt } from "./frameMove";

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
