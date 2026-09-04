import { describe, expect, it } from "vitest";

import {
  AppRunner,
  DEFAULT_CHARGING,
  PAD_INSET_MM,
  PAD_RADIUS_MM,
  padPoints,
  type FakeAppSpec,
} from "./fakeApps";
import { FakeWorld, FULL_BATTERY_V } from "./fakeWorld";
import { parseOverlayItems, parseOut } from "./overlay";

function seeded(count: number): FakeWorld {
  const world = new FakeWorld({ count, placement: "grid", seed: 4 });
  world.setTuning({ speedPct: 80, spread: 2, wanderWhenIdle: false, drainScale: 1 });
  return world;
}

/** Run the world and its apps for `seconds`, on a clock the test owns. */
function run(world: FakeWorld, runner: AppRunner, seconds: number, from = 0): number {
  const dt = 0.05;
  let now = from;
  for (let s = 0; s < Math.round(seconds / dt); s++) {
    runner.step(world, dt, now);
    world.step(dt);
    now += dt * 1000;
  }
  return now;
}

function distanceTo(world: FakeWorld, bot: number, x: number, y: number): number {
  return Math.hypot(world.x[bot] - x, world.y[bot] - y);
}

describe("holding a set of targets", () => {
  it("brings the swarm onto the pins of a word", () => {
    const world = seeded(9);
    const runner = new AppRunner();
    const ink = [];
    for (let i = 0; i < 9; i++) {
      ink.push({ x: 600 + (i % 3) * 400, y: 600 + Math.floor(i / 3) * 400 });
    }
    runner.setSpec({ kind: "letters", word: "X", ink, arrive: 40 });
    run(world, runner, 60);

    for (const pin of ink) {
      let nearest = Infinity;
      for (let i = 0; i < world.count; i++) {
        nearest = Math.min(nearest, distanceTo(world, i, pin.x, pin.y));
      }
      expect(nearest).toBeLessThan(120);
    }
  });

  it("lets the swarm go again when the app is deselected", () => {
    const world = seeded(4);
    const runner = new AppRunner();
    runner.setSpec({
      kind: "goals",
      pins: [{ x: 1000, y: 1000 }],
      radius: 300,
      arrive: 40,
    });
    run(world, runner, 20);
    expect([...world.hasTarget]).toEqual([1, 1, 1, 1]);

    runner.setSpec({ kind: "none" });
    run(world, runner, 1, 20_000);
    expect([...world.hasTarget]).toEqual([0, 0, 0, 0]);
  });

  it("paints the show's LEDs by angle and gives them back afterwards", () => {
    const world = seeded(12);
    const runner = new AppRunner();
    const identity = Float32Array.from(world.hue);
    runner.setSpec({ kind: "show", figure: "ring", tempo: 100, guides: true, playing: true, arrive: 100 });
    run(world, runner, 2);
    expect([...world.hue]).not.toEqual([...identity]);

    runner.setSpec({ kind: "none" });
    run(world, runner, 1, 2000);
    expect([...world.hue]).toEqual([...identity]);
  });

  it("turns the show's figure while it plays and holds it while it is paused", () => {
    const world = seeded(12);
    const runner = new AppRunner();
    const spec = (playing: boolean): FakeAppSpec => ({
      kind: "show",
      figure: "ring",
      tempo: 100,
      playing,
      guides: true,
      arrive: 100,
    });
    runner.setSpec(spec(true));
    run(world, runner, 4);
    const turned = runner.showPhase;
    expect(turned).toBeGreaterThan(0.1);

    runner.setSpec(spec(false));
    run(world, runner, 4, 4000);
    expect(runner.showPhase).toBeCloseTo(turned, 9);
  });
});

describe("the charging cycle", () => {
  it("drains, sends a low bot to the nearest pad, and releases it full", () => {
    const world = seeded(4);
    const runner = new AppRunner();
    runner.setCharging({ threshold: 2950, dwell: 10, selected: true });
    // A pointer to chase, so the fleet is driving and the batteries fall.
    world.setTarget({ x: world.side / 2, y: world.side / 2 });

    const started = world.battery[0];
    let now = run(world, runner, 5);
    expect(world.battery[0]).toBeLessThan(started);

    world.battery[0] = 2.94;
    now = run(world, runner, 6, now);
    const pads = padPoints(world.side);
    let nearest = Infinity;
    for (let p = 0; p < 4; p++) {
      nearest = Math.min(nearest, distanceTo(world, 0, pads[p * 2], pads[p * 2 + 1]));
    }
    expect(nearest).toBeLessThanOrEqual(PAD_RADIUS_MM);
    expect(world.held[0]).toBe(1);

    run(world, runner, 8, now);
    expect(world.battery[0]).toBeGreaterThan(FULL_BATTERY_V - 0.02);
    expect(world.held[0]).toBe(0);
  });

  it("leaves a bot above the threshold where it is", () => {
    const world = seeded(4);
    const runner = new AppRunner();
    runner.setCharging({ threshold: 2000, dwell: 5, selected: true });
    run(world, runner, 10);
    expect([...world.held]).toEqual([0, 0, 0, 0]);
    expect(runner.out(world).items.filter((i) => i.type === "badge")).toHaveLength(0);
  });

  it("seats no more bots than there are pads", () => {
    const world = seeded(20);
    const runner = new AppRunner();
    runner.setCharging({ threshold: 2950, dwell: 60, selected: true });
    world.battery.fill(2.9);
    run(world, runner, 30);
    const badges = runner.out(world).items.filter((i) => i.type === "badge");
    expect(badges.length).toBeLessThanOrEqual(4);
    expect(badges.length).toBeGreaterThan(0);
  });

  it("puts a pad in each corner of the arena", () => {
    const pads = padPoints(2000);
    expect([...pads]).toEqual([
      PAD_INSET_MM,
      PAD_INSET_MM,
      2000 - PAD_INSET_MM,
      PAD_INSET_MM,
      PAD_INSET_MM,
      2000 - PAD_INSET_MM,
      2000 - PAD_INSET_MM,
      2000 - PAD_INSET_MM,
    ]);
  });
});

describe("what the apps publish", () => {
  const world = seeded(12);

  /** Every item the runner emits, through the same validation as a script's. */
  function drawable(runner: AppRunner) {
    const out = runner.out(world);
    const wire = JSON.parse(JSON.stringify({ kind: "overlay", items: out.items }));
    const parsed = parseOut(wire);
    expect(parsed).not.toBeNull();
    expect(parseOverlayItems(wire.items)).toHaveLength(out.items.length);
    return out;
  }

  it("rings each pin with the count standing on it", () => {
    const runner = new AppRunner();
    runner.setSpec({
      kind: "goals",
      pins: [
        { x: 400, y: 400 },
        { x: 1600, y: 1600 },
      ],
      radius: 320,
      arrive: 40,
    });
    const out = drawable(runner);
    expect(out.items).toHaveLength(2);
    expect(out.items[0]).toMatchObject({ type: "point", r: 320, color: "accent" });
    expect(out.status).toBe("12 bots over 2 pins");
  });

  it("draws a region with its share and the points it was sampled into", () => {
    const runner = new AppRunner();
    runner.setSpec({ kind: "region", rects: [{ x: 200, y: 200, w: 800, h: 800 }], arrive: 40 });
    const out = drawable(runner);
    expect(out.items[0]).toMatchObject({ type: "rect", label: "12 bots" });
    expect(out.items.filter((i) => i.type === "point")).toHaveLength(12);
    expect(out.status).toBe("12 bots over 1 regions");
  });

  it("says what the show is doing", () => {
    const runner = new AppRunner();
    runner.setSpec({ kind: "show", figure: "wave", tempo: 50, guides: true, playing: false, arrive: 100 });
    const out = drawable(runner);
    expect(out.status).toBe("wave, paused, 12 bots");
  });

  it("counts the bots spelling and the bots parked", () => {
    const runner = new AppRunner();
    runner.setSpec({
      kind: "letters",
      word: "DOT",
      ink: [
        { x: 100, y: 100 },
        { x: 300, y: 100 },
      ],
      arrive: 40,
    });
    const out = drawable(runner);
    expect(out.items).toHaveLength(2);
    expect(out.status).toBe("DOT: 2 bots spelling, 10 parked");
  });

  it("draws the pads and says how many bots are low", () => {
    const runner = new AppRunner();
    runner.setCharging({ ...DEFAULT_CHARGING, threshold: 3000, selected: true });
    const out = drawable(runner);
    expect(out.items.filter((i) => i.type === "point")).toHaveLength(4);
    expect(out.status).toBe("0 on pads, 12 of 12 below 3000 mV");
  });

  it("draws nothing at all for an app that only takes the pointer", () => {
    const runner = new AppRunner();
    runner.setSpec({ kind: "none" });
    expect(runner.out(world)).toEqual({ items: [], status: null });
  });

  it("asks for input before it draws anything", () => {
    const runner = new AppRunner();
    runner.setSpec({ kind: "goals", pins: [], radius: 320, arrive: 40 });
    expect(runner.out(world).status).toBe("waiting for a pin on the map");
    runner.setSpec({ kind: "region", rects: [], arrive: 40 });
    expect(runner.out(world).status).toBe("waiting for a region on the map");
  });
});
