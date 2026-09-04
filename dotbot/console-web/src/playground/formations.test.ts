import { describe, expect, it } from "vitest";

import { toPoints } from "./assign";
import {
  figureOverlay,
  fillPoints,
  formation,
  hueByAngle,
  regionSlots,
  ringPoints,
  ringTargets,
  shareByArea,
  spareRing,
  splitByProximity,
} from "./formations";

const SIDE = 4000;
/** What `formation` reaches out to on a 4 m arena: half the side, less 200. */
const REACH = SIDE / 2 - 200;

function radii(points: Float64Array, cx = SIDE / 2, cy = SIDE / 2): number[] {
  const out: number[] = [];
  for (let i = 0; i < points.length; i += 2) {
    out.push(Math.hypot(points[i] - cx, points[i + 1] - cy));
  }
  return out;
}

describe("ringPoints", () => {
  it("spaces the count evenly on the circle", () => {
    const points = ringPoints(0, 0, 4, 100);
    expect(points.length).toBe(8);
    expect(radii(points, 0, 0).every((r) => Math.abs(r - 100) < 1e-9)).toBe(true);
    expect(points[0]).toBeCloseTo(100, 9);
    expect(points[1]).toBeCloseTo(0, 9);
  });

  it("starts at the phase it is given", () => {
    const points = ringPoints(0, 0, 4, 100, Math.PI / 2);
    expect(points[0]).toBeCloseTo(0, 9);
    expect(points[1]).toBeCloseTo(100, 9);
  });
});

describe("the show's figures", () => {
  const count = 60;

  it("places one point per bot, whatever the figure", () => {
    for (const figure of ["ring", "double ring", "spiral", "pulse", "wave", "unknown"]) {
      expect(formation(figure, count, SIDE, SIDE, 0.4).length).toBe(count * 2);
    }
  });

  it("puts the ring on one radius", () => {
    for (const r of radii(formation("ring", count, SIDE, SIDE, 0))) {
      expect(r).toBeCloseTo(REACH, 6);
    }
  });

  it("splits the double ring between an inner and an outer radius", () => {
    const points = formation("double ring", count, SIDE, SIDE, 0);
    const r = radii(points);
    for (const inner of r.slice(0, count / 2)) expect(inner).toBeCloseTo(REACH * 0.5, 6);
    for (const outer of r.slice(count / 2)) expect(outer).toBeCloseTo(REACH, 6);
  });

  it("opens the spiral out from the centre to the reach", () => {
    const r = radii(formation("spiral", count, SIDE, SIDE, 0));
    expect(r[0]).toBeCloseTo(REACH * 0.15, 6);
    expect(r[r.length - 1]).toBeCloseTo(REACH, 6);
  });

  it("breathes the pulse between the phases of its sine", () => {
    const small = radii(formation("pulse", count, SIDE, SIDE, -Math.PI / 2))[0];
    const big = radii(formation("pulse", count, SIDE, SIDE, Math.PI / 2))[0];
    expect(small).toBeCloseTo(REACH * 0.1, 6);
    expect(big).toBeCloseTo(REACH, 6);
  });

  it("moves the wave up and down without moving it sideways", () => {
    const a = formation("wave", count, SIDE, SIDE, 0);
    const b = formation("wave", count, SIDE, SIDE, 1.2);
    expect(a[0]).toBeCloseTo(b[0], 6);
    expect(a[1]).not.toBeCloseTo(b[1], 3);
  });

  it("keeps every point inside the walls", () => {
    for (const figure of ["ring", "double ring", "spiral", "pulse", "wave"]) {
      const points = formation(figure, count, 2000, 2000, 0.7);
      for (const v of points) {
        expect(v).toBeGreaterThanOrEqual(90);
        expect(v).toBeLessThanOrEqual(2000 - 90);
      }
    }
  });

  it("draws a ring closed, a spiral open and a double ring as two paths", () => {
    const closed = figureOverlay("ring", formation("ring", count, SIDE, SIDE, 0));
    expect(closed).toHaveLength(1);
    expect(closed[0]).toMatchObject({ type: "polyline", closed: true });
    expect(figureOverlay("spiral", formation("spiral", count, SIDE, SIDE, 0))[0]).toMatchObject({
      type: "polyline",
    });
    expect(figureOverlay("double ring", formation("double ring", count, SIDE, SIDE, 0))).toHaveLength(2);
  });
});

describe("hueByAngle", () => {
  it("reads the bearing from the arena centre, in degrees", () => {
    const points = Float64Array.from([SIDE, SIDE / 2, SIDE / 2, SIDE, 0, SIDE / 2]);
    expect([...hueByAngle(points, SIDE, SIDE)]).toEqual([0, 90, 180]);
  });
});

describe("splitByProximity", () => {
  it("gives each bot the pin it is nearest to", () => {
    const bots = toPoints([
      { x: 10, y: 0 },
      { x: 990, y: 0 },
      { x: 400, y: 0 },
    ]);
    const pins = toPoints([
      { x: 0, y: 0 },
      { x: 1000, y: 0 },
    ]);
    expect([...splitByProximity(bots, pins)]).toEqual([0, 1, 0]);
  });

  it("keeps everyone on pin zero when there is only one", () => {
    const bots = toPoints([
      { x: 10, y: 0 },
      { x: 3000, y: 3000 },
    ]);
    expect([...splitByProximity(bots, toPoints([{ x: 0, y: 0 }]))]).toEqual([0, 0]);
  });
});

describe("ringTargets", () => {
  it("rings each group around its own pin at the radius asked for", () => {
    const bots = toPoints([
      { x: 500, y: 500 },
      { x: 600, y: 500 },
      { x: 3400, y: 3400 },
      { x: 3500, y: 3500 },
    ]);
    const pins = toPoints([
      { x: 700, y: 700 },
      { x: 3300, y: 3300 },
    ]);
    const targets = ringTargets(bots, pins, 300, SIDE, SIDE);
    expect(targets.length).toBe(8);
    for (const i of [0, 1]) {
      expect(Math.hypot(targets[i * 2] - 700, targets[i * 2 + 1] - 700)).toBeCloseTo(300, 6);
    }
    for (const i of [2, 3]) {
      expect(Math.hypot(targets[i * 2] - 3300, targets[i * 2 + 1] - 3300)).toBeCloseTo(300, 6);
    }
  });

  it("sends a group of one to the pin itself", () => {
    const targets = ringTargets(
      toPoints([{ x: 0, y: 0 }]),
      toPoints([{ x: 900, y: 900 }]),
      300,
      SIDE,
      SIDE,
    );
    expect([...targets]).toEqual([900, 900]);
  });
});

describe("shareByArea", () => {
  it("splits the fleet in proportion to the areas", () => {
    const counts = shareByArea(
      [
        { x: 0, y: 0, w: 2000, h: 1000 },
        { x: 0, y: 0, w: 1000, h: 1000 },
      ],
      30,
    );
    expect(counts).toEqual([20, 10]);
    expect(counts.reduce((a, b) => a + b, 0)).toBe(30);
  });

  it("gives every region a bot while there are enough to go round", () => {
    const rects = [
      { x: 0, y: 0, w: 100, h: 100 },
      { x: 0, y: 0, w: 5000, h: 5000 },
      { x: 0, y: 0, w: 200, h: 200 },
    ];
    expect(shareByArea(rects, 5).every((c) => c >= 1)).toBe(true);
  });

  it("hands the bots to the largest regions when there are too few", () => {
    const rects = [
      { x: 0, y: 0, w: 100, h: 100 },
      { x: 0, y: 0, w: 5000, h: 5000 },
      { x: 0, y: 0, w: 200, h: 200 },
    ];
    expect(shareByArea(rects, 2)).toEqual([0, 1, 1]);
  });

  it("gives nothing away when there is nothing to give", () => {
    expect(shareByArea([], 10)).toEqual([]);
    expect(shareByArea([{ x: 0, y: 0, w: 10, h: 10 }], 0)).toEqual([0]);
  });
});

describe("fillPoints and regionSlots", () => {
  it("samples a region into as many points as it was given bots", () => {
    const rect = { x: 100, y: 200, w: 1000, h: 800 };
    const points = fillPoints(rect, 12);
    expect(points.length).toBe(24);
    for (let i = 0; i < points.length; i += 2) {
      expect(points[i]).toBeGreaterThan(rect.x);
      expect(points[i]).toBeLessThan(rect.x + rect.w);
      expect(points[i + 1]).toBeGreaterThan(rect.y);
      expect(points[i + 1]).toBeLessThan(rect.y + rect.h);
    }
  });

  it("puts one point per bot over the whole set of regions", () => {
    const rects = [
      { x: 0, y: 0, w: 1000, h: 1000 },
      { x: 2000, y: 2000, w: 500, h: 500 },
    ];
    expect(regionSlots(rects, 40).length).toBe(80);
  });
});

describe("spareRing", () => {
  it("parks the leftovers on a ring inside the walls", () => {
    const points = spareRing(8, SIDE, SIDE);
    expect(points.length).toBe(16);
    for (const r of radii(points)) expect(r).toBeCloseTo(SIDE / 2 - 150, 6);
  });

  it("parks nobody when nobody is spare", () => {
    expect(spareRing(0, SIDE, SIDE).length).toBe(0);
    expect(spareRing(-3, SIDE, SIDE).length).toBe(0);
  });
});
