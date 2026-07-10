import { describe, expect, it } from "vitest";

import { PyDotBot, SwarmitNode } from "./types";
import { deriveState, merge } from "./useFleet";

const py = (over: Partial<PyDotBot> = {}): PyDotBot => ({
  address: "badcafe111111111",
  application: 0,
  status: 0,
  ...over,
});

const sw = (over: Partial<SwarmitNode> = {}): SwarmitNode => ({
  device: "DotBotV3",
  status: "Running",
  battery: 3900,
  pos_x: 100,
  pos_y: 200,
  ...over,
});

describe("deriveState", () => {
  it("control-plane INACTIVE/LOST wins over the swarmit state", () => {
    expect(deriveState(py({ status: 1 }), sw())).toBe("Inactive");
    expect(deriveState(py({ status: 2 }), sw({ status: "Programming" }))).toBe(
      "Inactive",
    );
  });

  it("passes swarmit lifecycle states through", () => {
    for (const s of [
      "Running",
      "Programming",
      "Bootloader",
      "Stopping",
      "Resetting",
    ]) {
      expect(deriveState(py(), sw({ status: s }))).toBe(s);
    }
  });

  it("maps an unknown swarmit state to Inactive", () => {
    expect(deriveState(py(), sw({ status: "Off" }))).toBe("Inactive");
  });

  it("control-plane-only active bot is Running", () => {
    expect(deriveState(py(), undefined)).toBe("Running");
  });

  it("no data at all is Inactive", () => {
    expect(deriveState(undefined, undefined)).toBe("Inactive");
  });
});

describe("merge", () => {
  it("unions both planes and sorts by id", () => {
    const bots = merge(
      { bbbb: py({ address: "bbbb" }) },
      { aaaa: sw(), bbbb: sw() },
    );
    expect(bots.map((b) => b.id)).toEqual(["aaaa", "bbbb"]);
  });

  it("prefers the controller position, falls back to swarmit", () => {
    const [a] = merge(
      { a: py({ address: "a", lh2_position: { x: 1, y: 2 } }) },
      { a: sw() },
    );
    expect(a.position).toEqual({ x: 1, y: 2 });
    const [b] = merge({}, { b: sw() });
    expect(b.position).toEqual({ x: 100, y: 200 });
  });

  it("treats direction -1000 (unknown) as no heading", () => {
    const [a] = merge({ a: py({ address: "a", direction: -1000 }) }, {});
    expect(a.heading).toBeNull();
    const [b] = merge({ b: py({ address: "b", direction: 45 }) }, {});
    expect(b.heading).toBe(45);
  });

  it("converts a swarmit-only battery from mV to V", () => {
    const [a] = merge({}, { a: sw({ battery: 3900 }) });
    expect(a.battery).toBeCloseTo(3.9);
  });

  it("only an active Running control-plane bot is drivable", () => {
    const [a] = merge({ a: py({ address: "a" }) }, {});
    expect(a.drivable).toBe(true);
    // swarmit-only (e.g. sitting in the bootloader): never drivable
    const [b] = merge({}, { b: sw({ status: "Bootloader" }) });
    expect(b.drivable).toBe(false);
    // known to the controller but flashing right now: not drivable
    const [c] = merge(
      { c: py({ address: "c" }) },
      { c: sw({ status: "Programming" }) },
    );
    expect(c.drivable).toBe(false);
  });

  it("maps firmware AUTO mode to nav=auto", () => {
    const [a] = merge({ a: py({ address: "a", mode: 1 }) }, {});
    expect(a.nav).toBe("auto");
    const [b] = merge({ b: py({ address: "b", mode: 0 }) }, {});
    expect(b.nav).toBe("drive");
  });
});
