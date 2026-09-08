import { describe, expect, it } from "vitest";

import { assignTargets, gather, toPoints } from "./assign";

function totalCost(sources: Float64Array, targets: Float64Array, assign: Int32Array): number {
  let sum = 0;
  for (let i = 0; i < assign.length; i++) {
    const dx = targets[assign[i] * 2] - sources[i * 2];
    const dy = targets[assign[i] * 2 + 1] - sources[i * 2 + 1];
    sum += Math.hypot(dx, dy);
  }
  return sum;
}

describe("assignTargets", () => {
  it("gives every bot a target of its own", () => {
    const bots = toPoints([
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 200, y: 0 },
    ]);
    const slots = toPoints([
      { x: 0, y: 500 },
      { x: 100, y: 500 },
      { x: 200, y: 500 },
      { x: 300, y: 500 },
    ]);
    const assign = assignTargets(bots, slots);
    expect(assign).toHaveLength(3);
    expect(new Set(assign).size).toBe(3);
  });

  it("takes the obvious pairing when there is one", () => {
    const bots = toPoints([
      { x: 0, y: 0 },
      { x: 1000, y: 0 },
    ]);
    const slots = toPoints([
      { x: 1010, y: 0 },
      { x: 10, y: 0 },
    ]);
    expect([...assignTargets(bots, slots)]).toEqual([1, 0]);
  });

  // The crossing greedy leaves behind: the bot served first takes the target
  // the second one was sitting on.
  it("uncrosses a pair the greedy pass got wrong", () => {
    const bots = toPoints([
      { x: 0, y: 0 },
      { x: 90, y: 0 },
    ]);
    const slots = toPoints([
      { x: 100, y: 0 },
      { x: -1000, y: 0 },
    ]);
    const assign = assignTargets(bots, slots);
    expect([...assign]).toEqual([1, 0]);
    expect(totalCost(bots, slots, assign)).toBeLessThan(
      totalCost(bots, slots, Int32Array.from([0, 1])),
    );
  });

  it("refuses a set that cannot cover the fleet", () => {
    expect(() => assignTargets(toPoints([{ x: 0, y: 0 }]), new Float64Array(0))).toThrow();
  });

  it("returns the points themselves in bot order", () => {
    const slots = toPoints([
      { x: 5, y: 6 },
      { x: 7, y: 8 },
    ]);
    expect([...gather(slots, Int32Array.from([1, 0]))]).toEqual([7, 8, 5, 6]);
  });

  // The fake world reassigns whenever the map changes, and the worker still
  // has to step the physics afterwards.
  it("assigns a thousand bots to a thousand points well inside a second", () => {
    const n = 1000;
    const bots = new Float64Array(n * 2);
    const slots = new Float64Array(n * 2);
    for (let i = 0; i < n; i++) {
      bots[i * 2] = (i * 977) % 6000;
      bots[i * 2 + 1] = (i * 613) % 6000;
      slots[i * 2] = (i % 40) * 150 + 100;
      slots[i * 2 + 1] = Math.floor(i / 40) * 150 + 100;
    }
    const started = performance.now();
    const assign = assignTargets(bots, slots);
    const elapsed = performance.now() - started;
    expect(new Set(assign).size).toBe(n);
    expect(elapsed).toBeLessThan(700);
  });
});
