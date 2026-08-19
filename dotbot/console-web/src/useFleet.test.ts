import { describe, expect, it } from "vitest";

import { PyDotBot, SwarmitNode } from "./types";
import { deriveLink, deriveState, isCrashed, merge } from "./useFleet";

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

describe("deriveState (the sandbox axis)", () => {
  it("reports only what swarmit says, ignoring the control plane", () => {
    // The two axes are independent: a bot can be mid-Programming and unheard
    // at the same time, and the old single state hid the sandbox in that case.
    expect(deriveState(sw({ status: "Programming" }))).toBe("Programming");
    for (const s of ["Running", "Programming", "Bootloader", "Stopping", "Resetting"]) {
      expect(deriveState(sw({ status: s }))).toBe(s);
    }
  });

  it("has no sandbox state for a bot swarmit does not know", () => {
    // Saying "Running" here claimed a sandbox a bare-mode bot does not have.
    expect(deriveState(undefined)).toBeNull();
  });

  it("does not invent a state for a lifecycle value it does not know", () => {
    expect(deriveState(sw({ status: "Off" }))).toBeNull();
  });
});

describe("deriveLink (the control-plane axis)", () => {
  it("maps PyDotBot's DotBotStatus", () => {
    expect(deriveLink(py({ status: 0 }))).toBe("active");
    expect(deriveLink(py({ status: 1 }))).toBe("inactive");
    expect(deriveLink(py({ status: 2 }))).toBe("lost");
  });

  it("is unknown for a bot the control plane has never seen", () => {
    expect(deriveLink(undefined)).toBe("unknown");
  });
});

describe("the two axes stay independent", () => {
  it("keeps the sandbox state on a bot the control plane has lost", () => {
    const [b] = merge({ aaaa: py({ address: "aaaa", status: 2 }) }, { aaaa: sw({ status: "Programming" }) });
    expect(b.state).toBe("Programming");
    expect(b.link).toBe("lost");
    expect(b.drivable).toBe(false);
  });

  it("drives a bare-mode bot that has no sandbox at all", () => {
    const [b] = merge({ aaaa: py({ address: "aaaa", status: 0 }) }, {});
    expect(b.state).toBeNull();
    expect(b.link).toBe("active");
    expect(b.drivable).toBe(true);
  });

  it("will not drive a swarmit bot the control plane cannot reach", () => {
    const [b] = merge({}, { aaaa: sw({ status: "Running" }) });
    expect(b.link).toBe("unknown");
    expect(b.drivable).toBe(false);
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

describe("isCrashed", () => {
  const node = (over: Partial<SwarmitNode>): SwarmitNode => ({
    device: "DotBotV3",
    status: "Running",
    battery: 3900,
    pos_x: 0,
    pos_y: 0,
    ...over,
  });

  it("is false when the server reported no reset_reason", () => {
    expect(isCrashed(undefined)).toBe(false);
    expect(isCrashed(node({}))).toBe(false);
  });

  it("counts a fault, the crash deadman and a lockup", () => {
    expect(isCrashed(node({ reset_reason: 0, fault: 1 }))).toBe(true);
    expect(isCrashed(node({ reset_reason: 1 << 1 }))).toBe(true);
    expect(isCrashed(node({ reset_reason: 1 << 4 }))).toBe(true);
  });

  it("leaves an ordinary boot alone", () => {
    expect(isCrashed(node({ reset_reason: 0 }))).toBe(false);
    expect(isCrashed(node({ reset_reason: 1 << 3 }))).toBe(false); // soft-reset
    expect(isCrashed(node({ reset_reason: 1 << 25 }))).toBe(false); // stopped
  });
});

describe("merge takes the reset label from the server", () => {
  it("passes reset_cause through and reports it missing rather than guessing", () => {
    const [a] = merge({}, { A: { device: "DotBotV3", status: "Running", battery: 3900, pos_x: 0, pos_y: 0, reset_cause: "stopped" } });
    expect(a.resetCause).toBe("stopped");
    const [b] = merge({}, { B: { device: "DotBotV3", status: "Running", battery: 3900, pos_x: 0, pos_y: 0 } });
    expect(b.resetCause).toBeNull();
  });
});
