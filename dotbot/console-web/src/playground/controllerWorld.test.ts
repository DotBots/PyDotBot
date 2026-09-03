import { describe, expect, it } from "vitest";

import { fleetToPoses, foldMotion, hueOf, sampleMotion } from "./controllerWorld";
import type { UnifiedBot } from "../types";

function bot(over: Partial<UnifiedBot>): UnifiedBot {
  return {
    id: "AA",
    state: null,
    link: "active",
    position: { x: 100, y: 200 },
    heading: 45,
    battery: 3.3,
    led: null,
    deviceType: "DotBot",
    application: 0,
    drivable: true,
    nav: "drive",
    waypoints: [],
    trail: [],
    image: null,
    resetCause: null,
    severity: "normal",
    batteryPct: null,
    batteryLevel: null,
    swarmit: null,
    ...over,
  };
}

describe("hueOf", () => {
  it("reads the hue off a lit LED", () => {
    expect(hueOf({ red: 255, green: 0, blue: 0 }, "AA")).toBe(0);
    expect(hueOf({ red: 0, green: 255, blue: 0 }, "AA")).toBeCloseTo(120);
    expect(hueOf({ red: 0, green: 0, blue: 255 }, "AA")).toBeCloseTo(240);
  });

  it("gives an unlit bot a colour of its own, stably", () => {
    const first = hueOf(null, "BADCAFE111111111");
    expect(first).toBe(hueOf(null, "BADCAFE111111111"));
    expect(first).not.toBe(hueOf(null, "DEADBEEF22222222"));
    expect(first).toBeGreaterThanOrEqual(0);
    expect(first).toBeLessThan(360);
  });

  it("treats a grey LED as unlit rather than as a hue", () => {
    expect(hueOf({ red: 120, green: 120, blue: 120 }, "AA")).toBe(hueOf(null, "AA"));
  });
});

describe("fleetToPoses", () => {
  it("lays the fleet out as x, y, heading triples", () => {
    const { poses, hues, addresses, applications } = fleetToPoses([
      bot({ id: "AA", position: { x: 100, y: 200 }, heading: 45 }),
      bot({ id: "BB", position: { x: 300, y: 400 }, heading: -90, application: 1 }),
    ]);
    expect(Array.from(poses)).toEqual([100, 200, 45, 300, 400, -90]);
    expect(hues).toHaveLength(2);
    expect(addresses).toEqual(["AA", "BB"]);
    expect(applications).toEqual([0, 1]);
  });

  it("drops a bot the controller has never located", () => {
    const { poses, addresses } = fleetToPoses([
      bot({ id: "AA", position: null }),
      bot({ id: "BB", position: { x: 1, y: 2 } }),
    ]);
    expect(addresses).toEqual(["BB"]);
    expect(Array.from(poses)).toEqual([1, 2, 45]);
  });

  it("faces a bot with no heading yet along the arena's zero", () => {
    const { poses } = fleetToPoses([bot({ heading: null })]);
    expect(poses[2]).toBe(0);
  });
});

describe("foldMotion and sampleMotion", () => {
  const DIAG = 2828;
  const fleet = (x: number, heading: number) => [bot({ id: "AA", position: { x, y: 0 }, heading })];

  it("places a first fix instantly", () => {
    const m = foldMotion(new Map(), fleet(100, 45), 0, DIAG);
    expect(sampleMotion(m.get("AA")!, 0)).toEqual({ x: 100, y: 0, heading: 45, live: false });
  });

  it("glides from the last drawn spot to the next fix over the update interval", () => {
    let m = foldMotion(new Map(), fleet(0, 0), 0, DIAG);
    m = foldMotion(m, fleet(100, 0), 100, DIAG);
    expect(sampleMotion(m.get("AA")!, 150)).toMatchObject({ x: 50, live: true });
    expect(sampleMotion(m.get("AA")!, 200)).toMatchObject({ x: 100, live: false });
  });

  it("turns through the short arc between headings", () => {
    let m = foldMotion(new Map(), fleet(0, 350), 0, DIAG);
    m = foldMotion(m, fleet(100, 10), 100, DIAG);
    const mid = sampleMotion(m.get("AA")!, 150).heading;
    expect(((mid % 360) + 360) % 360).toBeCloseTo(0);
  });

  it("drops a bot that lost its position", () => {
    const m = foldMotion(
      foldMotion(new Map(), fleet(0, 0), 0, DIAG),
      [bot({ id: "AA", position: null })],
      100,
      DIAG,
    );
    expect(m.size).toBe(0);
  });
});
