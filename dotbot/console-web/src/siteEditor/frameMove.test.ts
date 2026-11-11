import { describe, expect, it } from "vitest";

import { anchorErrors, forbidden, frameTwin, NO_MOVE, originDragged, originOnPlan, toNew, toOld, plainWarning, turnDragged, turnedAbout, turnedBy, withOrigin, zeroAt } from "./frameMove";

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
    // a timer that drifts a few ms per sample still opens it
    const drifting = [0, 504, 1009, 1513, 2018].map((t) => ({ t, p: [100, 200] as [number, number] }));
    expect(stillness(drifting, 2018).still).toBe(true);
    expect(stillness(drifting.map((x) => ({ ...x, t: x.t + 3 })), 2025).still).toBe(true);
  });
});

describe("the origin from robots on spots", () => {
  it("measures each robot against its spot under a move", () => {
    // A known move: turn 5 degrees about (530, 610), origin shifted by (40, -20)
    const truth = { theta_deg: 5, pivot: [530, 610] as [number, number], dx: 40, dy: -20, note: null };
    const spots: [number, number][] = [
      [300, 400],
      [900, 700],
    ];
    const anchors = spots.map((spot, i) => ({ robot: String(i), fix: toOld(truth, spot), spot }));
    for (const e of anchorErrors(truth, anchors)) expect(e).toBeLessThan(1e-6);
    expect(anchorErrors(NO_MOVE, anchors)[0]).toBeGreaterThan(10);
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

describe("turning a move about a point", () => {
  it("swings every point of the new frame about that point", () => {
    const m = { theta_deg: 3, pivot: [400, 300] as [number, number], dx: 50, dy: -20, note: null };
    const c: [number, number] = [700, 500];
    const t = turnedAbout(m, c, 10);
    expect(t.theta_deg).toBe(13);
    for (const p of [[0, 0], [1000, 0], [250, 800]] as [number, number][]) {
      const a = toOld(m, p);
      const r = (10 * Math.PI) / 180;
      const want = [c[0] + Math.cos(r) * (a[0] - c[0]) - Math.sin(r) * (a[1] - c[1]), c[1] + Math.sin(r) * (a[0] - c[0]) + Math.cos(r) * (a[1] - c[1])];
      const got = toOld(t, p);
      expect(got[0]).toBeCloseTo(want[0], 0);
      expect(got[1]).toBeCloseTo(want[1], 0);
    }
  });
});

describe("a move's warnings", () => {
  it("drop ids and say floor", () => {
    expect(plainWarning("340088da: 2 spin circle(s) (222A34F9458E8AAD, 901B4217EE67C999) land outside the site's extent, where robots drop their positions")).toBe(
      "2 measured spots land outside the extent, where robots drop their positions",
    );
  });
});

describe("the origin dragged on the plan", () => {
  it("shifts it by the drag, snapped to 10 mm, or to 1 mm free", () => {
    const m = originDragged(NO_MOVE, null, [100, 100], [223, 54], 10);
    expect([m.dx, m.dy]).toEqual([120, -50]);
    expect(toOld(m, [0, 0])).toEqual([120, -50]);
    const free = originDragged(NO_MOVE, null, [100, 100], [223, 54], 1);
    expect([free.dx, free.dy]).toEqual([123, -46]);
  });

  it("keeps the turn, and reads the drag in the frame the plan is drawn in", () => {
    const drawn = { theta_deg: 90, pivot: [0, 0] as [number, number], dx: 0, dy: 0, note: null };
    // On a plan turned a quarter, a drag along its x goes along the saved y
    const m = originDragged(drawn, drawn, [0, 0], [100, 0], 10);
    expect(m.theta_deg).toBe(90);
    const o = toOld(m, [0, 0]);
    expect(o[0]).toBeCloseTo(0, 6);
    expect(o[1]).toBeCloseTo(100, 6);
    expect(originOnPlan(m, drawn).at[0]).toBeCloseTo(100, 6);
    expect(originOnPlan(m, drawn).deg).toBe(0);
  });
});

describe("the turn handle dragged on the plan", () => {
  const sweep = (deg: number): [number, number] => [300 * Math.cos((deg * Math.PI) / 180), 300 * Math.sin((deg * Math.PI) / 180)];

  it("turns the frame about the origin in 0.5 degree steps, the origin kept", () => {
    const base = { ...NO_MOVE, dx: 40, dy: 20, pivot: [40, 20] as [number, number] };
    const m = turnDragged(base, null, [340, 20], [40 + sweep(12.3)[0], 20 + sweep(12.3)[1]], 0.5);
    expect(m.theta_deg).toBe(12.5);
    const o = toOld(m, [0, 0]);
    expect(o[0]).toBeCloseTo(40, 6);
    expect(o[1]).toBeCloseTo(20, 6);
  });

  it("takes 15 degree steps with Shift, and stays within a half turn either way", () => {
    expect(turnDragged(NO_MOVE, null, [300, 0], sweep(37), 15).theta_deg).toBe(30);
    expect(turnDragged({ ...NO_MOVE, theta_deg: 170 }, null, [300, 0], sweep(30), 15).theta_deg).toBe(-165);
  });
});

describe("a quarter turn by button", () => {
  it("adds or takes 90 degrees to the typed turn", () => {
    expect(turnedBy({ ...NO_MOVE, theta_deg: 2 }, 90).theta_deg).toBe(92);
    expect(turnedBy({ ...NO_MOVE, theta_deg: -100 }, -90).theta_deg).toBe(170);
    expect(turnedBy({ ...NO_MOVE, theta_deg: 90 }, 90).theta_deg).toBe(180);
  });
});
