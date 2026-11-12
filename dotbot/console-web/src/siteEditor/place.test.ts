import { describe, expect, it } from "vitest";

import { fromMarks, moveBy, propose, spunRobots } from "./place";

describe("placing a spin in the room", () => {
  it("puts the first robot on its mark and the second on the line to its own", () => {
    const { move, spinMm, tapeMm } = fromMarks([100, 100], [600, 400], [400, 100], [600, 700]);
    expect(move.theta_deg).toBeCloseTo(90);
    const a = moveBy(move, [100, 100]);
    const b = moveBy(move, [400, 100]);
    expect(a[0]).toBeCloseTo(600);
    expect(a[1]).toBeCloseTo(400);
    expect(b[0]).toBeCloseTo(600);
    expect(b[1]).toBeCloseTo(700);
    expect(spinMm).toBeCloseTo(300);
    expect(tapeMm).toBeCloseTo(300);
  });

  it("averages a robot seen by both stations once", () => {
    const robots = spunRobots([
      { circles: [{ name: "A1", x: 100, y: 100 }, { name: "B2", x: 500, y: 100 }] },
      { circles: [{ name: "A1", x: 102, y: 98 }] },
    ]);
    expect(robots.map((r) => r.name)).toEqual(["A1", "B2"]);
    expect(robots[0].at).toEqual([101, 99]);
  });

  it("proposes the field round the robots and names one placed below zero", () => {
    const robots = [
      { name: "A1", at: [100, 100] as [number, number] },
      { name: "B2", at: [900, 700] as [number, number] },
    ];
    const p = propose(robots, { theta_deg: 0, dx: 500, dy: 500 }, null);
    expect(p.field).toEqual([510, 510, 990 - 510 + 500, 1290 - 510]);
    expect(p.extent).toEqual([1490 + 500, 1290 + 500]);
    expect(p.below).toEqual([]);
    expect(propose(robots, { theta_deg: 0, dx: -200, dy: 0 }, null).below).toEqual(["A1"]);
    expect(propose(robots, { theta_deg: 0, dx: 0, dy: 0 }, [800, 800]).outside).toEqual(["B2"]);
  });
});
