import { describe, expect, it } from "vitest";

import { MarkerBot, sameMarkerBot } from "./BotMarker";
import type { BotPose, LH2Position } from "./types";

const shift = (p: LH2Position, dx: number): LH2Position => ({ x: p.x + dx, y: p.y });

const pose = (dx = 0, heading = 0): BotPose => ({
  heading_deg: heading,
  heading_source: "ekf",
  photodiode: shift({ x: 0, y: 0 }, dx),
  axle: shift({ x: 0, y: -20 }, dx),
  centre: shift({ x: 0, y: -10 }, dx),
  nose: shift({ x: 0, y: 30 }, dx),
  led: shift({ x: 5, y: 0 }, dx),
  outline: [{ x: -30, y: -40 }, { x: 30, y: -40 }, { x: 0, y: 40 }].map((p) => shift(p, dx)),
  wheels: [[{ x: -35, y: -25 }, { x: -30, y: -25 }].map((p) => shift(p, dx))],
  reach_mm: 50,
  core_mm: 30,
  envelope_mm: 80,
});

const bot = (extra: Partial<MarkerBot> = {}): MarkerBot => ({
  id: "a",
  state: "Running",
  severity: "normal",
  resetCause: null,
  battery: 2.9,
  batteryPct: 80,
  batteryLevel: "ok",
  led: { red: 1, green: 2, blue: 3 },
  pose: pose(),
  axle: { x: 0, y: -20 },
  ...extra,
});

describe("sameMarkerBot", () => {
  it("holds for a robot that only moved: the animator draws where", () => {
    const moved = bot({ pose: pose(333.3), axle: { x: 333.3, y: -20 }, led: { red: 1, green: 2, blue: 3 } });
    expect(sameMarkerBot(bot(), moved)).toBe(true);
  });

  it("breaks on anything the marker draws", () => {
    expect(sameMarkerBot(bot(), bot({ pose: pose(0, 90) }))).toBe(false);
    expect(sameMarkerBot(bot(), bot({ pose: null }))).toBe(false);
    expect(sameMarkerBot(bot(), bot({ state: "Stopping" }))).toBe(false);
    expect(sameMarkerBot(bot(), bot({ led: { red: 9, green: 2, blue: 3 } }))).toBe(false);
    expect(sameMarkerBot(bot(), bot({ batteryPct: 20 }))).toBe(false);
    expect(sameMarkerBot(bot(), bot({ severity: "crashed" }))).toBe(false);
    expect(sameMarkerBot(bot(), bot({ axle: { x: 4, y: -20 } }))).toBe(false);
    expect(sameMarkerBot(bot(), bot({ axle: null }))).toBe(false);
  });
});
