import { describe, expect, it } from "vitest";

import {
  FALLBACK_BODY_RADIUS_MM,
  assign,
  bodyRadiusMm,
  describeHazards,
  hazardsOf,
  hungarian,
  legsOf,
  orderFits,
  segmentsCross,
  spacingMm,
  swap,
} from "./spread";
import type { BotPose, UnifiedBot } from "./types";

const bot = (id: string, x: number | null, y = 0, extra: Partial<UnifiedBot> = {}) =>
  ({ id, position: x === null ? null : { x, y }, axle: null, pose: null, ...extra }) as UnifiedBot;

// Brute force over every permutation, for small cases.
function bestCost(cost: number[][]): number {
  const n = cost.length;
  const m = cost[0].length;
  let best = Infinity;
  const walk = (i: number, used: Set<number>, acc: number) => {
    if (i === n) return void (best = Math.min(best, acc));
    for (let j = 0; j < m; j++) if (!used.has(j)) walk(i + 1, new Set([...used, j]), acc + cost[i][j]);
  };
  walk(0, new Set(), 0);
  return best;
}

describe("hungarian", () => {
  it("finds the cheapest square assignment", () => {
    const cost = [
      [4, 1, 3],
      [2, 0, 5],
      [3, 2, 2],
    ];
    const col = hungarian(cost);
    expect(new Set(col).size).toBe(3);
    expect(col.reduce((a, j, i) => a + cost[i][j], 0)).toBe(5);
  });

  it("matches brute force on random rectangular cases", () => {
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 100;
    for (let k = 0; k < 40; k++) {
      const n = 1 + (k % 5);
      const m = n + (k % 3);
      const cost = Array.from({ length: n }, () => Array.from({ length: m }, rnd));
      const col = hungarian(cost);
      expect(new Set(col).size).toBe(n);
      expect(col.reduce((a, j, i) => a + cost[i][j], 0)).toBeCloseTo(bestCost(cost), 6);
    }
  });

  it("refuses more rows than columns", () => {
    expect(() => hungarian([[1], [2]])).toThrow();
  });
});

describe("assign", () => {
  it("gives each target the robot that makes the total shortest, not the nearest first", () => {
    // Nearest first would give B the target at 2 (1 mm) and send A 6 mm to
    // the other; the shortest total sends A 2 mm and B 3 mm.
    const bots = [bot("A", 0), bot("B", 3)];
    expect(assign(bots, [{ x: 2, y: 0 }, { x: 6, y: 0 }])).toEqual(["A", "B"]);
    expect(assign(bots, [{ x: 6, y: 0 }, { x: 2, y: 0 }])).toEqual(["B", "A"]);
  });

  it("measures from the axle when the robot reports one", () => {
    const bots = [bot("A", 0, 0, { axle: { x: 100, y: 0 } }), bot("B", 50)];
    expect(assign(bots, [{ x: 100, y: 0 }, { x: 50, y: 0 }])).toEqual(["A", "B"]);
  });

  it("assigns the targets placed so far, and nothing past the robots", () => {
    expect(assign([bot("A", 0), bot("B", 100)], [{ x: 90, y: 0 }])).toEqual(["B"]);
    expect(assign([bot("A", 0)], [{ x: 0, y: 0 }, { x: 1, y: 0 }])).toEqual([]);
  });
});

describe("swap and orderFits", () => {
  it("trades targets between two robots", () => {
    expect(swap(["A", "B", "C"], 0, "C")).toEqual(["C", "B", "A"]);
  });

  it("hands a target to a robot that had none", () => {
    expect(swap(["A", "B"], 1, "C")).toEqual(["A", "C"]);
  });

  it("drops an order that no longer matches the targets or the robots", () => {
    expect(orderFits(["A", "B"], ["A", "B"], 2)).toBe(true);
    expect(orderFits(["A", "B"], ["A", "B"], 3)).toBe(false);
    expect(orderFits(["A", "C"], ["A", "B"], 2)).toBe(false);
    expect(orderFits(["A", "A"], ["A", "B"], 2)).toBe(false);
    expect(orderFits(null, ["A"], 1)).toBe(false);
  });
});

describe("segmentsCross", () => {
  const p = (x: number, y: number) => ({ x, y });
  it("sees an X", () => expect(segmentsCross(p(0, 0), p(10, 10), p(0, 10), p(10, 0))).toBe(true));
  it("passes parallel paths", () => expect(segmentsCross(p(0, 0), p(10, 0), p(0, 5), p(10, 5))).toBe(false));
  it("passes paths that would only meet if extended", () =>
    expect(segmentsCross(p(0, 0), p(4, 4), p(10, 0), p(6, 4))).toBe(false));
  it("counts a shared endpoint and a collinear overlap", () => {
    expect(segmentsCross(p(0, 0), p(10, 0), p(10, 0), p(10, 10))).toBe(true);
    expect(segmentsCross(p(0, 0), p(10, 0), p(5, 0), p(20, 0))).toBe(true);
    expect(segmentsCross(p(0, 0), p(4, 0), p(5, 0), p(20, 0))).toBe(false);
  });
});

describe("spacing", () => {
  const pose = {
    axle: { x: 0, y: 0 },
    outline: [
      { x: -30, y: -40 },
      { x: 30, y: 40 },
    ],
    wheels: [[{ x: 60, y: 0 }]],
  } as unknown as BotPose;

  it("is twice the farthest body point from the axle", () => {
    expect(bodyRadiusMm(pose)).toBe(60);
    expect(spacingMm([bot("A", 0, 0, { pose }), bot("B", 0)])).toBe(120);
  });

  it("falls back to the v3 body without a pose", () => {
    expect(spacingMm([bot("A", 0)])).toBe(2 * FALLBACK_BODY_RADIUS_MM);
  });
});

describe("hazardsOf", () => {
  const extent = { x: 0, y: 0, w: 1000, h: 1000, name: "site" };

  it("flags crossing paths, crowded targets and targets off the site", () => {
    const bots = [bot("AAAA", 0, 0), bot("BBBB", 0, 500), bot("CCCC", null)];
    const targets = [
      { x: 500, y: 500 },
      { x: 500, y: 0 },
      { x: 1200, y: 50 },
    ];
    const legs = legsOf(bots, targets, ["AAAA", "BBBB", "CCCC"]);
    const h = hazardsOf(legs, 200, extent);
    expect(h).toEqual({ crossings: [[0, 1]], tooClose: [], outside: [2], unplaced: ["CCCC"] });
    expect(describeHazards(h, legs, 200)).toEqual([
      "AAAA and BBBB: paths cross",
      "target 3: outside the site",
      "CCCC: no position, path unknown",
    ]);
  });

  it("flags targets closer than the spacing, and finds nothing in a clean spread", () => {
    const bots = [bot("A", 0, 0), bot("B", 0, 500)];
    const close = legsOf(bots, [{ x: 400, y: 0 }, { x: 400, y: 100 }], ["A", "B"]);
    expect(hazardsOf(close, 167, extent).tooClose).toEqual([[0, 1]]);
    const clean = legsOf(bots, [{ x: 400, y: 0 }, { x: 400, y: 500 }], ["A", "B"]);
    expect(hazardsOf(clean, 167, extent)).toEqual({ crossings: [], tooClose: [], outside: [], unplaced: [] });
  });
});
