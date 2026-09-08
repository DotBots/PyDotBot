import { describe, expect, it } from "vitest";

import {
  arrive,
  BOT_FOOTPRINT_MM,
  FakeWorld,
  headingOf,
  MAX_WHEEL_SPEED,
  seek,
  separation,
  unicycleStep,
  wheelSpeedFromPwm,
  wrapDeg,
} from "./fakeWorld";

describe("wheelSpeedFromPwm", () => {
  it("matches the simulator's conversion and saturates at full throttle", () => {
    // pwm * D * Kv / (R * 127), with D=44, Kv=700, R=50.
    expect(wheelSpeedFromPwm(100)).toBeCloseTo((100 * 44 * 700) / (50 * 127), 6);
    expect(wheelSpeedFromPwm(200)).toBe(MAX_WHEEL_SPEED);
    expect(wheelSpeedFromPwm(-200)).toBe(-MAX_WHEEL_SPEED);
  });
});

describe("unicycleStep", () => {
  it("drives along +y at heading 0", () => {
    const p = unicycleStep({ x: 100, y: 100, heading: 0 }, 200, 200, 0.5);
    expect(p.x).toBeCloseTo(100, 6);
    expect(p.y).toBeCloseTo(200, 6);
    expect(p.heading).toBeCloseTo(0, 6);
  });

  it("drives along -x at heading 90, the arena frame's quarter turn", () => {
    const p = unicycleStep({ x: 100, y: 100, heading: 90 }, 200, 200, 0.5);
    expect(p.x).toBeCloseTo(0, 6);
    expect(p.y).toBeCloseTo(100, 6);
  });

  // The sign that inverts silently: the left wheel leading must turn the bot
  // clockwise, the same way the console's drive pad reads.
  it("turns clockwise when the left wheel leads", () => {
    const p = unicycleStep({ x: 0, y: 0, heading: 0 }, 100, 0, 1);
    expect(p.heading).toBeGreaterThan(0);
  });

  it("turns counter-clockwise when the right wheel leads", () => {
    const p = unicycleStep({ x: 0, y: 0, heading: 0 }, 0, 100, 1);
    expect(p.heading).toBeLessThan(0);
  });

  it("spins in place with opposite wheels", () => {
    const p = unicycleStep({ x: 50, y: 50, heading: 0 }, 100, -100, 0.2);
    expect(p.x).toBeCloseTo(50, 6);
    expect(p.y).toBeCloseTo(50, 6);
    expect(p.heading).not.toBeCloseTo(0, 3);
  });

  it("keeps heading inside (-180, 180]", () => {
    const p = unicycleStep({ x: 0, y: 0, heading: 170 }, 400, -400, 1);
    expect(p.heading).toBeGreaterThan(-180);
    expect(p.heading).toBeLessThanOrEqual(180);
  });
});

describe("headingOf and wrapDeg", () => {
  it("inverts the forward vector", () => {
    expect(headingOf({ x: 0, y: 1 })).toBeCloseTo(0, 6);
    expect(headingOf({ x: -1, y: 0 })).toBeCloseTo(90, 6);
    expect(headingOf({ x: 0, y: -1 })).toBeCloseTo(180, 6);
    expect(headingOf({ x: 1, y: 0 })).toBeCloseTo(-90, 6);
  });

  it("folds turns into a half circle either way", () => {
    expect(wrapDeg(190)).toBeCloseTo(-170, 6);
    expect(wrapDeg(-190)).toBeCloseTo(170, 6);
    expect(wrapDeg(720)).toBeCloseTo(0, 6);
  });
});

describe("seek and arrive", () => {
  it("seeks at full speed regardless of distance", () => {
    const near = seek({ x: 0, y: 0 }, { x: 10, y: 0 }, 300);
    const far = seek({ x: 0, y: 0 }, { x: 4000, y: 0 }, 300);
    expect(Math.hypot(near.x, near.y)).toBeCloseTo(300, 6);
    expect(Math.hypot(far.x, far.y)).toBeCloseTo(300, 6);
    expect(near.x).toBeGreaterThan(0);
  });

  it("arrives eased: full speed outside the slow radius, tapering inside it", () => {
    const outside = arrive({ x: 0, y: 0 }, { x: 1000, y: 0 }, 300, 200);
    const inside = arrive({ x: 0, y: 0 }, { x: 100, y: 0 }, 300, 200);
    expect(Math.hypot(outside.x, outside.y)).toBeCloseTo(300, 6);
    expect(Math.hypot(inside.x, inside.y)).toBeCloseTo(150, 6);
  });

  it("asks for nothing when it is already there", () => {
    expect(seek({ x: 5, y: 5 }, { x: 5, y: 5 }, 300)).toEqual({ x: 0, y: 0 });
    expect(arrive({ x: 5, y: 5 }, { x: 5, y: 5 }, 300, 200)).toEqual({ x: 0, y: 0 });
  });
});

describe("separation", () => {
  it("pushes away from a single close neighbour", () => {
    const v = separation({ x: 100, y: 0 }, [{ x: 0, y: 0 }], 200, 300);
    expect(v.x).toBeCloseTo(300, 6);
    expect(v.y).toBeCloseTo(0, 6);
  });

  it("ignores neighbours beyond the radius", () => {
    expect(separation({ x: 0, y: 0 }, [{ x: 500, y: 0 }], 200, 300)).toEqual({ x: 0, y: 0 });
  });

  it("cancels between two neighbours placed symmetrically", () => {
    const v = separation({ x: 0, y: 0 }, [
      { x: 100, y: 0 },
      { x: -100, y: 0 },
    ], 200, 300);
    expect(Math.hypot(v.x, v.y)).toBeCloseTo(0, 6);
  });
});

describe("FakeWorld", () => {
  it("seeds every bot inside the arena", () => {
    const w = new FakeWorld({ count: 200, placement: "random", seed: 7 });
    for (let i = 0; i < w.count; i++) {
      expect(w.x[i]).toBeGreaterThanOrEqual(0);
      expect(w.x[i]).toBeLessThanOrEqual(w.side);
      expect(w.y[i]).toBeGreaterThanOrEqual(0);
      expect(w.y[i]).toBeLessThanOrEqual(w.side);
    }
  });

  // A crowd that is handed no goal must open out, and stop once it has: this
  // is what keeps the follow blob a blob rather than one pile of glyphs.
  it("settles a crowd at least a footprint apart", () => {
    const w = new FakeWorld({ count: 40, placement: "random", seed: 3 });
    w.setTuning({ speedPct: 60, spread: 2, wanderWhenIdle: false });
    w.setTarget(null);
    const mid = w.side / 2;
    for (let i = 0; i < w.count; i++) {
      w.x[i] = mid - 400 + ((i * 137) % 800);
      w.y[i] = mid - 400 + ((i * 251) % 800);
    }
    for (let s = 0; s < 3000; s++) w.step(0.02);

    let closest = Infinity;
    for (let i = 0; i < w.count; i++) {
      for (let j = i + 1; j < w.count; j++) {
        closest = Math.min(closest, Math.hypot(w.x[i] - w.x[j], w.y[i] - w.y[j]));
      }
    }
    expect(closest).toBeGreaterThanOrEqual(BOT_FOOTPRINT_MM);
  });

  it("brings a lone bot to the target it is given", () => {
    const w = new FakeWorld({ count: 1, placement: "grid", seed: 1 });
    w.setTuning({ speedPct: 80, spread: 2, wanderWhenIdle: false });
    w.x[0] = 400;
    w.y[0] = 400;
    w.heading[0] = 180;
    const target = { x: 1400, y: 1200 };
    w.setTarget(target);
    for (let s = 0; s < 1500; s++) w.step(0.02);
    expect(Math.hypot(w.x[0] - target.x, w.y[0] - target.y)).toBeLessThan(BOT_FOOTPRINT_MM);
  });

  it("reports itself idle once nothing is driving", () => {
    const w = new FakeWorld({ count: 4, placement: "grid", seed: 5 });
    w.setTuning({ speedPct: 60, spread: 2, wanderWhenIdle: false });
    w.setTarget(null);
    for (let s = 0; s < 400; s++) w.step(0.02);
    expect(w.moving).toBe(false);
  });

  it("drives to an assigned target and stops inside the arrival radius", () => {
    const w = new FakeWorld({ count: 1, placement: "grid", seed: 1 });
    w.setTuning({ speedPct: 80, spread: 2, wanderWhenIdle: true });
    w.x[0] = 300;
    w.y[0] = 300;
    w.targets[0] = 1500;
    w.targets[1] = 1200;
    w.hasTarget[0] = 1;
    w.arriveMm = 60;
    for (let s = 0; s < 1500; s++) w.step(0.02);
    expect(Math.hypot(w.x[0] - 1500, w.y[0] - 1200)).toBeLessThanOrEqual(60);
  });

  it("keeps a held bot where it is, whatever else is pulling at it", () => {
    const w = new FakeWorld({ count: 1, placement: "grid", seed: 1 });
    w.setTarget({ x: 1900, y: 1900 });
    w.held[0] = 1;
    const at = { x: w.x[0], y: w.y[0] };
    for (let s = 0; s < 200; s++) w.step(0.02);
    expect(w.x[0]).toBeCloseTo(at.x, 6);
    expect(w.y[0]).toBeCloseTo(at.y, 6);
  });

  it("drains the battery with the distance driven, and not while parked", () => {
    const w = new FakeWorld({ count: 1, placement: "grid", seed: 1 });
    w.setTuning({ speedPct: 100, spread: 2, wanderWhenIdle: false });
    w.setTarget({ x: w.side - 200, y: w.side - 200 });
    const full = w.battery[0];
    for (let s = 0; s < 300; s++) w.step(0.02);
    const driven = w.battery[0];
    expect(driven).toBeLessThan(full);

    w.setTarget(null);
    w.held[0] = 1;
    for (let s = 0; s < 300; s++) w.step(0.02);
    expect(w.battery[0]).toBe(driven);
  });

  it("drains faster when the showcase asks it to", () => {
    const drop = (drainScale: number) => {
      const w = new FakeWorld({ count: 1, placement: "grid", seed: 1 });
      w.setTuning({ speedPct: 100, spread: 2, wanderWhenIdle: false, drainScale });
      w.setTarget({ x: w.side - 200, y: w.side - 200 });
      const full = w.battery[0];
      for (let s = 0; s < 300; s++) w.step(0.02);
      return full - w.battery[0];
    };
    expect(drop(10)).toBeCloseTo(drop(1) * 10, 6);
  });

  it("packs a snapshot as x, y, heading per bot", () => {
    const w = new FakeWorld({ count: 3, placement: "grid", seed: 2 });
    const snap = w.snapshot();
    expect(snap.length).toBe(9);
    expect(snap[0]).toBeCloseTo(w.x[0], 2);
    expect(snap[4]).toBeCloseTo(w.y[1], 2);
    expect(snap[8]).toBeCloseTo(w.heading[2], 2);
  });

  it("grows the arena with the bot count and never shrinks below the default room", () => {
    expect(new FakeWorld({ count: 10, placement: "grid", seed: 1 }).side).toBe(2000);
    expect(new FakeWorld({ count: 1000, placement: "grid", seed: 1 }).side).toBeGreaterThan(2000);
  });
});
