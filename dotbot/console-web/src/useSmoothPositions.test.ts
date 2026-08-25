import { describe, expect, it } from "vitest";

import {
  MAX_DURATION_MS,
  MIN_DURATION_MS,
  lerpPos,
  nextPosState,
  positionAt,
} from "./useSmoothPositions";

const MAP_DIAGONAL = Math.hypot(2000, 2000);

describe("lerpPos", () => {
  it("interpolates linearly between two points", () => {
    expect(lerpPos({ x: 0, y: 0 }, { x: 100, y: 200 }, 0.5)).toEqual({ x: 50, y: 100 });
  });
});

describe("nextPosState", () => {
  it("snaps instantly on first sight of a bot (no prior state)", () => {
    const s = nextPosState(undefined, { x: 10, y: 20 }, 1000, MAP_DIAGONAL);
    expect(s.duration).toBe(0);
    expect(positionAt(s, 1000)).toEqual({ x: 10, y: 20 });
  });

  it("keeps the previous state when the target has not changed", () => {
    const s0 = nextPosState(undefined, { x: 10, y: 20 }, 1000, MAP_DIAGONAL);
    const s1 = nextPosState(s0, { x: 10, y: 20 }, 1200, MAP_DIAGONAL);
    expect(s1).toBe(s0);
  });

  it("animates from the in-flight interpolated position, not the last target", () => {
    // t=0 -> (0,0); update at t=0 sets target (100,0), duration 200ms.
    const s0 = nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL);
    const s1 = { ...nextPosState(s0, { x: 100, y: 0 }, 0, MAP_DIAGONAL), duration: 200 };
    // halfway through that transition (t=100ms), a new update arrives.
    const s2 = nextPosState(s1, { x: 100, y: 50 }, 100, MAP_DIAGONAL);
    expect(s2.from).toEqual({ x: 50, y: 0 }); // interpolated, not (100, 0)
    expect(s2.to).toEqual({ x: 100, y: 50 });
  });

  it("uses the observed update interval as the next animation duration, clamped", () => {
    const s0 = nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL);
    const s1 = nextPosState(s0, { x: 10, y: 0 }, 30, MAP_DIAGONAL); // 30ms gap -> clamped up
    expect(s1.duration).toBe(MIN_DURATION_MS);
    const s2 = nextPosState(s1, { x: 20, y: 0 }, 30 + 5000, MAP_DIAGONAL); // 5s gap -> clamped down
    expect(s2.duration).toBe(MAX_DURATION_MS);
    const s3 = nextPosState(s2, { x: 30, y: 0 }, 30 + 5000 + 250, MAP_DIAGONAL); // 250ms gap -> as-is
    expect(s3.duration).toBe(250);
  });

  it("treats a large jump as a teleport: instant, no animation", () => {
    const s0 = nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL);
    const s1 = nextPosState(s0, { x: 1900, y: 1900 }, 100, MAP_DIAGONAL);
    expect(s1.duration).toBe(0);
    expect(positionAt(s1, 100)).toEqual({ x: 1900, y: 1900 });
  });
});

describe("positionAt", () => {
  it("clamps at the target once the duration has elapsed", () => {
    const s = nextPosState(nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL), { x: 100, y: 0 }, 0, MAP_DIAGONAL);
    const withDuration = { ...s, duration: 200 };
    expect(positionAt(withDuration, 500)).toEqual({ x: 100, y: 0 });
  });
});
